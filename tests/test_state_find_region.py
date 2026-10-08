import threading
import unittest
from datetime import datetime, timezone
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from ed_companion.navigation.mining_market import MiningMarketError
from ed_companion.navigation.state_find_catalog import (
    fetch_edframe_state_find_delta, merge_edframe_state_find_page,
    retain_state_find_region, state_find_region,
)
from ed_companion.phase14.controller_navigation import NavigationMixin


class StateFindRegionTests(unittest.TestCase):
    def test_invalid_and_zero_origin(self):
        self.assertEqual(state_find_region([0, 0, 0])["origin"], [0., 0., 0.])
        for origin in (None, [], [1, 2], [1, 2, float("nan")], [1, 2, float("inf")], ["bad", 0, 0]):
            self.assertIsNone(state_find_region(origin))

    def test_regional_request_and_server_confirmation(self):
        region = state_find_region([1, 2, 3])
        response = Mock()
        response.json.return_value = {
            "results": [], "region": region, "hasMore": False,
        }
        get = Mock(return_value=response)
        page = fetch_edframe_state_find_delta(origin=[1, 2, 3], get=get)
        self.assertEqual(page["region"], region)
        self.assertEqual(get.call_args.kwargs["params"],
                         {"limit": 500, "x": 1., "y": 2., "z": 3., "max_distance": 250.})
        response.json.return_value["region"] = None
        with self.assertRaises(MiningMarketError):
            fetch_edframe_state_find_delta(origin=[1, 2, 3], get=get)

    def test_failed_position_does_not_send_global_request(self):
        get = Mock()
        with self.assertRaises(MiningMarketError):
            fetch_edframe_state_find_delta(origin=[], get=get)
        get.assert_not_called()

    def test_cache_keeps_local_then_nearby_not_last_global_rows(self):
        local = {"system": "Local", "evidence_kind": "LOCAL_JOURNAL", "star_pos": [999, 0, 0]}
        nearby = {"system": "Near", "star_pos": [1, 0, 0]}
        distant = {"system": "Far", "star_pos": [500, 0, 0]}
        unknown = {"system": "Unknown"}
        kept = retain_state_find_region([local, nearby, distant, unknown], origin=[0, 0, 0], limit=2)
        self.assertEqual(kept, [nearby, local])

    def test_unbounded_merge_keeps_overflow_for_existing_archive(self):
        rows = [{"system": str(i)} for i in range(5)]
        kept, _ = merge_edframe_state_find_page(rows, {}, limit=None)
        self.assertEqual(kept, rows)

    def shell(self):
        region = state_find_region([1, 2, 3])
        controller = SimpleNamespace(
            _state={"currentPosition": [1, 2, 3]},
            _edframe_catalog_enabled=True, _profile_generation=4,
            _edframe_state_find_sync_meta={"region": region, "cursor": "old"},
            _hge_sightings=[], _hge_file_lock=threading.Lock(), _hge_save_sequences={},
            hge_cache_file="hge.json", state_find_sync_file="sync.json",
            _persist_json=Mock(return_value=True), _archive_history=Mock(return_value=True),
            _append_edframe_catalog_log=Mock(), connectionChanged=Mock(), hgeChanged=Mock(),
            edFrameStateFindSyncFinished=Mock(), _start_network_worker=Mock(return_value=True),
            _maybe_refresh_regional_state_finds=Mock(),
        )
        for name in ("_finish_legacy_state_find_storage", "_publish_state_find_page"):
            setattr(controller, name, MethodType(getattr(NavigationMixin, name), controller))
        return controller

    def test_cursor_reused_only_at_same_origin(self):
        for changed in (False, True):
            controller = self.shell()
            if changed:
                controller._state["currentPosition"] = [4, 5, 6]
            NavigationMixin.syncEdFrameStateFinds(controller)
            request = controller._active_edframe_state_find_sync_request
            self.assertEqual(request["cursor"], "" if changed else "old")
            worker = controller._start_network_worker.call_args.args[0]
            with patch("ed_companion.phase14.controller_navigation.fetch_edframe_state_find_delta",
                       return_value={}) as fetch:
                worker()
            self.assertEqual(fetch.call_args.kwargs["origin"], [4., 5., 6.] if changed else [1., 2., 3.])

    def test_finish_rejects_stale_location_and_profile(self):
        for changed_profile in (False, True):
            controller = self.shell()
            region = controller._edframe_state_find_sync_meta["region"]
            controller._active_edframe_state_find_sync_request = {"id": "job", "region": region}
            if changed_profile:
                controller._profile_generation = 5
            else:
                controller._state["currentPosition"] = [4, 5, 6]
            NavigationMixin._finish_edframe_state_find_sync(controller, {
                "id": "job", "generation": 4, "success": True, "page": {},
            })
            controller._persist_json.assert_not_called()
            self.assertEqual(controller._hge_sightings, [])

    def test_finish_stores_facts_before_region_cursor(self):
        controller = self.shell()
        region = controller._edframe_state_find_sync_meta["region"]
        controller._active_edframe_state_find_sync_request = {"id": "job", "region": region}
        stamp = datetime.now(timezone.utc).isoformat()
        NavigationMixin._finish_edframe_state_find_sync(controller, {
            "id": "job", "generation": 4, "success": True, "page": {
                "signals": [{"system": "Near", "star_pos": [1, 2, 3],
                             "signal_timestamp": stamp, "time_remaining": 3600,
                             "evidence_kind": "EDDN_SIGNAL"}],
                "nextCursor": "next", "generatedAt": stamp,
            },
        })
        calls = controller._persist_json.call_args_list
        self.assertEqual([call.args[0] for call in calls], ["hge.json", "sync.json"])
        self.assertEqual(controller._edframe_state_find_sync_meta["region"], region)
        self.assertEqual(controller._edframe_state_find_sync_meta["cursor"], "next")
        self.assertEqual(len(controller._hge_sightings), 1)

    def test_save_failure_does_not_advance_region_cursor(self):
        controller = self.shell()
        region = controller._edframe_state_find_sync_meta["region"]
        controller._active_edframe_state_find_sync_request = {"id": "job", "region": region}
        controller._persist_json.return_value = False
        NavigationMixin._finish_edframe_state_find_sync(controller, {
            "id": "job", "generation": 4, "success": True,
            "page": {"nextCursor": "next"},
        })
        self.assertEqual(controller._edframe_state_find_sync_meta["cursor"], "old")

    def test_no_position_preserves_data(self):
        controller = self.shell()
        controller._state = {}
        NavigationMixin.syncEdFrameStateFinds(controller)
        controller._start_network_worker.assert_not_called()
        controller._persist_json.assert_not_called()

    def test_overflow_archived_and_local_evidence_kept(self):
        controller = self.shell()
        region = controller._edframe_state_find_sync_meta["region"]
        controller._active_edframe_state_find_sync_request = {"id": "job", "region": region}
        stamp = datetime.now(timezone.utc).isoformat()
        local = {"system": "Local", "star_pos": [999, 0, 0],
                 "signal_timestamp": stamp, "time_remaining": 3600,
                 "evidence_kind": "LOCAL_JOURNAL"}
        controller._hge_sightings = [local]
        with patch("ed_companion.phase14.controller_navigation.HGE_OBSERVATION_LIMIT", 2):
            NavigationMixin._finish_edframe_state_find_sync(controller, {
                "id": "job", "generation": 4, "success": True, "page": {
                    "signals": [
                        {"system": name, "star_pos": position, "signal_timestamp": stamp,
                         "time_remaining": 3600, "evidence_kind": "EDDN_SIGNAL"}
                        for name, position in (("Near", [1, 2, 3]), ("Far", [200, 0, 0]))
                    ], "nextCursor": "next",
                },
            })
        self.assertEqual({row["system"] for row in controller._hge_sightings}, {"Local", "Near"})
        archived = controller._archive_history.call_args.args[1]
        self.assertEqual([row["system"] for row in archived], ["Far"])

    def test_region_changes_are_coalesced_within_one_minute(self):
        controller = self.shell()
        controller.syncEdFrameStateFinds = Mock()
        controller._state["currentPosition"] = [4, 5, 6]
        controller._edframe_state_find_started_at = 100.
        with patch("ed_companion.phase14.controller_navigation.time.monotonic", return_value=110.), \
             patch("ed_companion.phase14.controller_navigation.QTimer.singleShot") as timer:
            NavigationMixin._maybe_refresh_regional_state_finds(controller)
            NavigationMixin._maybe_refresh_regional_state_finds(controller)
        timer.assert_called_once()
        self.assertEqual(timer.call_args.args[0], 50000)
        controller.syncEdFrameStateFinds.assert_not_called()


if __name__ == "__main__":
    unittest.main()
