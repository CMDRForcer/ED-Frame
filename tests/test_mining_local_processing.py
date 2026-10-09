"""Local geometry reuse must not reuse freshness, evidence or route scores."""
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import threading
import unittest
from unittest.mock import Mock, patch

from ed_companion.navigation.catalog_json import catalog_record_snapshot, catalog_view_value
from ed_companion.navigation.mining_batch import mining_observation_key, prepare_mining_batch
from ed_companion.navigation.mining_geometry import MiningGeometryCache
from ed_companion.phase14.controller import CockpitController
from ed_companion.phase14.controller_navigation import NavigationMixin


def ring(system, coordinates, **values):
    return {"system": system, "ring": f"{system} A Ring", "coordinates": coordinates,
            "ringType": "Metallic", "reserveLevel": "PristineResources",
            "evidence": "HOTSPOT_CONFIRMED", "source": "Synthetic",
            "observedAt": "2026-10-09T11:00:00Z", "hotspots": [{"commodity": "platinum"}],
            **values}


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class MiningGeometryTests(unittest.TestCase):
    def setUp(self):
        self.cache = MiningGeometryCache()

    def select(self, rows, origin=(0, 0, 0), radius=250, system="Origin", validator=None):
        return list(self.cache.rows_for(rows, system, origin, radius,
                    validator or CockpitController._valid_star_position))

    def legacy_selection(self, rows, origin, radius, system):
        selected = []
        for row in rows:
            coordinates = CockpitController._valid_star_position(row.get("coordinates"))
            if str(row.get("system") or "").strip().casefold() == system.casefold():
                distance = 0.0
            elif origin is not None and coordinates is not None:
                distance = round(math.sqrt(sum((a - b) ** 2 for a, b in zip(origin, coordinates))), 1)
            else:
                distance = None
            if distance is not None and not float(distance) > radius:
                selected.append((row, distance))
        return selected

    def test_exact_radius_rounding_invalid_missing_and_nonfinite_coordinates(self):
        rows = [ring(str(index), value) for index, value in enumerate([
            [250.049, 0, 0], [250.051, 0, 0], [200, 200, 0], [0, 0, 0],
            ["1", "2", "3"], ["bad", 1, 2], None, [1, 2],
            [float("nan"), 5000, 0], [float("inf"), 0, 0],
        ])] + [ring(" ORIGIN ", None)]
        for origin in ((0, 0, 0), None, (float("nan"), 0, 0), (float("inf"), 0, 0)):
            actual = self.select(rows, origin=origin)
            expected = self.legacy_selection(rows, origin, 250, "Origin")
            self.assertEqual(encoded(actual), encoded(expected))

    def test_repeated_geometry_avoids_another_catalog_walk(self):
        rows = [ring("Near", [1, 2, 3]), ring("Far", [5000, 0, 0])]
        validator = Mock(wraps=CockpitController._valid_star_position)
        first = self.select(rows, validator=validator)
        self.assertEqual(validator.call_count, 2)
        second = self.select(rows, validator=validator)
        self.assertEqual(first, second)
        self.assertEqual(validator.call_count, 2)
        self.assertIs(second[0][0], rows[0])

    def test_snapshot_origin_system_radius_and_length_invalidate(self):
        rows = [ring("Near", [100, 0, 0]), ring("Origin", None)]
        validator = Mock(wraps=CockpitController._valid_star_position)
        self.select(rows, validator=validator)
        for values in ({"rows": copy.deepcopy(rows)}, {"origin": (50, 0, 0)},
                       {"radius": 99}, {"system": "Other"}):
            before = validator.call_count
            inputs = {"rows": rows, **values}
            self.select(**inputs, validator=validator)
            self.assertGreater(validator.call_count, before)
        # Replacement-only production sources also guard a changed length.
        rows.append(ring("New", [1, 0, 0]))
        self.assertIn("New", [row["system"] for row, _distance in self.select(rows)])

    def test_limit_bounds_index_storage_and_never_changes_source_facts(self):
        import sys
        rows = [ring(str(index), [0, 0, 0]) for index in range(self.cache.MAX_ROWS)]
        original = encoded(rows[0])
        self.select(rows)
        self.assertLess(sys.getsizeof(self.cache._selection.positions)
                        + sys.getsizeof(self.cache._selection.distances), 2 * 1024 * 1024)
        self.assertEqual(encoded(rows[0]), original)

    def test_oversized_region_streams_all_rows_without_retaining_an_index(self):
        self.cache.MAX_ROWS = 3
        rows = [ring(str(index), [index, 0, 0]) for index in range(12)]
        self.assertEqual([row for row, _distance in self.select(rows)], rows)
        self.assertIsNone(self.cache._selection)
        self.assertIsNone(self.cache._key)
        self.assertEqual([row for row, _distance in self.select(rows)], rows)

    def test_older_iterator_remains_snapshot_bound_after_replacement(self):
        old = [ring("Old", [1, 0, 0])]
        new = [ring("New", [2, 0, 0])]
        iterator = self.cache.rows_for(old, "Origin", (0, 0, 0), 250,
                                      CockpitController._valid_star_position)
        self.select(new)
        self.assertEqual([row["system"] for row, _distance in iterator], ["Old"])
        self.assertIs(self.cache._selection.source, new)

    def test_concurrent_workers_cannot_receive_another_snapshots_rows(self):
        barrier = threading.Barrier(2)
        result = []
        def run(name, position):
            rows = [ring(name, position)]
            def validator(value):
                barrier.wait(timeout=3)
                return CockpitController._valid_star_position(value)
            result.append((name, self.select(rows, validator=validator)))
        workers = [threading.Thread(target=run, args=(name, [index, 0, 0]))
                   for index, name in enumerate(("One", "Two"))]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(len(result), 2)
        for name, selection in result:
            self.assertEqual(selection[0][0]["system"], name)

    def facade(self, rows, cached=True):
        owner = NavigationMixin()
        owner._state = {"system": "Origin", "currentPosition": [0, 0, 0]}
        owner._network_threads_lock = True
        owner._valid_star_position = CockpitController._valid_star_position
        owner._mining_rows = lambda: rows
        owner._mining_rows_cache_key = "fixed-rows"
        if cached:
            owner._mining_geometry_cache = self.cache
        return owner

    def test_cached_and_uncached_views_are_exact_for_all_query_filters(self):
        rng = random.Random(42)
        rows = [catalog_record_snapshot(ring(f"System {index}",
                [rng.uniform(-500, 500) for _ in range(3)],
                ringType=("Metallic", "MetalRich", "Rocky", "Icy")[index % 4],
                reserveLevel=("PristineResources", "MajorResources")[index % 2],
                hotspots=[{"commodity": ("platinum", "osmium", "painite")[index % 3]}],
                miningSiteType="belt" if index % 7 == 0 else "ring"))
                for index in range(500)]
        old, new = self.facade(rows, False), self.facade(rows)
        for commodity, method, reserve, evidence, radius, belts in (
            ("Platinum", "LASER", "ALL RESERVES", "ALL EVIDENCE", 250, True),
            ("Osmium", "LASER", "PRISTINE", "ALL EVIDENCE", 250, False),
            ("Painite", "CORE", "PRISTINE + MAJOR", "RECHECK_RECOMMENDED", 500, True),
            ("ALL COMMODITIES", "LASER", "MAJOR", "ALL EVIDENCE", 250, True),
            ("Platinum", "LASER", "ALL RESERVES", "ALL EVIDENCE", 0, False),
        ):
            with patch("ed_companion.phase14.controller_navigation.mining_candidate_freshness",
                       side_effect=lambda row: {**row, "stale": False, "recheckRecommended": False}):
                args = (commodity, radius, evidence, reserve, method, "Origin", belts)
                self.assertEqual(old._mining_find_page(*args), new._mining_find_page(*args))

    def test_geometry_hit_reassesses_time_dependent_freshness(self):
        rows = [ring("Near", [1, 0, 0])]
        owner = self.facade(rows)
        validator = Mock(wraps=CockpitController._valid_star_position)
        owner._valid_star_position = validator
        args = ("Platinum", 250, "RECHECK_RECOMMENDED", "ALL RESERVES", "LASER", "Origin", True)
        for stale in (False, True):
            owner._mining_find_cache_key = None
            with patch("ed_companion.phase14.controller_navigation.mining_candidate_freshness",
                       return_value={**rows[0], "stale": stale, "recheckRecommended": stale}):
                self.assertEqual(len(owner._mining_find_page(*args)), int(stale))
        # Two origin validations, but only the first call walks the one source row.
        self.assertEqual(validator.call_count, 3)

    def test_profile_path_and_reset_replace_controller_geometry_scope(self):
        owner = CockpitController.__new__(CockpitController)
        owner.profile_context = Mock(key="alpha")
        owner._profile_generation = 1
        owner.mining_catalog_file = Path("first.json")
        owner._mining_catalog = {"candidates": [], "resetAt": ""}
        owner._state = {}
        owner._mining_rows = lambda: []
        owner._mining_plan_key = lambda args: ("scope", args)
        owner._start_network_worker = Mock(return_value=True)
        owner._mining_powerplay_index_context = lambda: "scope"
        for field, value in (("initial", ""), ("generation", 2),
                             ("profile", "beta"), ("path", "second.json"), ("reset", "new")):
            previous = getattr(owner, "_mining_geometry_cache", None)
            owner._active_mining_plan = None
            if field == "generation":
                owner._profile_generation = value
            elif field == "profile":
                owner.profile_context = Mock(key=value)
            elif field == "path":
                owner.mining_catalog_file = Path(value)
            elif field == "reset":
                owner._mining_catalog["resetAt"] = value
            owner._queue_mining_plan(())
            self.assertIsNot(owner._mining_geometry_cache, previous)


class MiningFactTests(unittest.TestCase):
    def test_fact_identity_matches_legacy_recursive_json_for_nested_values(self):
        ignored = {"learnedAt", "distanceLy", "ageSeconds", "stale",
                   "recheckRecommended", "confirmationStatus", "freshnessLimitSeconds"}
        def legacy(value):
            if isinstance(value, dict):
                return {key: legacy(field) for key, field in value.items() if key not in ignored}
            if isinstance(value, (list, tuple)):
                return [legacy(item) for item in value]
            return value
        row = {"source": "Ünicode", "learnedAt": "ignored", "observedAt": "kept",
               "facts": ({"stale": True, "observedAt": "nested-kept", "yield": 0.0,
                          "nested": [None, False, 0, "", {"distanceLy": 1, "fraction": 1.5}]},),
               "empty": [], "dict": {}}
        expected = hashlib.sha256(encoded(legacy(row)).encode()).hexdigest()
        self.assertEqual(mining_observation_key(row), expected)
        other = copy.deepcopy(row)
        other["observedAt"] = "new real observation"
        self.assertNotEqual(mining_observation_key(other), expected)

    def test_snapshot_leaf_shortcut_preserves_independent_nested_containers(self):
        value = {"metadata": [None, 0, False, {"Ä": [1, {"value": 3.5}]}],
                 "tuple": ("a", {"b": []}), "exclude": "derived"}
        before = copy.deepcopy(value)
        snapshot = catalog_record_snapshot(value, exclude={"exclude"})
        self.assertEqual(catalog_view_value(snapshot),
                         {key: json.loads(encoded(field)) for key, field in value.items() if key != "exclude"})
        snapshot["metadata"][3]["Ä"][1]["value"] = 8
        self.assertEqual(value, before)

    def test_cleanup_and_history_failure_keep_copy_on_write_contract(self):
        old = [ring("Old", [0, 0, 0], ageSeconds=100), ring("Untouched", [1, 0, 0])]
        new = [ring("New", [2, 0, 0], ageSeconds=200)]
        before = copy.deepcopy((old, new))
        result = prepare_mining_batch(old, new, transient_fields={"ageSeconds"}, snapshot_arrays=True)
        self.assertTrue(all("ageSeconds" not in row for row in result["candidates"]))
        self.assertIs(result["candidates"][1], old[1])
        archive = Mock()
        archive.archive.side_effect = OSError("failed")
        failed = prepare_mining_batch(old, new, archive=archive, snapshot_arrays=True)
        self.assertEqual(failed["archiveError"], "OSError")
        self.assertIsInstance(failed["candidates"][-1]["coordinates"], tuple)
        self.assertEqual((old, new), before)


if __name__ == "__main__":
    unittest.main()
