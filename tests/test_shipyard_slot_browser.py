"""Exercise the actual QML slot predicates with Qt's JavaScript engine."""
import json
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtQml import QJSEngine


class ShipyardSlotBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])
        cls.source = Path("qml/pages/ShipyardPage.qml").read_text(encoding="utf-8")

    def predicate(self, group, slot, row, follow=True):
        start = self.source.index("    function slotAllows(row)")
        end = self.source.index("    function selectSlot(row)", start)
        engine = QJSEngine()
        script = (
            "var moduleGroup = " + json.dumps(group) + ";"
            "var selectedSlot = " + json.dumps(slot) + ";"
            "var fitCurrentShip = " + json.dumps(follow) + ";"
            + self.source[start:end]
            + "slotAllows(" + json.dumps(row) + ")"
        )
        result = engine.evaluate(script)
        self.assertFalse(result.isError(), result.toString())
        return result.toBool()

    def test_core_family_and_size_are_both_checked(self):
        slot = {"slot": "FrameShiftDrive", "slotSize": 5}
        self.assertTrue(self.predicate("CORE", slot, {
            "moduleCoreSlot": "FrameShiftDrive", "moduleClass": "5"}))
        self.assertFalse(self.predicate("CORE", slot, {
            "moduleCoreSlot": "FrameShiftDrive", "moduleClass": "6"}))
        self.assertFalse(self.predicate("CORE", slot, {
            "moduleCoreSlot": "PowerPlant", "moduleClass": "5"}))

    def test_selected_hardpoint_not_largest_ship_hardpoint(self):
        slot = {"slot": "MediumHardpoint1", "slotSize": 2}
        self.assertTrue(self.predicate("HARDPOINTS", slot, {"moduleClass": "2"}))
        self.assertFalse(self.predicate("HARDPOINTS", slot, {"moduleClass": "3"}))

    def test_unknown_class_and_free_browse_remain_visible(self):
        slot = {"slot": "Slot01_Size3", "slotSize": 3}
        self.assertTrue(self.predicate("OPTIONAL", slot, {"moduleClass": "UNKNOWN"}))
        self.assertTrue(self.predicate("OPTIONAL", slot, {"moduleClass": "8"}, follow=False))
        self.assertTrue(self.predicate("OPTIONAL", {}, {"moduleClass": "8"}))

    def test_utility_class_zero(self):
        self.assertTrue(self.predicate("UTILITY", {
            "slot": "TinyHardpoint1", "slotSize": 0}, {"moduleClass": "0"}))

    def test_backend_slot_evidence_overrides_size_only_guess(self):
        slot = {"slot": "Slot01_Size3", "slotSize": 3}
        for status, expected in (("FITS", True), ("UNKNOWN", True), ("INCOMPATIBLE", False)):
            self.assertEqual(self.predicate("OPTIONAL", slot, {
                "moduleClass": 2, "currentShipSlotFits": {
                    "Slot01_Size3": {"status": status}}}), expected)
        self.assertFalse(self.predicate("OPTIONAL", slot, {
            "moduleClass": 2, "currentShipSlotFits": {}}))

    def test_comparison_toggle_and_numeric_class_sort(self):
        start = self.source.index("    function moduleVariantRows()")
        end = self.source.index("    function slotRows()", start)
        engine = QJSEngine()
        rows = [{"moduleFamilyKey": "test", "moduleClass": size, "currentShipFitStatus": status}
                for size, status in ((8, "INCOMPATIBLE"), (2, "FITS"), (3, "UNKNOWN"))]
        result = engine.evaluate('var modules=' + json.dumps(rows) + ';'
            'var moduleFamilyKey="test", moduleClassFilter="ANY", moduleRatingFilter="ANY", moduleMountFilter="ANY";'
            'var fitCurrentShip=true, showIncompatibleVariants=false;'
            'function matchesModuleGroup(row){return true;} function slotAllows(row){return row.currentShipFitStatus!=="INCOMPATIBLE";}'
            + self.source[start:end] + 'moduleVariantRows().map(function(r){return r.moduleClass;}).join(",")')
        self.assertFalse(result.isError(), result.toString())
        self.assertEqual(result.toString(), "2,3")
        self.assertEqual(engine.evaluate('showIncompatibleVariants=true;moduleVariantRows().map(function(r){return r.moduleClass;}).join(",")').toString(), "2,3,8")

    def test_mining_tab_spans_groups_but_excludes_combat_mines(self):
        start = self.source.index("    function isMiningModule(row)")
        end = self.source.index("    function moduleFamilyRows()", start)
        engine = QJSEngine()
        result = engine.evaluate('var moduleGroup = "MINING";' + self.source[start:end])
        self.assertFalse(result.isError(), result.toString())
        for name, included in (("MINING LASER", True), ("REFINERY", True),
                               ("PROSPECTOR LIMPET CONTROLLER", True),
                               ("PULSE WAVE ANALYSER", True), ("CARGO RACK", True),
                               ("MINE LAUNCHER", False), ("BEAM LASER", False)):
            with self.subTest(name=name):
                result = engine.evaluate("matchesModuleGroup(" + json.dumps({"moduleFamily": name}) + ")")
                self.assertFalse(result.isError(), result.toString())
                self.assertEqual(result.toBool(), included)

    def test_exclusive_categories_and_broker_subgroups(self):
        start = self.source.index("    function isMiningModule(row)")
        end = self.source.index("    function moduleFamilyRows()", start)
        engine = QJSEngine()
        engine.evaluate('var moduleGroup = ""; var brokerFilter = "ALL BROKERS";' + self.source[start:end])
        cases = [
            ({"displayName": "MINING LASER", "moduleGroup": "HARDPOINTS"}, "MINING"),
            ({"displayName": "REFINERY", "moduleGroup": "OPTIONAL"}, "MINING"),
            ({"displayName": "GUARDIAN FRAME SHIFT DRIVE BOOSTER", "moduleGroup": "OPTIONAL", "acquisitionRoute": "TECH_BROKER"}, "TECH BROKER"),
            ({"displayName": "PRISMATIC SHIELD GENERATOR", "moduleGroup": "OPTIONAL", "acquisitionRoute": "POWERPLAY"}, "POWERPLAY"),
            ({"displayName": "MINING LANCE BEAM LASER", "moduleGroup": "HARDPOINTS", "acquisitionRoute": "POWERPLAY"}, "MINING"),
            ({"displayName": "BEAM LASER", "moduleGroup": "HARDPOINTS"}, "HARDPOINTS"),
        ]
        for row, expected in cases:
            included = []
            for group in ("HARDPOINTS", "UTILITY", "CORE", "OPTIONAL", "MINING", "TECH BROKER", "POWERPLAY"):
                engine.evaluate("moduleGroup = " + json.dumps(group))
                result = engine.evaluate("matchesModuleGroup(" + json.dumps(row) + ")")
                self.assertFalse(result.isError(), result.toString())
                if result.toBool():
                    included.append(group)
            self.assertEqual(included, [expected], row)
        engine.evaluate('moduleGroup = "TECH BROKER"; brokerFilter = "HUMAN";')
        self.assertFalse(engine.evaluate("matchesModuleGroup(" + json.dumps(cases[2][0]) + ")").toBool())
        engine.evaluate('brokerFilter = "GUARDIAN";')
        self.assertTrue(engine.evaluate("matchesModuleGroup(" + json.dumps(cases[2][0]) + ")").toBool())
