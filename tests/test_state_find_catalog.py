import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from ed_companion.navigation.state_find_catalog import (
    fetch_edframe_state_find_delta,
    merge_edframe_state_find_page,
)
from ed_companion.phase14.controller import CockpitController
from ed_companion.navigation.hge import partition_hge_observations, rank_all_hge_sightings


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class StateFindCatalogTests(unittest.TestCase):
    def test_fetch_splits_snapshots_and_signals(self):
        calls = []

        def get(url, **kwargs):
            calls.append((url, kwargs))
            return Response({
                "results": [
                    {"kind": "BGS", "snapshot": {"system": "Cubeo"}},
                    {"kind": "SIGNAL", "row": {"system": "Achenar"}},
                ],
                "nextCursor": "next",
                "hasMore": False,
            })

        page = fetch_edframe_state_find_delta(cursor="old", get=get)
        self.assertEqual(page["snapshots"], [{"system": "Cubeo"}])
        self.assertEqual(page["signals"], [{"system": "Achenar"}])
        self.assertEqual(calls[0][1]["params"]["cursor"], "old")

    def test_central_signal_cannot_replace_local_journal_evidence(self):
        base = {
            "system": "Cubeo", "signal_timestamp": "2099-01-01T00:00:00Z",
            "faction": "Faction", "state": "Boom", "find_type": "HGE",
            "time_remaining": 3600,
        }
        local = {**base, "evidence_kind": "LOCAL_JOURNAL", "source": "Journal"}
        server = {**base, "evidence_kind": "EDDN_SIGNAL", "source": "EDDN FSS"}
        rows, stats = merge_edframe_state_find_page(
            [local], {"signals": [server], "snapshots": []},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["evidence_kind"], "LOCAL_JOURNAL")
        self.assertEqual(stats["signalsApplied"], 0)

    def test_bgs_snapshot_replaces_only_server_bgs_for_same_system(self):
        old = {
            "system": "Cubeo", "system_address": 123,
            "signal_timestamp": "2026-10-03T08:00:00Z",
            "received_at": "2026-10-03T08:00:00Z",
            "source": "EDDN System BGS", "evidence_kind": "BGS_PREDICTION",
        }
        entered = {
            "system": "Cubeo", "system_address": 123,
            "signal_timestamp": "2099-01-01T00:00:00Z",
            "received_at": "2099-01-01T00:00:00Z",
            "source": "Manual", "evidence_kind": "ENTERED",
            "time_remaining": 3600,
        }
        fresh = {**old, "signal_timestamp": "2099-01-01T00:00:00Z"}
        rows, stats = merge_edframe_state_find_page([old, entered], {
            "snapshots": [{
                "system": "Cubeo", "system_address": 123,
                "observed_at": "2099-01-01T00:00:00Z",
                "observations": [fresh],
            }],
            "signals": [],
        })
        self.assertEqual(stats["snapshotsApplied"], 1)
        self.assertIn(entered, rows)
        self.assertIn({**fresh, "catalog_transport": "ED-Frame server"}, rows)
        self.assertNotIn("catalog_transport", fresh)

    def test_server_bgs_reaches_finder_as_prediction_not_verified_hge(self):
        stamp = datetime.now(timezone.utc).isoformat()
        prediction = {
            "system": "Cubeo", "system_address": 123,
            "star_pos": [1, 0, 0], "signal_timestamp": stamp,
            "received_at": stamp, "source": "EDDN System BGS",
            "evidence_kind": "BGS_PREDICTION", "find_type": "HGE",
            "faction": "Faction", "state": "Boom", "allegiance": "Federation",
            "time_remaining": 0,
            "materials": [{"material": "protoheatradiators", "confidence": .62}],
        }
        rows, _ = merge_edframe_state_find_page([], {"snapshots": [{
            "system": "Cubeo", "system_address": 123,
            "observed_at": stamp, "observations": [prediction],
        }], "signals": []})
        controller = CockpitController.__new__(CockpitController)
        controller._hge_sightings = rows
        controller._eddn_context = {}
        controller._system_coordinate_index = Mock(return_value={})
        controller._eddn_delivery_for_candidate = Mock(return_value="")
        ui = controller._build_state_find_rows(
            state={"system": "Elsewhere", "currentPosition": [0, 0, 0]}, sightings=rows,
        )
        self.assertEqual(len(ui), 1)
        self.assertEqual(ui[0]["status"], "POSSIBLE")
        self.assertEqual(ui[0]["remainingSeconds"], 0)
        self.assertEqual(controller._state_find_cache_summary()["serverBgs"], 1)
        self.assertEqual(controller._state_find_cache_summary()["serverSignals"], 0)

    def test_server_transport_does_not_extend_expired_signal(self):
        stamp = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        signal = {"system": "Expired", "system_address": 9,
            "star_pos": [0, 0, 0], "signal_timestamp": stamp,
            "time_remaining": 60, "source": "EDDN FSS",
            "evidence_kind": "EDDN_SIGNAL", "find_type": "HGE"}
        rows, _ = merge_edframe_state_find_page([], {"signals": [signal]})
        self.assertEqual(rank_all_hge_sightings(rows), [])
        active, historical = partition_hge_observations(rows)
        self.assertEqual(active, [])
        self.assertEqual(historical[0]["time_remaining"], 60)


if __name__ == "__main__":
    unittest.main()
