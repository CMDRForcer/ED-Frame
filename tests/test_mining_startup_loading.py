"""Demand loading must never mistake unloaded disk data for an empty catalog."""
import copy
import json
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from ed_companion.navigation.mining_batch import prepare_mining_batch
from ed_companion.navigation.mining_finder import mining_candidate_positions
from ed_companion.phase14.controller import CockpitController


def ring(name):
    return {"system": "Test", "ring": name, "ringType": "Metallic",
            "evidence": "CATALOG_CANDIDATE", "coordinates": [0, 0, 0]}


class MiningStartupLoadingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        c = CockpitController.__new__(CockpitController)
        self.c = c
        c.profile_context = Mock(key="alpha")
        c._profile_generation = 2
        c.mining_catalog_file = root / "rings.json"
        c.mining_powerplay_catalog_file = root / "powerplay.json"
        c.mining_powerplay_observations_file = root / "observations.json"
        self.disk = {"identityVersion": 2, "updatedAt": "2026-10-09T00:00:00Z",
                     "candidates": [ring("Test A Ring")]}
        c.mining_catalog_file.write_text(json.dumps(self.disk), encoding="utf-8")
        c.mining_powerplay_catalog_file.write_text(json.dumps({"systems": [
            {"system": "Test", "power": "Aisling Duval"},
        ]}), encoding="utf-8")
        c.mining_powerplay_observations_file.write_text(json.dumps([
            {"system": "Old", "power": "Aisling Duval", "observedAt": "2026-10-09T00:00:00Z"},
        ]), encoding="utf-8")
        c._mining_catalog = {"candidates": []}
        c._mining_catalog_loaded = False
        c._mining_catalog_load_future = None
        c._mining_catalog_load_token = 0
        c._mining_catalog_revision = 0
        c._mining_catalog_positions = {}
        c._mining_catalog_positions_identity = None
        c._mining_powerplay_catalog = {}
        c._mining_powerplay_observations = []
        c._pending_mining_candidates = []
        c._pending_mining_powerplay_observations = []
        c._pending_bgs_snapshots = []
        c._pending_hge_observations = []
        c._hge_sightings = []
        c._next_hge_expiry_epoch = time.time() + 3600
        c._mining_sync_busy = False
        c._mining_sync_status = "Ready"
        c._mining_rows_cache = []
        c._state = {}
        c._network_threads_lock = threading.Lock()
        c._shutdown_complete = False
        c._history_archive = Mock()
        c._archive_history = Mock(return_value=True)
        self.workers = []
        c._start_network_worker = lambda target, name: self.workers.append((target, name)) or True
        for name in ("miningCatalogLoaded", "miningObservationBatchFinished", "miningChanged",
                     "connectionChanged", "stateChanged", "miningRowsReady"):
            setattr(c, name, Mock())
        c._save_mining_json = Mock()

    def complete_load(self):
        worker, name = self.workers.pop(0)
        self.assertEqual(name, "mining-catalog-load")
        worker()
        payload = self.c.miningCatalogLoaded.emit.call_args.args[0]
        self.c._finish_mining_catalog_load(payload)
        return payload

    def test_first_use_queues_one_load_without_io_or_an_empty_view_build(self):
        c = self.c
        with patch("ed_companion.phase14.controller_navigation.load_json_file", wraps=None) as read:
            self.assertEqual(c._mining_rows(), [])
            self.assertEqual(c._mining_rows(), [])
            read.assert_not_called()
        self.assertEqual(len(self.workers), 1)
        self.assertFalse(c._mining_catalog_loaded)
        self.assertTrue(CockpitController.miningSyncBusy.fget(c))
        self.assertIn("Loading", CockpitController.miningSyncStatus.fget(c))

    def test_qml_first_use_defers_notification_to_avoid_a_binding_loop(self):
        c = self.c
        c.timer = Mock()
        with patch("ed_companion.phase14.controller_navigation.QTimer.singleShot") as later:
            self.assertEqual(c._mining_rows(), [])
            c.miningChanged.emit.assert_not_called()
            later.assert_called_once_with(0, c.miningChanged.emit)
        self.assertEqual(len(self.workers), 1)

    def test_load_retains_every_fact_and_defers_the_ring_merge_index(self):
        c = self.c
        self.assertFalse(c._ensure_mining_catalog_loaded())
        payload = self.complete_load()
        self.assertEqual(json.loads(json.dumps(c._mining_catalog)), self.disk)
        self.assertIsNone(payload[5])
        self.assertEqual(c._mining_catalog_positions, {})
        self.assertIsNone(c._mining_catalog_positions_identity)
        self.assertTrue(c._mining_catalog_loaded)
        self.assertIsNone(c._mining_catalog_load_future)
        self.assertEqual(c._mining_system_names, ["Test"])
        self.assertFalse(CockpitController.miningSyncBusy.fget(c))
        self.assertTrue(c._ensure_mining_catalog_loaded())
        self.assertEqual(self.workers, [])

    def test_powerplay_arrays_are_shared_not_copied_or_duplicated(self):
        c = self.c
        c._ensure_mining_catalog_loaded()
        payload = self.complete_load()
        self.assertIs(c._mining_powerplay_catalog, payload[9]["catalog"])
        self.assertIs(c._mining_powerplay_observations, payload[9]["observations"])
        revision = c._mining_catalog_revision
        c._finish_mining_catalog_load(payload)
        self.assertEqual(c._mining_catalog_revision, revision)
        self.assertEqual(len(c._mining_powerplay_observations), 1)

    def test_unloaded_save_cannot_overwrite_the_existing_file(self):
        c = self.c
        original = c.mining_catalog_file.read_bytes()
        c._save_mining_catalog()
        c._save_mining_json.assert_not_called()
        self.assertEqual(c.mining_catalog_file.read_bytes(), original)

    def test_observations_wait_then_merge_with_disk_not_with_empty_startup_state(self):
        c = self.c
        incoming = [ring("Test B Ring")]
        original = c.mining_catalog_file.read_bytes()
        self.assertTrue(c._dispatch_mining_observation_batch(incoming, search_refresh=True))
        self.assertEqual(c._pending_mining_candidates, incoming)
        c.flushHgeObservationBatch(True)
        self.assertEqual(c._pending_mining_candidates, incoming)
        self.assertEqual(len(self.workers), 1)
        self.complete_load()
        worker, name = self.workers.pop(0)
        self.assertEqual(name, "mining-observation-merge")
        worker()
        result = c.miningObservationBatchFinished.emit.call_args.args[0]
        self.assertTrue(result["searchRefresh"])
        c._finish_mining_observation_batch(result)
        self.assertEqual([row["ring"] for row in c._mining_catalog["candidates"]],
                         ["Test A Ring", "Test B Ring"])
        c._save_mining_json.assert_called_once()
        self.assertEqual(c.mining_catalog_file.read_bytes(), original)  # Mock writer only.

    def test_shutdown_with_pending_new_data_hydrates_and_durably_merges_first(self):
        c = self.c
        c._shutdown_complete = True
        c._pending_mining_candidates = [ring("Test B Ring")]
        c.flushHgeObservationBatch(True)
        self.assertEqual(self.workers, [])
        self.assertTrue(c._mining_catalog_loaded)
        self.assertEqual([row["ring"] for row in c._mining_catalog["candidates"]],
                         ["Test A Ring", "Test B Ring"])
        c._save_mining_json.assert_called_once()
        self.assertEqual(c._pending_mining_candidates, [])

    def test_shutdown_consumes_worker_result_even_if_qt_completion_is_queued(self):
        c = self.c
        c._ensure_mining_catalog_loaded()
        worker, _name = self.workers.pop(0)
        worker()  # Future is ready; no Qt event has published it.
        c._shutdown_complete = True
        c._pending_mining_candidates = [ring("Test B Ring")]
        c.flushHgeObservationBatch(True)
        self.assertEqual(len(c._mining_catalog["candidates"]), 2)
        before = copy.deepcopy(c._mining_catalog)
        c._finish_mining_catalog_load(c.miningCatalogLoaded.emit.call_args.args[0])
        self.assertEqual(c._mining_catalog, before)

    def test_shutdown_without_mining_data_does_not_load_or_touch_the_catalog(self):
        c = self.c
        before = c.mining_catalog_file.read_bytes()
        c._shutdown_complete = True
        c.flushHgeObservationBatch(True)
        self.assertEqual(self.workers, [])
        self.assertFalse(c._mining_catalog_loaded)
        c._save_mining_json.assert_not_called()
        self.assertEqual(c.mining_catalog_file.read_bytes(), before)

    def test_public_powerplay_reports_are_retained_until_cached_facts_are_loaded(self):
        c = self.c
        rows = [{"system": "New", "power": "Aisling Duval", "observedAt": "2026-10-09T00:01:00Z"}]
        self.assertFalse(c._publish_mining_powerplay(rows))
        self.assertEqual(c._pending_mining_powerplay_observations, rows)
        c._save_mining_json.assert_not_called()
        self.complete_load()
        self.assertEqual({row["system"] for row in c._mining_powerplay_observations}, {"Old", "New"})
        self.assertEqual(c._pending_mining_powerplay_observations, [])

    def test_stale_profile_token_and_path_do_not_publish(self):
        c = self.c
        c._ensure_mining_catalog_loaded()
        worker, _name = self.workers.pop(0)
        worker()
        payload = c.miningCatalogLoaded.emit.call_args.args[0]
        for field, replacement in ((0, 999), (1, 999), (2, "beta"), (3, "other.json")):
            invalid = list(payload)
            invalid[field] = replacement
            c._finish_mining_catalog_load(tuple(invalid))
            self.assertFalse(c._mining_catalog_loaded)
            self.assertEqual(c._mining_catalog["candidates"], [])
        c._finish_mining_catalog_load(payload)
        self.assertTrue(c._mining_catalog_loaded)

    def test_failed_worker_dispatch_keeps_inputs_and_original_file(self):
        c = self.c
        c._start_network_worker = Mock(return_value=False)
        original = c.mining_catalog_file.read_bytes()
        incoming = [ring("Test B Ring")]
        self.assertTrue(c._dispatch_mining_observation_batch(incoming))
        self.assertEqual(c._pending_mining_candidates, incoming)
        self.assertIsNone(c._mining_catalog_load_future)
        c._save_mining_json.assert_not_called()
        self.assertEqual(c.mining_catalog_file.read_bytes(), original)

    def test_load_failure_has_a_retry_delay_not_a_binding_triggered_reload_loop(self):
        c = self.c
        c._ensure_mining_catalog_loaded()
        with patch("ed_companion.phase14.controller_navigation.load_json_file", side_effect=OSError("fixture")):
            self.complete_load()
        for _ in range(10):
            self.assertFalse(c._ensure_mining_catalog_loaded())
        self.assertEqual(self.workers, [])
        c._mining_plan_deferred = True
        self.assertFalse(c._mining_plan_is_busy())

    def test_failed_final_load_archives_new_facts_without_overwriting_old_file(self):
        c = self.c
        c._shutdown_complete = True
        incoming = [ring("Test B Ring")]
        c._pending_mining_candidates = incoming
        original = c.mining_catalog_file.read_bytes()
        with patch("ed_companion.phase14.controller_navigation.load_json_file", side_effect=OSError("fixture")):
            c.flushHgeObservationBatch(True)
        c._archive_history.assert_called_once_with("mining_observations", incoming)
        self.assertEqual(c._pending_mining_candidates, [])
        self.assertEqual(c.mining_catalog_file.read_bytes(), original)
        c._save_mining_json.assert_not_called()

    def test_load_error_never_publishes_empty_data_or_writes(self):
        c = self.c
        original = c.mining_catalog_file.read_bytes()
        c._ensure_mining_catalog_loaded()
        with patch("ed_companion.phase14.controller_navigation.load_json_file", side_effect=OSError("fixture")):
            self.complete_load()
        self.assertFalse(c._mining_catalog_loaded)
        self.assertEqual(c._mining_catalog["candidates"], [])
        c._save_mining_json.assert_not_called()
        self.assertEqual(c.mining_catalog_file.read_bytes(), original)

    def test_reset_waits_for_hydration_before_archiving_existing_data(self):
        c = self.c
        c.resetMiningCatalog()
        self.assertTrue(c._mining_catalog_reset_requested)
        c._archive_history.assert_not_called()
        c.resetMiningCatalog = Mock()
        self.complete_load()
        c.resetMiningCatalog.assert_called_once()
        self.assertFalse(c._mining_catalog_reset_requested)

    def test_switching_to_mining_starts_lazy_load_but_other_navigation_does_not(self):
        c = self.c
        c._last_page = 0
        c.uiConfigSaveTimer = Mock()
        c.setLastPage(1)
        self.assertEqual(self.workers, [])
        c.setLastPage(12)
        self.assertEqual(len(self.workers), 1)
        c.setLastPage(0)
        c.setLastPage(12)
        self.assertEqual(len(self.workers), 1)

    def test_exclusively_owned_worker_index_is_not_copied_again(self):
        old = [ring("Test A Ring")]
        positions = mining_candidate_positions(old)
        private = dict(positions)
        result = prepare_mining_batch(old, [ring("Test B Ring")], positions=private, positions_owned=True)
        self.assertIs(result["positions"], private)
        self.assertEqual(len(private), 2)
        self.assertEqual(len(positions), 1)
        self.assertEqual(len(old), 1)


if __name__ == "__main__":
    unittest.main()
