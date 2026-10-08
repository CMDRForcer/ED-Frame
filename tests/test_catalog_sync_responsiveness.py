"""Catalog/import contention must never pull persistence back onto Qt's thread."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import Mock, patch

from ed_companion.navigation.mining_market_store import MarketCatalogStore
from ed_companion.navigation.state_find_batch import prepare_state_find_page
from ed_companion.navigation.state_find_catalog import state_find_region
from ed_companion.phase14.controller import CockpitController


MODULE = "ed_companion.phase14.controller_navigation."
QUERY = {"startSystem": "cubeo", "commodity": "platinum", "nearbyLy": 250,
         "minDemand": 5000, "maxMarketAgeHours": 1, "landingPad": "LARGE"}


def signal(system="Near", **changes):
    return {"system": system, "star_pos": [1, 2, 3],
            "signal_timestamp": datetime.now(timezone.utc).isoformat(),
            "time_remaining": 3600, "evidence_kind": "EDDN_SIGNAL", **changes}


class CatalogSyncResponsivenessTests(unittest.TestCase):
    def controller(self, directory):
        controller = CockpitController.__new__(CockpitController)
        controller._network_threads_lock = threading.Lock()
        controller._start_network_worker = Mock(return_value=True)
        controller._profile_generation = 4
        controller.profile_context = Mock(key="alpha")
        controller._state = {"system": "Cubeo", "currentPosition": [1, 2, 3]}
        controller._mining_market_store = MarketCatalogStore(Path(directory) / "markets.sqlite3")
        controller._edframe_catalog_enabled = True
        controller._mining_market_revision = 0
        controller._mining_file_lock = threading.Lock()
        controller.mining_catalog_file = Path(directory) / "rings.json"
        controller._schedule_mining_market_backup = Mock(return_value=True)
        controller._append_edframe_catalog_log = Mock()
        controller._maybe_refresh_regional_state_finds = Mock()
        controller._history_archive = Mock()
        controller._hge_sightings = []
        controller._hge_file_lock = threading.Lock()
        controller._hge_save_sequence = 0
        controller._hge_save_sequences = {}
        controller.hge_cache_file = Path(directory) / "hge.json"
        controller.state_find_sync_file = Path(directory) / "cursor.json"
        controller._edframe_state_find_sync_meta = {"cursor": "old"}
        controller._edframe_state_find_sync_busy = True
        controller._active_edframe_state_find_sync_request = {
            "id": "state", "region": state_find_region([1, 2, 3]),
        }
        for name in ("connectionChanged", "miningChanged", "hgeChanged", "stateChanged",
                     "localMiningMarketFinished", "edFrameStateFindSyncFinished",
                     "miningVerificationChanged"):
            setattr(controller, name, Mock())
        return controller

    def state_result(self, controller, **changes):
        return {"id": "state", "generation": 4, "success": True,
                "region": controller._active_edframe_state_find_sync_request["region"],
                "page": {"signals": [signal()], "nextCursor": "next", "hasMore": False},
                **changes}

    def run_worker(self, controller):
        target = controller._start_network_worker.call_args.args[0]
        errors = []
        def run():
            try:
                target()
            except BaseException as exc:
                errors.append(exc)
        worker = threading.Thread(target=run)
        worker.start()
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])

    def test_source_status_waits_for_import_only_on_worker(self):
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            store = controller._mining_market_store
            written_on = []
            original = store.record_source_result
            def record(*args, **kwargs):
                written_on.append(threading.get_ident())
                original(*args, **kwargs)
            store.record_source_result = record
            with store._lock:
                started = time.monotonic()
                controller._record_catalog_source_result("ED-Frame", success=True)
                self.assertLess(time.monotonic() - started, .25)
                target = controller._start_network_worker.call_args.args[0]
                entered = threading.Event()
                def run():
                    entered.set()
                    target()
                worker = threading.Thread(target=run)
                worker.start()
                self.assertTrue(entered.wait(1))
                self.assertEqual(written_on, [])
                self.assertTrue(worker.is_alive())
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(written_on, [worker.ident])
            self.assertNotEqual(worker.ident, threading.get_ident())
            self.assertTrue(store.source_status("ED-Frame")["last_success_at"])

    def test_source_status_rejects_profile_reset_store_and_opt_out(self):
        for change in ("profile", "reset", "store", "disabled"):
            with self.subTest(change=change), TemporaryDirectory() as directory:
                controller = self.controller(directory)
                original = controller._mining_market_store
                controller._record_catalog_source_result("stale", success=True)
                if change == "profile":
                    controller._profile_generation += 1
                elif change == "reset":
                    original._store_generation += 1
                elif change == "store":
                    controller._mining_market_store = MarketCatalogStore(Path(directory) / "new.sqlite3")
                else:
                    controller._edframe_catalog_enabled = False
                self.run_worker(controller)
                self.assertEqual(original.source_status("stale"), {})

    def test_catalog_completion_reuses_worker_count_and_only_queues_write(self):
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            controller._active_edframe_catalog_sync_request = {"id": "catalog"}
            controller._edframe_catalog_stats = {}
            controller._mining_market_cache = {}
            store = controller._mining_market_store
            with patch.object(store, "count", side_effect=AssertionError("GUI count")), \
                 patch.object(store, "record_source_result", side_effect=AssertionError("GUI write")):
                controller._finish_edframe_catalog_sync({
                    "id": "catalog", "generation": 4, "success": True,
                    "ingested": 2, "localCount": 123, "hasMore": False,
                })
            self.assertEqual(controller._edframe_catalog_stats["localMarkets"], 123)
            self.assertEqual(controller._mining_market_revision, 1)
            self.assertEqual(controller._start_network_worker.call_args.args[1], "catalog-source-status")

    def test_warm_target_persistence_is_deferred_and_retains_priorities(self):
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            controller._remember_mining_warm_targets(QUERY)
            self.assertEqual(controller._mining_market_store.warm_targets(), [])
            self.run_worker(controller)
            targets = controller._mining_market_store.warm_targets()
            self.assertEqual(len(targets), 12)
            self.assertEqual(targets[0]["commodity"], "platinum")
            self.assertEqual(targets[0]["priority"], 100)
            self.assertEqual(targets[0]["useCount"], 1)

    def test_delayed_warm_writer_cannot_replace_newer_search_settings(self):
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            stamp = datetime.now(timezone.utc)
            with patch(MODULE + "datetime", wraps=datetime) as clock:
                clock.now.side_effect = [stamp, stamp + timedelta(seconds=1)]
                controller._remember_mining_warm_targets({**QUERY, "nearbyLy": 100})
                controller._remember_mining_warm_targets({**QUERY, "nearbyLy": 500})
            self.run_worker(controller)  # Newer worker acquires the DB lock first.
            old_worker = controller._start_network_worker.call_args_list[0].args[0]
            worker = threading.Thread(target=old_worker)
            worker.start()
            worker.join(3)
            self.assertFalse(worker.is_alive())
            target = controller._mining_market_store.warm_targets()[0]
            self.assertEqual(target["nearbyLy"], 500)
            self.assertEqual(target["useCount"], 2)
            # Defaults for another commodity must not erase explicit intent.
            controller._remember_mining_warm_targets({**QUERY, "commodity": "gold", "nearbyLy": 50})
            self.run_worker(controller)
            platinum = next(row for row in controller._mining_market_store.warm_targets()
                            if row["commodity"] == "platinum")
            self.assertEqual(platinum["nearbyLy"], 500)

    def test_warm_target_reset_cannot_resurrect_queue(self):
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            controller._remember_mining_warm_targets(QUERY)
            controller._mining_market_store._store_generation += 1
            self.run_worker(controller)
            self.assertEqual(controller._mining_market_store.warm_targets(), [])

    def local_snapshot(self):
        return {"timestamp": datetime.now(timezone.utc).isoformat(),
                "StarSystem": "Cubeo", "StationName": "Medupe City", "MarketID": 42,
                "Items": [{"Name": "$Platinum_Name;", "SellPrice": 250000,
                           "Demand": 5000, "DemandBracket": 3}]}

    def test_local_market_is_stored_on_worker_then_published_without_gui_write(self):
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            store = controller._mining_market_store
            self.assertEqual(controller._ingest_local_mining_market_snapshot(self.local_snapshot()), 1)
            self.assertEqual(store.count(), 0)
            self.run_worker(controller)
            self.assertEqual(store.count(), 1)
            result = controller.localMiningMarketFinished.emit.call_args.args[0]
            with patch.object(store, "ingest", side_effect=AssertionError("GUI write")):
                controller._finish_local_mining_market(result)
            self.assertEqual(controller._mining_market_revision, 1)
            controller.miningChanged.emit.assert_called_once()

    def test_local_market_profile_or_reset_switch_skips_old_storage(self):
        for change in ("profile", "reset"):
            with self.subTest(change=change), TemporaryDirectory() as directory:
                controller = self.controller(directory)
                controller._ingest_local_mining_market_snapshot(self.local_snapshot())
                if change == "profile":
                    controller._profile_generation += 1
                else:
                    controller._mining_market_store._store_generation += 1
                self.run_worker(controller)
                result = controller.localMiningMarketFinished.emit.call_args.args[0]
                controller._finish_local_mining_market(result)
                self.assertEqual(controller._mining_market_store.count(), 0)
                controller.miningChanged.emit.assert_not_called()

    def test_local_market_save_failure_retries_only_same_file_version(self):
        for newer in (False, True):
            with self.subTest(newer=newer), TemporaryDirectory() as directory:
                controller = self.controller(directory)
                controller._local_market_snapshot_fingerprint = "new" if newer else "observed"
                controller._ingest_local_mining_market_snapshot(self.local_snapshot(), fingerprint="observed")
                with patch.object(controller._mining_market_store, "ingest", side_effect=sqlite3.OperationalError("busy")):
                    self.run_worker(controller)
                controller._finish_local_mining_market(controller.localMiningMarketFinished.emit.call_args.args[0])
                self.assertEqual(controller._local_market_snapshot_fingerprint, "new" if newer else "")
                self.assertEqual(controller._mining_market_revision, 0)

    def test_state_find_finish_only_dispatches_no_gui_merge_archive_or_save(self):
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            with patch(MODULE + "prepare_state_find_page", side_effect=AssertionError("GUI merge")), \
                 patch(MODULE + "atomic_write_chunks", side_effect=AssertionError("GUI write")):
                controller._finish_edframe_state_find_sync(self.state_result(controller))
            controller._history_archive.archive.assert_not_called()
            self.assertTrue(controller._edframe_state_find_sync_busy)
            self.assertEqual(controller._hge_sightings, [])
            self.assertEqual(controller._start_network_worker.call_args.args[1], "edframe-state-find-storage")

    def test_state_find_worker_saves_facts_before_cursor_then_publishes(self):
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            controller._finish_edframe_state_find_sync(self.state_result(controller))
            from ed_companion.persistence import atomic_write_chunks
            events = []
            def write(path, chunks):
                events.append((path, threading.get_ident()))
                return atomic_write_chunks(path, chunks)
            with patch(MODULE + "atomic_write_chunks", side_effect=write):
                self.run_worker(controller)
            self.assertEqual([path for path, _ in events], [controller.hge_cache_file, controller.state_find_sync_file])
            self.assertTrue(all(ident != threading.get_ident() for _, ident in events))
            self.assertEqual(controller._edframe_state_find_sync_meta["cursor"], "old")
            result = controller.edFrameStateFindSyncFinished.emit.call_args.args[0]
            with patch(MODULE + "atomic_write_chunks", side_effect=AssertionError("GUI save")):
                controller._finish_edframe_state_find_sync(result)
            self.assertFalse(controller._edframe_state_find_sync_busy)
            self.assertEqual(controller._edframe_state_find_sync_meta["cursor"], "next")
            self.assertEqual(controller._hge_sightings[0]["system"], "Near")
            self.assertEqual(json.loads(controller.hge_cache_file.read_text()), controller._hge_sightings)

    def test_state_find_rebase_preserves_new_journal_rows_and_terminates(self):
        for timing in ("before_worker", "after_worker"):
            with self.subTest(timing=timing), TemporaryDirectory() as directory:
                controller = self.controller(directory)
                controller._finish_edframe_state_find_sync(self.state_result(controller))
                local = signal("Local", evidence_kind="LOCAL_JOURNAL")
                if timing == "before_worker":
                    controller._hge_sightings = [local]
                self.run_worker(controller)
                if timing == "after_worker":
                    controller._hge_sightings = [local]
                controller._finish_edframe_state_find_sync(controller.edFrameStateFindSyncFinished.emit.call_args.args[0])
                self.assertEqual(controller._start_network_worker.call_count, 2)
                self.run_worker(controller)
                controller._finish_edframe_state_find_sync(controller.edFrameStateFindSyncFinished.emit.call_args.args[0])
                self.assertEqual(controller._start_network_worker.call_count, 2)
                self.assertFalse(controller._edframe_state_find_sync_busy)
                self.assertEqual({row["system"] for row in controller._hge_sightings}, {"Local", "Near"})
                self.assertEqual(json.loads(controller.hge_cache_file.read_text()), controller._hge_sightings)

    def test_state_find_sequence_change_retries_without_duplicate_history(self):
        for timing in ("before_worker", "after_worker"):
            with self.subTest(timing=timing), TemporaryDirectory() as directory:
                controller = self.controller(directory)
                controller._finish_edframe_state_find_sync(self.state_result(controller))
                if timing == "before_worker":
                    controller._hge_save_sequences[str(controller.hge_cache_file)] += 1
                self.run_worker(controller)
                if timing == "after_worker":
                    controller._hge_save_sequences[str(controller.hge_cache_file)] += 1
                controller._finish_edframe_state_find_sync(controller.edFrameStateFindSyncFinished.emit.call_args.args[0])
                self.run_worker(controller)
                controller._finish_edframe_state_find_sync(controller.edFrameStateFindSyncFinished.emit.call_args.args[0])
                self.assertEqual(controller._start_network_worker.call_count, 2)
                self.assertFalse(controller._edframe_state_find_sync_busy)

    def test_state_find_completed_worker_cannot_publish_into_replaced_cache_path(self):
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            controller._finish_edframe_state_find_sync(self.state_result(controller))
            self.run_worker(controller)
            controller.hge_cache_file = Path(directory) / "other-profile.json"
            controller._finish_edframe_state_find_sync(controller.edFrameStateFindSyncFinished.emit.call_args.args[0])
            self.assertFalse(controller._edframe_state_find_sync_busy)
            self.assertEqual(controller._hge_sightings, [])
            self.assertFalse(controller.hge_cache_file.exists())
            self.assertEqual(controller._edframe_state_find_sync_meta["cursor"], "old")

    def test_qt_heartbeat_keeps_running_while_state_find_writer_waits(self):
        from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
        self.__class__._qt_app = QCoreApplication.instance() or QCoreApplication([])
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            loop = QEventLoop()
            timer = QTimer()
            beats = []
            timer.timeout.connect(lambda: beats.append(time.monotonic()))
            timer.setInterval(10)
            with controller._hge_file_lock:
                controller._finish_edframe_state_find_sync(self.state_result(controller))
                target = controller._start_network_worker.call_args.args[0]
                worker = threading.Thread(target=target)
                worker.start()
                timer.start()
                QTimer.singleShot(200, loop.quit)
                loop.exec()
                timer.stop()
                self.assertGreaterEqual(len(beats), 8)
                self.assertTrue(worker.is_alive())
                controller.edFrameStateFindSyncFinished.emit.assert_not_called()
            worker.join(3)
            self.assertFalse(worker.is_alive())
            controller._finish_edframe_state_find_sync(controller.edFrameStateFindSyncFinished.emit.call_args.args[0])
            self.assertFalse(controller._edframe_state_find_sync_busy)

    def test_state_find_stale_location_profile_opt_out_clear_busy_without_writes(self):
        for change in ("location", "profile", "disabled"):
            with self.subTest(change=change), TemporaryDirectory() as directory:
                controller = self.controller(directory)
                controller._finish_edframe_state_find_sync(self.state_result(controller))
                if change == "location":
                    controller._state["currentPosition"] = [4, 5, 6]
                elif change == "profile":
                    controller._profile_generation += 1
                else:
                    controller._edframe_catalog_enabled = False
                self.run_worker(controller)
                controller._finish_edframe_state_find_sync(controller.edFrameStateFindSyncFinished.emit.call_args.args[0])
                self.assertFalse(controller._edframe_state_find_sync_busy)
                self.assertFalse(controller.hge_cache_file.exists())
                self.assertFalse(controller.state_find_sync_file.exists())
                self.assertEqual(controller._edframe_state_find_sync_meta["cursor"], "old")

    def test_state_find_save_or_archive_failure_never_advances_cursor(self):
        for failure in ("cache", "cursor", "archive"):
            with self.subTest(failure=failure), TemporaryDirectory() as directory:
                controller = self.controller(directory)
                result = self.state_result(controller)
                if failure == "archive":
                    result["page"]["signals"][0]["signal_timestamp"] = (
                        datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
                    controller._history_archive.archive.side_effect = sqlite3.OperationalError("busy")
                controller._finish_edframe_state_find_sync(result)
                from ed_companion.persistence import atomic_write_chunks
                def write(path, chunks):
                    if path == (controller.hge_cache_file if failure == "cache" else controller.state_find_sync_file):
                        return False
                    return atomic_write_chunks(path, chunks)
                with patch(MODULE + "atomic_write_chunks", side_effect=write):
                    self.run_worker(controller)
                controller._finish_edframe_state_find_sync(controller.edFrameStateFindSyncFinished.emit.call_args.args[0])
                self.assertEqual(controller._edframe_state_find_sync_meta["cursor"], "old")
                self.assertEqual(controller._hge_sightings, [])
                self.assertFalse(controller._edframe_state_find_sync_busy)

    def test_state_find_storage_rejected_during_shutdown_releases_busy(self):
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            controller._start_network_worker.return_value = False
            controller._finish_edframe_state_find_sync(self.state_result(controller))
            self.assertFalse(controller._edframe_state_find_sync_busy)
            self.assertIsNone(controller._active_edframe_state_find_sync_request)

    def test_state_find_preparation_archives_expired_and_overflow_without_changing_evidence(self):
        local = signal("Local", evidence_kind="LOCAL_JOURNAL")
        expired = signal("Expired", signal_timestamp="2000-01-01T00:00:00Z")
        prediction = signal("BGS", evidence_kind="BGS_PREDICTION", time_remaining=0)
        archive = Mock()
        prepared = prepare_state_find_page([local, prediction], {"signals": [expired, signal()]},
                                           state_find_region([1, 2, 3]), limit=2, archive=archive)
        retained = prepared["preparedRows"]
        self.assertIn(local, retained)
        all_rows = [*retained, *archive.archive.call_args.args[1]]
        self.assertEqual({row["system"] for row in all_rows}, {"Local", "BGS", "Expired", "Near"})
        self.assertEqual(next(row for row in all_rows if row["system"] == "BGS")["evidence_kind"], "BGS_PREDICTION")
        self.assertEqual(next(row for row in all_rows if row["system"] == "Local")["evidence_kind"], "LOCAL_JOURNAL")

    def test_state_find_missing_archive_cannot_prune_history(self):
        with self.assertRaises(OSError):
            prepare_state_find_page([], {"signals": [signal(signal_timestamp="2000-01-01T00:00:00Z")]},
                                    state_find_region([1, 2, 3]), limit=2)

    def verification_result(self, controller):
        controller._active_mining_verification_request = {"id": "verify"}
        return {"id": "verify", "profileKey": "alpha", "generation": 4,
                "path": str(controller.mining_catalog_file), "markets": [{"commodity": "platinum"}],
                "candidates": [], "total": 1}

    def test_verification_completion_never_repeats_worker_storage(self):
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            result = self.verification_result(controller)
            store = controller._mining_market_store
            with patch.object(store, "ingest", return_value=1) as ingest, \
                 patch.object(store, "record_source_result") as record:
                worker = threading.Thread(target=controller._persist_verified_mining_markets,
                                          args=(result, store, controller._mining_file_lock))
                worker.start()
                worker.join(3)
                self.assertFalse(worker.is_alive())
                ingest.assert_called_once()
                record.assert_called_once()
            with patch.object(store, "ingest", side_effect=AssertionError("GUI ingest")), \
                 patch.object(store, "record_source_result", side_effect=AssertionError("GUI write")):
                controller._finish_mining_verification(result)
            self.assertEqual(controller._mining_market_revision, 1)

    def test_verification_context_change_skips_worker_storage(self):
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            result = self.verification_result(controller)
            controller._profile_generation += 1
            store = controller._mining_market_store
            with patch.object(store, "ingest") as ingest:
                controller._persist_verified_mining_markets(result, store, controller._mining_file_lock)
            ingest.assert_not_called()

    def test_verification_storage_error_is_reported_without_gui_retry(self):
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            result = self.verification_result(controller)
            store = controller._mining_market_store
            with patch.object(store, "ingest", side_effect=sqlite3.OperationalError("busy")) as ingest:
                controller._persist_verified_mining_markets(result, store, controller._mining_file_lock)
                controller._finish_mining_verification(result)
            ingest.assert_called_once()
            self.assertEqual(controller._mining_market_revision, 0)
            self.assertIn("market save failed", controller._mining_verification_status)

    def test_verification_ring_merge_is_dispatched_not_performed_in_gui(self):
        with TemporaryDirectory() as directory:
            controller = self.controller(directory)
            result = self.verification_result(controller)
            result.update(markets=[], candidates=[{"system": "Cubeo"}])
            controller._dispatch_mining_observation_batch = Mock(return_value=True)
            with patch(MODULE + "merge_mining_candidate_batch", side_effect=AssertionError("GUI ring merge")):
                controller._finish_mining_verification(result)
            controller._dispatch_mining_observation_batch.assert_called_once_with(result["candidates"])


if __name__ == "__main__":
    unittest.main()
