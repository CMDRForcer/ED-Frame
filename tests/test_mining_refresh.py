"""Connection reuse, concurrency and off-UI persistence contracts."""

from pathlib import Path
import sqlite3
import threading
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from ed_companion.navigation.mining_refresh import fetch_mining_refresh
from ed_companion.phase14.controller import CockpitController


QUERY = {
    "startSystem": "shanteneri", "commodity": "platinum", "nearbyLy": 250,
    "maxMarketAgeHours": 1, "landingPad": "L", "minDemand": 5000,
}
ORIGIN = {"coordinates": [110.9375, -113.0625, 41.21875]}
MODULE = "ed_companion.navigation.mining_refresh."


class Session:
    def __init__(self):
        self.closed = False
        self.owner = None
        self.calls = []

    def __enter__(self):
        self.owner = threading.get_ident()
        return self

    def __exit__(self, *_args):
        self.closed = True

    def get(self, url, **kwargs):
        if self.owner != threading.get_ident():
            raise AssertionError("A Session was shared across threads")
        self.calls.append((url, kwargs))
        return Mock()


class MiningRefreshTests(unittest.TestCase):
    def factory(self):
        session = Session()
        with self.lock:
            self.sessions.append(session)
        return session

    def setUp(self):
        self.sessions = []
        self.lock = threading.Lock()

    def test_all_domains_overlap_and_each_reuses_its_own_session(self):
        barrier = threading.Barrier(3)

        def sites(_system, get, **kwargs):
            barrier.wait(timeout=3)
            get("page1"); get("page2")
            kwargs["diagnostics"].update(count=2, pages=2, bounded=False)
            return [{"ring": "A"}, {"ring": "B"}]

        def powerplay(**kwargs):
            barrier.wait(timeout=3)
            kwargs["get"]("powerplay")
            return [{"power": "Aisling Duval"}]

        def markets(*_args, **kwargs):
            barrier.wait(timeout=3)
            kwargs["get"]("central"); kwargs["get"]("fallback")
            self.assertEqual(kwargs["max_age_hours"], 1)
            self.assertEqual(kwargs["landing_pad"], "L")
            self.assertEqual(kwargs["max_distance"], 250)
            self.assertIs(kwargs["origin"], ORIGIN)
            kwargs["provider_status"]["ED-Frame"] = "OK"
            return [{"station": "Port"}]

        with patch(MODULE + "fetch_edframe_mining_candidates", side_effect=sites), \
                patch(MODULE + "fetch_edframe_powerplay", side_effect=powerplay), \
                patch(MODULE + "fetch_market_imports", side_effect=markets):
            result = fetch_mining_refresh(QUERY, origin=ORIGIN, session_factory=self.factory)
        self.assertTrue(result["success"])
        self.assertEqual(len(result["serverCandidates"]), 2)
        self.assertEqual(result["siteCoverage"], {"count": 2, "pages": 2, "bounded": False})
        self.assertEqual(result["markets"], [{"station": "Port"}])
        self.assertEqual(len(self.sessions), 3)
        self.assertTrue(all(session.closed for session in self.sessions))
        self.assertEqual(sorted(len(session.calls) for session in self.sessions), [1, 2, 2])

    def test_market_failure_does_not_drop_rings_or_powerplay(self):
        with patch(MODULE + "fetch_edframe_mining_candidates", return_value=[{"ring": "A"}]), \
                patch(MODULE + "fetch_edframe_powerplay", return_value=[{"power": "P"}]), \
                patch(MODULE + "fetch_market_imports", side_effect=ValueError("offline")):
            result = fetch_mining_refresh(QUERY, origin=ORIGIN, session_factory=self.factory)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "offline")
        self.assertEqual(result["serverCandidates"], [{"ring": "A"}])
        self.assertEqual(result["serverPowerplay"], [{"power": "P"}])
        self.assertTrue(all(session.closed for session in self.sessions))

    def test_ring_failure_does_not_drop_other_domains(self):
        with patch(MODULE + "fetch_edframe_mining_candidates", side_effect=ValueError("ring error")), \
                patch(MODULE + "fetch_edframe_powerplay", return_value=[{"power": "P"}]), \
                patch(MODULE + "fetch_market_imports", return_value=[{"station": "Port"}]):
            result = fetch_mining_refresh(QUERY, origin=ORIGIN, session_factory=self.factory)
        self.assertTrue(result["success"])
        self.assertEqual(result["siteError"], "ring error")
        self.assertEqual(result["serverPowerplay"], [{"power": "P"}])

    def test_coordinate_fallback_keeps_one_session_and_disabled_server_stays_disabled(self):
        with patch(MODULE + "fetch_edframe_system_coordinates") as central, \
                patch(MODULE + "fetch_edsm_system_coordinates", return_value=ORIGIN) as edsm, \
                patch(MODULE + "fetch_edframe_mining_candidates") as sites, \
                patch(MODULE + "fetch_edframe_powerplay") as powerplay, \
                patch(MODULE + "fetch_market_imports", return_value=[]) as markets:
            result = fetch_mining_refresh(QUERY, include_edframe=False, session_factory=self.factory)
        self.assertTrue(result["success"])
        central.assert_not_called(); sites.assert_not_called(); powerplay.assert_not_called()
        edsm.assert_called_once()
        self.assertFalse(markets.call_args.kwargs["include_edframe"])
        self.assertEqual(len(self.sessions), 2)

    def test_coordinate_failure_retains_market_fallback(self):
        with patch(MODULE + "fetch_edframe_system_coordinates", side_effect=ValueError("server")), \
                patch(MODULE + "fetch_edsm_system_coordinates", side_effect=ValueError("edsm")), \
                patch(MODULE + "fetch_edframe_mining_candidates") as sites, \
                patch(MODULE + "fetch_market_imports", return_value=[{"station": "Port"}]):
            result = fetch_mining_refresh(QUERY, session_factory=self.factory)
        self.assertTrue(result["success"])
        self.assertEqual(result["originError"], "edsm")
        sites.assert_not_called()

    def test_cancel_prevents_next_http_call_and_closes_session(self):
        current = Mock(side_effect=[True, False])

        def markets(*_args, **kwargs):
            kwargs["get"]("first")
            kwargs["get"]("must-not-send")
            return []

        with patch(MODULE + "fetch_market_imports", side_effect=markets):
            result = fetch_mining_refresh(QUERY, origin=ORIGIN, include_edframe=False,
                                          session_factory=self.factory, is_current=current)
        self.assertFalse(result["success"])
        self.assertEqual([url for url, _ in self.sessions[0].calls], ["first"])
        self.assertTrue(self.sessions[0].closed)

    def controller(self):
        controller = CockpitController.__new__(CockpitController)
        controller.profile_context = Mock(key="alpha")
        controller._profile_generation = 3
        controller.mining_market_cache_file = Path("test-market-cache.json")
        controller._mining_market_store = Mock()
        controller._mining_market_store.count.return_value = 12
        controller._mining_market_store.warm_summary.return_value = {"fresh": 1, "total": 1}
        controller._persist_json = Mock(return_value=True)
        controller._mining_market_revision = 0
        controller._mining_market_failure_count = 0
        controller._mining_market_busy = False
        controller._shutdown_complete = False
        controller._known_mining_origin = Mock(return_value=ORIGIN)
        controller.refreshMiningPowerplayCatalog = Mock()
        controller._remember_mining_origin = Mock(return_value=False)
        controller._schedule_mining_market_backup = Mock()
        controller._launch_pending_mining_market_refresh = Mock(return_value=False)
        controller.miningChanged = Mock()
        controller.stateChanged = Mock()
        controller.miningMarketFinished = Mock()
        return controller

    def result(self, **changes):
        return {"id": "request", "profileKey": "alpha", "generation": 3,
                "path": "test-market-cache.json", "success": True,
                "query": QUERY, "markets": [{"station": "Port"}], **changes}

    def test_user_search_preempts_warming_without_marking_target_failed(self):
        controller = self.controller()
        controller._start_network_worker = Mock(return_value=True)
        controller._remember_mining_warm_targets = Mock()
        controller._start_mining_market_refresh(QUERY, background=True)
        old = dict(controller._active_mining_market_request)
        old_worker = controller._start_network_worker.call_args.args[0]
        controller.refreshMiningMarkets("Shanteneri", "Gold", 250, 5000, 1, "L")
        new = controller._active_mining_market_request
        self.assertNotEqual(new["id"], old["id"])
        self.assertFalse(new["background"])
        self.assertEqual(new["query"]["commodity"], "gold")
        controller._mining_market_store.reset_mock()

        def canceled(*_args, **kwargs):
            self.assertFalse(kwargs["is_current"]())
            return {"success": False, "error": "superseded"}

        with patch("ed_companion.phase14.controller_navigation.fetch_mining_refresh", side_effect=canceled):
            old_worker()
        controller._finish_mining_market_sync(controller.miningMarketFinished.emit.call_args.args[0])
        self.assertIs(controller._active_mining_market_request, new)
        self.assertTrue(controller._mining_market_busy)
        self.assertEqual(controller._mining_market_store.mock_calls, [])
        controller._persist_json.assert_not_called()

    def test_running_user_search_keeps_latest_followup_queued(self):
        controller = self.controller()
        controller._start_network_worker = Mock(return_value=True)
        controller._remember_mining_warm_targets = Mock()
        controller._start_mining_market_refresh(QUERY, background=False)
        active = controller._active_mining_market_request
        controller.refreshMiningMarkets("Shanteneri", "Gold", 250, 5000, 1, "L")
        self.assertIs(controller._active_mining_market_request, active)
        self.assertEqual(controller._pending_mining_market_query["commodity"], "gold")
        self.assertEqual(controller._start_network_worker.call_count, 1)

    def test_unknown_origin_all_commodities_search_also_preempts_warming(self):
        controller = self.controller()
        controller._start_network_worker = Mock(return_value=True)
        controller._remember_mining_warm_targets = Mock()
        controller._start_mining_market_refresh(QUERY, background=True)
        old_id = controller._active_mining_market_request["id"]
        controller._known_mining_origin.return_value = None
        controller.refreshMiningMarkets("Unknown", "ALL COMMODITIES", 250, 0, 1, "L")
        self.assertNotEqual(controller._active_mining_market_request["id"], old_id)
        self.assertFalse(controller._active_mining_market_request["background"])

    def test_actual_worker_persists_before_emission_not_from_completion_slot(self):
        controller = self.controller()
        worker_thread_ids = []
        controller._persist_json.side_effect = lambda *_args: worker_thread_ids.append(threading.get_ident()) or True
        controller._start_network_worker = Mock(return_value=True)
        with patch("ed_companion.phase14.controller_navigation.fetch_mining_refresh",
                   return_value={"success": True, "markets": [{"station": "Port"}]}):
            self.assertTrue(controller._start_mining_market_refresh(QUERY, background=False))
            self.assertFalse(controller._persist_json.called)
            target = controller._start_network_worker.call_args.args[0]
            worker = threading.Thread(target=target)
            worker.start(); worker.join(timeout=3)
            self.assertFalse(worker.is_alive())
        self.assertEqual(worker_thread_ids, [worker.ident])
        result = controller.miningMarketFinished.emit.call_args.args[0]
        self.assertEqual(result["retained"], 12)
        controller._mining_market_store.reset_mock()
        controller._persist_json.reset_mock()
        controller._finish_mining_market_sync(result)
        self.assertEqual(controller._mining_market_cache["markets"], [{"station": "Port"}])
        self.assertEqual(controller._mining_market_store.mock_calls, [])
        controller._persist_json.assert_not_called()

    def test_stale_request_profile_generation_or_path_never_writes(self):
        for changes in ({"id": "stale"}, {"profileKey": "beta"},
                        {"generation": 2}, {"path": "other.json"}):
            controller = self.controller()
            controller._active_mining_market_request = {"id": "request"}
            controller._persist_mining_market_result(self.result(**changes),
                                                      controller._mining_market_store, threading.Lock())
            self.assertEqual(controller._mining_market_store.mock_calls, [])
            controller._persist_json.assert_not_called()

    def test_reset_invalidates_worker_waiting_for_write_lock(self):
        controller = self.controller()
        controller._active_mining_market_request = {"id": "request"}
        lock = threading.Lock()
        with lock:
            worker = threading.Thread(target=controller._persist_mining_market_result,
                                      args=(self.result(), controller._mining_market_store, lock))
            worker.start()
            controller._active_mining_market_request = None
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(controller._mining_market_store.mock_calls, [])
        controller._persist_json.assert_not_called()

    def test_failed_persistence_does_not_discard_fetched_results(self):
        controller = self.controller()
        controller._active_mining_market_request = {"id": "request"}
        controller._mining_market_store.ingest.side_effect = sqlite3.OperationalError("locked")
        result = self.result()
        controller._persist_mining_market_result(result, controller._mining_market_store, threading.Lock())
        self.assertTrue(result["success"])
        self.assertEqual(result["persistenceError"], "OperationalError")
        controller._finish_mining_market_sync(result)
        self.assertIn("local cache save failed", controller._mining_market_status)
        self.assertEqual(controller._mining_market_cache["markets"], [{"station": "Port"}])

    def test_coordinate_snapshot_is_saved_by_worker_and_completion_only_updates_names(self):
        with TemporaryDirectory() as directory:
            controller = self.controller()
            controller._data_dir = Path(directory)
            controller._add_mining_system_names = Mock()
            controller._start_network_worker = Mock(return_value=True)
            origin = {**ORIGIN, "system": "Shanteneri"}
            with patch("ed_companion.phase14.controller_navigation.fetch_mining_refresh",
                       return_value={"success": True, "markets": [], "origin": origin}):
                controller._start_mining_market_refresh(QUERY, background=False)
                worker = threading.Thread(target=controller._start_network_worker.call_args.args[0])
                worker.start(); worker.join(timeout=3)
            self.assertFalse(worker.is_alive())
            paths = [args.args[0] for args in controller._persist_json.call_args_list]
            self.assertIn(Path(directory, "system_coordinates.json"), paths)
            result = controller.miningMarketFinished.emit.call_args.args[0]
            self.assertTrue(result["originUpdated"])
            controller._persist_json.reset_mock()
            controller._finish_mining_market_sync(result)
            controller._persist_json.assert_not_called()
            controller._add_mining_system_names.assert_called_once_with([{"system": "Shanteneri"}])

    def test_delayed_worker_cannot_write_replacement_profile_or_complete_its_request(self):
        controller = self.controller()
        old_store = controller._mining_market_store
        controller._start_network_worker = Mock(return_value=True)
        controller._start_mining_market_refresh(QUERY, background=False)
        worker = controller._start_network_worker.call_args.args[0]
        controller.profile_context = Mock(key="beta")
        controller._profile_generation += 1
        controller.mining_market_cache_file = Path("beta.json")
        controller._mining_market_store = Mock()
        controller._active_mining_market_request = {"id": "new-profile-request"}
        with patch("ed_companion.phase14.controller_navigation.fetch_mining_refresh",
                   return_value={"success": True, "markets": [{"station": "Old Port"}]}):
            worker()
        self.assertEqual(old_store.mock_calls, [])
        self.assertEqual(controller._mining_market_store.mock_calls, [])
        controller._persist_json.assert_not_called()
        controller._finish_mining_market_sync(controller.miningMarketFinished.emit.call_args.args[0])
        self.assertEqual(controller._active_mining_market_request["id"], "new-profile-request")
        self.assertTrue(controller._mining_market_busy)

    def test_json_save_failure_is_visible_and_preserves_results(self):
        controller = self.controller()
        controller._active_mining_market_request = {"id": "request"}
        controller._persist_json.return_value = False
        result = self.result()
        controller._persist_mining_market_result(result, controller._mining_market_store, threading.Lock())
        self.assertTrue(result["success"])
        self.assertIn("persistenceError", result)
        self.assertEqual(result["retained"], 12)


if __name__ == "__main__":
    unittest.main()
