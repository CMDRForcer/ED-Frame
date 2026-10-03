import unittest

from ed_companion.navigation.state_find_catalog import (
    fetch_edframe_state_find_delta,
    merge_edframe_state_find_page,
)


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
        self.assertIn(fresh, rows)


if __name__ == "__main__":
    unittest.main()
