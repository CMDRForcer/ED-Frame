import unittest
from pathlib import Path

from ed_companion.integrations.eddn import supports_event
from ed_companion.navigation.mining_contract import (
    LOCAL_MINING_EVENT_FIELDS,
    MINING_EVIDENCE_LEVELS,
    MINING_FRESHNESS_SECONDS,
    MINING_FINDER_OPEN_QUESTIONS,
    MINING_SOURCE_POLICY,
    mining_finder_contract,
)


class MiningFinderContractTests(unittest.TestCase):
    def test_market_status_keeps_complete_conditional_binding(self):
        source = (Path(__file__).resolve().parents[1] / 'qml/pages/MiningFinderPage.qml').read_text(encoding='utf-8')
        self.assertRegex(source, r'text: resultRows\.length > 0 && cockpit\.miningPlanBusy\s+'
                         r'\? appWindow\.t\("mining\.updating_routes", [^\n]+\)\s+'
                         r': cockpit\.miningMarketSyncBusy\s+'
                         r'\? appWindow\.t\("mining\.market_checking"')

    def test_search_modes_keep_region_filters_without_quick_search_bar(self):
        source = (Path(__file__).resolve().parents[1] / 'qml/pages/MiningFinderPage.qml').read_text(encoding='utf-8')
        self.assertNotIn('objectName: "qa-mining-quick-search"', source)
        self.assertIn('"MEASURED PLATINUM", "PLATINUM + RES"', source)
        preset = source.split('function selectOptimization(value) {', 1)[1].split('function resetForMethod', 1)[0]
        for retained in ('nearbyLy', 'startSystem', 'minDemand', 'powerOverride'):
            self.assertNotIn(retained + ' =', preset)

    def test_evidence_levels_do_not_claim_guaranteed_yield(self):
        self.assertEqual(MINING_EVIDENCE_LEVELS, (
            "LOCAL_CONFIRMED", "LIVE_REPORTED", "CATALOG_CANDIDATE",
        ))
        self.assertNotIn("GUARANTEED", MINING_EVIDENCE_LEVELS)
        self.assertEqual(MINING_FRESHNESS_SECONDS["LIVE_REPORTED"], 86400)

    def test_only_existing_public_mining_observations_use_eddn(self):
        self.assertEqual(
            MINING_SOURCE_POLICY["eddn"]["events"],
            ("Scan", "SAASignalsFound", "FSSBodySignals"),
        )
        for event_name in MINING_SOURCE_POLICY["eddn"]["events"]:
            self.assertTrue(supports_event({"event": event_name}))
        for local_only in (
            "ProspectedAsteroid", "MiningRefined", "Cargo", "MarketSell",
        ):
            self.assertNotIn(local_only, MINING_SOURCE_POLICY["eddn"]["events"])

    def test_contract_excludes_identity_and_localised_fields(self):
        forbidden = {
            "Commander", "FID", "PrivateGroup", "Type_Localised",
            "Name_Localised", "SRVType_Localised",
        }
        for fields in LOCAL_MINING_EVENT_FIELDS.values():
            self.assertTrue(forbidden.isdisjoint(fields))

    def test_rhino_unknowns_are_explicit_and_contract_is_serialisable(self):
        self.assertTrue(any("Rhino" in item for item in MINING_FINDER_OPEN_QUESTIONS))
        contract = mining_finder_contract()
        self.assertIn("frontier_journal", contract["sources"])
        self.assertIn("spansh", contract["sources"])
        self.assertNotIn("inara", contract["sources"])


if __name__ == "__main__":
    unittest.main()
