"""Short-lived regional reuse must not cache partial or stale evidence."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

from ed_companion.navigation.mining_region_cache import MiningRegionCache
from ed_companion.navigation.mining_refresh import fetch_mining_refresh
from ed_companion.navigation.mining_finder import EDFRAME_CATALOG_SITES_URL
from ed_companion.navigation.mining_powerplay import EDFRAME_POWERPLAY_URL
from tests import test_mining_refresh as refresh_tests
from tests.test_mining_refresh import ORIGIN, QUERY, MODULE


NOW = datetime.now(timezone.utc)
COMPLETE = {"complete": True, "bounded": False, "pages": 1}


class MiningRegionCacheTests(unittest.TestCase):
    def setUp(self):
        self.clock = Mock(return_value=1000.0)
        self.cache = MiningRegionCache(clock=self.clock, wall_clock=lambda: NOW.timestamp())
        self.sites = [{"system": "Mine", "ring": "Mine A Ring", "observedAt": NOW.isoformat(),
                       "learnedAt": NOW.isoformat(), "hotspots": [{"type": "Platinum", "count": 1}]}]
        self.powers = [{"system": "Mine", "power": "Aisling Duval", "powerState": "Stronghold",
                        "observedAt": NOW.isoformat(), "controllingPower": "Aisling Duval"}]

    def put(self, kind="sites", **changes):
        return self.cache.put(kind, QUERY, ORIGIN, changes.pop("rows", self.sites),
                              changes.pop("coverage", COMPLETE), started_at=1000.0, **changes)

    def test_reuse_is_isolated_and_does_not_renew_ttl_or_observation_times(self):
        self.assertTrue(self.put())
        self.clock.return_value = 1010.0
        rows, coverage = self.cache.get("sites", QUERY, ORIGIN)
        self.assertEqual(rows, self.sites)
        self.assertTrue(coverage["cacheHit"])
        self.assertEqual(coverage["cacheAgeSeconds"], 10)
        rows[0]["hotspots"][0]["count"] = 99
        self.assertEqual(self.cache.get("sites", QUERY, ORIGIN)[0], self.sites)
        self.clock.return_value = 1300.0
        self.assertIsNone(self.cache.get("sites", QUERY, ORIGIN))

    def test_powerplay_expires_earlier_and_never_crosses_source_freshness_limit(self):
        self.assertTrue(self.put("powerplay", rows=self.powers))
        self.clock.return_value = 1060.0
        self.assertIsNone(self.cache.get("powerplay", QUERY, ORIGIN))

        self.clock.return_value = 1000.0
        almost_old = [{**self.powers[0], "observedAt": (NOW - timedelta(days=14, seconds=-2)).isoformat()}]
        self.assertTrue(self.put("powerplay", rows=almost_old))
        self.clock.return_value = 1003.0
        self.assertIsNone(self.cache.get("powerplay", QUERY, ORIGIN))

    def test_wall_clock_jump_cannot_make_newly_stale_powerplay_look_current(self):
        self.put("powerplay", rows=self.powers)
        self.cache._wall_clock = lambda: (NOW + timedelta(days=15)).timestamp()
        self.assertIsNone(self.cache.get("powerplay", QUERY, ORIGIN))

    def test_scope_covers_coordinates_radius_commodity_but_not_market_filters(self):
        self.put()
        for query, origin in (({**QUERY, "nearbyLy": 500}, ORIGIN),
                              ({**QUERY, "commodity": "gold"}, ORIGIN),
                              (QUERY, {"coordinates": [1, 2, 3]})):
            self.assertIsNone(self.cache.get("sites", query, origin))
        self.assertIsNotNone(self.cache.get("sites", {**QUERY, "minDemand": 10,
                                                     "landingPad": "S", "maxMarketAgeHours": 24}, ORIGIN))
        self.put("powerplay", rows=self.powers)
        self.assertIsNotNone(self.cache.get("powerplay", {**QUERY, "commodity": "gold"}, ORIGIN))

    def test_partial_unknown_inconsistent_or_canceled_results_are_never_admitted(self):
        for coverage in ({}, {**COMPLETE, "bounded": True}, {**COMPLETE, "complete": False},
                         {**COMPLETE, "consistent": False}, {**COMPLETE, "partialError": "Timeout"}):
            self.assertFalse(self.put(coverage=coverage))
        self.assertFalse(self.put(is_current=lambda: False))
        self.clock.return_value = 1400.0  # A long download is already outside the reuse window.
        self.assertFalse(self.put())
        self.assertEqual(self.cache.entry_count, 0)

    def test_cancellation_during_serialization_does_not_populate_cache(self):
        self.assertFalse(self.put(is_current=Mock(side_effect=[True, False])))
        self.assertEqual(self.cache.entry_count, 0)

    def test_memory_budget_and_entry_limit_evict_without_persisting_any_files(self):
        tiny = MiningRegionCache(clock=self.clock, max_bytes=1000, max_entries=2)
        for radius in (50, 100, 250):
            self.assertTrue(tiny.put("sites", {**QUERY, "nearbyLy": radius}, ORIGIN,
                                     self.sites, COMPLETE, started_at=1000.0))
        self.assertEqual(tiny.entry_count, 2)
        self.assertLessEqual(tiny.stored_bytes, 1000)
        self.assertIsNone(tiny.get("sites", {**QUERY, "nearbyLy": 50}, ORIGIN))
        too_small = MiningRegionCache(clock=self.clock, max_bytes=1)
        self.assertFalse(too_small.put("sites", QUERY, ORIGIN, self.sites, COMPLETE, started_at=1000.0))

    def test_large_documents_use_small_json_blocks_and_preserve_every_row(self):
        rows = [{**self.sites[0], "ring": f"Mine {i} Ring"} for i in range(1000)]
        self.assertTrue(self.put(rows=rows))
        self.assertEqual(self.cache.get("sites", QUERY, ORIGIN)[0], rows)
        self.assertGreater(len(next(iter(self.cache._entries.values())).blocks), 1)

    def test_expanded_limit_refuses_oversized_data_even_when_highly_compressible(self):
        with patch("ed_companion.navigation.mining_region_cache.MAX_EXPANDED_BYTES", 50):
            self.assertFalse(self.put())

    def test_incomplete_powerplay_with_no_pagination_proof_is_refetched(self):
        calls = []

        class Session:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def get(inner, url, **kwargs):
                calls.append(url)
                return Mock(status_code=200, json=Mock(return_value={"results": self.powers}))

        self.put()
        with patch(MODULE + "fetch_market_imports", return_value=[]):
            for _ in range(2):
                result = fetch_mining_refresh(QUERY, origin=ORIGIN, region_cache=self.cache, session_factory=Session)
                self.assertFalse(result["powerplayCoverage"]["complete"])
        self.assertEqual(calls, [EDFRAME_POWERPLAY_URL, EDFRAME_POWERPLAY_URL])

    def test_empty_complete_answers_cache_but_malformed_rows_do_not(self):
        self.assertTrue(self.put(rows=[]))
        self.assertEqual(self.cache.get("sites", QUERY, ORIGIN)[0], [])
        self.assertFalse(self.put(rows=[{"system": "Mine"}]))

    def test_invalid_scope_and_changed_server_never_match_a_cached_region(self):
        self.put()
        for coordinates in ([], [1, 2], [float("nan"), 2, 3]):
            self.assertIsNone(self.cache.get("sites", QUERY, {"coordinates": coordinates}))
        with patch("ed_companion.navigation.mining_region_cache.EDFRAME_CATALOG_SITES_URL", "other-server"):
            self.assertIsNone(self.cache.get("sites", QUERY, ORIGIN))

    def test_cached_conditional_confirmation_is_not_presented_as_a_new_confirmation(self):
        self.put(coverage={**COMPLETE, "notModified": True, "revision": "example"})
        _, coverage = self.cache.get("sites", QUERY, ORIGIN)
        self.assertNotIn("notModified", coverage)
        self.assertEqual(coverage["revision"], "example")

    def test_actual_paged_fetches_drop_from_87_to_two_market_calls_on_repeat(self):
        calls = []
        lock = threading.Lock()

        class Session:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def get(inner, url, **kwargs):
                with lock:
                    calls.append(url)
                params = kwargs.get("params", {})
                if url == EDFRAME_CATALOG_SITES_URL:
                    page = params["offset"] // 1000
                    payload = {"results": [{"system": f"Mine {page}", "ring": f"Mine {page} A Ring",
                                            "x": 1, "y": 2, "z": 3, "observedAt": NOW.isoformat()}],
                               "hasMore": page < 25, "nextOffset": (page + 1) * 1000}
                elif url == EDFRAME_POWERPLAY_URL:
                    page = int(params.get("cursor", "0"))
                    payload = {"results": [{**self.powers[0], "system": f"Power {page}"}],
                               "hasMore": page < 58, "nextCursor": str(page + 1)}
                else:
                    payload = {}
                return Mock(status_code=200, json=Mock(return_value=payload))

        def markets(*_args, **kwargs):
            kwargs["get"]("market-central")
            kwargs["get"]("market-fallback")
            return [{"station": "Port", "observedAt": NOW.isoformat()}]

        with patch(MODULE + "fetch_market_imports", side_effect=markets):
            first = fetch_mining_refresh(QUERY, origin=ORIGIN, region_cache=self.cache, session_factory=Session)
            self.assertEqual(len(calls), 87)
            calls.clear()
            repeated = fetch_mining_refresh(QUERY, origin=ORIGIN, region_cache=self.cache, session_factory=Session)
            self.assertEqual(calls, ["market-central", "market-fallback"])
        for key in ("serverCandidates", "serverPowerplay", "markets"):
            self.assertEqual(first[key], repeated[key])
        self.assertTrue(repeated["siteCoverage"]["cacheHit"])
        self.assertTrue(repeated["powerplayCoverage"]["cacheHit"])

    def test_failed_domains_retry_while_successful_domains_are_reused(self):
        def sites(*_args, **kwargs):
            kwargs["diagnostics"].update(COMPLETE)
            return self.sites

        with patch(MODULE + "fetch_edframe_mining_candidates", side_effect=sites) as rings, \
                patch(MODULE + "fetch_edframe_powerplay", side_effect=RuntimeError("offline")) as powers, \
                patch(MODULE + "fetch_market_imports", side_effect=RuntimeError("offline")) as markets:
            for _ in range(2):
                result = fetch_mining_refresh(QUERY, origin=ORIGIN, region_cache=self.cache)
                self.assertFalse(result["success"])
            self.assertEqual(rings.call_count, 1)
            self.assertEqual(powers.call_count, 2)
            self.assertEqual(markets.call_count, 2)

    def test_disabled_server_does_not_consult_populated_regional_cache(self):
        self.put()
        with patch.object(self.cache, "get") as load, \
                patch(MODULE + "fetch_market_imports", return_value=[]) as markets:
            fetch_mining_refresh(QUERY, origin=ORIGIN, include_edframe=False, region_cache=self.cache)
        load.assert_not_called()
        self.assertFalse(markets.call_args.kwargs["include_edframe"])

    def test_powerplay_expiry_refetches_only_that_domain_and_markets(self):
        self.put()
        self.put("powerplay", rows=self.powers)
        self.clock.return_value = 1060.0
        with patch(MODULE + "fetch_edframe_mining_candidates") as rings, \
                patch(MODULE + "fetch_edframe_powerplay", return_value=self.powers) as powers, \
                patch(MODULE + "fetch_market_imports", return_value=[]) as markets:
            result = fetch_mining_refresh(QUERY, origin=ORIGIN, region_cache=self.cache)
        rings.assert_not_called()
        powers.assert_called_once()
        markets.assert_called_once()
        self.assertTrue(result["siteCoverage"]["cacheHit"])
        self.assertNotIn("cacheHit", result["powerplayCoverage"])

    def test_canceled_cached_search_does_not_publish_cached_domains(self):
        self.put()
        self.put("powerplay", rows=self.powers)
        with patch(MODULE + "fetch_market_imports", return_value=[]):
            result = fetch_mining_refresh(QUERY, origin=ORIGIN, region_cache=self.cache,
                                          is_current=lambda: False)
        self.assertNotIn("serverCandidates", result)
        self.assertNotIn("serverPowerplay", result)

    def test_explicit_current_system_refresh_invalidates_regional_reuse(self):
        controller = refresh_tests.MiningRefreshTests().controller()
        controller._mining_region_cache = self.cache
        controller._mining_sync_busy = False
        controller._state = {}  # No current system: bypass still takes effect.
        controller.refreshMiningFinder()
        self.assertIsNone(controller._mining_region_cache)

    def test_controller_captures_profile_cache_and_replaces_it_for_new_generation_or_path(self):
        controller = refresh_tests.MiningRefreshTests().controller()
        controller._start_network_worker = Mock(return_value=True)
        controller._start_mining_market_refresh(QUERY, background=False)
        old_worker = controller._start_network_worker.call_args.args[0]
        original = controller._mining_region_cache
        controller._active_mining_market_request = None
        controller._mining_market_busy = False
        controller._profile_generation += 1
        controller.mining_market_cache_file = Path("other-profile.json")
        controller._start_mining_market_refresh(QUERY, background=False)
        self.assertIsNot(controller._mining_region_cache, original)
        with patch("ed_companion.phase14.controller_navigation.fetch_mining_refresh", return_value={}) as fetch:
            old_worker()
        self.assertIs(fetch.call_args.kwargs["region_cache"], original)
        self.assertFalse(fetch.call_args.kwargs["is_current"]())


if __name__ == "__main__":
    unittest.main()
