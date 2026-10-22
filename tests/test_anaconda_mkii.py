"""Launch reference and physical module identity regressions for Anaconda Mk II."""
import json
import unittest
from pathlib import Path

from ed_companion.journal.fleet import rebuild_fleet
from ed_companion.loadout_export import build_loadout_export
from ed_companion.module_identity import canonical_module_id, same_module_identity
from ed_companion.navigation.shipyard_finder import (
    build_module_catalog, build_ship_catalog, evaluate_ship_access,
    module_catalog_with_ship_fit, module_fit_reference,
)
from ed_companion.phase14.state_fleet import (
    latest_loadout_slots_by_ship, module_purchase_identity,
    module_store_core_replacement, ship_slot_layout, slot_power_mw,
)
from tools.build_module_fit_reference import merge_reference_supplement


DATA = Path(__file__).resolve().parents[1] / "ed_data"


class AnacondaMkIITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ships = json.loads((DATA / "ships.json").read_text())
        cls.ship = next(s for s in cls.ships if s["symbol"] == "AnacondaMkII")
        cls.slots = ship_slot_layout(cls.ship, [], [])
        cls.display = json.loads((DATA / "module_display.json").read_text())
        cls.catalog = build_module_catalog(cls.display, include_hull_armour=True)

    def fit(self, symbol, ship="anacondamkii"):
        row = next(r for r in self.catalog if r["symbol"] == symbol)
        return module_catalog_with_ship_fit([row], self.slots, ship)[0]

    def test_frontier_symbol_resolves_in_fleet_without_guessing(self):
        fleet = rebuild_fleet([{
            "event": "Loadout", "timestamp": "2026-10-21T12:00:00Z",
            "Ship": "anacondamkii", "ShipID": 18,
        }], self.ships)
        self.assertEqual(fleet["ships"][0]["type"], "Anaconda Mk II")

    def test_early_access_has_no_invented_credit_price_or_wrong_schematic(self):
        prices = json.loads((DATA / "ship_reference_prices.json").read_text())
        ship = next(s for s in build_ship_catalog(self.ships, prices)
                    if s["symbol"] == "anacondamkii")
        self.assertNotIn("referencePrice", ship)
        self.assertEqual(ship["schematicSource"], "assets/ships/AnacondaMkII.svg")
        self.assertTrue((DATA.parent / ship["schematicSource"]).is_file())
        self.assertEqual(evaluate_ship_access(ship, {})["purchaseStatus"], "ARX EARLY ACCESS")
        self.assertEqual(evaluate_ship_access(ship, {})["purchaseTone"], "UNKNOWN")

    def test_ship_graphic_renders_with_transparent_margins(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer
        renderer = QSvgRenderer(str(DATA.parent / "assets/ships/AnacondaMkII.svg"))
        self.assertTrue(renderer.isValid())
        image = QImage(600, 400, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        self.assertTrue(any(image.pixelColor(x, 200).alpha() > 0 for x in range(250, 350)))
        # Both bow spars are visible; the opening between them stays clear.
        self.assertEqual(image.pixelColor(300, 60).alpha(), 0)
        self.assertTrue(any(image.pixelColor(x, 60).alpha() > 0 for x in range(260, 295)))
        self.assertTrue(any(image.pixelColor(x, 60).alpha() > 0 for x in range(305, 340)))
        # Fleet cards magnify schematics by 1.28. The safety canvas must
        # still leave clear edges, otherwise the bow/stern get clipped.
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.translate(300, 200)
        painter.scale(1.28, 1.28)
        painter.translate(-300, -200)
        from PySide6.QtCore import QRectF
        renderer.render(painter, QRectF(0, 0, 600, 400))
        painter.end()
        self.assertTrue(all(image.pixelColor(x, y).alpha() == 0
                            for x in range(600) for y in (0, 399)))

    def test_graphic_uses_existing_native_vector_style(self):
        import xml.etree.ElementTree as ET
        root = ET.parse(DATA.parent / "assets/ships/AnacondaMkII.svg").getroot()
        self.assertEqual(root.attrib["viewBox"], "0 0 1200 800")
        self.assertEqual(root.attrib["color"], "#47d7ed")
        self.assertFalse(any(n.tag.rsplit("}", 1)[-1] in {"image", "filter", "script"}
                             for n in root.iter()))
        paths = list(root.iter("{http://www.w3.org/2000/svg}path"))
        self.assertGreater(len(paths), 100)
        self.assertEqual({n.attrib["stroke"] for n in paths}, {"currentColor"})
        self.assertEqual({n.attrib["stroke-width"] for n in paths}, {"1.2", "3.2"})
        for n in paths:
            self.assertEqual(n.attrib["stroke-linejoin"], "round")
            if n.attrib["fill"] != "none":
                self.assertEqual(n.attrib["fill"], "#47d7ed")
                self.assertEqual(n.attrib["fill-opacity"], "0.16")

    def test_complete_physical_layout_and_restricted_slot_names(self):
        by_group = {}
        for row in self.slots:
            by_group.setdefault(row["group"], []).append(row)
        self.assertEqual(len({s["slot"] for s in self.slots}), len(self.slots))
        self.assertEqual([s["slotSize"] for s in by_group["HARDPOINTS"]], [4, 3, 3, 3, 3, 1, 1])
        self.assertEqual(len(by_group["UTILITY MOUNTS"]), 8)
        self.assertEqual([s["slotSize"] for s in by_group["CORE INTERNALS"]], [0, 8, 7, 8, 5, 8, 8, 6])
        optional = {s["slot"]: s for s in by_group["OPTIONAL INTERNALS"]}
        self.assertEqual(len(optional), 15)  # Includes military and approach suite.
        self.assertEqual(optional["Cargo01"]["slotSize"], 6)
        self.assertEqual(optional["Cargo01"]["restriction"], "cargo")
        for name in ("Military01", "Military02"):
            self.assertEqual(optional[name]["slotSize"], 5)
            self.assertEqual(optional[name]["restriction"], "military")
        self.assertEqual(optional["Slot11_Size1"]["slotSize"], 1)
        self.assertEqual(optional["PlanetaryApproachSuite"]["restriction"], "planetaryApproachSuite")

    def test_journal_and_desired_modules_bind_to_real_cargo_slot(self):
        events = [{"event": "Loadout", "ShipID": 18, "Ship": "AnacondaMkII",
                   "Modules": [{"Slot": "Cargo01", "Item": "Int_LargeCargoRack_Size6_Class1"}]}]
        installed = latest_loadout_slots_by_ship(events)["18"]
        slots = ship_slot_layout(self.ship, installed, [], {"Cargo01": "int_fueltank_size6_class3"})
        cargo = next(s for s in slots if s["slot"] == "Cargo01")
        self.assertFalse(cargo["empty"])
        self.assertEqual(cargo["desiredSourceSlot"], "Cargo01")
        self.assertTrue(cargo["moduleChange"])

    def test_cargo_slot_rejects_other_equipment_but_accepts_tank(self):
        for symbol, expected in (
            ("int_largecargorack_size6_class1", "FITS"),
            ("int_cargorack_size6_class1", "FITS"),
            ("int_fueltank_size6_class3", "FITS"),
            ("int_largecargorack_size7_class1", "INCOMPATIBLE"),
            ("int_shieldgenerator_size5_class5", "INCOMPATIBLE"),
        ):
            with self.subTest(symbol=symbol):
                self.assertEqual(self.fit(symbol)["currentShipSlotFits"]["Cargo01"]["status"], expected)
        self.assertEqual(self.fit("int_largecargorack_size6_class1")["currentShipSlotFits"]["Military01"]["status"], "INCOMPATIBLE")

    def test_mkii_modules_are_not_freely_approved_on_other_hulls(self):
        for symbol in ("int_largecargorack_size6_class1", "hpt_miningtoolv2_fixed_large"):
            with self.subTest(symbol=symbol):
                self.assertEqual(self.fit(symbol)["currentShipFitStatus"], "FITS")
                self.assertEqual(self.fit(symbol, "anaconda")["currentShipFitStatus"], "INCOMPATIBLE")

    def test_rack_capacity_is_reference_not_an_invented_hull_maximum(self):
        ref = module_fit_reference()
        self.assertEqual(ref["ships"]["anacondamkii"]["hullMass"], 940)
        for size, capacity in ((6, 96), (7, 192), (8, 384)):
            self.assertEqual(ref["modules"][f"int_largecargorack_size{size}_class1"]["cargoCapacity"], capacity)
        self.assertNotIn("maxCargo", self.ship)
        self.assertNotIn("heatCapacity", self.ship)

    def test_standard_and_ablative_armour_never_share_identity(self):
        for hull in ("anacondamkii", "explorer_nx"):
            with self.subTest(hull=hull):
                standard = f"{hull}_armour_grade1_default"
                ablative = f"{hull}_armour_grade1"
                self.assertFalse(same_module_identity(standard, ablative))
                self.assertTrue(same_module_identity(standard, "ship_armour_grade1"))
                self.assertEqual(module_purchase_identity(ablative), ("MK II ABLATIVE LIGHTWEIGHT ALLOY", "1C"))
                self.assertEqual(module_purchase_identity(standard), ("LIGHTWEIGHT ALLOYS", "1C"))
                self.assertEqual(slot_power_mw({"moduleId": ablative})[0], 0)
        self.assertTrue(same_module_identity("lakonminer_armour_grade1", "ship_armour_grade1"))

    def test_armour_store_restores_standard_and_clears_engineering(self):
        ship = "AnacondaMkII"
        replacement = module_store_core_replacement({"Slot": "Armour", "Ship": ship})
        self.assertEqual(replacement, "AnacondaMkII_armour_grade1_default")
        events = [
            {"event": "Loadout", "ShipID": 18, "Ship": ship, "Modules": [{
                "Slot": "Armour", "Item": "AnacondaMkII_Armour_Grade1",
                "Engineering": {"Level": 5, "BlueprintName": "Armour_HeavyDuty"},
            }]},
            {"event": "ModuleStore", "ShipID": 18, "Ship": ship,
             "Slot": "Armour", "StoredItem": "AnacondaMkII_Armour_Grade1"},
        ]
        armour = latest_loadout_slots_by_ship(events)["18"][0]
        self.assertEqual(armour["moduleId"], "ship_armour_grade1")
        self.assertFalse(armour["engineered"])

    def test_armour_export_does_not_copy_engineering_to_another_variant(self):
        events = [{"event": "Loadout", "ShipID": 18, "Ship": "AnacondaMkII",
                   "Modules": [{"Slot": "Armour", "Item": "AnacondaMkII_Armour_Grade1",
                                "Engineering": {"Level": 5, "BlueprintName": "Armour_HeavyDuty"}}]}]
        payload = build_loadout_export(events, 18, "AnacondaMkII", [{
            "slot": "Armour", "moduleId": "ship_armour_grade1",
        }], [])
        self.assertNotIn("Engineering", payload["Modules"][0])

    def test_armour_browser_exposes_distinct_hull_variants_not_generic_aliases(self):
        standard = self.fit("anacondamkii_armour_grade1_default")
        ablative = self.fit("anacondamkii_armour_grade1")
        self.assertNotEqual(standard["displayName"], ablative["displayName"])
        self.assertEqual(ablative["currentShipFitStatus"], "FITS")
        self.assertEqual(self.fit("anacondamkii_armour_grade1", "anaconda")["currentShipFitStatus"], "INCOMPATIBLE")
        self.assertFalse(any(r["symbol"].startswith("ship_armour_") for r in self.catalog))

    def test_reviewed_supplement_is_included_in_generated_reference(self):
        supplement = json.loads((DATA / "module_fit_reference_supplement.json").read_text())
        ref = module_fit_reference()
        self.assertEqual(len(supplement["source"]["sha256"]), 64)
        for section in ("ships", "modules"):
            for symbol, fields in supplement[section].items():
                for key, value in fields.items():
                    self.assertEqual(ref[section][symbol][key], value, (symbol, key))

    def test_reference_refresh_preserves_future_permissions_and_updated_power(self):
        reference = {"ships": {}, "modules": {
            "repeater": {"allowedShips": ["lakonminer", "future_ship"], "power": 2.0},
        }}
        supplement = {"source": {"url": "reviewed-source"}, "ships": {}, "modules": {
            "repeater": {"allowedShips": ["lakonminer", "anacondamkii"]},
        }}
        merge_reference_supplement(reference, supplement)
        self.assertEqual(reference["modules"]["repeater"]["allowedShips"],
                         ["lakonminer", "future_ship", "anacondamkii"])
        self.assertEqual(reference["modules"]["repeater"]["power"], 2.0)
