import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from ed_companion.navigation.signal_sharing import public_signal_observations, signal_observation_key
from ed_companion.navigation.state_find_catalog import fetch_edframe_state_find_delta, merge_edframe_state_find_page
from ed_companion.navigation.hge import rank_all_hge_sightings
from ed_companion.phase14.controller_navigation import NavigationMixin


class SignalSharingTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.row = dict(system="Sol", system_address=1, star_pos=[0, 0, 0],
                        signal_timestamp=self.now.isoformat(), time_remaining=600,
                        find_type="HGE", faction="Public faction", state="Boom",
                        source="Local Elite Journal", evidence_kind="LOCAL_JOURNAL",
                        Commander="PRIVATE", JournalPath="PRIVATE", Ship="PRIVATE")

    def test_only_public_fields_leave_client(self):
        row = public_signal_observations([self.row], now=self.now)[0]
        self.assertEqual(set(row), {"system", "system_address", "star_pos", "signal_timestamp",
                                    "time_remaining", "find_type", "faction", "state"})
        self.assertNotIn("PRIVATE", str(row))
        self.assertEqual(signal_observation_key(row), signal_observation_key(dict(reversed(list(row.items())))))

    def test_lifetime_boundaries_and_expiry(self):
        for lifetime, expected in [(0, 0), (0.5, 0), (1, 1), (7200, 1), (7201, 0), (float("nan"), 0)]:
            with self.subTest(lifetime=lifetime):
                self.assertEqual(len(public_signal_observations([{**self.row, "time_remaining": lifetime}], now=self.now)), expected)
        expired = {**self.row, "signal_timestamp": (self.now-timedelta(seconds=600)).isoformat()}
        self.assertEqual(public_signal_observations([expired], now=self.now), [])

    def test_no_eddn_bgs_or_test_upload(self):
        for changed in ({"source": "EDDN FSS"}, {"evidence_kind": "BGS_PREDICTION"}, {"self_test": True}):
            self.assertEqual(public_signal_observations([{**self.row, **changed}], now=self.now), [])

    def test_invalid_identity_timestamp_and_coordinates(self):
        for changed in ({"star_pos": [float("inf"), 0, 0]}, {"star_pos": []},
                        {"signal_timestamp": "2026-10-07T12:00:00"},
                        {"signal_timestamp": (self.now+timedelta(minutes=3)).isoformat()},
                        {"system": ""}, {"system": "x\x00"}, {"find_type": "MISSION"}):
            self.assertEqual(public_signal_observations([{**self.row, **changed}], now=self.now), [])

    def test_batch_is_bounded(self):
        self.assertEqual(len(public_signal_observations([self.row]*200, now=self.now)), 100)

    def test_no_upload_without_consent(self):
        stub = SimpleNamespace(_edframe_signal_sharing_enabled=False, _start_network_worker=Mock())
        NavigationMixin._maybe_share_state_signals(stub)
        stub._start_network_worker.assert_not_called()

    def test_sighting_transport_never_promotes_lifetime(self):
        response = Mock()
        response.json.return_value = dict(results=[dict(kind="SIGHTING", row=self.row)], nextCursor="next", hasMore=False)
        page = fetch_edframe_state_find_delta(get=lambda *args, **kwargs: response)
        self.assertEqual(page["signals"][0]["time_remaining"], 0)
        self.assertFalse(page["signals"][0]["local_verified"])
        self.assertEqual(rank_all_hge_sightings(page["signals"], now=self.now), [])

    def test_lifetime_evidence_wins_over_untimed_sighting_in_either_order(self):
        timed = {**self.row, "source": "ED-Frame community Journal", "evidence_kind": "EDDN_SIGNAL"}
        untimed = {**timed, "time_remaining": 0}
        for rows in ([timed, untimed], [untimed, timed]):
            merged, _ = merge_edframe_state_find_page([], {"signals": rows})
            self.assertEqual(len(merged), 1)
            self.assertEqual(merged[0]["time_remaining"], 600)
        merged, _ = merge_edframe_state_find_page([timed], {"signals": [untimed]})
        self.assertEqual(merged[0]["time_remaining"], 600)

    def test_stale_profile_completion_is_ignored(self):
        stub = SimpleNamespace(_profile_generation=2, _edframe_signal_upload_busy=True)
        NavigationMixin._finish_edframe_signal_upload(stub, {"generation": 1, "success": True})
        self.assertTrue(stub._edframe_signal_upload_busy)


if __name__ == "__main__":
    unittest.main()
