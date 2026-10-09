"""Parallel checks retain budgets, evidence, ordering and request fences."""

from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

from ed_companion.navigation.mining_verification import (
    iter_verification_jobs, verification_market_origin,
)
from ed_companion.phase14.controller import CockpitController


class VerificationJobsTests(unittest.TestCase):
    def test_two_lanes_reuse_owned_sessions_and_close_after_all_checks(self):
        sessions, active, maximum = [], 0, 0
        lock = threading.Lock()
        barrier = threading.Barrier(2)

        class Session:
            def __init__(self):
                self.owner = threading.get_ident()
                self.closed = False
                sessions.append(self)

            def get(self, url):
                nonlocal active, maximum
                self_test.assertEqual(threading.get_ident(), self.owner)
                self_test.assertFalse(self.closed)
                with lock:
                    active += 1
                    maximum = max(maximum, active)
                if url in ("powerplay", "ring"):
                    barrier.wait(2)
                with lock:
                    active -= 1
                return url

            def close(self):
                self.closed = True

        self_test = self
        jobs = [(kind, index) for index, kind in enumerate(
            ["powerplay", "ring", *["market"] * 6]
        )]
        results = list(iter_verification_jobs(
            jobs, lambda kind, target, get: get(kind), session_factory=Session,
        ))
        self.assertEqual(maximum, 2)
        self.assertEqual(len(sessions), 2)
        self.assertTrue(all(session.closed for session in sessions))
        self.assertEqual({index for index, *_ in results}, set(range(8)))
        self.assertTrue(all(error is None for *_, error in results))

    def test_failure_is_isolated_and_every_job_still_completes(self):
        sessions = []

        def factory():
            session = Mock(get=Mock(return_value="public"))
            sessions.append(session)
            return session

        def execute(kind, target, get):
            if target == 1:
                raise LookupError("missing")
            return get(kind)

        results = list(iter_verification_jobs(
            [("market", index) for index in range(6)], execute,
            session_factory=factory,
        ))
        self.assertEqual(len(results), 6)
        errors = [error for *_, error in results if error is not None]
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], LookupError)
        for session in sessions:
            session.close.assert_called_once()

    def test_superseded_input_blocks_every_later_get_and_queued_job(self):
        current = [True]
        session = Mock()

        def first_get(url):
            current[0] = False
            return "first"

        session.get.side_effect = first_get

        def execute(kind, target, get):
            get("first")
            get("must-not-send")

        results = list(iter_verification_jobs(
            [("market", 0)], execute, is_current=lambda: current[0],
            session_factory=lambda: session,
        ))
        session.get.assert_called_once_with("first")
        self.assertIsInstance(results[0][-1], RuntimeError)
        session.close.assert_called_once()
        factory = Mock()
        results = list(iter_verification_jobs(
            [("market", index) for index in range(6)], execute,
            is_current=lambda: False, session_factory=factory,
        ))
        self.assertEqual(len(results), 6)
        self.assertTrue(all(isinstance(row[-1], RuntimeError) for row in results))
        factory.assert_not_called()

    def test_empty_jobs_open_no_connections(self):
        factory = Mock()
        self.assertEqual(list(iter_verification_jobs([], Mock(), session_factory=factory)), [])
        factory.assert_not_called()

    def test_coordinate_reuse_is_finite_independent_and_for_mine_not_sale(self):
        row = {"system": "Mine", "coordinates": [1, 2, 3],
               "sellSystem": "Sale", "sellCoordinates": [4, 5, 6]}
        origin = verification_market_origin(row)
        self.assertEqual(origin, {"system": "Mine", "coordinates": [1.0, 2.0, 3.0]})
        row["coordinates"][0] = 99
        self.assertEqual(origin["coordinates"], [1, 2, 3])
        for coordinates in (None, [], [1, 2], "123", [True, 2, 3],
                            [float("nan"), 2, 3], [1, float("inf"), 3], ["bad", 2, 3]):
            with self.subTest(coordinates=coordinates):
                self.assertIsNone(verification_market_origin({**row, "coordinates": coordinates}))
        self.assertIsNone(verification_market_origin({**row, "system": ""}))
        self.assertEqual(verification_market_origin({**row, "coordinates": (0, 0, 0)})[
            "coordinates"], [0, 0, 0])


class VerificationControllerTests(unittest.TestCase):
    def controller(self):
        c = CockpitController.__new__(CockpitController)
        c.profile_context = Mock(key="alpha")
        c._profile_generation = 2
        c.mining_catalog_file = Path("catalog.json")
        c._known_mining_origin = Mock(return_value={"coordinates": [50, 60, 70]})
        c._start_network_worker = Mock(return_value=True)
        c.miningChanged = Mock()
        c.miningVerificationChanged = Mock()
        c.miningVerificationProgress = Mock()
        c.miningVerificationFinished = Mock()
        c._persist_verified_mining_markets = Mock()
        return c

    def routes(self, count=6):
        return [{"system": f"Mine {index}", "coordinates": [index, 2, 3],
                 "sellSystem": "Sale", "sellCoordinates": [40, 50, 60],
                 "optimization": "POWERPLAY MERITS", "powerplayStatus": "POWERPLAY_DATA_MISSING",
                 "sameSystemSaleRequired": True, "marketMatchesFilters": False,
                 "selectedCommodity": "platinum", "selectedPower": "Aisling Duval"}
                for index in range(count)]

    def test_powerplay_does_not_block_markets_and_completion_order_does_not_change_results(self):
        c = self.controller()
        c.verifyMiningRoutes(self.routes(), "Origin", "Platinum", 1, 5000, "LARGE")
        market_started = threading.Event()
        first_market_released = threading.Event()
        origins = {}

        def powerplay(targets, **kwargs):
            self.assertTrue(market_started.wait(2), "Powerplay serialized the independent market checks")
            first_market_released.set()
            return {"rows": [], "checked": [row["system"] for row in targets], "failed": []}

        def markets(system, commodity, **kwargs):
            market_started.set()
            if system == "Mine 0":
                self.assertTrue(first_market_released.wait(2))
            origins[system] = kwargs["origin"]
            self.assertEqual(kwargs["max_distance"], 1)
            self.assertEqual(kwargs["max_days_ago"], 1)
            self.assertEqual(kwargs["landing_pad"], "LARGE")
            return [{"system": system, "commodity": commodity, "station": "Public"}]

        with patch("ed_companion.phase14.controller_navigation.fetch_powerplay_targets", side_effect=powerplay), \
                patch("ed_companion.phase14.controller_navigation.fetch_market_imports", side_effect=markets):
            c._start_network_worker.call_args.args[0]()
        result = c.miningVerificationFinished.emit.call_args.args[0]
        self.assertEqual([row["system"] for row in result["markets"]],
                         [f"Mine {index}" for index in range(6)])
        self.assertEqual(result["marketSucceeded"], [f"mine {index}\x1fplatinum" for index in range(6)])
        self.assertEqual(result["marketFailed"], [])
        self.assertEqual(result["powerplayLookup"]["failed"], [])
        for index in range(6):
            self.assertEqual(origins[f"Mine {index}"],
                             {"system": f"Mine {index}", "coordinates": [index, 2, 3]})
        progress = [call.args[0] for call in c.miningVerificationProgress.emit.call_args_list]
        self.assertEqual(len(progress), 7)
        self.assertEqual(progress[-1]["completed"], result["total"])
        self.assertEqual(sorted(row["completed"] for row in progress), [row["completed"] for row in progress])
        self.assertTrue(all(row["failures"] == 0 for row in progress))
        c._persist_verified_mining_markets.assert_called_once()

    def test_profile_path_reset_and_shutdown_fence_queued_http(self):
        for change in (lambda c: setattr(c, "_profile_generation", 3),
                       lambda c: setattr(c, "mining_catalog_file", Path("other.json")),
                       lambda c: setattr(c, "_active_mining_verification_request", None),
                       lambda c: setattr(c, "_shutdown_complete", True),
                       lambda c: setattr(c, "_edframe_catalog_enabled", False)):
            with self.subTest(change=change):
                c = self.controller()
                c.verifyMiningRoutes(self.routes(), "Origin", "Platinum", 1, 5000, "LARGE")
                change(c)
                with patch("ed_companion.phase14.controller_navigation.fetch_market_imports") as markets, \
                        patch("ed_companion.phase14.controller_navigation.fetch_powerplay_targets") as powers:
                    c._start_network_worker.call_args.args[0]()
                markets.assert_not_called()
                powers.assert_not_called()

    def test_disabled_catalog_keeps_market_fallback_without_central_requests(self):
        c = self.controller()
        c._edframe_catalog_enabled = False
        c.verifyMiningRoutes(self.routes(), "Origin", "Platinum", 1, 5000, "LARGE")
        with patch("ed_companion.phase14.controller_navigation.fetch_market_imports", return_value=[]) as markets, \
                patch("ed_companion.phase14.controller_navigation.fetch_powerplay_targets") as powers:
            c._start_network_worker.call_args.args[0]()
        self.assertEqual(markets.call_count, 6)
        self.assertTrue(all(call.kwargs["include_edframe"] is False for call in markets.call_args_list))
        powers.assert_not_called()
        result = c.miningVerificationFinished.emit.call_args.args[0]
        self.assertEqual(len(result["marketSucceeded"]), 6)
        self.assertEqual(result["marketFailed"], [])
        self.assertTrue(all(row["state"] == "NO_DATA" for row in result["marketOutcomes"]))

    def test_settings_cancellation_never_writes_or_poison_retry_caches_and_restarts_pending(self):
        for queue_pending in (False, True):
            with self.subTest(queue_pending=queue_pending):
                c = self.controller()
                c._mining_powerplay_lookup_cache = {"retained": 123}
                c._mining_powerplay_market_verification_cache = {"retained": {"state": "FOUND"}}
                c._mining_verification_cache = {42: {"retryAfter": 123}}
                c.verifyMiningRoutes(self.routes(), "Origin", "Platinum", 1, 5000, "LARGE")
                result = {**c._active_mining_verification_request,
                          "markets": [{"system": "Mine 0"}],
                          "marketFailed": [{"key": "mine 0\x1fplatinum"}],
                          "powerplayLookup": {"failed": ["Mine 0"]}}
                c._mining_market_verification_states["unrelated"] = {"state": "FOUND"}
                c._edframe_catalog_enabled = False
                if queue_pending:
                    c._pending_mining_verification = {
                        "routes": self.routes(1), "startSystem": "Origin", "commodity": "Platinum",
                        "maxMarketAgeHours": 1, "minDemand": 5000, "landingPad": "LARGE",
                    }
                c._start_network_worker.reset_mock()
                store = Mock()
                c._mining_market_store = store
                c._persist_verified_mining_markets = CockpitController._persist_verified_mining_markets.__get__(c)
                c._persist_verified_mining_markets(result, store, threading.Lock())
                store.ingest.assert_not_called()
                with patch.object(c, "_publish_mining_powerplay") as publish:
                    c._finish_mining_verification(result)
                publish.assert_not_called()
                self.assertEqual(c._mining_powerplay_lookup_cache, {"retained": 123})
                self.assertEqual(c._mining_powerplay_market_verification_cache,
                                 {"retained": {"state": "FOUND"}})
                self.assertEqual(c._mining_verification_cache, {42: {"retryAfter": 123}})
                self.assertIsNone(c._pending_mining_verification)
                if queue_pending:
                    c._start_network_worker.assert_called_once()
                    self.assertNotEqual(c._active_mining_verification_request["id"], result["id"])
                    self.assertFalse(c._active_mining_verification_request["catalogEnabled"])
                    self.assertTrue(c._mining_verification_busy)
                else:
                    c._start_network_worker.assert_not_called()
                    self.assertIsNone(c._active_mining_verification_request)
                    self.assertFalse(c._mining_verification_busy)
                    self.assertIn("cancelled", c._mining_verification_status)
                self.assertEqual(set(c._mining_market_verification_states),
                                 {"unrelated", "mine 0\x1fplatinum"} if queue_pending else {"unrelated"})


if __name__ == "__main__":
    unittest.main()
