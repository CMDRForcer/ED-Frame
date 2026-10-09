"""Contract tests for the opt-in disk store, never a live profile migration."""
import copy
import json
from pathlib import Path
import random
import sqlite3
import tempfile
import threading
import unittest

from ed_companion.navigation.mining_geometry import nearby_rows
from tools.mining_ring_store_prototype import (
    PrototypeRingStore, StoreScope, build_store, encode, file_digest,
    iter_catalog, valid_position,
)


SCOPE = StoreScope("synthetic", "generation-one")


def ring(name, coordinates, **values):
    return {"system": name, "ring": name + " A Ring", "coordinates": coordinates,
            "observedAt": "2020-01-01T00:00:00Z", "learnedAt": "2026-10-09T12:00:00Z",
            "source": "Synthetic", "hotspots": [{"commodity": "platinum", "count": 0}],
            **values}


class PrototypeRingStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.source = self.root / "public.json"
        self.path = self.root / "rings.sqlite3"
        self.addCleanup(self.directory.cleanup)

    def build(self, rows, **metadata):
        payload = {"identityVersion": 2, **metadata, "candidates": rows}
        self.source.write_text(encode(payload), encoding="utf-8-sig")
        original = file_digest(self.source)
        build_store(self.source, self.path, SCOPE)
        self.assertEqual(file_digest(self.source), original)
        return PrototypeRingStore(self.path, SCOPE)

    def test_full_payload_order_duplicates_history_and_root_metadata_preserved(self):
        rows = [ring("Ä Test", [1, 2, 3], extra={"facts": [0, None, False]},
                     sourceObservations=[{"source": "Old", "observedAt": "1999-01-01"}]),
                ring("Ä Test", [1, 2, 3]), None, "legacy", {"ring": "No system"}]
        store = self.build(rows, resetAt="", unknown={"nested": [True, None]})
        self.assertEqual(list(store.iter_all()), rows)
        self.assertEqual(store.metadata()["root"],
                         {"identityVersion": 2, "resetAt": "", "unknown": {"nested": [True, None]}})
        self.assertEqual(store.metadata()["manifest"]["count"], 5)
        # Old observations remain selectable; the store applies no age cutoff.
        self.assertEqual(list(store.nearby("Ä Test", None, 250)), rows[:2])

    def test_chunk_boundaries_bom_escapes_nested_values_and_numeric_tokens(self):
        rows = [ring("界 \\\"", [1e-100, -1.2345e100, 0], nested=[[1, 2], {"key": "ä"}])]
        self.source.write_text(encode({"before": [1e-200], "candidates": rows, "after": 1e100}),
                               encoding="utf-8-sig")
        for chunk_size in (1, 2, 3, 7, 64 * 1024):
            metadata = {}
            self.assertEqual(list(iter_catalog(self.source, metadata, chunk_size=chunk_size)), rows)
            self.assertEqual(metadata, {"before": [1e-200], "after": 1e100})

    def test_compact_regional_rows_preserve_facts_and_independent_nested_records(self):
        rows = [ring("A long synthetic system name", [1, 2, 3], ring="First", nested=[["ä", None]]),
                ring("A long synthetic system name", [1, 2, 3], ring="Second", nested=[["ä", None]])]
        store = self.build(rows)
        actual = list(store.nearby("Origin", [0, 0, 0], 250, snapshot_arrays=True))
        self.assertEqual(encode(actual), encode(rows))
        self.assertIs(actual[0]["system"], actual[1]["system"])
        self.assertIsInstance(actual[0]["coordinates"], tuple)
        actual[0]["hotspots"][0]["count"] = 43
        self.assertEqual(actual[1]["hotspots"][0]["count"], 0)
        self.assertEqual(list(store.iter_all()), rows)

    def test_radius_rounding_order_same_system_missing_and_nonfinite_coordinates(self):
        values = [[250.049, 0, 0], [250.051, 0, 0], [500.049, 0, 0],
                  [500.051, 0, 0], [200, 200, 0], ["1", "2", "3"],
                  ["bad", 1, 2], None, [1, 2], [float("nan"), 5000, 0],
                  [float("inf"), 0, 0]]
        rows = [ring(str(index), value) for index, value in enumerate(values)]
        rows += [ring(" ORIGIN ", None), ring("Origin", [9000, 0, 0])]
        store = self.build(rows)
        for radius in (250, 500):
            for origin in ((0, 0, 0), None, (float("nan"), 0, 0), (float("inf"), 0, 0)):
                expected = [rows[index] for index, _distance in
                            nearby_rows(rows, "Origin", origin, radius, valid_position)]
                self.assertEqual(encode(list(store.nearby("Origin", origin, radius))), encode(expected))

    def test_random_regions_and_rtree_float_rounding_match_full_scan(self):
        randomizer = random.Random(43)
        rows = [ring(str(i), [randomizer.uniform(-10000, 10000) for _ in range(3)])
                for i in range(1400)]
        rows += [ring("Boundary", [123456.75 + 250.049, -123456.75, 0])]
        store = self.build(rows)
        for origin, radius in (([123456.75, -123456.75, 0], 250),
                               ([0, 0, 0], 500), ([100, -100, 0], 20000)):
            expected = [rows[i] for i, _ in nearby_rows(rows, "Origin", origin, radius, valid_position)]
            self.assertEqual(list(store.nearby("Origin", origin, radius)), expected)
        self.assertEqual(list(store.nearby("Origin", None, 0)), rows)

    def test_unusable_or_changed_json_cannot_publish_or_overwrite(self):
        for value in ('{"candidates":[{}]', '{"candidates":[],"candidates":[]}',
                      '{"candidates":null}', '{"other":[]}', '{"candidates":[]} extra'):
            self.source.write_text(value, encoding="utf-8")
            with self.assertRaises(ValueError):
                build_store(self.source, self.path, SCOPE)
            self.assertFalse(self.path.exists())
            self.assertEqual(list(self.root.glob("*.building-*")), [])
        store = self.build([ring("Existing", [0, 0, 0])])
        with self.assertRaises(FileExistsError):
            build_store(self.source, self.path, SCOPE)
        self.assertEqual(len(list(store.iter_all())), 1)

    def test_source_change_during_build_is_rejected(self):
        self.source.write_text(encode({"candidates": [ring(str(i), [0, 0, 0]) for i in range(512)]}))
        def change(_count):
            with self.source.open("a") as handle:
                handle.write(" ")
        with self.assertRaisesRegex(ValueError, "changed"):
            build_store(self.source, self.path, SCOPE, checkpoint=change)
        self.assertFalse(self.path.exists())

    def test_scope_fences_and_missing_store_never_create_files(self):
        with self.assertRaises(sqlite3.OperationalError):
            list(PrototypeRingStore(self.path, SCOPE).iter_all())
        self.assertFalse(self.path.exists())
        self.build([ring("Test", [0, 0, 0])])
        for scope in (StoreScope("other-profile", SCOPE.generation),
                      StoreScope(SCOPE.profile, "later-generation")):
            with self.assertRaisesRegex(ValueError, "mismatch"):
                list(PrototypeRingStore(self.path, scope).nearby("Test", [0, 0, 0], 250))

    def test_independent_concurrent_readers_do_not_mix_regions_or_change_store(self):
        rows = [ring("Near", [0, 0, 0]), ring("Far", [10000, 0, 0])]
        store = self.build(copy.deepcopy(rows))
        original = file_digest(self.path)
        barrier = threading.Barrier(2)
        results, errors = {}, []
        def read(name, origin):
            try:
                barrier.wait(timeout=5)
                results[name] = list(store.nearby(name, origin, 250))
            except Exception as exc:
                errors.append(exc)
        workers = [threading.Thread(target=read, args=("Near", [0, 0, 0])),
                   threading.Thread(target=read, args=("Far", [10000, 0, 0]))]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)
            self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results, {"Near": rows[:1], "Far": rows[1:]})
        self.assertEqual(file_digest(self.path), original)
        self.assertFalse(self.path.with_name(self.path.name + "-wal").exists())


if __name__ == "__main__":
    unittest.main()
