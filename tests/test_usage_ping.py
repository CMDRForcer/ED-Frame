import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

from ed_companion import APP_VERSION
from ed_companion.integrations import usage_ping
from ed_companion.integrations.usage_ping import UsagePing
from ed_companion.background_work import BackgroundWork
from ed_companion.phase14.controller_usage import UsageMixin


class UsagePingTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.service = UsagePing(self.root)
        self.post = Mock(return_value=SimpleNamespace(status_code=200))
        self.dev = patch.object(usage_ping, 'is_development_build', return_value=False)
        self.dev_mock = self.dev.start()
        self.addCleanup(self.dev.stop)
        self.env = patch.dict('os.environ', {'EDFRAME_NO_USAGE_PING': '0'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def ping(self, **kwargs):
        return self.service.ping(catalog_enabled=True, post=self.post, base_url='https://catalog.invalid', **kwargs)

    def test_no_ping_or_id_created_for_development_build(self):
        self.dev_mock.return_value = True
        self.assertFalse(self.ping())
        self.post.assert_not_called()
        self.assertFalse(self.service.path.exists())

    def test_environment_opt_out_creates_no_id(self):
        with patch.dict('os.environ', {'EDFRAME_NO_USAGE_PING': '1'}):
            self.assertFalse(self.ping())
        self.post.assert_not_called()
        self.assertFalse(self.service.path.exists())

    def test_retired_opt_out_does_not_block_automatic_counting(self):
        self.service.path.write_text(json.dumps({'enabled': False}))
        self.service = UsagePing(self.root)
        self.assertTrue(self.ping())
        self.post.assert_called_once()
        self.assertNotIn('enabled', json.loads(self.service.path.read_text()))

    def test_disabled_catalog_creates_no_id_or_ping(self):
        self.assertFalse(self.service.ping(catalog_enabled=False, post=self.post))
        self.post.assert_not_called()
        self.assertFalse(self.service.path.exists())

    def test_exact_payload_header_timeout_and_daily_success_persistence(self):
        with patch.object(usage_ping, 'utc_day', return_value='2026-10-13'):
            self.assertTrue(self.ping())
            self.assertFalse(self.ping())
            restarted = UsagePing(self.root)
            self.assertFalse(restarted.ping(catalog_enabled=True, post=self.post))
        identity = self.service.install_id
        self.assertEqual(UUID(identity).version, 4)
        self.post.assert_called_once_with('https://catalog.invalid/v1/usage/ping',
            json={'install_id': identity, 'app_version': APP_VERSION},
            headers={'User-Agent': f'ED-Frame/{APP_VERSION}'}, timeout=5, allow_redirects=False)
        self.assertEqual(json.loads(self.service.path.read_text()), {
            'install_id': identity, 'last_attempt_day': '2026-10-13',
            'last_successful_day': '2026-10-13'})
        with patch.object(usage_ping, 'utc_day', return_value='2026-10-14'):
            self.assertTrue(self.ping())
        self.assertEqual(self.post.call_count, 2)

    def test_failure_is_local_only_and_not_retried_after_restart(self):
        self.post.side_effect = TimeoutError('Must not be shown in UI or logs')
        with patch.object(usage_ping, 'utc_day', return_value='2026-10-13'):
            with self.assertLogs(usage_ping.__name__, level='INFO') as logs:
                self.assertFalse(self.ping())
            self.assertNotIn('Must not be shown', ''.join(logs.output))
            self.assertFalse(UsagePing(self.root).ping(catalog_enabled=True, post=self.post))
        self.assertNotIn('last_successful_day', json.loads(self.service.path.read_text()))
        self.assertEqual(self.post.call_count, 1)
        with patch.object(usage_ping, 'utc_day', return_value='2026-10-14'):
            self.post.side_effect = None
            self.assertTrue(self.ping())
        self.assertEqual(self.post.call_count, 2)

    def test_http_error_and_redirect_are_not_success_or_retried(self):
        for code in (301, 429, 500):
            with self.subTest(code=code):
                self.service = UsagePing(self.root / str(code))
                self.post.return_value.status_code = code
                self.assertFalse(self.ping())
                self.assertFalse(self.ping())
                self.assertNotIn('last_successful_day', json.loads(self.service.path.read_text()))

    def test_shared_config_survives_profile_changes_and_deduplicates_instances(self):
        identity = self.service.ensure_install_id()
        other_commander = UsagePing(self.root)
        self.assertEqual(other_commander.ensure_install_id(), identity)
        self.assertEqual(UsagePing(self.root).install_id, identity)
        self.assertEqual(self.service.path.parent, self.root)

    def test_failed_state_write_prevents_http(self):
        with patch.object(usage_ping, 'atomic_write', return_value=False):
            self.assertFalse(self.ping())
        self.post.assert_not_called()

    def test_queued_ping_rechecks_catalog_and_environment(self):
        self.assertFalse(self.service.ping(catalog_enabled=lambda: False, post=self.post))
        with patch.dict('os.environ', {'EDFRAME_NO_USAGE_PING': '1'}):
            self.assertFalse(self.ping())
        self.post.assert_not_called()

    def test_malformed_day_config_is_safe(self):
        self.service.path.write_text(json.dumps({'last_attempt_day': None}))
        service = UsagePing(self.root)
        self.assertTrue(service.due(True))

    def test_http_wait_runs_in_existing_background_scheduler(self):
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        threads = []
        scheduler = BackgroundWork(on_thread=threads.append)
        self.addCleanup(scheduler.close)
        self.addCleanup(lambda: [thread.join(3) for thread in threads])
        self.addCleanup(release.set)
        controller = SimpleNamespace(_usage_ping=self.service, _shutdown_complete=False,
            _edframe_catalog_enabled=True, usageChanged=Mock(),
            _start_network_worker=lambda target,name: scheduler.submit(target, name))
        def slow_post(*args, **kwargs):
            started.set()
            release.wait(2)
            finished.set()
            return SimpleNamespace(status_code=200)
        with patch.object(usage_ping.requests, 'post', side_effect=slow_post):
            before = time.monotonic()
            UsageMixin._maybe_usage_ping(controller)
            self.assertLess(time.monotonic() - before, 0.5)
            self.assertTrue(started.wait(2))
            self.assertFalse(finished.is_set())
            self.assertEqual(UUID(self.service.install_id).version, 4)  # No network-held state lock.
            release.set()
            self.assertTrue(finished.wait(2))
