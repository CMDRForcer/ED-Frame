from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from ed_companion.navigation import mining_planner as planner_module
from ed_companion.navigation.mining_planner import (
    OPTIMIZE_DISTANCE,
    OPTIMIZE_MERITS,
    OPTIMIZE_PROFIT,
    OPTIMIZE_YIELD,
    market_filter_diagnostics,
    plan_mining_routes,
)


NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def candidate(system, distance, target="HOTSPOT", **extra):
    return {
        "system": system,
        "ring": f"{system} A Ring",
        "distanceLy": distance,
        "targetMatch": target,
        "targetMatchName": target,
        "reserveLevel": "PristineResources",
        "evidence": "LIVE_REPORTED",
        "observedAt": "2026-09-30T11:00:00Z",
        **extra,
    }


class MiningPlannerTests(unittest.TestCase):
    def test_verification_contract_covers_all_market_powerplay_pairs(self):
        expected = {
            (planner_module.MARKET_VERIFIED,
             planner_module.POWERPLAY_VERIFIED): "VERIFIED",
            (planner_module.MARKET_TOO_OLD,
             planner_module.POWERPLAY_VERIFIED): "KNOWN",
            (planner_module.MARKET_OUTSIDE_FILTERS,
             planner_module.POWERPLAY_VERIFIED): "KNOWN",
            (planner_module.NO_MARKET_DATA,
             planner_module.POWERPLAY_VERIFIED): "KNOWN",
            (planner_module.MARKET_VERIFIED,
             planner_module.POWERPLAY_DATA_MISSING): "POWERPLAY_DATA_MISSING",
            (planner_module.MARKET_TOO_OLD,
             planner_module.POWERPLAY_DATA_MISSING): "MARKET_TOO_OLD",
            (planner_module.MARKET_OUTSIDE_FILTERS,
             planner_module.POWERPLAY_DATA_MISSING): "MARKET_OUTSIDE_FILTERS",
            (planner_module.NO_MARKET_DATA,
             planner_module.POWERPLAY_DATA_MISSING): "NO_MARKET_DATA",
        }
        for market_status in (
            planner_module.MARKET_VERIFIED,
            planner_module.MARKET_TOO_OLD,
            planner_module.MARKET_OUTSIDE_FILTERS,
            planner_module.NO_MARKET_DATA,
        ):
            for powerplay_status in (
                planner_module.POWERPLAY_VERIFIED,
                planner_module.POWERPLAY_DATA_MISSING,
                planner_module.NOT_ELIGIBLE,
            ):
                with self.subTest(
                    market=market_status, powerplay=powerplay_status,
                ):
                    result = planner_module._verification_status(
                        market_status, powerplay_status,
                        market_reason="market reason",
                        powerplay_reason="powerplay reason",
                    )
                    self.assertEqual(
                        result["state"],
                        "INELIGIBLE" if powerplay_status
                        == planner_module.NOT_ELIGIBLE else expected[
                            (market_status, powerplay_status)
                        ],
                    )
                    self.assertTrue(result["reason"])

    def test_market_boundaries_and_specific_filter_reasons(self):
        base = {
            "commodity": "platinum", "station": "Boundary Hub",
            "system": "Boundary", "sellPrice": 200000,
            "landingPadSize": "L", "observedAt": "2026-09-30T11:00:00Z",
        }
        for demand in (5000, 500000):
            result = planner_module._market_filter_assessment(
                {**base, "demand": demand}, landing_pad="LARGE",
                min_demand=5000, max_demand=500000,
                max_market_age_hours=1, now=NOW,
            )
            self.assertEqual(result["status"], planner_module.MARKET_VERIFIED)
            self.assertTrue(result["matchesFilters"])

        stale = planner_module._market_filter_assessment(
            {**base, "demand": 5000,
             "observedAt": "2026-09-30T10:59:59Z"},
            landing_pad="LARGE", min_demand=5000, max_demand=500000,
            max_market_age_hours=1, now=NOW,
        )
        self.assertEqual(stale["status"], planner_module.MARKET_TOO_OLD)
        self.assertIn("AGE", stale["reasonCodes"])

        cases = [
            ({**base, "demand": 4999}, "DEMAND"),
            ({**base, "demand": 500001}, "DEMAND"),
            ({**base, "demand": 5000, "landingPadSize": "M"}, "PAD"),
            ({**base, "demand": 5000, "fleetCarrier": True}, "CARRIER"),
        ]
        for market, code in cases:
            with self.subTest(code=code):
                result = planner_module._market_filter_assessment(
                    market, landing_pad="LARGE", min_demand=5000,
                    max_demand=500000, max_market_age_hours=1, now=NOW,
                )
                self.assertEqual(
                    result["status"], planner_module.MARKET_OUTSIDE_FILTERS,
                )
                self.assertIn(code, result["reasonCodes"])

    def test_diagnostic_examples_have_honest_independent_statuses(self):
        now = datetime(2026, 10, 3, 16, 30, tzinfo=timezone.utc)
        candidates = [
            candidate("HIP 11402", 10, ring="HIP 11402 A 2 B Ring"),
            candidate("HIP 32145", 20, ring="HIP 32145 4 A Ring"),
            candidate("HIP 32145", 20, ring="HIP 32145 4 B Ring"),
            candidate(
                "Col 285 Sector GV-D b13-4", 30,
                ring="Col 285 Sector GV-D b13-4 3 a",
            ),
        ]
        markets = [{
            "marketId": 4360741123, "commodity": "platinum",
            "system": "HIP 11402", "station": "Raimi Hub",
            "sellPrice": 297710, "demand": 8679,
            "landingPadSize": "L", "observedAt": "2026-10-03T16:00:02Z",
        }, {
            "marketId": 4280268035, "commodity": "platinum",
            "system": "HIP 32145", "station": "Conklin Landing",
            "sellPrice": 59972, "demand": 208803,
            "landingPadSize": "L", "observedAt": "2026-10-03T16:11:32Z",
        }, {
            "marketId": 4212636675, "commodity": "platinum",
            "system": "Col 285 Sector GV-D b13-4",
            "station": "Einäugiger Glatzenaal", "sellPrice": 54548,
            "demand": 81484, "landingPadSize": "L",
            "observedAt": "2026-10-03T15:49:30Z",
        }]
        planned = plan_mining_routes(
            candidates, "Platinum", OPTIMIZE_MERITS,
            min_demand=5000, max_demand=500000,
            max_market_age_hours=1, landing_pad="LARGE",
            power="Aisling Duval", power_goal="REINFORCE",
            markets=markets, powerplay_systems=[{
                "system": "HIP 11402", "power": "Aisling Duval",
                "controllingPower": "Aisling Duval", "powerState": "Stronghold",
            }], now=now,
        )
        by_ring = {row["ring"]: row for row in planned}
        self.assertEqual(
            by_ring["HIP 11402 A 2 B Ring"]["verificationStatus"], "VERIFIED",
        )
        for ring in (
            "HIP 32145 4 A Ring", "HIP 32145 4 B Ring",
            "Col 285 Sector GV-D b13-4 3 a",
        ):
            self.assertEqual(
                by_ring[ring]["marketStatus"], planner_module.MARKET_VERIFIED,
            )
            self.assertEqual(
                by_ring[ring]["verificationStatus"],
                planner_module.POWERPLAY_DATA_MISSING,
            )
            self.assertIn("Market fresh", by_ring[ring]["pendingReason"])

    def test_reconstructed_thirty_route_status_distribution(self):
        candidates = []
        markets = []
        powerplay = []
        for index in range(30):
            system = f"Distribution {index}"
            candidates.append(candidate(system, index + 1))
            if index < 5:
                powerplay.append({
                    "system": system, "power": "Aisling Duval",
                    "controllingPower": "Aisling Duval",
                    "powerState": "Stronghold",
                })
            if index < 14:
                markets.append({
                    "commodity": "platinum", "system": system,
                    "station": f"Hub {index}", "sellPrice": 200000 + index,
                    "demand": 10000, "landingPadSize": "L",
                    "observedAt": "2026-09-30T11:30:00Z",
                })
            elif index < 17:
                markets.append({
                    "commodity": "platinum", "system": system,
                    "station": f"Old Hub {index}", "sellPrice": 200000,
                    "demand": 10000, "landingPadSize": "L",
                    "observedAt": "2026-09-30T10:59:59Z",
                })
            elif index < 23:
                markets.append({
                    "commodity": "platinum", "system": system,
                    "station": f"Low Hub {index}", "sellPrice": 200000,
                    "demand": 4999, "landingPadSize": "L",
                    "observedAt": "2026-09-30T11:30:00Z",
                })
        planned = plan_mining_routes(
            candidates, "Platinum", OPTIMIZE_MERITS,
            min_demand=5000, max_demand=500000,
            max_market_age_hours=1, landing_pad="LARGE",
            power="Aisling Duval", power_goal="REINFORCE",
            markets=markets, powerplay_systems=powerplay,
            result_limit=30, now=NOW,
        )
        counts = {}
        for row in planned:
            counts[row["verificationStatus"]] = (
                counts.get(row["verificationStatus"], 0) + 1
            )
        self.assertEqual(counts, {
            "VERIFIED": 5,
            planner_module.POWERPLAY_DATA_MISSING: 9,
            planner_module.MARKET_TOO_OLD: 3,
            planner_module.MARKET_OUTSIDE_FILTERS: 6,
            planner_module.NO_MARKET_DATA: 7,
        })

    def test_market_diagnostics_distinguish_filtered_from_missing_data(self):
        diagnostics = market_filter_diagnostics(
            [{
                "commodity": "Platinum", "station": "Old Market",
                "system": "Old", "sellPrice": 200000, "demand": 10000,
                "landingPadSize": "L",
                "observedAt": "2026-09-30T08:00:00Z",
            }],
            "Platinum", landing_pad="LARGE", min_demand=5000,
            max_demand=500000, max_market_age_hours=1, now=NOW,
        )

        self.assertEqual(diagnostics["total"], 1)
        self.assertEqual(diagnostics["eligible"], 0)
        self.assertEqual(diagnostics["reason"], "AGE")
        self.assertIn("OUTSIDE THE 1 H AGE LIMIT", diagnostics["summary"])

    def test_shared_markets_are_projected_once_not_once_per_candidate(self):
        candidates = [candidate(f"Mine {index}", index + 1) for index in range(50)]
        markets = [{
            "commodity": "Platinum",
            "station": f"Market {index}",
            "system": f"Sell {index}",
            "sellPrice": 200000 + index,
            "demand": 10000,
            "observedAt": "2026-09-30T11:30:00Z",
        } for index in range(80)]
        original = planner_module.mining_commodity_id
        calls = 0

        def counted(value):
            nonlocal calls
            calls += 1
            return original(value)

        with patch.object(
            planner_module, "mining_commodity_id", side_effect=counted,
        ):
            planned = plan_mining_routes(
                candidates, "Platinum", OPTIMIZE_PROFIT,
                min_demand=5000, max_market_age_hours=2,
                markets=markets, now=NOW,
            )

        self.assertEqual(len(planned), 30)
        self.assertLess(calls, 200)

    def test_secondary_market_catalog_is_indexed_once_per_search(self):
        candidates = [candidate(
            f"Mine {index}", index + 1,
            hotspots=[
                {"commodity": "Platinum"}, {"commodity": "Osmium"},
            ],
        ) for index in range(50)]
        markets = [{
            "marketId": index + 1,
            "commodity": "Platinum" if index % 2 else "Osmium",
            "station": f"Market {index}", "system": f"Sell {index}",
            "sellPrice": 200000 + index, "demand": 10000,
            "observedAt": "2026-09-30T11:30:00Z",
        } for index in range(500)]
        original = planner_module.mining_commodity_id
        calls = 0

        def counted(value):
            nonlocal calls
            calls += 1
            return original(value)

        with patch.object(
            planner_module, "mining_commodity_id", side_effect=counted,
        ):
            planned = plan_mining_routes(
                candidates, "Platinum", OPTIMIZE_PROFIT,
                prefer_secondary=True, markets=markets, now=NOW,
            )

        self.assertEqual(len(planned), 30)
        self.assertLess(calls, 2000)

    def test_acquire_fallback_does_not_rescan_every_market_per_ring(self):
        candidates = [candidate(
            f"Mine {index}", index + 1,
            controllingPower="Aisling Duval", powerState="Exploited",
            coordinates=[index, 0, 0],
        ) for index in range(40)]
        markets = [{
            "commodity": "Platinum",
            "station": f"Market {index}",
            "system": f"Sell {index}",
            "coordinates": [index, 5, 0],
            "sellPrice": 200000 + index,
            "demand": 10000,
            "observedAt": "2026-09-30T11:30:00Z",
        } for index in range(500)]
        original = planner_module._merit_status

        with patch.object(
            planner_module, "_merit_status", wraps=original,
        ) as merit_status:
            planned = plan_mining_routes(
                candidates, "Platinum", OPTIMIZE_MERITS,
                power="Aisling Duval", power_goal="ACQUIRE",
                markets=markets, now=NOW,
            )

        self.assertEqual(len(planned), 30)
        self.assertLessEqual(merit_status.call_count, len(candidates) * 2)

    def test_shared_eddn_market_resolves_price_demand_and_age(self):
        rows = plan_mining_routes(
            [{
                "system": "Mine", "ring": "A Ring", "distanceLy": 10,
                "targetMatch": "HOTSPOT", "ringTypeName": "Metallic",
                "reserveName": "Pristine", "sourceEvidence": "CATALOG_CANDIDATE",
                "observedAt": "2026-10-01T09:00:00Z",
            }],
            "Platinum", "HIGHEST PROFIT", min_demand=5000,
            max_market_age_hours=2, landing_pad="LARGE",
            markets=[{
                "commodity": "platinum", "station": "Sell Here",
                "system": "Market", "sellPrice": 250000,
                "demand": 0, "demandInfinite": True,
                "landingPadSize": "L", "source": "EDDN index",
                "observedAt": "2026-10-01T09:30:00Z",
            }],
            now=datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(rows[0]["marketKnown"])
        self.assertEqual(rows[0]["sellPrice"], 250000)
        self.assertTrue(rows[0]["demandInfinite"])
        self.assertEqual(rows[0]["marketSource"], "EDDN index")
        self.assertIsNotNone(rows[0]["profitScore"])
        self.assertFalse(rows[0]["meritKnown"])

    def test_market_exposes_station_arrival_distance(self):
        rows = plan_mining_routes(
            [candidate("Mine", 10)], "Platinum", OPTIMIZE_PROFIT,
            markets=[{
                "commodity": "Platinum", "station": "Far Orbital",
                "system": "Market", "sellPrice": 250000,
                "demand": 10000, "distanceToArrivalLs": 1234.5,
                "observedAt": "2026-09-30T11:30:00Z",
            }], now=NOW,
        )

        self.assertEqual(rows[0]["stationDistanceLs"], 1234.5)

    def test_route_excludes_carriers_and_exposes_station_metadata(self):
        rows = plan_mining_routes(
            [candidate("Mine", 10)], "Platinum", OPTIMIZE_PROFIT,
            markets=[{
                "commodity": "Platinum", "station": "Carrier",
                "system": "Market", "sellPrice": 999999, "demand": 10000,
                "fleetCarrier": True,
                "observedAt": "2026-09-30T11:30:00Z",
            }, {
                "commodity": "Platinum", "station": "Safe Port",
                "system": "Market", "sellPrice": 250000, "demand": 10000,
                "stationType": "Coriolis", "landingPadSize": "L",
                "distanceToArrivalLs": 321.5, "services": ["Commodities"],
                "economies": ["Industrial"], "primaryEconomy": "Industrial",
                "government": "Democracy", "controllingFaction": "Test",
                "fleetCarrier": False, "carrierDockingAccess": "all",
                "statusFlags": ["Docked"],
                "receivedAt": "2026-09-30T11:30:01Z",
                "observedAt": "2026-09-30T11:30:00Z",
            }], now=NOW,
        )

        self.assertEqual(rows[0]["station"], "Safe Port")
        self.assertEqual(rows[0]["stationType"], "Coriolis")
        self.assertEqual(rows[0]["landingPadSize"], "L")
        self.assertEqual(rows[0]["stationServices"], ["Commodities"])
        self.assertEqual(rows[0]["marketStatusFlags"], ["Docked"])
        self.assertFalse(rows[0]["fleetCarrier"])

    def test_powerplay_verified_groups_sort_pending_before_ineligible(self):
        rows = [
            candidate("Rejected", 1, controllingPower="Aisling Duval",
                      powerState="Headquarters", markets=[{
                          "commodity": "Platinum", "station": "HQ Port",
                          "system": "Rejected", "sellPrice": 300000,
                          "demand": 20000,
                          "observedAt": "2026-09-30T11:30:00Z",
                      }]),
            candidate("Pending", 2, controllingPower="Aisling Duval",
                      powerState="Fortified"),
            candidate("Verified", 20, markets=[{
                "commodity": "Platinum", "station": "Verified Port",
                "system": "Verified", "sellPrice": 150000,
                "demand": 5000, "meritEligible": True,
                "observedAt": "2026-09-30T11:30:00Z",
            }]),
        ]

        planned = plan_mining_routes(
            rows, "Platinum", OPTIMIZE_MERITS,
            power="Aisling Duval", power_goal="REINFORCE", now=NOW,
        )

        self.assertEqual(
            [row["system"] for row in planned],
            ["Verified", "Pending", "Rejected"],
        )
        self.assertEqual(
            [row["powerplayVerificationState"] for row in planned],
            ["VERIFIED", "NO_MARKET_DATA", "INELIGIBLE"],
        )
        self.assertEqual(
            planned[1]["powerplayVerificationLabel"],
            "NO MARKET DATA",
        )

    def test_all_commodities_selects_a_concrete_ring_and_market_pair(self):
        planned = plan_mining_routes(
            [candidate(
                "Multi Mine", 10, controllingPower="Aisling Duval",
                powerState="Fortified", candidateCommodities=[
                    {"id": "platinum", "evidence": "HOTSPOT"},
                    {"id": "painite", "evidence": "RING_TYPE"},
                ],
            )],
            "ALL COMMODITIES", OPTIMIZE_MERITS,
            power="Aisling Duval", power_goal="REINFORCE",
            max_market_age_hours=1, markets=[{
                "commodity": "platinum", "station": "Old Platinum Port",
                "system": "Multi Mine", "sellPrice": 300000,
                "demand": 20000,
                "observedAt": "2026-09-30T08:00:00Z",
            }, {
                "commodity": "painite", "station": "Current Painite Port",
                "system": "Multi Mine", "sellPrice": 200000,
                "demand": 10000,
                "observedAt": "2026-09-30T11:30:00Z",
            }], now=NOW,
        )

        self.assertEqual(planned[0]["selectedCommodity"], "painite")
        self.assertEqual(planned[0]["selectedCommodityName"], "Painite")
        self.assertEqual(planned[0]["station"], "Current Painite Port")
        self.assertTrue(planned[0]["marketMatchesFilters"])
        self.assertEqual(
            planned[0]["powerplayVerificationState"], "VERIFIED",
        )

    def test_stale_or_low_demand_market_is_not_presented_as_a_route(self):
        planned = plan_mining_routes(
            [candidate(
                "Known Mine", 10, controllingPower="Aisling Duval",
                powerState="Fortified",
            )],
            "Platinum", OPTIMIZE_MERITS,
            power="Aisling Duval", power_goal="REINFORCE",
            min_demand=5000, max_market_age_hours=1,
            markets=[{
                "commodity": "platinum", "station": "Known Port",
                "system": "Known Mine", "sellPrice": 220000,
                "demand": 1000,
                "observedAt": "2026-09-29T11:30:00Z",
            }], now=NOW,
        )

        self.assertFalse(planned[0]["marketKnown"])
        self.assertFalse(planned[0]["marketMatchesFilters"])
        self.assertEqual(planned[0]["marketReliabilityState"], "MISSING")
        self.assertIsNone(planned[0]["profitScore"])
        self.assertEqual(
            planned[0]["powerplayVerificationState"], "MARKET_TOO_OLD",
        )

    def test_plain_mining_result_survives_without_market_claims(self):
        rows = plan_mining_routes(
            [candidate("Mining Only", 12)], "Platinum", OPTIMIZE_YIELD,
            min_demand=5000, max_market_age_hours=1, now=NOW,
        )

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["marketKnown"])
        self.assertIsNone(rows[0]["profitScore"])
        self.assertIsNone(rows[0]["meritScore"])
        self.assertEqual(rows[0]["profitStars"], "—")
        self.assertEqual(rows[0]["meritStars"], "—")

    def test_optimization_changes_ranking_without_parallel_search_paths(self):
        rows = [
            candidate("Strong Far", 80, target="LOCAL_YIELD"),
            candidate("Weak Near", 5, target="RING_TYPE"),
        ]

        yield_first = plan_mining_routes(
            rows, "Platinum", OPTIMIZE_YIELD, now=NOW,
        )
        distance_first = plan_mining_routes(
            rows, "Platinum", OPTIMIZE_DISTANCE, now=NOW,
        )

        self.assertEqual(yield_first[0]["system"], "Strong Far")
        self.assertEqual(distance_first[0]["system"], "Weak Near")

    def test_profit_uses_only_fresh_market_with_required_demand(self):
        rows = [candidate("Fresh", 20, markets=[{
            "commodity": "Platinum", "station": "Fresh Hub",
            "sellPrice": 220000, "demand": 9000,
            "observedAt": "2026-09-30T11:30:00Z",
        }]), candidate("Stale", 10, markets=[{
            "commodity": "Platinum", "station": "Old Hub",
            "sellPrice": 500000, "demand": 50000,
            "observedAt": "2026-09-29T11:30:00Z",
        }])]

        planned = plan_mining_routes(
            rows, "Platinum", OPTIMIZE_PROFIT, min_demand=5000,
            max_market_age_hours=2, now=NOW,
        )

        self.assertEqual(planned[0]["system"], "Fresh")
        self.assertTrue(planned[0]["marketKnown"])
        stale = next(row for row in planned if row["system"] == "Stale")
        self.assertFalse(stale["marketKnown"])
        self.assertIsNone(stale["profitScore"])

    def test_merit_rating_requires_explicit_or_supported_power_evidence(self):
        rows = [candidate("Confirmed", 20, markets=[{
            "commodity": "Platinum", "station": "Power Hub",
            "sellPrice": 200000, "demand": 9000,
            "observedAt": "2026-09-30T11:30:00Z", "meritEligible": True,
        }]), candidate("Unknown", 5, markets=[{
            "commodity": "Platinum", "station": "Unknown Hub",
            "sellPrice": 250000, "demand": 12000,
            "observedAt": "2026-09-30T11:30:00Z",
        }])]

        planned = plan_mining_routes(
            rows, "Platinum", OPTIMIZE_MERITS, min_demand=1000,
            max_market_age_hours=2, power="Nakato Kaine",
            power_goal="Reinforce", now=NOW,
        )

        self.assertEqual(planned[0]["system"], "Confirmed")
        self.assertEqual(planned[0]["meritStars"], "★★★★★")
        self.assertEqual(planned[0]["mineToSellLy"], 0.0)
        self.assertFalse(planned[1]["meritKnown"])

    def test_same_system_market_distance_is_zero_without_coordinates(self):
        planned = plan_mining_routes(
            [candidate("Local Mine", 10, markets=[{
                "commodity": "Platinum", "station": "Local Port",
                "system": "Local Mine", "sellPrice": 220000,
                "demand": 12000,
                "observedAt": "2026-09-30T11:30:00Z",
            }])],
            "Platinum", OPTIMIZE_PROFIT, now=NOW,
        )

        self.assertTrue(planned[0]["marketKnown"])
        self.assertEqual(planned[0]["mineToSellLy"], 0.0)

    def test_cross_system_market_uses_known_coordinates_for_distance(self):
        planned = plan_mining_routes(
            [candidate(
                "Mine", 10, coordinates=[0, 0, 0], markets=[{
                    "commodity": "Platinum", "station": "Remote Port",
                    "system": "Remote", "coordinates": [3, 4, 0],
                    "sellPrice": 220000, "demand": 12000,
                    "observedAt": "2026-09-30T11:30:00Z",
                }],
            )],
            "Platinum", OPTIMIZE_PROFIT, now=NOW,
        )

        self.assertEqual(planned[0]["mineToSellLy"], 5.0)

    def test_partial_power_match_never_becomes_a_merit_claim(self):
        planned = plan_mining_routes([candidate("Power Context", 10, markets=[{
            "commodity": "Platinum", "station": "Context Hub",
            "sellPrice": 200000, "demand": 9000,
            "observedAt": "2026-09-30T11:30:00Z",
            "controllingPower": "Nakato Kaine",
            "powerState": "Reinforcement",
        }])], "Platinum", OPTIMIZE_MERITS, power="Nakato Kaine",
            power_goal="Reinforce", now=NOW)

        self.assertFalse(planned[0]["meritKnown"])
        self.assertIsNone(planned[0]["meritScore"])
        self.assertIn("UNKNOWN", planned[0]["meritStatus"])

    def test_reinforce_requires_mining_and_sale_in_same_controlled_system(self):
        row = candidate(
            "Aisling Mine", 10, controllingPower="Aisling Duval",
            powerState="Fortified", coordinates=[0, 0, 0], markets=[{
                "commodity": "Platinum", "station": "Local Port",
                "system": "Aisling Mine", "sellPrice": 180000,
                "demand": 12000, "observedAt": "2026-09-30T11:30:00Z",
            }, {
                "commodity": "Platinum", "station": "Remote Port",
                "system": "Remote", "sellPrice": 300000,
                "demand": 20000, "observedAt": "2026-09-30T11:30:00Z",
            }],
        )

        planned = plan_mining_routes(
            [row], "Platinum", OPTIMIZE_MERITS, power="Aisling Duval",
            power_goal="REINFORCE", now=NOW,
        )

        self.assertEqual(planned[0]["station"], "Local Port")
        self.assertEqual(planned[0]["meritScore"], 5.0)
        self.assertEqual(planned[0]["mineToSellLy"], 0.0)

    def test_power_presence_never_becomes_reinforce_control(self):
        row = candidate("Contested Mine", 10, coordinates=[0, 0, 0], markets=[{
            "commodity": "Platinum", "station": "Local Port",
            "system": "Contested Mine", "sellPrice": 180000,
            "demand": 12000, "observedAt": "2026-09-30T11:30:00Z",
        }])
        catalog = [{
            "system": "Contested Mine", "power": "Aisling Duval",
            "powerState": "Stronghold", "coordinates": [0, 0, 0],
            "powerRelationship": "PRESENCE", "controlKnown": False,
        }, {
            "system": "Contested Mine", "power": "Yuri Grom",
            "powerState": "Stronghold", "coordinates": [0, 0, 0],
            "powerRelationship": "PRESENCE", "controlKnown": False,
        }]

        planned = plan_mining_routes(
            [row], "Platinum", OPTIMIZE_MERITS, power="Aisling Duval",
            power_goal="REINFORCE", powerplay_systems=catalog, now=NOW,
        )

        self.assertFalse(planned[0]["meritKnown"])
        self.assertIsNone(planned[0]["meritScore"])
        self.assertIn("CONTROLLING POWER MISSING", planned[0]["meritStatus"])

    def test_power_presence_never_becomes_acquire_source_control(self):
        row = candidate("Presence Only", 10, coordinates=[0, 0, 0])
        catalog = [{
            "system": "Presence Only", "power": "Aisling Duval",
            "powerState": "Stronghold", "coordinates": [0, 0, 0],
            "powerRelationship": "PRESENCE", "controlKnown": False,
        }, {
            "system": "Acquire Target", "power": "Aisling Duval",
            "powerState": "Unoccupied", "coordinates": [25, 0, 0],
            "powerRelationship": "PRESENCE", "controlKnown": False,
        }]
        markets = [{
            "commodity": "Platinum", "station": "Target Port",
            "system": "Acquire Target", "coordinates": [25, 0, 0],
            "sellPrice": 200000, "demand": 12000,
            "observedAt": "2026-09-30T11:30:00Z",
        }]

        planned = plan_mining_routes(
            [row], "Platinum", OPTIMIZE_MERITS, power="Aisling Duval",
            power_goal="ACQUIRE", powerplay_systems=catalog,
            markets=markets, now=NOW,
        )

        self.assertFalse(planned[0]["meritKnown"])
        self.assertIsNone(planned[0]["meritScore"])
        self.assertIn("CONTROLLING POWER MISSING", planned[0]["meritStatus"])

    def test_same_system_merit_goals_never_offer_a_remote_sell_market(self):
        for goal, opposing_power in (
            ("REINFORCE", "ANY"),
            ("UNDERMINE", "Felicia Winters"),
        ):
            with self.subTest(goal=goal):
                row = candidate(
                    "Mining System", 10,
                    controllingPower=(
                        "Aisling Duval" if goal == "REINFORCE"
                        else "Felicia Winters"
                    ),
                    powerState="Fortified",
                    powers=["Felicia Winters", "Aisling Duval"],
                    markets=[{
                        "commodity": "Platinum", "station": "Remote Port",
                        "system": "Remote System", "sellPrice": 300000,
                        "demand": 20000,
                        "observedAt": "2026-09-30T11:30:00Z",
                    }],
                )

                planned = plan_mining_routes(
                    [row], "Platinum", OPTIMIZE_MERITS,
                    power="Aisling Duval", power_goal=goal,
                    opposing_power=opposing_power, now=NOW,
                )

                self.assertFalse(planned[0]["marketKnown"])
                self.assertEqual(planned[0]["station"], "")
                self.assertEqual(planned[0]["sellSystem"], "")
                self.assertTrue(planned[0]["sameSystemSaleRequired"])
                self.assertFalse(planned[0]["meritKnown"])
                self.assertIn(
                    "SAME-SYSTEM SELL MARKET NOT VERIFIED",
                    planned[0]["meritStatus"],
                )

    def test_reinforce_shared_market_is_limited_to_the_mining_system(self):
        planned = plan_mining_routes(
            [candidate(
                "Local System", 10, controllingPower="Aisling Duval",
                powerState="Fortified",
            )],
            "Platinum", OPTIMIZE_MERITS, power="Aisling Duval",
            power_goal="REINFORCE", markets=[{
                "commodity": "Platinum", "station": "Remote Rich Port",
                "system": "Remote System", "sellPrice": 350000,
                "demand": 30000,
                "observedAt": "2026-09-30T11:30:00Z",
            }, {
                "commodity": "Platinum", "station": "Local Port",
                "system": "Local System", "sellPrice": 180000,
                "demand": 12000,
                "observedAt": "2026-09-30T11:30:00Z",
            }],
            now=NOW,
        )

        self.assertEqual(planned[0]["station"], "Local Port")
        self.assertEqual(planned[0]["sellSystem"], "Local System")
        self.assertEqual(planned[0]["meritScore"], 5.0)

    def test_acquire_keeps_the_cross_system_sell_route(self):
        row = candidate(
            "Stronghold Source", 10, controllingPower="Aisling Duval",
            powerState="Stronghold", coordinates=[0, 0, 0], markets=[{
                "commodity": "Platinum", "station": "Acquire Port",
                "system": "Expansion Target", "sellPrice": 200000,
                "demand": 12000,
                "observedAt": "2026-09-30T11:30:00Z",
            }],
        )
        planned = plan_mining_routes(
            [row], "Platinum", OPTIMIZE_MERITS, power="Aisling Duval",
            power_goal="ACQUIRE", powerplay_systems=[{
                "system": "Expansion Target", "power": "Aisling Duval",
                "powerState": "Unoccupied", "coordinates": [25, 0, 0],
            }], now=NOW,
        )

        self.assertTrue(planned[0]["marketKnown"])
        self.assertFalse(planned[0]["sameSystemSaleRequired"])
        self.assertEqual(planned[0]["sellSystem"], "Expansion Target")
        self.assertEqual(planned[0]["meritScore"], 5.0)

    def test_headquarters_is_known_but_not_a_reinforcement_target(self):
        row = candidate(
            "Cubeo", 0, controllingPower="Aisling Duval",
            powerState="Headquarters", coordinates=[0, 0, 0], markets=[{
                "commodity": "Platinum", "station": "Chelomey Orbital",
                "system": "Cubeo", "sellPrice": 180000,
                "demand": 12000, "observedAt": "2026-09-30T11:30:00Z",
            }],
        )

        planned = plan_mining_routes(
            [row], "Platinum", OPTIMIZE_MERITS, power="Aisling Duval",
            power_goal="REINFORCE", now=NOW,
        )

        self.assertTrue(planned[0]["meritKnown"])
        self.assertEqual(planned[0]["meritScore"], 0.0)
        self.assertIn("HEADQUARTERS CANNOT BE REINFORCED", planned[0]["meritStatus"])

    def test_acquire_pairs_stronghold_source_with_unoccupied_target_in_30ly(self):
        row = candidate(
            "Stronghold Mine", 10, controllingPower="Aisling Duval",
            powerState="Stronghold", coordinates=[0, 0, 0], markets=[{
                "commodity": "Platinum", "station": "Acquire Port",
                "system": "Target", "sellPrice": 200000, "demand": 12000,
                "observedAt": "2026-09-30T11:30:00Z",
            }],
        )
        catalog = [{
            "system": "Target", "power": "Aisling Duval",
            "powerState": "Unoccupied", "coordinates": [25, 0, 0],
            "systemState": "Expansion",
        }]

        planned = plan_mining_routes(
            [row], "Platinum", OPTIMIZE_MERITS, power="Aisling Duval",
            power_goal="ACQUIRE", powerplay_systems=catalog,
            system_state="EXPANSION", now=NOW,
        )

        self.assertEqual(planned[0]["meritScore"], 5.0)
        self.assertEqual(planned[0]["mineToSellLy"], 25.0)
        self.assertIn("25.0/30 LY", planned[0]["meritStatus"])

    def test_headquarters_supplies_the_same_acquisition_radius_as_stronghold(self):
        row = candidate(
            "Cubeo", 0, controllingPower="Aisling Duval",
            powerState="Headquarters", coordinates=[0, 0, 0], markets=[{
                "commodity": "Platinum", "station": "Acquire Port",
                "system": "Target", "sellPrice": 200000, "demand": 12000,
                "observedAt": "2026-09-30T11:30:00Z",
            }],
        )
        catalog = [{
            "system": "Target", "power": "Aisling Duval",
            "powerState": "Unoccupied", "coordinates": [25, 0, 0],
        }]

        planned = plan_mining_routes(
            [row], "Platinum", OPTIMIZE_MERITS, power="Aisling Duval",
            power_goal="ACQUIRE", powerplay_systems=catalog, now=NOW,
        )

        self.assertEqual(planned[0]["meritScore"], 5.0)
        self.assertIn("25.0/30 LY", planned[0]["meritStatus"])

    def test_acquire_rejects_target_beyond_fortified_20ly_limit(self):
        row = candidate(
            "Fortified Mine", 10, controllingPower="Aisling Duval",
            powerState="Fortified", coordinates=[0, 0, 0], markets=[{
                "commodity": "Platinum", "station": "Far Port",
                "system": "Far Target", "sellPrice": 200000,
                "demand": 12000, "observedAt": "2026-09-30T11:30:00Z",
            }],
        )
        catalog = [{
            "system": "Far Target", "power": "Aisling Duval",
            "powerState": "Unoccupied", "coordinates": [21, 0, 0],
        }]

        planned = plan_mining_routes(
            [row], "Platinum", OPTIMIZE_MERITS, power="Aisling Duval",
            power_goal="ACQUIRE", powerplay_systems=catalog, now=NOW,
        )

        self.assertEqual(planned[0]["meritScore"], 0.0)
        self.assertIn("EXCEEDS 20 LY", planned[0]["meritStatus"])

    def test_undermine_requires_same_opposing_system_and_contesting_power(self):
        row = candidate(
            "Enemy Mine", 10, controllingPower="Felicia Winters",
            powerState="Fortified", powers=["Felicia Winters", "Aisling Duval"],
            markets=[{
                "commodity": "Platinum", "station": "Enemy Port",
                "system": "Enemy Mine", "sellPrice": 200000,
                "demand": 12000, "observedAt": "2026-09-30T11:30:00Z",
            }],
        )

        planned = plan_mining_routes(
            [row], "Platinum", OPTIMIZE_MERITS, power="Aisling Duval",
            power_goal="UNDERMINE", opposing_power="Felicia Winters", now=NOW,
        )

        self.assertEqual(planned[0]["meritScore"], 5.0)
        self.assertIn("FELICIA WINTERS", planned[0]["meritStatus"])

    def test_authoritative_live_fact_overrides_edsm_presence_for_undermine(self):
        row = candidate("HR 6948", 10, markets=[{
            "commodity": "Platinum", "station": "Atwater Terminal",
            "system": "HR 6948", "sellPrice": 57966,
            "demand": 17479, "observedAt": "2026-09-30T11:30:00Z",
        }])
        powerplay = [{
            "system": "HR 6948", "power": "Aisling Duval",
            "powerState": "Exploited", "powerRelationship": "PRESENCE",
            "controlKnown": False,
        }, {
            "system": "HR 6948", "power": "Aisling Duval",
            "powerState": "Exploited", "controllingPower": "Yuri Grom",
            "powers": ["Yuri Grom", "Aisling Duval"],
            "powerRelationship": "PRESENCE", "controlKnown": True,
            "observedAt": "2026-10-02T12:00:00Z",
        }]

        planned = plan_mining_routes(
            [row], "Platinum", OPTIMIZE_MERITS, power="Aisling Duval",
            power_goal="UNDERMINE", opposing_power="Yuri Grom",
            powerplay_systems=powerplay, now=NOW,
        )

        self.assertEqual(planned[0]["meritScore"], 5.0)
        self.assertIn("YURI GROM", planned[0]["meritStatus"])

    def test_requested_pad_requires_confirmed_market_access(self):
        planned = plan_mining_routes([candidate("Unknown Pad", 10, markets=[{
            "commodity": "Platinum", "station": "Orbital",
            "sellPrice": 200000, "demand": 9000,
            "observedAt": "2026-09-30T11:30:00Z",
        }])], "Platinum", OPTIMIZE_PROFIT, landing_pad="LARGE", now=NOW)

        self.assertFalse(planned[0]["marketKnown"])

    def test_market_choice_follows_the_selected_goal(self):
        row = candidate("Two Markets", 10, markets=[{
            "commodity": "Platinum", "station": "Merit Port",
            "sellPrice": 150000, "demand": 9000,
            "observedAt": "2026-09-30T11:30:00Z", "meritEligible": True,
        }, {
            "commodity": "Platinum", "station": "Profit Port",
            "sellPrice": 300000, "demand": 9000,
            "observedAt": "2026-09-30T11:30:00Z",
        }])

        merit = plan_mining_routes([row], "Platinum", OPTIMIZE_MERITS, now=NOW)
        profit = plan_mining_routes([row], "Platinum", OPTIMIZE_PROFIT, now=NOW)

        self.assertEqual(merit[0]["station"], "Merit Port")
        self.assertEqual(profit[0]["station"], "Profit Port")

    def test_hotspot_filter_keeps_observed_yield_and_hotspots_only(self):
        planned = plan_mining_routes([
            candidate("Observed", 5, target="LOCAL_YIELD"),
            candidate("Hotspot", 6, target="HOTSPOT"),
            candidate("Ring", 1, target="RING_TYPE"),
        ], "Platinum", OPTIMIZE_YIELD, require_hotspot=True, now=NOW)

        self.assertEqual(
            {row["system"] for row in planned}, {"Observed", "Hotspot"}
        )

    def test_ring_filter_is_applied_before_route_ranking(self):
        planned = plan_mining_routes([
            candidate("Metallic", 8, ringTypeName="Metallic"),
            candidate("Icy", 4, ringTypeName="Icy"),
        ], "Platinum", OPTIMIZE_DISTANCE, ring_filter="METALLIC", now=NOW)

        self.assertEqual([row["system"] for row in planned], ["Metallic"])

    def test_rings_only_hides_belts_without_removing_normal_rings(self):
        planned = plan_mining_routes([
            candidate(
                "Ring System", 8, ringTypeName="Metallic",
                miningSiteType="RING",
            ),
            candidate(
                "Belt System", 4, ringTypeName="Metallic",
                miningSiteType="BELT", ring="Belt System A Belt Cluster 1",
            ),
        ], "Platinum", OPTIMIZE_DISTANCE, rings_only=True, now=NOW)

        self.assertEqual([row["system"] for row in planned], ["Ring System"])

    def test_optional_secondary_and_system_state_filters_are_real(self):
        rows = [
            candidate("With State", 10, systemState="Boom", hotspots=[
                {"commodity": "Platinum"}, {"commodity": "Painite"},
            ]),
            candidate("Without State", 9, hotspots=[{"commodity": "Platinum"}]),
        ]

        planned = plan_mining_routes(
            rows, "Platinum", OPTIMIZE_YIELD, prefer_secondary=True,
            require_system_state=True, now=NOW,
        )

        self.assertEqual([row["system"] for row in planned], ["With State"])
        self.assertTrue(planned[0]["secondaryPreferred"])
        self.assertEqual(planned[0]["secondaryCommodityCount"], 1)
        self.assertEqual(planned[0]["secondaryCommodityNames"], ["Painite"])
        self.assertEqual(
            planned[0]["secondaryCommodities"][0]["evidenceLabel"],
            "HOTSPOT",
        )

    def test_all_commodities_never_counts_selected_primary_as_secondary(self):
        planned = plan_mining_routes(
            [candidate("Multi", 4, hotspots=[
                {"commodity": "Platinum"}, {"commodity": "Painite"},
            ])],
            "ALL COMMODITIES", OPTIMIZE_PROFIT,
            prefer_secondary=True, min_demand=1000,
            max_market_age_hours=2, markets=[{
                "marketId": 42, "commodity": "Painite",
                "station": "Shared Port", "system": "Sell",
                "sellPrice": 300000, "demand": 5000,
                "observedAt": "2026-09-30T11:30:00Z",
            }, {
                "marketId": 42, "commodity": "Platinum",
                "station": "Shared Port", "system": "Sell",
                "sellPrice": 200000, "demand": 5000,
                "observedAt": "2026-09-30T11:30:00Z",
            }], now=NOW,
        )

        self.assertEqual(planned[0]["selectedCommodity"], "painite")
        self.assertEqual(planned[0]["secondaryCommodityNames"], ["Platinum"])
        self.assertEqual(planned[0]["secondaryCommodityCount"], 1)
        self.assertEqual(planned[0]["secondaryMarketCount"], 1)
        self.assertEqual(
            planned[0]["secondaryCommodities"][0]["sellPrice"], 200000,
        )

    def test_secondary_sale_requires_the_selected_route_station(self):
        planned = plan_mining_routes(
            [candidate("Mine", 4, hotspots=[
                {"commodity": "Platinum"}, {"commodity": "Osmium"},
            ])],
            "Platinum", OPTIMIZE_PROFIT,
            prefer_secondary=True, min_demand=1000,
            max_market_age_hours=2, markets=[{
                "marketId": 1, "commodity": "Platinum",
                "station": "Primary Port", "system": "Sell",
                "sellPrice": 250000, "demand": 5000,
                "observedAt": "2026-09-30T11:30:00Z",
            }, {
                "marketId": 2, "commodity": "Osmium",
                "station": "Other Port", "system": "Sell",
                "sellPrice": 300000, "demand": 5000,
                "observedAt": "2026-09-30T11:30:00Z",
            }], now=NOW,
        )

        secondary = planned[0]["secondaryCommodities"][0]
        self.assertEqual(secondary["name"], "Osmium")
        self.assertFalse(secondary["marketKnown"])
        self.assertEqual(planned[0]["secondaryMarketCount"], 0)

    def test_more_resources_prefers_a_route_that_sells_the_extras_together(self):
        def route(name, market_id, include_osmium):
            markets = [{
                "marketId": market_id, "commodity": "Platinum",
                "station": f"{name} Port", "system": name,
                "sellPrice": 250000, "demand": 5000,
                "observedAt": "2026-09-30T11:30:00Z",
            }]
            if include_osmium:
                markets.append({
                    "marketId": market_id, "commodity": "Osmium",
                    "station": f"{name} Port", "system": name,
                    "sellPrice": 200000, "demand": 5000,
                    "observedAt": "2026-09-30T11:30:00Z",
                })
            return candidate(
                name, 5, hotspots=[
                    {"commodity": "Platinum"}, {"commodity": "Osmium"},
                ], markets=markets,
            )

        planned = plan_mining_routes(
            [route("Uncovered", 1, False), route("Covered", 2, True)],
            "Platinum", OPTIMIZE_PROFIT, prefer_secondary=True,
            min_demand=1000, max_market_age_hours=2, now=NOW,
        )

        self.assertEqual(planned[0]["system"], "Covered")
        self.assertEqual(planned[0]["secondaryMarketCount"], 1)


class MiningFinderUiContractTests(unittest.TestCase):
    def test_unified_page_replaces_split_modes_and_shows_ratings(self):
        root = Path(__file__).resolve().parents[1]
        qml = (root / "qml/pages/MiningFinderPage.qml").read_text(
            encoding="utf-8"
        )
        main = (root / "Main.qml").read_text(encoding="utf-8-sig")

        self.assertIn("OPTIMIZE FOR", qml)
        self.assertIn("POWERPLAY MERITS", qml)
        self.assertIn("BEST YIELD", qml)
        self.assertIn("HIGHEST PROFIT", qml)
        self.assertIn("SHORTEST ROUTE", qml)
        self.assertIn("YIELD QUALITY", qml)
        self.assertIn("PROFITABILITY", qml)
        self.assertIn("MERIT SUITABILITY", qml)
        self.assertIn("DATA CONFIDENCE", qml)
        self.assertIn("function applySearch()", qml)
        self.assertIn('property string appliedCommodityFilter: "Platinum"', qml)
        self.assertIn("appliedCommodityFilter = commodityFilter", qml)
        self.assertIn('id: startSystemField', qml)
        self.assertIn('appliedStartSystem = startSystem.trim()', qml)
        self.assertIn('cockpit.miningSystemSuggestions(startSystem, 8)', qml)
        self.assertIn('id: systemSuggestionsPopup', qml)
        self.assertIn('miningFinderPage.chooseStartSystem(', qml)
        self.assertIn('cockpit.miningMarketDiagnostics(', qml)
        self.assertIn('"NO MARKET MATCHES ACTIVE FILTERS"', qml)
        self.assertIn("row.sameSystemSaleRequired", qml)
        self.assertIn('"NO VERIFIED SAME-SYSTEM MARKET"', qml)
        self.assertIn("readonly property bool marketQueryPending", qml)
        self.assertIn('"CHECKING SAME-SYSTEM MARKETS"', qml)
        self.assertIn("Layout.maximumWidth: routeSaleWidth", qml)
        self.assertIn(
            'appliedStartSystem, appliedCommodityFilter, appliedNearbyLy', qml,
        )
        self.assertIn('miningMethod === "RHINO SURFACE"', qml)
        self.assertIn('reserveFilter = "ALL RESERVES"', qml)
        self.assertIn('property bool requireHotspot: false', qml)
        self.assertIn('property int nearbyLy: 250', qml)
        self.assertIn("appliedRequireHotspot", qml)
        self.assertIn('id: ringBox', qml)
        self.assertIn('property bool ringsOnly: true', qml)
        self.assertIn('appWindow.t("mining.rings_only", "RINGS ONLY")', qml)
        self.assertIn('cockpit.verifyMiningRoutes(', qml)
        self.assertIn('"POWERPLAY VERIFIED"', qml)
        self.assertNotIn('"MARKET CHECK PENDING"', qml)
        self.assertIn('"POWERPLAY DATA MISSING"', qml)
        self.assertIn('"MARKET TOO OLD"', qml)
        self.assertIn('"NO MARKET DATA"', qml)
        self.assertIn('section.property: "verificationGroupLabel"', qml)
        self.assertIn("stationDistanceLs", qml)
        self.assertIn("selectedCommodityName", qml)
        self.assertIn("marketQualityStatus", qml)
        self.assertIn('property string selectedRouteKey: ""', qml)
        self.assertIn('property bool searchGoalExpanded: true', qml)
        self.assertIn('searchGoalExpanded = false', qml)
        self.assertIn('id: toggleSearchGoalButton', qml)
        self.assertIn('appWindow.t("mining.edit_search", "EDIT SEARCH")', qml)
        self.assertIn('id: catalogCoverageBadge', qml)
        self.assertIn('catalogCoverage.recordCompleteness', qml)
        self.assertIn('routeCoverage.marketPercent', qml)
        self.assertIn('not total galaxy coverage', qml)
        self.assertIn(': 48', qml)
        self.assertIn('miningRingFiltersForCommodity', qml)
        self.assertIn('"MORE RESOURCES"', qml)
        self.assertIn('function secondaryMiningSummary(row)', qml)
        self.assertIn('function secondarySaleSummary(row)', qml)
        self.assertIn('secondaryCommodityNames', qml)
        self.assertIn('"ALSO AT THIS STATION"', qml)
        self.assertIn('"SYSTEM STATE"', qml)
        self.assertIn("Layout.maximumHeight: 280", qml)
        self.assertIn("width: routesList.width; height: 68", qml)
        self.assertIn("Layout.minimumHeight: 120", qml)
        self.assertIn("PRICE / T", qml)
        self.assertIn("DATA AGE", qml)
        self.assertIn("MiningFinderPage {", main)
        self.assertNotIn("ColonisationPage {", main)
        self.assertNotIn('{"id": "colonisation"', main)

    def test_page_content_is_bounded_and_empty_state_stays_compact(self):
        root = Path(__file__).resolve().parents[1]
        qml = (root / "qml/pages/MiningFinderPage.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn('id: pageContent', qml)
        self.assertIn(
            'width: miningFinderPage.availableWorkspaceWidth', qml,
        )
        self.assertNotIn('availableWorkspaceWidth, 1580', qml)
        self.assertIn('anchors.fill: parent', qml)
        self.assertIn('Layout.maximumHeight: 220', qml)
        self.assertIn('Layout.preferredHeight: childrenRect.height', qml)
        self.assertIn('appWindow.t("mining.landing_pad", "LANDING PAD")', qml)
        self.assertIn(
            'appWindow.t("mining.powerplay_goal", "POWERPLAY GOAL")', qml,
        )
        self.assertIn(
            'appWindow.t("mining.opposing_power", "OPPOSING POWER")', qml,
        )
        self.assertIn(
            'appWindow.t("mining.max_demand", "MAX. DEMAND")', qml,
        )
        self.assertIn('gesturePolicy: TapHandler.DragThreshold', qml)
        self.assertIn(
            'onTapped: miningFinderPage.selectRoute(modelData)', qml,
        )
        self.assertIn(
            'appWindow.t("mining.copy_sell", "COPY SELL")', qml,
        )
        self.assertIn('function marketRouteName(row)', qml)
        self.assertIn('return system + " · " + market', qml)
        self.assertIn('text: marketRouteName(bestRoute)', qml)
        self.assertIn('component SmoothFilterSlider: ColumnLayout', qml)
        self.assertIn('snapMode: Slider.NoSnap', qml)
        self.assertIn('onPressedChanged:', qml)
        self.assertNotIn('onMoved:', qml)
        self.assertIn('width: Math.min(parent.width, 720)', qml)
        self.assertIn('searchRevision === 0', qml)
        self.assertIn('"READY TO PLAN A MINING ROUTE"', qml)
        self.assertIn('"NO MATCHING MINING EVIDENCE"', qml)
        self.assertIn('if (searchRevision === 0)', qml)
        self.assertIn('trackThickness: 12', qml)
        self.assertIn('thumbThickness: 8', qml)
        self.assertIn('function marketStationSummary(row)', qml)

    def test_connections_exposes_edsm_as_a_first_class_catalog_status(self):
        root = Path(__file__).resolve().parents[1]
        qml = (root / "Main.qml").read_text(encoding="utf-8-sig")
        self.assertIn(
            'text: window.t("connections.spansh_source_tab", "SPANSH")', qml
        )
        self.assertIn(
            'text: window.t("connections.edsm_tab", "EDSM")', qml
        )
        self.assertIn('connectionsPage.connectionMode = 5', qml)
        self.assertIn('"UPDATE EDSM CATALOG"', qml)
        self.assertIn('cockpit.miningPowerplaySyncStatus', qml)
        self.assertIn('cockpit.miningPowerplaySystemCount', qml)
        self.assertIn('cockpit.miningPowerplayLastRefresh', qml)

    def test_mining_header_and_connections_expose_edframe_fallback_state(self):
        root = Path(__file__).resolve().parents[1]
        main_qml = (root / "Main.qml").read_text(encoding="utf-8-sig")
        mining_qml = (
            root / "qml" / "pages" / "MiningFinderPage.qml"
        ).read_text(encoding="utf-8-sig")
        controller = (
            root / "ed_companion" / "phase14" / "controller_navigation.py"
        ).read_text(encoding="utf-8-sig")
        self.assertIn('"LOCAL %1 · DATA %2% · ROUTES %3"', mining_qml)
        self.assertIn('cockpit.edFrameCatalogOnline', mining_qml)
        self.assertIn('cockpit.miningCurrentAction', mining_qml)
        self.assertIn('cockpit.setEdFrameCatalogEnabled(checked)', main_qml)
        self.assertIn('cockpit.edFrameCatalogLog', main_qml)
        self.assertIn('"Disabled · local catalog active"', controller)
        self.assertIn('include_edframe=getattr(', controller)


if __name__ == "__main__":
    unittest.main()
