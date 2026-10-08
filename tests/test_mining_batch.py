"""Worker-owned ring merges, lossless rebasing and final-flush contracts."""

import json
import sqlite3
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from ed_companion.navigation.mining_batch import prepare_mining_batch
from ed_companion.navigation.mining_finder import mining_candidate_positions
from ed_companion.phase14.controller import CockpitController


def ring(name, **values):
    return {"system": "Test", "ring": name, "coordinates": [0, 0, 0],
            "ringType": "Metallic", "evidence": "CATALOG_CANDIDATE", **values}


class MiningBatchTests(unittest.TestCase):
    def controller(self):
        c = CockpitController.__new__(CockpitController)
        c.profile_context = Mock(key="alpha")
        c._profile_generation = 2
        c.mining_catalog_file = Path("catalog.json")
        c._mining_catalog = {"resetAt": "", "candidates": [ring("A")]}
        c._mining_catalog_revision = 1
        c._mining_catalog_positions = mining_candidate_positions(c._mining_catalog["candidates"])
        c._mining_catalog_positions_identity = id(c._mining_catalog["candidates"])
        c._network_threads_lock = threading.Lock()
        c._shutdown_complete = False
        c._pending_mining_candidates = []
        c._history_archive = Mock()
        c._start_network_worker = Mock(return_value=True)
        c.miningObservationBatchFinished = Mock()
        c.miningChanged = Mock()
        c.stateChanged = Mock()
        c.connectionChanged = Mock()
        c._save_mining_catalog = Mock()
        c._archive_history = Mock(return_value=True)
        c._add_mining_system_names = Mock()
        c._pending_bgs_snapshots = []
        c._pending_hge_observations = []
        c._hge_sightings = []
        c._next_hge_expiry_epoch = time.time() + 3600
        return c

    def run_worker(self, c):
        target = c._start_network_worker.call_args.args[0]
        worker = threading.Thread(target=target)
        worker.start(); worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        return c.miningObservationBatchFinished.emit.call_args.args[0], worker.ident

    def test_merge_and_history_run_only_on_worker_completion_only_publishes(self):
        c = self.controller()
        thread_ids = []
        c._history_archive.archive.side_effect = lambda *_args, **_kwargs: thread_ids.append(threading.get_ident())
        old = c._mining_catalog
        c._pending_mining_candidates = [ring("B")]
        c.flushHgeObservationBatch(True)
        self.assertIs(c._mining_catalog, old)
        c._history_archive.archive.assert_not_called()
        result, worker_id = self.run_worker(c)
        self.assertEqual(thread_ids, [worker_id, worker_id])
        c._history_archive.reset_mock()
        c._finish_mining_observation_batch(result)
        self.assertEqual([r["ring"] for r in c._mining_catalog["candidates"]], ["A", "B"])
        c._history_archive.archive.assert_not_called()
        c._archive_history.assert_not_called()
        c._save_mining_catalog.assert_called_once()

    def test_slow_history_does_not_block_dispatch_or_next_ui_batch_tick(self):
        c = self.controller()
        entered = threading.Event()
        release = threading.Event()
        workers = []

        def archive(*_args, **_kwargs):
            entered.set()
            if not release.wait(timeout=3):
                raise AssertionError("Test failed to release archive worker")

        def start(target, _name):
            worker = threading.Thread(target=target)
            workers.append(worker)
            worker.start()
            return True

        c._history_archive.archive.side_effect = archive
        c._start_network_worker = start
        try:
            c._pending_mining_candidates = [ring("B")]
            c.flushHgeObservationBatch(True)
            self.assertTrue(entered.wait(timeout=2))
            c._pending_mining_candidates = [ring("C")]
            c.flushHgeObservationBatch(True)
            self.assertEqual(c._pending_mining_candidates[0]["ring"], "C")
            self.assertIsNotNone(c._active_mining_observation_batch)
            self.assertEqual(c._mining_catalog["candidates"][0]["ring"], "A")
        finally:
            release.set()
            for worker in workers:
                worker.join(timeout=3)
                self.assertFalse(worker.is_alive())

    def test_worker_does_not_mutate_input_rows_or_position_map(self):
        rows = [ring("A", ageSeconds=123)]
        incoming = [ring("B", ageSeconds=45)]
        positions = mining_candidate_positions(rows)
        old_positions = dict(positions)
        result = prepare_mining_batch(rows, incoming, positions=positions, transient_fields={"ageSeconds"})
        self.assertEqual(rows[0]["ageSeconds"], 123)
        self.assertEqual(incoming[0]["ageSeconds"], 45)
        self.assertEqual(positions, old_positions)
        self.assertTrue(all("ageSeconds" not in r for r in result["candidates"]))

    def test_delayed_worker_cannot_read_a_later_mutated_controller_index(self):
        c = self.controller()
        c._dispatch_mining_observation_batch([ring("B")])
        c._mining_catalog_positions.update({
            **mining_candidate_positions([ring("B")]),
        })
        for key in mining_candidate_positions([ring("B")]):
            c._mining_catalog_positions[key] = 99
        result, _ = self.run_worker(c)
        self.assertNotIn("error", result)
        self.assertEqual([r["ring"] for r in result["candidates"]], ["A", "B"])

    def test_archive_failure_retains_every_raw_observation(self):
        archive = Mock()
        archive.archive.side_effect = sqlite3.OperationalError("locked")
        result = prepare_mining_batch([ring("A", note="old")], [ring("A", note="new")], archive=archive)
        self.assertEqual([r["note"] for r in result["candidates"]], ["old", "new"])
        self.assertEqual(result["archiveError"], "OperationalError")

    def test_real_history_captures_both_incoming_and_displaced_rows(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            prepare_mining_batch([ring("A", note="old")], [ring("A", note="new")], archive_path=path)
            with closing(sqlite3.connect(path)) as db:
                categories = {r[0] for r in db.execute("SELECT DISTINCT category FROM history")}
            self.assertEqual(categories, {"mining_observations", "mining_catalog"})

    def test_new_observations_wait_while_busy_then_merge_without_loss(self):
        c = self.controller()
        c._dispatch_mining_observation_batch([ring("B")])
        c._pending_mining_candidates = [ring("C")]
        c.flushHgeObservationBatch(True)
        self.assertEqual(c._start_network_worker.call_count, 1)
        self.assertEqual(c._pending_mining_candidates[0]["ring"], "C")
        result, _ = self.run_worker(c)
        c._finish_mining_observation_batch(result)
        self.assertEqual(c._start_network_worker.call_count, 2)
        result, _ = self.run_worker(c)
        c._finish_mining_observation_batch(result)
        self.assertEqual([r["ring"] for r in c._mining_catalog["candidates"]], ["A", "B", "C"])

    def test_concurrent_baseline_update_rebases_instead_of_overwriting(self):
        c = self.controller()
        c._dispatch_mining_observation_batch([ring("B")])
        result, _ = self.run_worker(c)
        c._mining_catalog = {"candidates": [ring("A"), ring("Baseline")]}
        c._mining_catalog_revision += 1
        c._finish_mining_observation_batch(result)
        result, _ = self.run_worker(c)
        c._finish_mining_observation_batch(result)
        self.assertEqual([r["ring"] for r in c._mining_catalog["candidates"]], ["A", "Baseline", "B"])

    def test_profile_generation_path_and_reset_guard_drop_stale_results(self):
        for change in ("profile", "generation", "path", "reset"):
            c = self.controller()
            c._dispatch_mining_observation_batch([ring("B")])
            result, _ = self.run_worker(c)
            if change == "profile":
                c.profile_context = Mock(key="beta")
            elif change == "generation":
                c._profile_generation += 1
            elif change == "path":
                c.mining_catalog_file = Path("other.json")
            else:
                c._mining_catalog["resetAt"] = "new-reset"
            old = c._mining_catalog
            c._finish_mining_observation_batch(result)
            self.assertIs(c._mining_catalog, old)
            c._save_mining_catalog.assert_not_called()
            self.assertEqual(c._pending_mining_candidates, [])

    def test_old_completion_cannot_clear_new_profiles_active_worker(self):
        c = self.controller()
        c._dispatch_mining_observation_batch([ring("B")])
        old, _ = self.run_worker(c)
        c._profile_generation += 1
        c._dispatch_mining_observation_batch([ring("New")])
        active = c._active_mining_observation_batch
        c._finish_mining_observation_batch(old)
        self.assertIs(c._active_mining_observation_batch, active)

    def test_worker_error_requeues_inputs_for_retry(self):
        c = self.controller()
        c._dispatch_mining_observation_batch([ring("B")])
        with self.assertLogs("ed_companion.phase14.controller_navigation", level="ERROR"), patch(
                "ed_companion.phase14.controller_navigation.prepare_mining_batch", side_effect=ValueError("test")):
            result, _ = self.run_worker(c)
        c._finish_mining_observation_batch(result)
        self.assertEqual(c._pending_mining_candidates[0]["ring"], "B")
        c._save_mining_catalog.assert_not_called()

    def test_final_flush_recovers_inflight_and_pending_rows_and_late_result_is_ignored(self):
        with TemporaryDirectory() as directory:
            c = self.controller()
            c.mining_catalog_file = Path(directory) / "catalog.json"
            c._save_mining_catalog = lambda: c.mining_catalog_file.write_text(json.dumps(c._mining_catalog))
            c._dispatch_mining_observation_batch([ring("B")])
            result, _ = self.run_worker(c)  # Queued Qt signal not yet handled.
            c._pending_mining_candidates = [ring("C")]
            c._shutdown_complete = True
            c.flushHgeObservationBatch(True)
            saved = json.loads(c.mining_catalog_file.read_text())
            self.assertEqual([r["ring"] for r in saved["candidates"]], ["A", "B", "C"])
            old = c._mining_catalog
            c._finish_mining_observation_batch(result)
            self.assertIs(c._mining_catalog, old)


if __name__ == "__main__":
    unittest.main()
