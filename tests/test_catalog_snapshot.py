"""Private GC-light facts preserve disk, history, merge and view semantics."""
import copy
import gc
import json
from pathlib import Path
import platform
from tempfile import TemporaryDirectory
import unittest

from ed_companion.navigation.catalog_json import (
    catalog_record_snapshot, catalog_view_value, iter_catalog_json,
    load_catalog_json, load_catalog_snapshot,
)
from ed_companion.navigation.mining_batch import prepare_mining_batch, mining_observation_key
from ed_companion.navigation.mining_planner import _powerplay_index
from ed_companion.persistence import atomic_write_chunks


class CatalogSnapshotTests(unittest.TestCase):
    def test_loader_opt_in_keeps_root_arrays_and_exact_json_and_view_values(self):
        original = {"candidates": [{"system": "Même", "ring": "Même A Ring",
            "coordinates": [1, 2, 3], "empty": [], "none": None,
            "observations": [{"source": "Test", "nested": [[1], []]}],
            "hotspots": [{"commodity": "platinum", "count": 2}]}]}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            atomic_write_chunks(path, iter_catalog_json(original))
            loaded = load_catalog_snapshot(path, {})
            self.assertIs(type(loaded["candidates"]), list)
            row = loaded["candidates"][0]
            self.assertIs(type(row), dict)
            self.assertIs(type(row["coordinates"]), tuple)
            self.assertEqual(row["observations"][0]["nested"], ((1,), ()))
            self.assertEqual(catalog_view_value(loaded), original)
            self.assertEqual(json.loads("".join(iter_catalog_json(loaded))), original)
            self.assertEqual(load_catalog_json(path, {}), original)
            for root in (original["candidates"], {"systems": original["candidates"]}):
                atomic_write_chunks(path, iter_catalog_json(root))
                self.assertEqual(catalog_view_value(load_catalog_snapshot(path, {})), root)

    def test_snapshot_and_view_are_independent_without_process_gc_changes(self):
        original = {"coordinates": [1, 2, 3], "nested": [{"x": [7]}]}
        thresholds, enabled = gc.get_threshold(), gc.isenabled()
        snapshot = catalog_record_snapshot(original)
        view = catalog_view_value(snapshot)
        view["nested"][0]["x"].append(9)
        original["nested"][0]["x"].append(8)
        self.assertEqual(snapshot["nested"][0]["x"], (7,))
        self.assertEqual(gc.get_threshold(), thresholds)
        self.assertEqual(gc.isenabled(), enabled)

    @unittest.skipUnless(platform.python_implementation() == "CPython", "CPython optimization")
    def test_normal_collector_can_untrack_long_lived_acyclic_facts(self):
        rows = [catalog_record_snapshot({"coordinates": [1, 2, 3],
                "observations": [{"powers": [], "source": "Test"}], "empty": []})
                for _ in range(500)]
        for _ in range(4):
            gc.collect()
        # Tuples containing mutable dicts can remain tracked. Scalar tuples,
        # empty arrays and leaf fact dicts no longer inflate the traversed heap.
        self.assertFalse(any(gc.is_tracked(row["coordinates"]) for row in rows))
        self.assertFalse(any(gc.is_tracked(row["empty"]) for row in rows))
        self.assertFalse(any(gc.is_tracked(row["observations"][0]) for row in rows))

    def test_merge_history_identity_and_failure_fallback_preserve_all_facts(self):
        old = [{"system": "Test", "ring": "Test A Ring", "coordinates": [1, 2, 3],
                "hotspots": [{"commodity": "platinum", "count": 1}], "observations": []},
               {"system": "Other", "ring": "Other A Ring", "hotspots": []}]
        incoming = [{"system": "Test", "ring": "Test A Ring", "coordinates": [],
                     "hotspots": [{"commodity": "gold", "count": 2}], "ageSeconds": 123}]
        original = copy.deepcopy((old, incoming))
        captured = {}
        class Archive:
            def archive(self, category, rows, **_kwargs):
                captured[category] = catalog_view_value(rows)
        plain = prepare_mining_batch(old, incoming, archive=Archive(), transient_fields={"ageSeconds"})
        expected_history = copy.deepcopy(captured)
        frozen = [catalog_record_snapshot(row) for row in old]
        compact = prepare_mining_batch(frozen, incoming, archive=Archive(),
                                      transient_fields={"ageSeconds"}, snapshot_arrays=True)
        self.assertEqual(catalog_view_value(compact["candidates"]), plain["candidates"])
        self.assertIs(compact["candidates"][1], frozen[1])
        self.assertEqual(captured, expected_history)
        self.assertEqual((old, incoming), original)
        self.assertEqual(mining_observation_key(frozen[0]), mining_observation_key(old[0]))
        class BrokenArchive:
            def archive(self, *_args, **_kwargs):
                raise OSError("full")
        failed = prepare_mining_batch(frozen, incoming, archive=BrokenArchive(), snapshot_arrays=True)
        self.assertEqual(catalog_view_value(failed["candidates"]), [*old, *incoming])
        self.assertEqual(failed["archiveError"], "OSError")

    def test_powerplay_empty_arrays_do_not_erase_older_coordinates(self):
        facts = [{"system": "Test", "power": "Aisling Duval", "coordinates": [1, 2, 3],
                  "powers": ["Aisling Duval"], "observedAt": "2026-10-07T10:00:00Z"},
                 {"system": "Test", "power": "Aisling Duval", "coordinates": [],
                  "observedAt": "2026-10-08T10:00:00Z"}]
        self.assertEqual(catalog_view_value(_powerplay_index([
            catalog_record_snapshot(row) for row in facts])), _powerplay_index(facts))


if __name__ == "__main__":
    unittest.main()
