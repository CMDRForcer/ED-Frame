"""Contracts for server-backed rings, markets, explicit control and yields."""
from datetime import datetime, timedelta, timezone
import unittest
from pathlib import Path
from unittest.mock import Mock

from ed_companion.navigation.mining_finder import (
    fetch_edframe_mining_candidates, merge_mining_candidates,
)
from ed_companion.navigation.mining_market import fetch_market_imports
from ed_companion.navigation.mining_planner import _powerplay_index, _secondary_resources
from ed_companion.navigation.mining_powerplay import fetch_edframe_powerplay
from ed_companion.phase14.controller import CockpitController


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class MiningServerIntegrationTests(unittest.TestCase):
    def test_ring_and_powerplay_results_survive_market_failure_but_not_profile_switch(self):
        for stale in (False, True):
            controller = CockpitController.__new__(CockpitController)
            controller.profile_context = Mock(key="alpha")
            controller._profile_generation = 1
            controller.mining_market_cache_file = Path("market-test.json")
            controller._active_mining_market_request = {"id": "test"}
            controller._remember_mining_origin = Mock(return_value=False)
            controller.miningChanged = Mock()
            controller._launch_pending_mining_market_refresh = Mock()
            ring = {"system": "Cubeo", "ring": "Cubeo A Ring"}
            fact = {"system": "Cubeo", "power": "Aisling Duval"}
            controller._finish_mining_market_sync({
                "id": "test", "profileKey": "other" if stale else "alpha",
                "generation": 1, "path": "market-test.json",
                "success": False, "error": "Market service unavailable",
                "serverCandidates": [ring], "serverPowerplay": [fact],
            })
            self.assertEqual(getattr(controller, "_pending_mining_candidates", []),
                             [] if stale else [ring])
            self.assertEqual(getattr(controller, "_pending_mining_powerplay_observations", []),
                             [] if stale else [fact])

    def test_regional_ring_query_uses_radius_not_exact_system(self):
        calls = []
        def get(url, **kwargs):
            calls.append(kwargs)
            return Response({"results": []})
        self.assertEqual(fetch_edframe_mining_candidates(
            "Cubeo", get, commodity="Platinum", origin=[1, 2, 3],
            max_distance=100,
        ), [])
        self.assertEqual(calls[0]["params"], {
            "x": 1.0, "y": 2.0, "z": 3.0, "max_distance": 100.0,
            "max_age_days": 3650, "commodity": "platinum", "limit": 200,
        })

    def test_regional_ring_query_rejects_missing_position(self):
        with self.assertRaises(ValueError):
            fetch_edframe_mining_candidates("Cubeo", None, max_distance=100)

    def test_market_reuses_origin_and_exact_age_without_coordinate_request(self):
        calls = []
        def get(url, **kwargs):
            calls.append((url, kwargs))
            return Response({"results": []} if url.endswith("/search") else [])
        fetch_market_imports("Cubeo", "Platinum", max_distance=100,
            max_days_ago=1, max_age_hours=1,
            origin={"coordinates": [1, 2, 3]}, get=get)
        self.assertFalse(any("systems/suggest" in url for url, _ in calls))
        self.assertEqual(calls[0][1]["params"]["max_age_hours"], 1)
        self.assertEqual(calls[0][1]["params"]["limit"], 200)

    def test_overlapping_community_snapshots_are_not_added(self):
        base = {"system": "Test", "ring": "Test A Ring",
                "yieldAggregationScope": "COMMUNITY", "evidence": "LIVE_REPORTED"}
        old = {**base, "learnedAt": "2026-10-06T10:00:00Z",
            "prospectorSampleCount": 2, "yieldStats": [{
                "commodity": "platinum", "prospectorHits": 2,
                "proportionSamples": 2, "proportionTotal": 40,
            }]}
        new = {**base, "learnedAt": "2026-10-07T10:00:00Z",
            "prospectorSampleCount": 3, "yieldStats": [{
                "commodity": "platinum", "prospectorHits": 3,
                "proportionSamples": 3, "proportionTotal": 90,
            }]}
        for rows in ([old, new], [new, old], [new, new]):
            merged = merge_mining_candidates(rows)[0]
            self.assertEqual(merged["prospectorSampleCount"], 3)
            self.assertEqual(merged["yieldStats"][0]["proportionSamples"], 3)
            self.assertEqual(merged["yieldStats"][0]["averageProportion"], 30)

    def test_secondary_measurements_identify_community_not_local(self):
        rows = _secondary_resources({"yieldAggregationScope": "COMMUNITY",
            "yieldStats": [{"commodity": "osmium", "prospectorHits": 2,
                            "averageProportion": 20}]}, "platinum", {}, [])
        self.assertEqual(rows[0]["evidenceLabel"], "COMMUNITY YIELD")
        self.assertFalse(rows[0]["localYield"])
        self.assertTrue(rows[0]["communityYield"])

    def test_server_cannot_assert_control_without_controller_or_fresh_timestamp(self):
        now = datetime.now(timezone.utc)
        base = {"system": "Cubeo", "power": "Aisling Duval",
                "powerState": "Stronghold", "powerRelationship": "CONTROL",
                "observedAt": now.isoformat(), "commander": "PRIVATE"}
        def get(url, **kwargs):
            return Response({"results": [base, {**base,
                "system": "Stale", "observedAt": (now - timedelta(days=2)).isoformat()}]})
        rows = fetch_edframe_powerplay(origin=[1, 2, 3], max_distance=100, get=get)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["controlKnown"])
        self.assertEqual(rows[0]["powerRelationship"], "PRESENCE")
        self.assertNotIn("commander", rows[0])

    def test_newest_controller_wins_independently_of_list_order(self):
        old = {"system": "Cubeo", "power": "Aisling Duval",
               "controllingPower": "Aisling Duval", "observedAt": "2026-10-06T10:00:00Z"}
        new = {**old, "power": "Zachary Hudson", "controllingPower": "Zachary Hudson",
               "observedAt": "2026-10-07T10:00:00Z"}
        for rows in ([old, new], [new, old]):
            facts = _powerplay_index(rows)
            self.assertEqual(facts["bySystem"]["cubeo"]["controllingPower"], "Zachary Hudson")


if __name__ == "__main__":
    unittest.main()
