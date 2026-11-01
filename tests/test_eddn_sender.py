"""Durable, independently scheduled EDDN uploads with bounded UI updates."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ed_companion.background_work import BackgroundWork
from ed_companion.integrations.eddn import EddnError
from ed_companion.integrations.eddn_delivery import DeliveryReceipts, journal_upload_identity
from ed_companion.phase14.controller import CockpitController
from ed_companion.work_resources import WorkResources


class Timer:
    def __init__(self): self.active, self.starts = False, 0
    def isActive(self): return self.active
    def start(self): self.active = True; self.starts += 1
    def stop(self): self.active = False


def queued(identifier="market"):
    return {"id": identifier, "target": "EDDN", "status": "queued", "attempts": 0,
            "profile_key": "profile", "context": {"gameversion": "CAPI-Live-market"},
            "event": {"schema": "commodity/3", "message": {
                "timestamp": "2026-11-01T09:00:00Z", "systemName": "Test",
                "stationName": "Test Carrier", "marketId": 42, "commodities": []}}}


class SenderTests(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        root = self.root = Path(self.scratch.name)
        self.journal = root / "journal"
        self.journal.mkdir()
        (self.journal / "Journal.2026-11-01T090000.01.log").write_text(
            json.dumps({"event": "Fileheader", "part": 1}) + "\n"
            + json.dumps({"event": "LoadGame", "FID": "F1"}) + "\n", encoding="utf-8")
        c = self.c = CockpitController.__new__(CockpitController)
        c._eddn_async_delivery = True
        c._eddn_busy = False
        c._profile_generation = 1
        c._eddn_profile_key = "profile"
        c._eddn_profile_identity = "F1"
        c._eddn_journal_root = str(self.journal)
        c.profile_context = SimpleNamespace(key="profile", identity="F1")
        c._eddn_config = {"consent": True, "upload_enabled": True, "retry_failed": True,
                          "uploader_id": "anonymous"}
        c._eddn_queue = [queued()]
        c.eddn_queue_file = root / "community_upload_queue.json"
        c.eddn_config_file = root / "eddn_config.json"
        c.eddn_quarantine_file = root / "quarantine.json"
        c.history_archive_file = root / "history.sqlite3"
        c.config_dir = root
        c.eddn_queue_file.write_text(json.dumps(c._eddn_queue), encoding="utf-8")
        c._eddn_delivery_timer = Timer()
        c._derived_cache = {}
        c._eddn_revision = 0
        c._eddn_status = "Ready"
        c.connectionChanged = Mock()
        c.hgeChanged = Mock()
        c.eddnFinished = Mock()
        c.eddnHistoryArchived = Mock()
        c._sync_eddn_profile = Mock(side_effect=AssertionError("Sender must not parse full Journal history"))
        c._eddn_delivery_summary = Mock(return_value={"lastSuccessAt": ""})
        self.workers = []
        c._start_network_worker = lambda target, name: self.workers.append((target, name)) or True
        self.gateway = Mock(return_value={"httpStatus": 200, "elapsedMs": 2,
                                          "schema": "commodity/3", "event": ""})
        self.addCleanup(patch.stopall)
        patch("ed_companion.phase14.controller_eddn.journal_dir", return_value=self.journal).start()
        patch("ed_companion.phase14.controller_eddn.os.environ", {}).start()
        patch("ed_companion.phase14.controller_eddn.send_eddn_event", self.gateway).start()
        patch("ed_companion.phase14.controller_eddn.QTimer.singleShot").start()

    def dispatch(self):
        self.c._eddn_next_upload_at = 0
        self.c._process_eddn_queue()
        upload = next(target for target, name in reversed(self.workers) if name == "eddn-upload")
        upload()
        return self.c.eddnFinished.emit.call_args.args

    def finish(self, result):
        self.c._finish_eddn(*result)

    def test_ack_is_durable_before_qt_receives_it_without_rewriting_queue(self):
        before = self.c.eddn_queue_file.read_bytes()
        result = self.dispatch()
        self.assertTrue(result[1])
        restored = [queued()]
        DeliveryReceipts(self.root / "eddn_delivery_receipts.sqlite3").restore(restored)
        self.assertEqual(restored[0]["status"], "sent")
        self.assertEqual(self.c._eddn_queue[0]["status"], "sending")
        self.assertEqual(self.c.eddn_queue_file.read_bytes(), before)
        self.finish(result)
        self.assertEqual(self.c._eddn_queue[0]["status"], "sent")
        self.assertEqual(self.c.eddn_queue_file.read_bytes(), before)
        self.c.connectionChanged.emit.assert_not_called()
        self.c._eddn_delivery_timer.active = False
        self.c._flush_eddn_delivery_update()
        self.assertEqual(json.loads(self.c.eddn_queue_file.read_text())[0]["status"], "sent")
        self.c.connectionChanged.emit.assert_called_once()

    def test_startup_recovers_ack_even_when_json_still_says_queued(self):
        self.dispatch()
        self.c._read_local_json = lambda path, default: json.loads(path.read_text()) if path.exists() else default
        recovered = self.c._load_eddn_queue()
        self.assertEqual(recovered[0]["status"], "sent")
        self.assertEqual(recovered[0]["receipt"]["httpStatus"], 200)

    def test_active_metadata_poll_does_not_hold_a_valid_bound_message(self):
        self.c._active_journal_inputs = object()
        self.c._journal_location_cache = {}
        result = self.dispatch()
        self.assertTrue(result[1])
        self.c._sync_eddn_profile.assert_not_called()
        self.gateway.assert_called_once()

    def test_profile_change_or_incomplete_new_session_sends_nothing(self):
        for payload in ({"event": "LoadGame", "FID": "F2"}, {"event": "Fileheader", "part": 1}):
            with self.subTest(payload=payload):
                self.c._eddn_queue = [queued()]
                (self.journal / "Journal.2026-11-01T100000.01.log").write_text(json.dumps(payload) + "\n")
                result = self.dispatch()
                self.assertTrue(json.loads(result[2])["deferred"])
                self.finish(result)
                self.assertEqual(self.c._eddn_queue[0]["attempts"], 0)
        self.gateway.assert_not_called()

    def test_upload_withdrawal_between_dispatch_and_worker_sends_nothing(self):
        self.c._process_eddn_queue()
        self.c._eddn_config["upload_enabled"] = False
        self.workers[-1][0]()
        self.gateway.assert_not_called()
        self.finish(self.c.eddnFinished.emit.call_args.args)
        self.assertEqual(self.c._eddn_queue[0]["status"], "queued")

    def test_cannot_send_a_queue_that_failed_to_persist(self):
        self.c._eddn_queue_persist_pending = True
        self.c._process_eddn_queue()
        self.assertEqual(self.workers, [])

    def test_rate_limit_is_durable_and_pauses_all_jobs(self):
        self.gateway.side_effect = EddnError("limited", status_code=429, retry_after=1800)
        result = self.dispatch()
        self.finish(result)
        deadline = self.c._eddn_queue[0]["next_retry_at"]
        restored = [queued()]
        self.c._eddn_receipts().restore(restored)
        self.assertEqual(restored[0]["status"], "retry")
        self.assertEqual(restored[0]["next_retry_at"], deadline)
        self.c._eddn_queue.append(queued("other"))
        self.c._eddn_next_upload_at = 0
        self.c._process_eddn_queue()
        self.assertEqual(len(self.workers), 1)

    def test_mandatory_gap_cannot_be_bypassed_by_polling(self):
        self.finish(self.dispatch())
        self.c._eddn_queue.append(queued("other"))
        self.c._process_eddn_queue()
        self.assertEqual(len(self.workers), 1)

    def test_early_timer_is_rearmed_without_a_full_journal_poll(self):
        self.finish(self.dispatch())
        self.c._eddn_queue.append(queued("other"))
        self.c._schedule_eddn_upload = Mock()
        self.c._process_eddn_queue()
        self.c._schedule_eddn_upload.assert_called_once()
        self.assertGreater(self.c._schedule_eddn_upload.call_args.args[0], 0)
        self.assertLessEqual(self.c._schedule_eddn_upload.call_args.args[0], 400)
        self.assertEqual(len(self.workers), 1)

    def test_storage_failure_before_http_retains_job_without_transmission(self):
        store = self.c._eddn_receipts()
        with patch.object(store, "record", side_effect=OSError("disk")):
            result = self.dispatch()
        self.finish(result)
        self.gateway.assert_not_called()
        self.assertEqual(self.c._eddn_queue[0]["status"], "queued")
        self.assertTrue(self.c._eddn_receipt_error)

    def test_receipt_failure_after_http_uses_json_and_stops_further_uploads(self):
        store = self.c._eddn_receipts()
        original = store.record
        def record(identifier, state, attempts, result=None):
            if state == "sent": raise OSError("disk")
            return original(identifier, state, attempts, result)
        with patch.object(store, "record", side_effect=record):
            result = self.dispatch()
        self.finish(result)
        self.assertEqual(json.loads(self.c.eddn_queue_file.read_text())[0]["status"], "sent")
        self.assertTrue(self.c._eddn_receipt_error)

    def test_worker_start_rejection_does_not_leave_sending_stuck(self):
        self.c._start_network_worker = lambda *_args: False
        self.c._process_eddn_queue()
        self.assertFalse(self.c._eddn_busy)
        self.assertEqual(self.c._eddn_queue[0]["status"], "queued")

    def test_multiple_completions_share_one_ui_flush(self):
        self.finish(self.dispatch())
        self.c._eddn_queue.append(queued("other"))
        self.finish(self.dispatch())
        self.assertEqual(self.c._eddn_delivery_timer.starts, 1)
        self.c.connectionChanged.emit.assert_not_called()

    def test_manual_retry_reset_survives_reopening_receipts(self):
        self.c._eddn_queue[0].update(status="failed", attempts=7, terminal_error=False)
        self.c._eddn_receipts().record("market", "failed", 7, {"last_error": "offline"})
        self.c.retryEddnJob("market")
        restored = json.loads(self.c.eddn_queue_file.read_text())
        self.c._eddn_receipts().restore(restored)
        self.assertEqual(restored[0]["attempts"], 0)
        self.assertEqual(restored[0]["status"], "retry")

    def test_gateway_cooldown_survives_job_pruning_and_restart(self):
        self.gateway.side_effect = EddnError("limited", status_code=429, retry_after=1800)
        self.finish(self.dispatch())
        deadline = self.c._eddn_gateway_pause_until
        self.c._eddn_receipts().forget(["market"])
        reopened = DeliveryReceipts(self.root / "eddn_delivery_receipts.sqlite3")
        self.assertEqual(reopened.restore([]), deadline)

    def test_late_completion_cannot_change_a_new_profile_queue(self):
        result = self.dispatch()
        self.c._profile_generation = 2
        self.c._eddn_queue = [queued()]
        self.c._eddn_busy = True
        self.finish(result)
        self.assertTrue(self.c._eddn_busy)
        self.assertEqual(self.c._eddn_queue[0]["status"], "queued")

    def test_unreadable_receipt_database_preserves_files_and_pauses_recovery(self):
        path = self.root / "eddn_delivery_receipts.sqlite3"
        damaged = b'broken receipt database'
        path.write_bytes(damaged)
        self.c._read_local_json = lambda p, default: json.loads(p.read_text()) if p.exists() else default
        recovered = self.c._load_eddn_queue()
        self.assertEqual(len(recovered), 1)
        self.assertTrue(self.c._eddn_receipt_error)
        self.assertEqual(path.read_bytes(), damaged)

    def test_history_is_archived_on_worker_then_pruned_after_durable_snapshot(self):
        self.c._eddn_queue = [{**queued(str(i)), "status": "sent"} for i in range(102)]
        self.c._queue_eddn_history_checkpoint()
        target, name = self.workers[-1]
        self.assertEqual(name, "eddn-history-checkpoint")
        self.assertFalse(self.c.history_archive_file.exists())
        target()
        payload = self.c.eddnHistoryArchived.emit.call_args.args[0]
        self.c._finish_eddn_history_checkpoint(payload)
        self.assertEqual(len(self.c._eddn_queue), 100)
        self.assertEqual(self.c._eddn_history_counts["eddn_sent"], 2)
        self.assertEqual(set(self.c._eddn_receipt_prune_pending), {"0", "1"})

    def test_old_archival_cannot_erase_a_new_receipt_for_the_same_job(self):
        store = self.c._eddn_receipts()
        store.record("market", "sent", 1, {"deliveryNonce": "old", "httpStatus": 200})
        store.record("market", "sent", 2, {"deliveryNonce": "new", "httpStatus": 200})
        store.forget_archived({"market": "old"})
        restored = [queued()]
        store.restore(restored)
        self.assertEqual(restored[0]["receipt"]["deliveryNonce"], "new")
        store.forget_archived({"market": "new"})
        restored = [queued()]
        store.restore(restored)
        self.assertEqual(restored[0]["status"], "queued")

    def test_old_archival_completion_cannot_remove_a_new_ack_from_memory(self):
        self.c._eddn_queue = [{**queued(str(i)), "status": "sent", "receipt": {"deliveryNonce": "old"}} for i in range(102)]
        self.c._queue_eddn_history_checkpoint()
        self.workers[-1][0]()
        payload = self.c.eddnHistoryArchived.emit.call_args.args[0]
        self.c._eddn_queue[0]["receipt"] = {"deliveryNonce": "new"}
        self.c._finish_eddn_history_checkpoint(payload)
        retained = next(row for row in self.c._eddn_queue if row["id"] == "0")
        self.assertEqual(retained["receipt"]["deliveryNonce"], "new")
        self.assertNotIn("0", self.c._eddn_receipt_prune_pending)


class IndependentSchedulingTests(unittest.TestCase):
    def test_one_upload_can_progress_even_on_a_saturated_two_core_pool(self):
        machine = WorkResources(cores=2, reader=lambda: (4096, 2500), cpu_reader=lambda: None)
        work = BackgroundWork(resources=machine)
        self.addCleanup(work.close)
        release, journal, interactive, upload, second = (threading.Event() for _ in range(5))
        self.addCleanup(release.set)
        work.submit(lambda: (journal.set(), release.wait(3)), "journal-state-one")
        work.submit(lambda: (interactive.set(), release.wait(3)), "frontier-capi-profile")
        self.assertTrue(journal.wait(1) and interactive.wait(1))
        work.submit(lambda: (upload.set(), release.wait(3)), "eddn-upload")
        self.assertTrue(upload.wait(1), "upload waited behind the general pool")
        work.submit(second.set, "eddn-upload")
        self.assertFalse(second.wait(.05), "two uploads ran simultaneously")
        self.assertEqual(work.snapshot()["uploadActive"], 1)
        release.set()
        self.assertTrue(second.wait(1))

    def test_identity_continuations_never_fall_back_to_another_session(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "Journal.2026-11-01T090000.01.log").write_text(json.dumps({"event":"LoadGame","FID":"F1"})+'\n')
            (root / "Journal.2026-11-01T090000.02.log").write_text(json.dumps({"event":"Fileheader","part":2})+'\n')
            self.assertEqual(journal_upload_identity(root), "F1")
            (root / "Journal.2026-11-01T100000.01.log").write_text(json.dumps({"event":"Fileheader","part":1})+'\n')
            self.assertEqual(journal_upload_identity(root), "")


if __name__ == "__main__":
    unittest.main()
