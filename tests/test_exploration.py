import unittest
from pathlib import Path

from ed_companion.exploration import exploration_ledger


def _scan(system, address, body_id, body_name, timestamp="2026-09-20T10:00:00Z", **extra):
    event = {
        "event": "Scan", "timestamp": timestamp, "ScanType": "Detailed",
        "StarSystem": system, "SystemAddress": address,
        "BodyID": body_id, "BodyName": body_name,
        "PlanetClass": "High metal content body",
        "MassEM": 1.0,
        "WasDiscovered": False, "WasMapped": False,
    }
    event.update(extra)
    return event


class ExplorationLedgerTests(unittest.TestCase):
    def test_scan_retains_value_evidence_and_reports_a_range(self):
        ledger = exploration_ledger([_scan(
            "Test A", 10, 2, "Test A 2", TerraformState="Terraformable",
            DistanceFromArrivalLS=123.5, Landable=True,
        )])

        self.assertEqual(ledger["summary"]["systemCount"], 1)
        self.assertEqual(ledger["summary"]["bodyCount"], 1)
        self.assertEqual(ledger["summary"]["valueStatus"], "range")
        body = ledger["findings"][0]
        self.assertEqual(body["terraformState"], "Terraformable")
        self.assertEqual(body["distanceFromArrivalLs"], 123.5)
        self.assertTrue(body["possibleFirstDiscovery"])
        self.assertGreater(body["estimatedValueMax"], body["estimatedValueMin"])
        self.assertIsNone(body["estimatedValue"])

    def test_nav_beacon_detail_is_not_counted_as_owned_scan_data(self):
        event = _scan("Test A", 10, 2, "Test A 2", ScanType="NavBeaconDetail")
        ledger = exploration_ledger([event])

        self.assertEqual(ledger["findings"], [])
        self.assertEqual(ledger["summary"]["bodyCount"], 0)

    def test_surface_mapping_and_signal_details_merge_into_the_body(self):
        events = [
            _scan("Test A", 10, 2, "Test A 2"),
            {
                "event": "SAASignalsFound", "timestamp": "2026-09-20T10:01:00Z",
                "SystemAddress": 10, "BodyID": 2, "BodyName": "Test A 2",
                "Signals": [{
                    "Type": "$SAA_SignalType_Biological;",
                    "Type_Localised": "Biological", "Count": 3,
                }],
                "Genuses": [{"Genus": "$Genus;", "Genus_Localised": "Aleoida"}],
            },
            {
                "event": "SAAScanComplete", "timestamp": "2026-09-20T10:02:00Z",
                "SystemAddress": 10, "BodyID": 2, "BodyName": "Test A 2",
                "ProbesUsed": 4, "EfficiencyTarget": 6,
            },
        ]

        body = exploration_ledger(events)["findings"][0]
        self.assertTrue(body["mapped"])
        self.assertTrue(body["efficiencyBonus"])
        self.assertTrue(body["possibleFirstMapped"])
        self.assertEqual(body["signals"][0]["count"], 3)
        self.assertEqual(body["genuses"][0]["name"], "Aleoida")

    def test_signal_before_scan_is_preserved_when_scan_arrives(self):
        events = [
            {
                "event": "FSSBodySignals", "timestamp": "2026-09-20T09:59:00Z",
                "StarSystem": "Test A", "SystemAddress": 10,
                "BodyID": 2, "BodyName": "Test A 2",
                "Signals": [{"Type": "$Signal;", "Count": 1}],
            },
            _scan("Test A", 10, 2, "Test A 2"),
        ]

        body = exploration_ledger(events)["findings"][0]
        self.assertTrue(body["hasScan"])
        self.assertEqual(body["signals"][0]["count"], 1)

    def test_sale_removes_only_the_named_system(self):
        events = [
            _scan("Test A", 10, 2, "Test A 2"),
            _scan("Test B", 11, 1, "Test B 1"),
            {
                "event": "MultiSellExplorationData",
                "timestamp": "2026-09-20T11:00:00Z",
                "Discovered": [{"SystemName": "Test A", "NumBodies": 1}],
                "BaseValue": 100, "Bonus": 20, "TotalEarnings": 120,
            },
        ]

        ledger = exploration_ledger(events)
        self.assertEqual(
            [row["systemName"] for row in ledger["findings"]], ["Test B"]
        )
        self.assertEqual(ledger["summary"]["lastSale"]["totalEarnings"], 120)

    def test_scan_after_sale_becomes_unsold_again(self):
        events = [
            _scan("Test A", 10, 2, "Test A 2"),
            {
                "event": "SellExplorationData",
                "timestamp": "2026-09-20T11:00:00Z", "Systems": ["Test A"],
            },
            _scan(
                "Test A", 10, 3, "Test A 3",
                timestamp="2026-09-20T12:00:00Z",
            ),
        ]

        findings = exploration_ledger(events)["findings"]
        self.assertEqual([row["bodyName"] for row in findings], ["Test A 3"])

    def test_plain_died_and_rejoin_do_not_erase_cartography(self):
        events = [
            _scan("Test A", 10, 2, "Test A 2"),
            {"event": "Died", "timestamp": "2026-09-20T11:00:00Z"},
            {
                "event": "Resurrect", "timestamp": "2026-09-20T11:01:00Z",
                "Option": "rejoin", "Cost": 0,
            },
        ]

        self.assertEqual(exploration_ledger(events)["summary"]["bodyCount"], 1)

    def test_confirmed_ship_rebuy_erases_unsold_cartography(self):
        events = [
            _scan("Test A", 10, 2, "Test A 2"),
            {"event": "Died", "timestamp": "2026-09-20T11:00:00Z"},
            {
                "event": "Resurrect", "timestamp": "2026-09-20T11:01:00Z",
                "Option": "rebuy", "Cost": 1000,
            },
        ]

        ledger = exploration_ledger(events)
        self.assertEqual(ledger["findings"], [])
        self.assertEqual(
            ledger["summary"]["lastLoss"]["timestamp"],
            "2026-09-20T11:01:00Z",
        )

    def test_known_odyssey_mapped_body_includes_efficiency_and_first_bonus_range(self):
        events = [
            {
                "event": "Fileheader", "timestamp": "2026-09-20T09:00:00Z",
                "Odyssey": True, "gameversion": "4.2.0.0",
            },
            _scan(
                "Test A", 10, 2, "Test A 2", PlanetClass="Earthlike body",
                MassEM=1.0,
            ),
            {
                "event": "SAAScanComplete", "timestamp": "2026-09-20T10:02:00Z",
                "SystemAddress": 10, "BodyID": 2, "BodyName": "Test A 2",
                "ProbesUsed": 4, "EfficiencyTarget": 6,
            },
        ]

        body = exploration_ledger(events)["findings"][0]

        self.assertEqual(body["valueStatus"], "range")
        self.assertEqual(body["estimatedValueMin"], 1536321)
        self.assertEqual(body["estimatedValueMax"], 4433370)
        self.assertIn("EARTH_LIKE", body["tags"])
        self.assertIn("MAPPED", body["tags"])
        self.assertIn("EFFICIENCY_BONUS", body["tags"])

    def test_previously_discovered_unmapped_planet_has_exact_estimate(self):
        events = [
            {"event": "Fileheader", "Odyssey": False, "gameversion": "3.8"},
            _scan(
                "Test A", 10, 2, "Test A 2", MassEM=1.0,
                WasDiscovered=True, WasMapped=True,
            ),
        ]

        body = exploration_ledger(events)["findings"][0]

        self.assertEqual(body["valueStatus"], "estimated")
        self.assertEqual(body["estimatedValue"], body["estimatedValueMin"])
        self.assertEqual(body["estimatedValueMin"], body["estimatedValueMax"])
        self.assertEqual(body["estimatedValue"], 15117)

    def test_belt_cluster_is_classified_as_zero_value(self):
        body = exploration_ledger([_scan(
            "Test A", 10, 5, "Test A A Belt Cluster 1",
            PlanetClass="", MassEM=None,
        )])["findings"][0]

        self.assertEqual(body["bodyKind"], "belt")
        self.assertEqual(body["findingClass"], "Belt cluster")
        self.assertEqual(body["estimatedValue"], 0)

    def test_missing_mass_is_partial_not_a_fabricated_zero(self):
        ledger = exploration_ledger([
            _scan("Test A", 10, 2, "Test A 2", MassEM=1.0),
            _scan("Test A", 10, 3, "Test A 3", MassEM=None),
        ])

        unknown = next(row for row in ledger["findings"] if row["bodyId"] == 3)
        self.assertEqual(unknown["valueStatus"], "unavailable")
        self.assertIsNone(unknown["estimatedValueMin"])
        self.assertEqual(ledger["summary"]["valueStatus"], "partial")
        self.assertEqual(ledger["summary"]["unvaluedBodyCount"], 1)

    def test_signal_and_high_value_tags_are_ready_for_details_ui(self):
        events = [
            _scan(
                "Test A", 10, 2, "Test A 2", PlanetClass="Water world",
                TerraformState="Terraformable", MassEM=1.0,
            ),
            {
                "event": "FSSBodySignals", "SystemAddress": 10,
                "BodyID": 2, "BodyName": "Test A 2",
                "Signals": [
                    {"Type": "$SAA_SignalType_Biological;", "Count": 3},
                    {"Type": "$SAA_SignalType_Geological;", "Count": 2},
                ],
            },
        ]

        body = exploration_ledger(events)["findings"][0]

        self.assertTrue(body["highValue"])
        self.assertEqual(body["biologicalSignalCount"], 3)
        self.assertEqual(body["geologicalSignalCount"], 2)
        self.assertIn("WATER_WORLD", body["tags"])
        self.assertIn("TERRAFORMABLE", body["tags"])


class ExplorationUiContractTests(unittest.TestCase):
    def test_exploration_page_shows_systems_findings_and_estimate_disclaimer(self):
        root = Path(__file__).resolve().parents[1]
        qml = (root / "qml" / "pages" / "ExplorationPage.qml").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn("cockpit.explorationSystems", qml)
        self.assertIn("cockpit.explorationFindings", qml)
        self.assertIn("estimatedValueMin", qml)
        self.assertIn("estimatedValueMax", qml)
        self.assertIn("exploration.estimate_notice", qml)

    def test_main_qml_registers_a_lazy_exploration_page(self):
        root = Path(__file__).resolve().parents[1]
        qml = (root / "Main.qml").read_text(encoding="utf-8-sig")

        self.assertIn('{"id": "exploration"', qml)
        self.assertIn("active: window.currentPage === 16", qml)
        self.assertIn("ExplorationPage {", qml)


if __name__ == "__main__":
    unittest.main()
