import unittest
from types import SimpleNamespace

from ed_companion.navigation.shipyard_finder import build_module_catalog, module_catalog_with_ship_fit, module_fit_reference


class ModuleFitRulesTests(unittest.TestCase):
    def project(self, symbol, family, slots, ship="adder", group="OPTIONAL", core="", **kwargs):
        return module_catalog_with_ship_fit([{
            "symbol": symbol, "moduleFamily": family, "moduleClass": 3,
            "moduleGroup": group, "moduleCoreSlot": core,
        }], slots, ship, **kwargs)[0]

    def test_reference_is_pinned_and_contains_real_mass_limits(self):
        data = module_fit_reference()
        self.assertEqual(len(data["commit"]), 40)
        self.assertEqual(len(data["rulesCommit"]), 40)
        self.assertEqual(data["ships"]["adder"]["hullMass"], 35)
        self.assertEqual(data["modules"]["int_shieldgenerator_size3_class5"]["maxmass"], 413)

    def test_fighter_hangar_and_luxury_hull_rules(self):
        slots = [{"group": "OPTIONAL INTERNALS", "slot": "Slot01_Size6", "slotSize": 6, "empty": True}]
        for symbol, family, allowed in (("int_fighterbay_size5_class1", "FIGHTER HANGAR", "anaconda"),
                                        ("int_passengercabin_size5_class4", "LUXURY CLASS PASSENGER CABIN", "orca")):
            self.assertEqual(self.project(symbol, family, slots)["currentShipFitStatus"], "INCOMPATIBLE")
            self.assertEqual(self.project(symbol, family, slots, allowed)["currentShipFitStatus"], "FITS")
            self.assertEqual(self.project(symbol, family, slots, "")["currentShipFitStatus"], "UNKNOWN")

    def test_singleton_replacement_not_second_installation(self):
        symbol = "int_shieldgenerator_size3_class5"
        slots = [{"group": "OPTIONAL INTERNALS", "slot": "A", "slotSize": 3, "moduleId": symbol},
                 {"group": "OPTIONAL INTERNALS", "slot": "B", "slotSize": 3, "empty": True}]
        result = self.project(symbol, "SHIELD GENERATOR", slots)
        self.assertEqual(result["currentShipSlotFits"]["A"]["status"], "FITS")
        self.assertEqual(result["currentShipSlotFits"]["B"]["status"], "INCOMPATIBLE")
        self.assertIn("limit", result["currentShipSlotFits"]["B"]["reason"])

    def test_shield_hull_mass_is_not_total_ship_mass(self):
        slots = [{"group": "OPTIONAL INTERNALS", "slot": "A", "slotSize": 3, "empty": True}]
        self.assertEqual(self.project("int_shieldgenerator_size3_class5", "SHIELD GENERATOR", slots, "type9")["currentShipFitStatus"], "INCOMPATIBLE")
        self.assertEqual(self.project("int_shieldgenerator_size3_class5", "SHIELD GENERATOR", slots, "unknown_new_ship")["currentShipFitStatus"], "UNKNOWN")

    def test_thruster_laden_mass_boundary_and_stale_snapshot(self):
        symbol = "int_engine_size3_class5"
        slots = [{"group": "CORE INTERNALS", "slot": "MainEngines", "slotSize": 3, "moduleId": symbol}]
        for mass, status in ((170, "FITS"), (170.01, "INCOMPATIBLE")):
            row = self.project(symbol, "THRUSTERS", slots, group="CORE", core="MainEngines", ship_stats={
                "unladenMass": mass, "cargoCapacity": 0, "fuelCapacity": {"Main": 10}, "modules": {"MainEngines": symbol}})
            self.assertEqual(row["currentShipFitStatus"], status)
        self.assertEqual(self.project(symbol, "THRUSTERS", slots, group="CORE", core="MainEngines")["currentShipFitStatus"], "UNKNOWN")
        slots[0]["engineered"] = True
        self.assertEqual(self.project(symbol, "THRUSTERS", slots, group="CORE", core="MainEngines", ship_stats={
            "unladenMass": 100, "cargoCapacity": 0, "fuelCapacity": 0, "modules": {"MainEngines": symbol}})["currentShipFitStatus"], "UNKNOWN")

    def test_unknown_module_and_energy_do_not_become_guarantees(self):
        slot = [{"group": "OPTIONAL INTERNALS", "slot": "A", "slotSize": 3, "empty": True}]
        row = self.project("new_module", "NEW MODULE", slot)
        self.assertEqual(row["currentShipFitStatus"], "UNKNOWN")
        self.assertIn("not verified", row["powerWarning"])

    def test_armour_uses_hull_identity_not_size_zero(self):
        cat = build_module_catalog({}, include_hull_armour=True)
        slots = [{"group": "CORE INTERNALS", "slot": "Armour", "slotSize": 0}]
        own = next(row for row in cat if row["symbol"] == "adder_armour_grade1")
        result = module_catalog_with_ship_fit([own], slots, "adder")[0]
        self.assertEqual(result["currentShipFitStatus"], "FITS")
        self.assertEqual(result["referencePrice"], 0)
        self.assertIn("EDSY", result["referencePriceSource"])
        self.assertEqual(module_catalog_with_ship_fit([own], slots, "anaconda")[0]["currentShipFitStatus"], "INCOMPATIBLE")

    def test_energy_over_budget_is_warning_not_fit_exclusion(self):
        reference = {"modules": {"candidate": {"power": 20}, "reactor": {"pgen": 10, "power": 0}}, "ships": {"adder": {"hullMass": 35}}}
        slots = [{"group": "OPTIONAL INTERNALS", "slot": "A", "slotSize": 3, "empty": True},
                 {"group": "CORE INTERNALS", "slot": "PowerPlant", "slotSize": 3, "moduleId": "reactor"}]
        row = self.project("candidate", "TEST", slots, reference=reference)
        self.assertEqual(row["currentShipFitStatus"], "FITS")
        self.assertIn("OVER BUDGET", row["currentShipSlotFits"]["A"]["powerWarning"])

    def test_cache_invalidates_for_loadout_and_hull_changes(self):
        from ed_companion.phase14.controller_navigation import NavigationMixin
        state = {"activeShipType": "adder", "activeShipSlots": [
            {"group": "OPTIONAL INTERNALS", "slot": "A", "slotSize": 3, "empty": True}]}
        controller = SimpleNamespace(_state=state, _shipyard_module_catalog=[{
            "symbol": "int_shieldgenerator_size3_class5", "moduleGroup": "OPTIONAL", "moduleClass": 3, "moduleFamily": "SHIELD GENERATOR"}])
        project = lambda: NavigationMixin._shipyard_module_projection(controller)
        first = project()
        self.assertIs(first, project())
        state["activeShipSlots"][0].update(moduleId="new_module", empty=False)
        second = project()
        self.assertIsNot(first, second)
        state["activeShipType"] = "anaconda"
        self.assertIsNot(second, project())

    def test_stale_mass_snapshot_and_unknown_slot_stay_unknown(self):
        symbol = "int_engine_size3_class5"
        slots = [{"group": "CORE INTERNALS", "slot": "MainEngines", "slotSize": 3, "moduleId": symbol},
                 {"group": "OPTIONAL INTERNALS", "slot": "A", "slotSize": 3, "empty": True}]
        row = self.project(symbol, "THRUSTERS", slots, group="CORE", core="MainEngines", ship_stats={
            "unladenMass": 100, "fuelCapacity": 10, "cargoCapacity": 0,
            "modules": {"MainEngines": symbol, "A": "removed_module"}})
        self.assertEqual(row["currentShipFitStatus"], "UNKNOWN")
        slots = [{"group": "OPTIONAL INTERNALS", "slot": "A", "slotSize": 6, "empty": True, "restriction": "futureRule"}]
        row = self.project("int_passengercabin_size5_class4", "LUXURY CLASS PASSENGER CABIN", slots, "orca")
        self.assertEqual(row["currentShipFitStatus"], "UNKNOWN")
        self.assertIn("future", row["currentShipFitReason"])


if __name__ == "__main__":
    unittest.main()
