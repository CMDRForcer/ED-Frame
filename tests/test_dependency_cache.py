"""Domain cache reuse must not hide relevant changes or clock expiry."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from ed_companion.phase14.controller import CockpitController
from ed_companion.phase14.dependency_cache import (
    dependency_revision, invalidate_state_cache, mining_candidates_signature,
)


class DependencyCacheTests(unittest.TestCase):
    def controller(self):
        c = CockpitController.__new__(CockpitController)
        c._state = {
            "system": "Origin", "currentPosition": [0, 0, 0],
            "localMiningEvidence": {"candidates": [{
                "system": "Origin", "ring": "Origin A Ring", "hotspots": [],
                "evidence": "CATALOG_CANDIDATE",
            }]},
            "fleet": [{"id": "1", "type": "Adder", "isCurrent": True}],
        }
        c.profile_context = Mock(key="alpha")
        c._profile_generation = 1
        c._state_revision = 1
        c._mining_catalog = {"candidates": [], "resetAt": ""}
        c._mining_market_revision = 1
        c._mining_catalog_revision = 1
        c._derived_cache = {}
        c._fleet_images = {}
        c.fleet_images_dir = Path("unused-images")
        c._ship_catalog = [{"name": "Adder", "symbol": "Adder"}]
        for name in ("stateChanged", "materialsChanged", "fleetChanged", "wishlistChanged",
                     "exobiologyChanged", "operationsChanged", "hgeChanged", "journalHealthChanged",
                     "logbookChanged", "miningChanged", "miningRowsReady"):
            setattr(c, name, Mock())
        return c

    def test_dependency_snapshot_detects_nested_inplace_and_same_sized_changes(self):
        c = self.controller()
        values = [{"a": [1]}]
        first = dependency_revision(c, "demo", values)
        self.assertEqual(dependency_revision(c, "demo", deepcopy(values)), first)
        values[0]["a"][0] = 2
        second = dependency_revision(c, "demo", values)
        self.assertGreater(second, first)
        values[0]["a"][0] = 1
        self.assertGreater(dependency_revision(c, "demo", values), second)

    def test_unrelated_replaced_state_reuses_ring_projection_and_ui_revision(self):
        c = self.controller()
        c._build_mining_rows = Mock(return_value=[{"ring": "prepared"}])
        with patch("ed_companion.phase14.controller_navigation.time.time", return_value=3601):
            first = c._mining_rows()
            revision = c._mining_ui_revision()
            previous = c._state
            c._state = deepcopy(previous)
            c._state["commanderOverview"] = {"credits": {"value": 999}}
            c._state["materials"] = [{"have": 42}]
            c._publish_full_state(previous)
            self.assertIs(c._mining_rows(), first)
            self.assertEqual(c._mining_ui_revision(), revision)
        c._build_mining_rows.assert_called_once()

    def test_local_rows_updates_even_without_a_count_change_rebuild(self):
        c = self.controller()
        first = c._mining_rows_identity(c._state, c._mining_catalog)
        c._state["localMiningEvidence"]["candidates"][0]["hotspots"] = [{"commodity": "platinum"}]
        self.assertNotEqual(c._mining_rows_identity(c._state, c._mining_catalog), first)

    def test_worker_signature_is_stable_for_equal_rows_but_changes_for_yield(self):
        rows = [{"system": "Origin", "yieldStats": [{"averageProportion": 25}]}]
        first = mining_candidates_signature(rows)
        self.assertEqual(mining_candidates_signature([dict(reversed(list(rows[0].items())))]), first)
        rows[0]["yieldStats"][0]["averageProportion"] = 30
        self.assertNotEqual(mining_candidates_signature(rows), first)

    def test_signed_worker_snapshot_does_not_copy_local_or_regional_rows_on_ui(self):
        class NoCopyRows(list):
            def __deepcopy__(self, memo):
                raise AssertionError("Large rows copied from UI getter")
        c = self.controller()
        c._state["localMiningEvidence"]["candidates"] = NoCopyRows([{"ring": "A"}])
        c._state["_miningCandidatesSignature"] = "worker-produced-content-digest"
        c._mining_catalog["candidates"] = NoCopyRows([{"ring": "B"}])
        first = c._mining_rows_identity(c._state, c._mining_catalog)
        self.assertEqual(c._mining_rows_identity(c._state, c._mining_catalog), first)
        c._state["_miningCandidatesSignature"] = "new-worker-digest"
        self.assertNotEqual(c._mining_rows_identity(c._state, c._mining_catalog), first)

    def test_position_system_catalog_reset_profile_generation_still_invalidate(self):
        for change in ("position", "system", "catalog", "reset", "profile", "generation"):
            c = self.controller()
            first = c._mining_rows_identity(c._state, c._mining_catalog)
            if change == "position":
                c._state["currentPosition"][0] = 100
            elif change == "system":
                c._state["system"] = "Elsewhere"
            elif change == "catalog":
                c._mining_catalog_revision += 1
            elif change == "reset":
                c._mining_catalog["resetAt"] = "new-reset"
            elif change == "profile":
                c.profile_context.key = "beta"
            else:
                c._profile_generation += 1
            self.assertNotEqual(c._mining_rows_identity(c._state, c._mining_catalog), first, change)

    def test_market_powerplay_verification_ship_loadout_and_commodities_update_ui_only(self):
        for change in ("market", "verification", "loadout", "ship", "cargo", "vehicle", "power", "commodity"):
            c = self.controller()
            c._state["moduleSlots"] = [{"moduleId": "old"}]
            with patch("ed_companion.phase14.controller_navigation.time.time", return_value=3601):
                rows_key = c._mining_rows_identity(c._state, c._mining_catalog)
                first = c._mining_ui_revision()
                if change == "market":
                    c._mining_market_revision += 1
                elif change == "verification":
                    c._mining_market_verification_states = {"Port": {"state": "ERROR"}}
                elif change == "loadout":
                    c._state["moduleSlots"][0]["moduleId"] = "mining-refinery"
                elif change == "ship":
                    c._state["selectedShipId"] = "new-ship"
                elif change == "cargo":
                    c._state["selectedShipStats"] = {"cargoCapacity": 512}
                elif change == "vehicle":
                    c._state["vehicleState"] = {"vehicles": [{"type": "rhino"}]}
                elif change == "power":
                    c._state["powerplayOverview"] = {"power": "Aisling Duval"}
                else:
                    c._state["localMiningEvidence"]["refinedCommodities"] = [{"id": "platinum"}]
                self.assertGreater(c._mining_ui_revision(), first, change)
                self.assertEqual(c._mining_rows_identity(c._state, c._mining_catalog), rows_key, change)

    def test_hourly_ring_refresh_and_minute_ui_freshness_advance_without_journal_events(self):
        c = self.controller()
        with patch("ed_companion.phase14.controller_navigation.time.time", return_value=3601):
            rows_key = c._mining_rows_identity(c._state, c._mining_catalog)
            first = c._mining_ui_revision()
        with patch("ed_companion.phase14.controller_navigation.time.time", return_value=3661):
            self.assertEqual(c._mining_rows_identity(c._state, c._mining_catalog), rows_key)
            self.assertGreater(c._mining_ui_revision(), first)
        with patch("ed_companion.phase14.controller_navigation.time.time", return_value=7201):
            self.assertNotEqual(c._mining_rows_identity(c._state, c._mining_catalog), rows_key)

    def test_fleet_cache_survives_credit_and_location_polls_but_other_caches_clear(self):
        c = self.controller()
        first = c._commander_fleet()
        c._derived_cache["commander_finance_history"] = ("old-revision", [])
        c._derived_cache[("hge_targets", 1)] = []
        c._state = {**deepcopy(c._state), "currentPosition": [100, 0, 0]}
        c._state_revision += 1
        invalidate_state_cache(c)
        self.assertIs(c._commander_fleet(), first)
        self.assertEqual(set(c._derived_cache), {"commander_fleet"})

    def test_fleet_data_images_catalog_directory_and_profile_all_invalidate(self):
        for change in ("fleet", "mapping", "catalog", "directory", "profile"):
            c = self.controller()
            first = c._commander_fleet()
            if change == "fleet":
                c._state["fleet"][0]["name"] = "Renamed"
            elif change == "mapping":
                c._fleet_images["1"] = "missing.png"
            elif change == "catalog":
                c._ship_catalog[0]["name"] = "Updated Adder"
            elif change == "directory":
                c.fleet_images_dir = Path("other-unused-images")
            else:
                c._profile_generation += 1
            self.assertIsNot(c._commander_fleet(), first, change)

    def test_image_appearing_or_disappearing_is_not_hidden_by_fleet_cache(self):
        c = self.controller()
        with TemporaryDirectory() as directory:
            c.fleet_images_dir = Path(directory)
            c._fleet_images["1"] = "image.png"
            first = c._commander_fleet()
            path = c.fleet_images_dir / "image.png"
            path.write_bytes(b"test-placeholder")
            second = c._commander_fleet()
            self.assertIsNot(first, second)
            self.assertTrue(second[0]["customImageSource"])
            path.unlink()
            self.assertFalse(c._commander_fleet()[0]["customImageSource"])

    def test_fleet_notifications_skip_unrelated_but_keep_inplace_and_initial_updates(self):
        c = self.controller()
        previous = deepcopy(c._state)
        c._publish_full_state(previous)
        c.fleetChanged.emit.assert_not_called()
        c._state = {**deepcopy(c._state), "commanderOverview": {"credits": 42}}
        c._publish_full_state(previous)
        c.fleetChanged.emit.assert_not_called()
        c._state["fleet"][0]["name"] = "Updated"
        c._publish_full_state(previous)
        c.fleetChanged.emit.assert_called_once()
        c.fleetChanged.reset_mock()
        c._publish_full_state()
        c.fleetChanged.emit.assert_not_called()
        c._state["fleet"][0]["name"] = "In-place update without previous state"
        c._publish_full_state()
        c.fleetChanged.emit.assert_called_once()

    def test_unrelated_state_during_worker_build_does_not_discard_valid_projection(self):
        c = self.controller()
        c._network_threads_lock = object()
        c._mining_rows_cache_key = None
        c._mining_rows_cache = []
        c._mining_rows_build_token = 0
        c._mining_rows_build_in_flight = False
        c._mining_rows_build_dirty = False
        c._start_network_worker = Mock(return_value=True)
        c._build_mining_rows = Mock(return_value=[{"ring": "valid-worker-result"}])
        initial_ui_revision = c._mining_ui_revision()
        self.assertTrue(c._queue_mining_rows_build())
        c._state = {**deepcopy(c._state), "commanderOverview": {"credits": 42}}
        c._start_network_worker.call_args.args[0]()
        c._finish_mining_rows_build(c.miningRowsReady.emit.call_args.args[0])
        self.assertEqual(c._mining_rows_cache[0]["ring"], "valid-worker-result")
        self.assertEqual(c._start_network_worker.call_count, 1)
        self.assertGreater(c._mining_ui_revision(), initial_ui_revision)

    def test_minute_freshness_rechecks_filter_without_rebuilding_all_ring_rows(self):
        c = self.controller()
        c._build_mining_rows = Mock(return_value=[{
            "system": "Origin", "ring": "Origin A Ring", "distanceLy": 0,
            "ringType": "Metallic", "evidence": "CATALOG_CANDIDATE",
            "hotspots": [{"commodity": "platinum", "count": 1}],
        }])
        with patch("ed_companion.phase14.controller_navigation.time.time", return_value=3601):
            first = c.miningFindPageForMethod("Platinum", 100, "ALL EVIDENCE", "ALL RESERVES", "LASER")
            self.assertIs(c.miningFindPageForMethod("Platinum", 100, "ALL EVIDENCE", "ALL RESERVES", "LASER"), first)
        with patch("ed_companion.phase14.controller_navigation.time.time", return_value=3661):
            second = c.miningFindPageForMethod("Platinum", 100, "ALL EVIDENCE", "ALL RESERVES", "LASER")
            self.assertIsNot(second, first)
            self.assertEqual(len(second), len(first))
        c._build_mining_rows.assert_called_once()


if __name__ == "__main__":
    unittest.main()
