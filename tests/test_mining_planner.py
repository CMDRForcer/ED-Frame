from datetime import datetime, timezone
from pathlib import Path
import unittest

from ed_companion.navigation.mining_planner import (
    OPTIMIZE_DISTANCE,
    OPTIMIZE_MERITS,
    OPTIMIZE_PROFIT,
    OPTIMIZE_YIELD,
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
        self.assertFalse(planned[1]["meritKnown"])

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
        self.assertIn(
            'appliedStartSystem, appliedCommodityFilter, appliedNearbyLy', qml,
        )
        self.assertIn('miningMethod === "RHINO SURFACE"', qml)
        self.assertIn('reserveFilter = "ALL RESERVES"', qml)
        self.assertIn('property bool requireHotspot: false', qml)
        self.assertIn('property int nearbyLy: 250', qml)
        self.assertIn("appliedRequireHotspot", qml)
        self.assertIn('id: ringBox', qml)
        self.assertIn('miningRingFiltersForCommodity', qml)
        self.assertIn('"MORE RESOURCES"', qml)
        self.assertIn('"SYSTEM STATE"', qml)
        self.assertIn("Layout.maximumHeight: 318", qml)
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
            'width: Math.min(miningFinderPage.availableWorkspaceWidth, 1580)',
            qml,
        )
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
        self.assertIn(
            'onClicked: miningFinderPage.selectRoute(modelData)', qml,
        )
        self.assertIn(
            'appWindow.t("mining.copy_sell", "COPY SELL")', qml,
        )
        self.assertIn('component SmoothFilterSlider: ColumnLayout', qml)
        self.assertIn('snapMode: Slider.NoSnap', qml)
        self.assertIn('onPressedChanged:', qml)
        self.assertNotIn('onMoved:', qml)
        self.assertIn('width: Math.min(parent.width, 720)', qml)


if __name__ == "__main__":
    unittest.main()
