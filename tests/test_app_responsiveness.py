"""Regression guards for app-wide blocking and catalog memory duplication."""
from contextlib import closing
from datetime import datetime, timezone
import json
import gzip
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import Mock, patch

from ed_companion.compact_json import pack_json, unpack_json
from ed_companion.history_archive import HistoryArchive
from ed_companion.navigation.catalog_json import load_catalog_json, iter_catalog_json
from ed_companion.navigation.mining_batch import prepare_mining_batch
from ed_companion.navigation.mining_market_store import MarketCatalogStore
from ed_companion.persistence import atomic_write, atomic_write_chunks, load_json_file
from ed_companion.phase14.controller import CockpitController


class AppResponsivenessTests(unittest.TestCase):
    def test_stream_load_and_save_preserve_nested_unicode_facts_and_order(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            value = {"metadata": {"version": 2}, "candidates": [
                {"system": "Même", "source": "Shared", "hotspots": [],
                 "note": "{}[\\\"]" + "ä" * 66000, "nullable": None},
                {"system": "Même", "source": "Shared", "coordinates": [1, 2, 3]},
            ], "tail": 12345}
            atomic_write_chunks(path, iter_catalog_json(value))
            loaded = load_catalog_json(path, {})
            self.assertEqual(loaded, value)
            self.assertIs(loaded["candidates"][0]["system"], loaded["candidates"][1]["system"])
            self.assertIs(loaded["candidates"][0]["source"], loaded["candidates"][1]["source"])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), value)

    def test_stream_rejects_incomplete_trailing_and_invalid_json(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for text in ('{"candidates":[{}', '{"candidates":[{},]}', '{}more', '{"x":truez}'):
                with self.subTest(text=text):
                    atomic_write(path, text)
                    with self.assertRaises(ValueError):
                        load_catalog_json(path, {})

    def test_stream_handles_empty_root_arrays_bom_and_number_chunk_boundary(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "array.json"
            for value in ([], {}, [1, True, None, 1e30, "value"], {"long": "a" * 65523, "number": 12345}):
                atomic_write(path, "\ufeff" + json.dumps(value))
                self.assertEqual(load_catalog_json(path, {}), value)

    def test_slow_catalog_save_does_not_block_unrelated_settings_file(self):
        with TemporaryDirectory() as directory:
            entered, release = threading.Event(), threading.Event()
            errors = []
            def chunks():
                yield '{"candidates":['
                entered.set()
                if not release.wait(3):
                    raise AssertionError("writer not released")
                yield "]}"
            def writer():
                try:
                    atomic_write_chunks(Path(directory) / "catalog.json", chunks())
                except Exception as exc:
                    errors.append(exc)
            worker = threading.Thread(target=writer)
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                started = time.monotonic()
                self.assertTrue(atomic_write(Path(directory) / "settings.json", '{"last_page":1}'))
                self.assertLess(time.monotonic() - started, 0.25)
                self.assertTrue(worker.is_alive())
            finally:
                release.set()
                worker.join(3)
            self.assertEqual(errors, [])

    def test_stream_persistence_protects_wrong_root_then_accepts_repaired_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            atomic_write(path, '[]')
            self.assertEqual(load_json_file(path, {}, loader=load_catalog_json), {})
            self.assertFalse(atomic_write(path, '{}'))
            self.assertEqual(path.read_text(), '[]')
            self.assertEqual(len(list(Path(directory).glob('*.corrupt-*'))), 1)
            path.write_text('{"repaired":true}', encoding="utf-8")
            self.assertEqual(load_json_file(path, {}, loader=load_catalog_json), {"repaired": True})
            self.assertTrue(atomic_write(path, '{}'))

    def test_new_compressed_backup_keeps_legacy_image_and_recovers_exact_rows(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "market.sqlite3"
            store = MarketCatalogStore(path)
            store.set_metadata("facts", "full exact value" * 1000)
            store.checkpoint()
            original = path.read_bytes()
            store.legacy_backup_path.write_bytes(original)
            self.assertTrue(store.has_backup())
            self.assertTrue(store.backup())
            self.assertEqual(store.legacy_backup_path.read_bytes(), original)
            snapshot = gzip.decompress(store.backup_path.read_bytes())
            self.assertTrue(snapshot.startswith(b"SQLite format 3\x00"))
            self.assertEqual(len(snapshot), len(original))
            self.assertLess(store.backup_path.stat().st_size, len(original) / 2)
            path.write_bytes(b"broken")
            self.assertEqual(store.metadata("facts"), "full exact value" * 1000)

    def test_bad_compressed_recovery_uses_legacy_and_failed_backup_keeps_last_good(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "market.sqlite3"
            store = MarketCatalogStore(path)
            store.set_metadata("facts", "legacy")
            store.checkpoint()
            store.legacy_backup_path.write_bytes(path.read_bytes())
            store.backup_path.write_bytes(b"bad gzip")
            path.write_bytes(b"broken")
            self.assertEqual(store.metadata("facts"), "legacy")
            self.assertTrue(store.backup())
            previous = store.backup_path.read_bytes()
            with patch("ed_companion.navigation.mining_market_store.os.replace", side_effect=OSError("disk")):
                self.assertFalse(store.backup())
            self.assertEqual(store.backup_path.read_bytes(), previous)
            self.assertFalse(store._backup_lock.locked())

    def test_reset_during_backup_cannot_restore_pre_reset_snapshot(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "market.sqlite3"
            store = MarketCatalogStore(path)
            store.set_metadata("facts", "before reset")
            self.assertTrue(store.backup())
            entered, release = threading.Event(), threading.Event()
            real_open = gzip.open
            def paused_open(path, mode, **kwargs):
                if mode == "wb":
                    entered.set()
                    self.assertTrue(release.wait(3))
                return real_open(path, mode, **kwargs)
            results = []
            with patch("ed_companion.navigation.mining_market_store.gzip.open", side_effect=paused_open):
                worker = threading.Thread(target=lambda: results.append(store.backup()))
                worker.start()
                try:
                    self.assertTrue(entered.wait(1))
                    self.assertTrue(store.reset())
                    self.assertEqual(store.metadata("facts"), "")
                finally:
                    release.set()
                    worker.join(3)
            self.assertEqual(results, [False])
            self.assertFalse(store.backup_path.exists())
            self.assertTrue(store.backup())
            path.write_bytes(b"broken after reset")
            self.assertEqual(store.metadata("facts"), "")

    def test_stream_save_failure_keeps_previous_file_and_cleans_own_temp(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            atomic_write(path, "old")
            def fail():
                yield "partial"
                raise RuntimeError("disk-like failure")
            with self.assertRaises(RuntimeError):
                atomic_write_chunks(path, fail())
            self.assertEqual(path.read_text(), "old")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_market_reader_does_not_wait_for_python_lock_or_open_wal_writer(self):
        with TemporaryDirectory() as directory:
            store = MarketCatalogStore(Path(directory) / "market.sqlite3")
            entered, release = threading.Event(), threading.Event()
            def writer():
                with store._lock, closing(store._connect()) as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("INSERT INTO catalog_meta(key,value) VALUES ('pending','new')")
                    entered.set()
                    release.wait(3)
                    db.commit()
            worker = threading.Thread(target=writer)
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                started = time.monotonic()
                self.assertEqual(store.metadata("pending", "old"), "old")
                self.assertEqual(store.count(), 0)
                self.assertLess(time.monotonic() - started, 0.25)
            finally:
                release.set()
                worker.join(3)
            self.assertEqual(store.metadata("pending"), "new")

    def test_unchanged_catalog_rows_are_shared_not_cloned_by_relay_batches(self):
        old = [{"system": "Test", "ring": "A", "coordinates": [0, 0, 0]}]
        result = prepare_mining_batch(old, [{"system": "Test", "ring": "B"}])
        self.assertIs(result["candidates"][0], old[0])
        self.assertIsInstance(result["positions"], dict)

    def test_retrieving_identical_facts_does_not_create_more_history_but_new_facts_do(self):
        with TemporaryDirectory() as directory:
            archive = HistoryArchive(Path(directory) / "history.sqlite3")
            first = {"system": "Test", "ring": "A", "source": "ED-Frame",
                     "observedAt": "2026-10-01T00:00:00Z", "learnedAt": "first"}
            second = {**first, "learnedAt": "later", "distanceLy": 2, "stale": True}
            prepare_mining_batch([], [first], archive=archive)
            prepare_mining_batch([], [second], archive=archive)
            self.assertEqual(archive.count("mining_observations"), 1)
            self.assertEqual(archive.records("mining_observations"), [second])
            prepare_mining_batch([], [{**second, "observedAt": "2026-10-02T00:00:00Z"}], archive=archive)
            self.assertEqual(archive.count("mining_observations"), 2)

    def test_history_compression_preserves_legacy_reads_exact_data_and_export(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            archive = HistoryArchive(path)
            old, new = {"id": "legacy"}, {"id": "new", "payload": "ä" * 10000}
            archive.archive("facts", [new], key_field="id")
            with closing(sqlite3.connect(path)) as db:
                payload = db.execute("SELECT payload FROM history").fetchone()[0]
                self.assertIsInstance(payload, bytes)
                self.assertLess(len(payload), 500)
                db.execute("INSERT INTO history VALUES ('facts','legacy','','',?)", (json.dumps(old),))
                db.commit()
            loaded = HistoryArchive(path)
            self.assertEqual(loaded.records("facts"), [old, new])
            destination = loaded.export_json(Path(directory) / "export.json")
            self.assertEqual([row["data"] for row in json.loads(destination.read_text(encoding="utf-8"))["records"]], [old, new])
            self.assertEqual(unpack_json(pack_json(json.dumps(new))), new)

    def test_tab_switch_debounces_disk_save_and_retains_shared_source(self):
        c = CockpitController.__new__(CockpitController)
        c._last_page = 12
        c.uiConfigSaveTimer = Mock()
        c._save_ui_config = Mock()
        source = c._mining_rows_cache = [{"ring": "A"}]
        c.setLastPage(1)
        c.setLastPage(2)
        c._save_ui_config.assert_not_called()
        self.assertEqual(c.uiConfigSaveTimer.start.call_count, 2)
        self.assertIs(c._mining_rows_cache, source)

    def test_powerplay_snapshot_save_is_queued_and_keeps_original_profile_target(self):
        with TemporaryDirectory() as directory:
            c = CockpitController.__new__(CockpitController)
            c._start_network_worker = Mock(return_value=True)
            path = Path(directory) / "alpha.json"
            snapshot = {"systems": [{"system": "Test", "coordinates": [1, 2, 3]}]}
            c._save_mining_json(path, snapshot)
            self.assertFalse(path.exists())
            worker = c._start_network_worker.call_args.args[0]
            c.profile_context = Mock(key="beta")
            c._mining_powerplay_catalog = {"systems": []}
            worker()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), snapshot)

    def test_maintenance_waits_for_active_reader_without_gating_normal_writes(self):
        with TemporaryDirectory() as directory:
            store = MarketCatalogStore(Path(directory) / "market.sqlite3")
            entered, release, completed = threading.Event(), threading.Event(), threading.Event()
            def reader():
                with store._reader():
                    entered.set()
                    release.wait(3)
            worker = threading.Thread(target=reader)
            worker.start()
            self.assertTrue(entered.wait(1))
            resetter = threading.Thread(target=lambda: (store.reset(), completed.set()))
            resetter.start()
            try:
                self.assertFalse(completed.wait(0.05))
            finally:
                release.set()
                worker.join(3)
                resetter.join(3)
            self.assertTrue(completed.is_set())
            self.assertEqual(store.count(), 0)

    def test_derived_cache_keeps_only_current_revision_per_domain(self):
        c = CockpitController.__new__(CockpitController)
        c._derived_cache = {"commander_fleet": (1, [])}
        for revision in range(100):
            value = c._cached_derived("test", revision, lambda: [revision])
            self.assertEqual(value, [revision])
        self.assertEqual(len(c._derived_cache), 2)
        self.assertIn(("test", 99), c._derived_cache)


class AsyncMiningPlanTests(unittest.TestCase):
    def controller(self, directory):
        c = CockpitController.__new__(CockpitController)
        c.profile_context = Mock(key="alpha")
        c._profile_generation = 1
        c._state = {"system": "Test", "currentPosition": [0, 0, 0], "localMiningEvidence": {}}
        c._mining_catalog = {"candidates": [{"system": "Test", "ring": "A",
            "coordinates": [0, 0, 0], "ringType": "Metallic", "reserveLevel": "Pristine",
            "hotspots": [{"commodity": "platinum", "count": 1}], "evidence": "CATALOG_CANDIDATE"}]}
        c._mining_rows_cache_key = ("rows",)
        c._mining_rows = lambda: c._mining_catalog["candidates"]
        c._mining_market_cache = {}
        c._mining_market_catalog = {"markets": []}
        c._mining_powerplay_catalog = {}
        c._mining_powerplay_observations = []
        c._mining_market_verification_states = {}
        c._mining_market_revision = 0
        c._data_dir = c._reference_data_dir = Path(directory)
        c._async_mining_plan_enabled = True
        c._network_threads_lock = threading.Lock()
        c._start_network_worker = Mock(return_value=True)
        c.miningPlanReady = Mock()
        c.miningChanged = Mock()
        return c

    args = ("Test", "Platinum", 100, "ALL RESERVES", "ANY RING", True,
            "LASER", "HIGHEST PROFIT", 1, 500000, 24, 30, False, False,
            False, False, "ANY", "", "REINFORCE", "ANY", "ANY")

    def run_worker(self, c):
        target = c._start_network_worker.call_args.args[0]
        worker = threading.Thread(target=target)
        worker.start(); worker.join(3)
        self.assertFalse(worker.is_alive())
        result = c.miningPlanReady.emit.call_args.args[0]
        self.assertEqual(result[-1], "")
        return result

    def test_plan_dispatch_returns_immediately_worker_publishes_identical_routes_and_diagnostics(self):
        with TemporaryDirectory() as directory:
            c = self.controller(directory)
            expected = c._compute_mining_plan_routes(*self.args)
            self.assertEqual(c.miningPlanRoutes(*self.args), [])
            self.assertIsNotNone(c._active_mining_plan)
            result = self.run_worker(c)
            c._finish_mining_plan(result)
            self.assertEqual(c.miningPlanRoutes(*self.args), expected)
            self.assertIsNone(c._active_mining_plan)
            self.assertEqual(c._start_network_worker.call_count, 1)
            self.assertTrue(c.miningMarketDiagnostics("Test", "Platinum", 100, 1, 500000, 24, "ANY")["originKnown"])

    def test_profile_switch_reset_and_changed_market_fence_old_worker_results(self):
        for changed in ("profile", "catalog", "market"):
            with self.subTest(changed=changed), TemporaryDirectory() as directory:
                c = self.controller(directory)
                c.miningPlanRoutes(*self.args)
                result = self.run_worker(c)
                if changed == "profile":
                    c._profile_generation += 1
                elif changed == "catalog":
                    c._mining_catalog_revision = 2
                else:
                    c._mining_market_revision += 1
                c._finish_mining_plan(result)
                self.assertFalse(hasattr(c, "_mining_plan_cache_key"))
                self.assertEqual(c.miningPlanRoutes(*self.args), [])
                self.assertEqual(c._start_network_worker.call_count, 2)

    def test_new_query_during_running_plan_does_not_reuse_old_query_results(self):
        with TemporaryDirectory() as directory:
            c = self.controller(directory)
            c.miningPlanRoutes(*self.args)
            newer = ("Other", *self.args[1:])
            self.assertEqual(c.miningPlanRoutes(*newer), [])
            self.assertEqual(c._start_network_worker.call_count, 1)
            c._finish_mining_plan(self.run_worker(c))
            self.assertFalse(hasattr(c, "_mining_plan_cache_key"))
            c.miningPlanRoutes(*newer)
            self.assertEqual(c._start_network_worker.call_count, 2)

    def test_same_query_refresh_retains_results_and_reuses_unchanged_snapshot(self):
        with TemporaryDirectory() as directory:
            c = self.controller(directory)
            c.miningPlanRoutes(*self.args)
            c._finish_mining_plan(self.run_worker(c))
            previous = c.miningPlanRoutes(*self.args)
            self.assertTrue(previous)
            c._mining_market_revision += 1
            self.assertIs(c.miningPlanRoutes(*self.args), previous)
            c._finish_mining_plan(self.run_worker(c))
            self.assertIs(c.miningPlanRoutes(*self.args), previous)
            self.assertEqual(c._start_network_worker.call_count, 2)

    def test_failed_refresh_retains_only_same_query_results_and_diagnostics(self):
        with TemporaryDirectory() as directory:
            c = self.controller(directory)
            c.miningPlanRoutes(*self.args)
            c._finish_mining_plan(self.run_worker(c))
            previous = c.miningPlanRoutes(*self.args)
            diagnostics = c._mining_plan_diagnostics
            c._mining_market_revision += 1
            self.assertIs(c.miningPlanRoutes(*self.args), previous)
            result = self.run_worker(c)
            c._finish_mining_plan((*result[:3], [], (), {}, "test failure"))
            self.assertIs(c.miningPlanRoutes(*self.args), previous)
            self.assertIs(c._mining_plan_diagnostics, diagnostics)
            self.assertIn("test failure", c._mining_sync_status)
            newer = ("Other", *self.args[1:])
            self.assertEqual(c.miningPlanRoutes(*newer), [])
            result = self.run_worker(c)
            c._finish_mining_plan((*result[:3], [], (), {}, "test failure"))
            self.assertEqual(c.miningPlanRoutes(*newer), [])
            c._profile_generation += 1
            self.assertEqual(c.miningPlanRoutes(*self.args), [])

    def test_completed_changed_route_replaces_snapshot_atomically(self):
        with TemporaryDirectory() as directory:
            c = self.controller(directory)
            c.miningPlanRoutes(*self.args)
            c._finish_mining_plan(self.run_worker(c))
            previous = c.miningPlanRoutes(*self.args)
            c._mining_market_revision += 1
            self.assertIs(c.miningPlanRoutes(*self.args), previous)
            result = self.run_worker(c)
            updated = [{**row, "price": 123456} for row in result[3]]
            c._finish_mining_plan((*result[:3], updated, *result[4:]))
            self.assertEqual(c.miningPlanRoutes(*self.args), updated)
            self.assertNotEqual(previous, updated)

    def test_async_diagnostics_requires_exact_demand_age_and_pad_query(self):
        with TemporaryDirectory() as directory:
            c = self.controller(directory)
            c._mining_market_cache = {"query": {"startSystem": "test", "commodity": "platinum",
                "nearbyLy": 100, "minDemand": 1, "maxMarketAgeHours": 24, "landingPad": "ANY"}}
            args = ("Test", "Platinum", 100, 1, 500000, 24, "ANY")
            self.assertTrue(c.miningMarketDiagnostics(*args)["cacheMatches"])
            for index, value in ((3, 2), (5, 1), (6, "LARGE")):
                changed = list(args)
                changed[index] = value
                self.assertFalse(c.miningMarketDiagnostics(*changed)["cacheMatches"])

    def test_lean_view_and_worker_preserve_all_route_modes(self):
        with TemporaryDirectory() as directory:
            c = self.controller(directory)
            now = datetime.now(timezone.utc).isoformat()
            c._mining_catalog["candidates"][0]["observedAt"] = now
            c._mining_market_catalog = {"markets": [{"system": "Test", "station": "Sale",
                "commodity": "platinum", "coordinates": [0, 0, 0], "landingPadSize": "L",
                "sellPrice": 250000, "demand": 10000, "observedAt": now}]}
            c._mining_powerplay_catalog = {"systems": [{"system": "Test",
                "controllingPower": "Aisling Duval", "powerState": "Exploited", "observedAt": now}]}
            original = json.loads(json.dumps(c._mining_catalog))
            for mode in ("HIGHEST PROFIT", "SHORTEST ROUTE", "POWERPLAY MERITS", "MEASURED PLATINUM", "PLATINUM + RES"):
                with self.subTest(mode=mode):
                    args = (*self.args[:7], mode, *self.args[8:])
                    decorated = c._build_mining_rows(c._state, c._mining_catalog)
                    c._mining_rows = lambda: decorated
                    del c._network_threads_lock
                    c._mining_find_cache_key = None
                    expected = c._compute_mining_plan_routes(*args)
                    lean = c._build_mining_rows(c._state, c._mining_catalog, decorate=False)
                    c._mining_rows = lambda: lean
                    c._network_threads_lock = threading.Lock()
                    self.assertEqual(c.miningPlanRoutes(*args), [])
                    c._finish_mining_plan(self.run_worker(c))
                    self.assertEqual(c.miningPlanRoutes(*args), expected)
            self.assertEqual(c._mining_catalog, original)


if __name__ == "__main__":
    unittest.main()
