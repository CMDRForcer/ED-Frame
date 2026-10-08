"""Complete, targeted Powerplay reads without duplicate ring retrievals."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

from ed_companion.navigation.mining_powerplay import (
    fetch_edframe_powerplay, fetch_powerplay_targets, missing_powerplay_targets,
)
from ed_companion.phase14.controller import CockpitController
from ed_companion.navigation.mining_planner import (
    _powerplay_index, _candidate_power_fact, _market_power_fact, _merit_status,
)


NOW = datetime.now(timezone.utc)


def fact(system, **fields):
    return {"system": system, "power": "Aisling Duval", "powerState": "Stronghold",
            "controllingPower": "Aisling Duval", "coordinates": [1, 2, 3],
            "observedAt": NOW.isoformat(), **fields}


def response(**payload):
    return Mock(json=Mock(return_value=payload))


def route(system="Mine", sale="Sale", **fields):
    return {"system": system, "systemAddress": 42, "ring": system + " A Ring",
            "coordinates": [1, 2, 3], "sellSystem": sale, "sellCoordinates": [4, 5, 6],
            "optimization": "POWERPLAY MERITS", "powerplayStatus": "POWERPLAY_DATA_MISSING",
            **fields}


class PowerplayLookupTests(unittest.TestCase):
    def test_regional_lookup_follows_pages_and_deduplicates_overlapping_facts(self):
        get = Mock(side_effect=[
            response(results=[fact("One")], hasMore=True, nextCursor="next"),
            response(results=[fact("One"), fact("Two")], hasMore=False),
        ])
        coverage = {}
        rows = fetch_edframe_powerplay(origin=[1, 2, 3], max_distance=500, get=get,
                                       diagnostics=coverage)
        self.assertEqual({row["system"] for row in rows}, {"One", "Two"})
        self.assertNotIn("cursor", get.call_args_list[0].kwargs["params"])
        self.assertEqual(get.call_args_list[1].kwargs["params"]["cursor"], "next")
        self.assertEqual(coverage, {"bounded": False, "pages": 2, "complete": True})

    def test_legacy_or_repeating_cursor_is_explicitly_incomplete_not_a_loop(self):
        for cursor in (None, "same"):
            get = Mock(return_value=response(results=[fact("One")], hasMore=True, nextCursor=cursor))
            coverage = {}
            rows = fetch_edframe_powerplay(origin=[1, 2, 3], max_distance=500, get=get,
                                           diagnostics=coverage)
            self.assertEqual(len(rows), 1)
            self.assertTrue(coverage["bounded"])
            self.assertEqual(get.call_count, 1 if cursor is None else 2)

    def test_continuation_failure_retains_first_page_without_claiming_full_coverage(self):
        get = Mock(side_effect=[response(results=[fact("One")], hasMore=True, nextCursor="next"),
                                TimeoutError("offline")])
        coverage = {}
        rows = fetch_edframe_powerplay(origin=[1, 2, 3], max_distance=500, get=get,
                                       diagnostics=coverage)
        self.assertEqual(rows[0]["system"], "One")
        self.assertTrue(coverage["bounded"])
        self.assertEqual(coverage["partialError"], "TimeoutError")

    def test_all_hundred_routes_include_deduplicated_mine_and_sale_systems(self):
        targets = missing_powerplay_targets([route(f"Mine {i}", "Shared sale") for i in range(100)])
        self.assertEqual(len(targets), 101)
        self.assertIn("Mine 99", {target["system"] for target in targets})
        self.assertEqual(sum(target["system"] == "Shared sale" for target in targets), 1)

    def test_recent_control_and_unoccupied_facts_avoid_network_but_presence_does_not(self):
        known = [fact("Mine"), fact("Sale", controllingPower="", powerState="Unoccupied")]
        self.assertEqual(missing_powerplay_targets([route()], known, now=NOW), [])
        presence = [fact("Mine", controllingPower="", controlKnown=False)]
        self.assertEqual(len(missing_powerplay_targets([route()], presence, now=NOW)), 2)
        stale = [fact("Mine", observedAt=(NOW - timedelta(days=2)).isoformat())]
        self.assertEqual(len(missing_powerplay_targets([route()], stale, now=NOW)), 2)
        self.assertEqual(missing_powerplay_targets([route()], now=NOW, retry_after={
            "mine": NOW.timestamp() + 600, "sale": NOW.timestamp() + 600,
        }), [])

    def test_known_ring_does_not_mask_unknown_powerplay_or_missing_coordinates(self):
        no_coordinates = route(coordinates=[], sellCoordinates=[])
        facts = [fact("Mine", coordinates=[]), fact("Sale", coordinates=[])]
        self.assertEqual(len(missing_powerplay_targets([no_coordinates], facts, now=NOW)), 2)
        self.assertEqual(missing_powerplay_targets([route(powerplayStatus="POWERPLAY_VERIFIED")]), [])
        self.assertEqual(missing_powerplay_targets([route(powerplayStatus="NOT_ELIGIBLE")]), [])
        self.assertEqual(missing_powerplay_targets([route(optimization="BEST YIELD")]), [])
        self.assertEqual(missing_powerplay_targets([route(selectedPower="UNCONFIRMED")]), [])

    def test_exact_batch_ignores_unrequested_facts_and_sends_only_unique_system_names(self):
        targets = missing_powerplay_targets([route(), route()])
        get = Mock(return_value=response(results=[fact("Mine"), fact("Sale"), fact("Other")],
                                         hasMore=False, selection="systems"))
        result = fetch_powerplay_targets(targets, origin=[1, 2, 3], get=get)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs["params"]["system"], ["mine", "sale"])
        self.assertEqual({row["system"] for row in result["rows"]}, {"Mine", "Sale"})
        self.assertEqual(result["checked"], ["Mine", "Sale"])
        self.assertEqual(result["failed"], [])

    def test_legacy_server_uses_small_spatial_queries_never_ring_downloads(self):
        targets = missing_powerplay_targets([route()])
        get = Mock(side_effect=[response(results=[], hasMore=False),
                                response(results=[fact("Mine"), fact("Other")], hasMore=False),
                                response(results=[fact("Sale")], hasMore=False)])
        coverage = {}
        result = fetch_powerplay_targets(targets, origin=[1, 2, 3], get=get, diagnostics=coverage)
        self.assertTrue(coverage["legacy"])
        self.assertEqual(get.call_count, 3)
        for call in get.call_args_list[1:]:
            self.assertTrue(call.args[0].endswith("/mining/powerplay"))
            self.assertEqual(call.kwargs["params"]["max_distance"], 1)
            self.assertNotIn("system", call.kwargs["params"])
        self.assertEqual(len(result["rows"]), 2)

    def test_empty_exact_response_is_negative_evidence_not_verified_eligibility(self):
        get = Mock(return_value=response(results=[], hasMore=False, selection="systems"))
        result = fetch_powerplay_targets(missing_powerplay_targets([route()]), origin=[], get=get)
        self.assertEqual(result, {"rows": [], "checked": ["Mine", "Sale"], "failed": []})

    def controller(self):
        c = CockpitController.__new__(CockpitController)
        c.profile_context = Mock(key="alpha")
        c._profile_generation = 2
        c.mining_catalog_file = Path("catalog.json")
        c.mining_powerplay_observations_file = Path("powerplay.json")
        c._known_mining_origin = Mock(return_value={"coordinates": [1, 2, 3]})
        c._start_network_worker = Mock(return_value=True)
        c._save_mining_json = Mock()
        c._mining_market_revision = 0
        c.miningChanged = Mock()
        c.stateChanged = Mock()
        c.miningVerificationChanged = Mock()
        c.miningVerificationProgress = Mock()
        c.miningVerificationFinished = Mock()
        return c

    def test_powerplay_worker_checks_all_routes_without_ring_requests_and_publishes_facts(self):
        c = self.controller()
        c.verifyMiningRoutes([route(f"Mine {i}", "Sale") for i in range(100)], "Origin")
        self.assertEqual(len(c._active_mining_verification_request["powerplayLookupTargets"]), 101)
        worker = c._start_network_worker.call_args.args[0]
        with patch("ed_companion.phase14.controller_navigation.fetch_powerplay_targets", return_value={
            "rows": [fact("Mine 99"), fact("Sale")], "checked": ["Mine 99", "Sale"], "failed": [],
        }) as fetch, patch("ed_companion.phase14.controller_navigation.fetch_edframe_mining_candidates") as rings:
            worker()
        fetch.assert_called_once()
        rings.assert_not_called()
        c._finish_mining_verification(c.miningVerificationFinished.emit.call_args.args[0])
        self.assertEqual(len(c._mining_powerplay_observations), 2)
        self.assertIn("mine 99", c._mining_powerplay_lookup_cache)
        c._save_mining_json.assert_called_once()

    def test_profile_changed_completion_cannot_pollute_facts_or_retry_cache(self):
        c = self.controller()
        c._active_mining_verification_request = {"id": "old"}
        c._mining_powerplay_lookup_cache = {}
        c._finish_mining_verification({
            "id": "old", "profileKey": "beta", "generation": 1, "path": "catalog.json",
            "powerplayLookup": {"rows": [fact("Mine")], "checked": ["Mine"], "failed": []},
        })
        self.assertEqual(c._mining_powerplay_lookup_cache, {})
        self.assertEqual(getattr(c, "_mining_powerplay_observations", []), [])
        c._save_mining_json.assert_not_called()

    def test_unchanged_powerplay_facts_do_not_schedule_repeated_saves_or_replans(self):
        c = self.controller()
        self.assertTrue(c._publish_mining_powerplay([fact("Mine")]))
        revision = c._mining_market_revision
        self.assertFalse(c._publish_mining_powerplay([fact("Mine")]))
        self.assertEqual(c._mining_market_revision, revision)
        c._save_mining_json.assert_called_once()

    def test_publication_and_targeted_lookup_preserve_regions_larger_than_twenty_thousand(self):
        c = self.controller()
        region = [fact(f"System {i}") for i in range(20_000)]
        region.append(fact("Older target", observedAt=(NOW - timedelta(hours=1)).isoformat()))
        self.assertTrue(c._publish_mining_powerplay(region))
        self.assertEqual(len(c._mining_powerplay_observations), 20_001)
        self.assertTrue(c._publish_mining_powerplay([fact("New targeted system")]))
        self.assertEqual(len(c._mining_powerplay_observations), 20_002)
        self.assertIn("Older target", {row["system"] for row in c._mining_powerplay_observations})
        self.assertEqual(missing_powerplay_targets(
            [route("Older target", "New targeted system")], c._mining_powerplay_observations, now=NOW,
        ), [])

    def test_relay_preserves_complete_region_and_unchanged_facts_do_not_replan(self):
        c = self.controller()
        c._mining_powerplay_observations = [fact(f"System {i}") for i in range(20_001)]
        c._pending_mining_powerplay_observations = [fact("Relay system")]
        c._pending_bgs_snapshots = []
        c._pending_hge_observations = []
        c._pending_mining_candidates = []
        c._hge_sightings = []
        c._next_hge_expiry_epoch = NOW.timestamp() + 3600
        c.connectionChanged = Mock()
        c.flushHgeObservationBatch(True)
        self.assertEqual(len(c._mining_powerplay_observations), 20_002)
        c._save_mining_json.assert_called_once()
        c.miningChanged.emit.assert_called_once()
        revision = c._mining_market_revision
        c._pending_mining_powerplay_observations = [fact("Relay system")]
        c.flushHgeObservationBatch(True)
        self.assertEqual(c._mining_market_revision, revision)
        c._save_mining_json.assert_called_once()
        c.miningChanged.emit.assert_called_once()

    def test_new_live_control_wins_over_older_ring_and_market_metadata(self):
        index = _powerplay_index([fact("Mine", controllingPower="Yuri Grom")])
        old = fact("Mine", observedAt=(NOW - timedelta(days=1)).isoformat())
        for join in (_candidate_power_fact, _market_power_fact):
            self.assertEqual(join(old, "Aisling Duval", index)["controllingPower"], "Yuri Grom")

    def test_explicit_new_unoccupied_target_clears_old_control_without_inventing_control(self):
        old_target = fact("Sale", observedAt=(NOW - timedelta(hours=1)).isoformat())
        fresh_target = fact("Sale", controllingPower="", powerState="Unoccupied")
        index = _powerplay_index([old_target, fact("Mine"), fresh_target])
        target = _market_power_fact(old_target, "Aisling Duval", index)
        self.assertEqual(target["controllingPower"], "")
        self.assertFalse(target["controlKnown"])
        status, score, _distance = _merit_status(
            {"system": "Mine"}, {"system": "Sale"}, "Aisling Duval", "ACQUIRE", "ANY", index,
        )
        self.assertIn("CONFIRMED", status)
        self.assertGreater(score, 0)

    def test_missing_observations_get_a_short_negative_cache_never_a_verified_label(self):
        c = self.controller()
        c.verifyMiningRoutes([route()], "Origin")
        request = dict(c._active_mining_verification_request)
        c._finish_mining_verification({**request, "powerplayLookup": {
            "rows": [], "checked": ["Mine", "Sale"], "failed": [],
        }})
        self.assertIn("2 systems without recent Powerplay evidence", c._mining_verification_status)
        self.assertNotIn("verified", c._mining_verification_status)
        self.assertGreater(c._mining_powerplay_lookup_cache["mine"], NOW.timestamp())
        c._start_network_worker.reset_mock()
        c.verifyMiningRoutes([route()], "Origin")
        c._start_network_worker.assert_not_called()
        self.assertIn("remain unknown", c._mining_verification_status)

    def test_successful_region_publishes_powerplay_before_markets_and_waits_for_ring_merge(self):
        c = self.controller()
        c.mining_market_cache_file = Path("market.json")
        c._active_mining_market_request = {"id": "region"}
        c._launch_pending_mining_market_refresh = Mock(return_value=False)
        c._schedule_mining_market_backup = Mock()
        def dispatch(_rows, **kwargs):
            self.assertTrue(kwargs["search_refresh"])
            c._active_mining_observation_batch = {"searchRefresh": True}
            return True
        c._dispatch_mining_observation_batch = Mock(side_effect=dispatch)
        def published():
            self.assertEqual(c._mining_powerplay_observations[0]["system"], "Mine")
        c.miningChanged.emit.side_effect = published
        c._finish_mining_market_sync({
            "id": "region", "profileKey": "alpha", "generation": 2,
            "path": "market.json", "success": True,
            "serverPowerplay": [fact("Mine")], "serverCandidates": [route()],
            "markets": [{"system": "Sale", "station": "Market"}],
        })
        self.assertTrue(c.miningMarketSyncBusy)
        self.assertEqual(c._mining_market_cache["markets"][0]["station"], "Market")
        self.assertEqual(getattr(c, "_pending_mining_powerplay_observations", []), [])
        c.miningChanged.emit.assert_called_once()
        c.stateChanged.emit.assert_not_called()  # No unrelated page rebuild for market facts.

    def test_worker_prepared_powerplay_is_fenced_and_rebased_before_publication(self):
        from ed_companion.navigation.catalog_json import catalog_view_value
        c = self.controller()
        c._network_threads_lock = threading.Lock()
        c._mining_powerplay_observations = [fact("Old")]
        incoming = [fact("Mine")]
        result = {}
        signal = Mock()
        self.assertTrue(c._defer_mining_powerplay_publication(result, incoming, signal))
        worker = c._start_network_worker.call_args.args[0]
        worker()
        self.assertFalse(c._save_mining_json.called)
        self.assertEqual([row["system"] for row in c._mining_powerplay_observations], ["Old"])
        # A relay published another fact while the first worker was running.
        c._mining_powerplay_observations = [fact("Old"), fact("Relay")]
        self.assertTrue(c._defer_mining_powerplay_publication(result, incoming, signal))
        c._start_network_worker.call_args.args[0]()
        self.assertFalse(c._defer_mining_powerplay_publication(result, incoming, signal))
        with patch("ed_companion.phase14.controller_navigation.merge_powerplay_observations",
                   side_effect=AssertionError("merge on UI")):
            self.assertTrue(c._publish_mining_powerplay(incoming, result["preparedPowerplay"]))
        self.assertEqual({row["system"] for row in c._mining_powerplay_observations},
                         {"Old", "Relay", "Mine"})
        self.assertEqual(catalog_view_value(c._mining_powerplay_observations[2])["coordinates"], [1, 2, 3])
        repeated = {}
        c._prepare_mining_powerplay_publication(repeated, incoming)
        self.assertFalse(c._publish_mining_powerplay(incoming, repeated["preparedPowerplay"]))

    def test_stale_market_completion_never_dispatches_powerplay_preparation(self):
        c = self.controller()
        c._network_threads_lock = threading.Lock()
        c.mining_market_cache_file = Path("market.json")
        c._active_mining_market_request = {"id": "old"}
        c._mining_market_busy = True
        c._finish_mining_market_sync({"id": "old", "profileKey": "old-profile",
            "generation": 1, "path": "market.json", "serverPowerplay": [fact("Mine")]})
        c._start_network_worker.assert_not_called()
        c._save_mining_json.assert_not_called()
        self.assertFalse(c._mining_market_busy)

    def test_market_completion_stays_busy_until_worker_facts_publish_before_markets(self):
        c = self.controller()
        c._network_threads_lock = threading.Lock()
        c._mining_powerplay_observations = []
        c.mining_market_cache_file = Path("market.json")
        c.miningMarketFinished = Mock()
        c._mining_market_busy = True
        c._active_mining_market_request = {"id": "region"}
        c._launch_pending_mining_market_refresh = Mock(return_value=False)
        c._mining_market_cache = {"markets": [{"station": "Old"}]}
        result = {"id": "region", "profileKey": "alpha", "generation": 2,
                  "path": "market.json", "success": True, "serverPowerplay": [fact("Mine")],
                  "markets": [{"system": "Sale", "station": "New"}]}
        c._finish_mining_market_sync(result)
        self.assertTrue(c._mining_market_busy)
        self.assertEqual(c._mining_market_cache["markets"][0]["station"], "Old")
        c.miningChanged.emit.assert_not_called()
        c._start_network_worker.call_args.args[0]()
        c.miningMarketFinished.emit.assert_called_once_with(result)
        def notified():
            self.assertEqual(c._mining_powerplay_observations[0]["system"], "Mine")
        c.miningChanged.emit.side_effect = notified
        with patch("ed_companion.phase14.controller_navigation.merge_powerplay_observations",
                   side_effect=AssertionError("merge on UI")):
            c._finish_mining_market_sync(result)
        self.assertFalse(c._mining_market_busy)
        self.assertEqual(c._mining_market_cache["markets"][0]["station"], "New")
        c.stateChanged.emit.assert_not_called()

    def test_profile_switch_during_verification_merge_discards_worker_result(self):
        c = self.controller()
        c._network_threads_lock = threading.Lock()
        c._mining_powerplay_observations = []
        c._active_mining_verification_request = {"id": "verify"}
        c._mining_verification_busy = True
        result = {"id": "verify", "profileKey": "alpha", "generation": 2,
                  "path": "catalog.json", "powerplayLookup": {"rows": [fact("Mine")]}}
        c._finish_mining_verification(result)
        self.assertTrue(c._mining_verification_busy)
        self.assertIsNotNone(c._active_mining_verification_request)
        c._start_network_worker.call_args.args[0]()
        c._profile_generation += 1
        c._finish_mining_verification(result)
        self.assertFalse(c._mining_verification_busy)
        self.assertEqual(c._mining_powerplay_observations, [])
        c._save_mining_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
