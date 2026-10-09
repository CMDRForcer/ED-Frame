"""Powerplay acquisition and freshness across projection, transport and planning."""
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock

from ed_companion.navigation.mining_powerplay import (
    project_powerplay_observations, merge_powerplay_observations,
    fetch_edframe_powerplay, missing_powerplay_targets,
)
from ed_companion.navigation.mining_planner import (
    plan_mining_routes, OPTIMIZE_MERITS, _powerplay_index, _merit_status,
)


NOW = datetime.now(timezone.utc)


def fact(system="Mine", **fields):
    return {"system": system, "power": "Aisling Duval", "powerState": "Stronghold",
            "controllingPower": "Aisling Duval", "powers": ["Aisling Duval"],
            "coordinates": [0, 0, 0], "observedAt": NOW.isoformat(),
            "source": "EDDN journal/1", **fields}


def market(system="Mine", **fields):
    return {"system": system, "station": "Port", "commodity": "platinum",
            "sellPrice": 200000, "demand": 10000, "observedAt": NOW.isoformat(),
            "coordinates": [0, 0, 0], **fields}


def plan(facts, **fields):
    return plan_mining_routes(
        [{"system": "Mine", "ring": "Mine A Ring", "coordinates": [0, 0, 0]}],
        "Platinum", OPTIMIZE_MERITS, power="Aisling Duval",
        powerplay_systems=facts, **{"power_goal": "REINFORCE", "markets": [market()],
                                   "now": NOW, **fields})[0]


class PowerplayEvidenceTests(unittest.TestCase):
    def test_explicit_unoccupied_without_powers_survives_all_client_stages(self):
        payload = {"event": "FSDJump", "timestamp": NOW.isoformat(),
                   "StarSystem": "Sale", "StarPos": [15, 0, 0],
                   "PowerplayState": "Unoccupied", "Commander": "PRIVATE"}
        rows = project_powerplay_observations(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["power"], "")
        self.assertNotIn("PRIVATE", str(rows))
        self.assertEqual(merge_powerplay_observations([], rows), rows)
        response = Mock(json=Mock(return_value={"results": rows, "hasMore": False}))
        received = fetch_edframe_powerplay(origin=[0, 0, 0], max_distance=250,
                                           get=Mock(return_value=response))
        self.assertEqual(len(received), 1)
        route = plan([fact(), *received], power_goal="ACQUIRE",
                     markets=[market("Sale", coordinates=[15, 0, 0])])
        self.assertEqual(route["verificationStatus"], "VERIFIED")
        self.assertEqual(route["sellSystem"], "Sale")

    def test_unoccupied_other_power_is_a_system_wide_acquire_target(self):
        target = fact("Sale", power="Yuri Grom", controllingPower="",
                      powers=["Yuri Grom"], powerState="Unoccupied", coordinates=[15, 0, 0])
        route = plan([fact(), target], power_goal="ACQUIRE",
                     markets=[market("Sale", coordinates=[15, 0, 0])])
        self.assertEqual(route["meritScore"], 5)

    def test_latest_unoccupied_clears_old_selected_power_control(self):
        old = fact(observedAt=(NOW - timedelta(hours=2)).isoformat())
        unoccupied = fact(power="Yuri Grom", controllingPower="", powers=["Yuri Grom"],
                          powerState="Unoccupied")
        for goal in ("REINFORCE", "UNDERMINE"):
            row = plan([old, unoccupied], power_goal=goal)
            self.assertEqual(row["powerplayStatus"], "NOT_ELIGIBLE")
            self.assertIn("UNOCCUPIED", row["meritStatus"])

    def test_old_control_is_not_freshened_by_new_presence(self):
        old = fact(observedAt=(NOW - timedelta(hours=25)).isoformat())
        presence = fact(controllingPower="", source="EDSM daily PowerPlay catalog",
                        powerRelationship="PRESENCE", controlKnown=False)
        row = plan([old, presence])
        self.assertEqual(row["powerplayStatus"], "POWERPLAY_DATA_MISSING")
        self.assertEqual(row["powerplayEvidenceState"], "STALE")
        self.assertEqual(row["powerplayVerificationLabel"], "POWERPLAY DATA TOO OLD")
        self.assertIn("25 h", row["pendingReason"])

    def test_same_cached_index_becomes_stale_without_any_source_write(self):
        index = _powerplay_index([fact()])
        candidate = {"system": "Mine"}
        sale = {"system": "Mine"}
        status, score, _ = _merit_status(candidate, sale, "Aisling Duval", "REINFORCE", "ANY", index, now=NOW)
        self.assertEqual(score, 5)
        status, score, _ = _merit_status(candidate, sale, "Aisling Duval", "REINFORCE", "ANY", index,
                                        now=NOW + timedelta(hours=24, seconds=1))
        self.assertIsNone(score)
        self.assertIn("TOO OLD", status)

    def test_missing_or_future_source_time_is_never_confirmed(self):
        for stamp in (None, "bad", (NOW + timedelta(minutes=6)).isoformat()):
            row = plan([fact(observedAt=stamp)])
            self.assertIsNone(row["meritScore"])
            self.assertEqual(row["powerplayEvidenceState"], "TIME_UNKNOWN")

    def test_old_acquire_target_remains_pending_and_is_looked_up(self):
        target = fact("Sale", power="", controllingPower="", powers=[],
                      powerState="Unoccupied", coordinates=[15, 0, 0],
                      observedAt=(NOW - timedelta(hours=25)).isoformat())
        row = plan([fact(), target], power_goal="ACQUIRE",
                   markets=[market("Sale", coordinates=[15, 0, 0])])
        self.assertEqual(row["powerplayEvidenceState"], "STALE")
        self.assertEqual(missing_powerplay_targets([row], [fact(), target], now=NOW)[0]["system"], "Sale")

    def test_replaced_participants_cannot_prove_old_contesting_membership(self):
        old = fact(controllingPower="Yuri Grom", powers=["Yuri Grom", "Aisling Duval"],
                   observedAt=(NOW - timedelta(hours=1)).isoformat())
        current = fact(power="Yuri Grom", controllingPower="Yuri Grom", powers=["Yuri Grom"])
        row = plan([old, current], power_goal="UNDERMINE")
        self.assertEqual(row["meritScore"], 0)
        self.assertIn("NOT CONTESTING", row["meritStatus"])

    def test_missing_participant_list_is_not_a_complete_opponent_snapshot(self):
        rows = project_powerplay_observations({"event": "FSDJump", "timestamp": NOW.isoformat(),
            "StarSystem": "Mine", "ControllingPower": "Yuri Grom", "PowerplayState": "Fortified"})
        row = plan(rows, power_goal="UNDERMINE")
        self.assertIsNone(row["meritScore"])
        self.assertIn("CONTESTING POWERS MISSING", row["meritStatus"])

    def test_malformed_or_contradictory_location_does_not_pollute_coverage(self):
        base = {"event": "FSDJump", "timestamp": NOW.isoformat(), "StarSystem": "Mine",
                "PowerplayState": "Fortified", "ControllingPower": "Aisling Duval"}
        for fields in ({"Powers": "Aisling Duval"}, {"PowerplayState": "Invented"},
                       {"StarPos": [float('nan'), 0, 0]}, {"PowerplayState": "Unoccupied"}):
            self.assertEqual(project_powerplay_observations({**base, **fields}), [])

    def test_merge_compares_actual_times_across_offsets_and_fractional_seconds(self):
        old = fact(observedAt="2026-10-09T12:00:00Z")
        newer = fact(controllingPower="Yuri Grom", observedAt="2026-10-09T14:00:00.500+02:00")
        for inputs in ([old, newer], [newer, old]):
            merged = merge_powerplay_observations([], inputs)
            self.assertEqual(len(merged), 1)
            self.assertEqual(merged[0]["controllingPower"], "Yuri Grom")


if __name__ == "__main__":
    unittest.main()
