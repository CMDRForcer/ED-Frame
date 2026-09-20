import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ed_companion.phase14.controller import CockpitController


class _Signal:
    def emit(self, *_args):
        pass


class BuildImportBindingTests(unittest.TestCase):
    def test_apply_binds_plan_to_desired_module_not_current_slot_module(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ship_metadata.json").write_text(json.dumps({
                "Test ship": {"id": 42, "type": "Mandalay"},
            }), encoding="utf-8")
            controller = CockpitController.__new__(CockpitController)
            controller._data_dir = root
            controller._state = {
                "ships": ["Test ship"],
                "engineeringShipSlots": [{
                    "slot": "PowerPlant",
                    "moduleId": "int_powerplant_size5_class1",
                }],
            }
            controller._build_import_target = "Test ship"
            controller._build_import_preview = {
                "compatible": True,
                "shipType": "Mandalay",
                "rows": [{
                    "status": "ready", "slotBound": True,
                    "slot": "PowerPlant", "planMode": "grade_only",
                    "blueprintGroup": "Power Plant\u241fOvercharged",
                    "grade": 1, "currentGrade": 0,
                    "desiredModule": "int_powerplant_size3_class5",
                    "moduleChange": True,
                }],
            }
            controller._blueprint_groups = {
                "Power Plant\u241fOvercharged": [{
                    "Type": "Power Plant", "Name": "Overcharged",
                    "Grade": 1, "Ingredients": [],
                }],
            }
            controller._experimentals = []
            controller._ship_catalog = []
            controller.refresh = lambda: None
            controller.engineeringChanged = _Signal()

            controller.applyBuildImport()

            tasks = json.loads(
                (root / "ship_blueprints.json").read_text(encoding="utf-8")
            )["Test ship"]
            planner = tasks[0][0]["_Planner"]
            desired = json.loads(
                (root / "desired_outfitting.json").read_text(encoding="utf-8")
            )
            self.assertEqual(planner["ship_id"], "42")
            self.assertEqual(planner["slot"], "PowerPlant")
            self.assertEqual(
                planner["module_id"], "int_powerplant_size3_class5"
            )
            self.assertFalse(planner["binding_required"])
            self.assertEqual(
                desired["42"]["PowerPlant"],
                "int_powerplant_size3_class5",
            )

    def test_apply_accepts_a_ship_whose_symbol_and_display_name_differ(self):
        # A build's "Ship" field is the raw Frontier/Coriolis symbol
        # (Python_NX), while ship_metadata.json stores the display name
        # (Python Mk II) the target-ship dropdown shows. These share no
        # words in common - unlike most ships, where the symbol and the
        # display name happen to look alike under a bare normalize().
        # Apply must resolve both to the same hull via the ship catalog,
        # exactly like the preview step already does, rather than reject
        # a perfectly valid, just-previewed import.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ship_metadata.json").write_text(json.dumps({
                "Python Mk II": {"id": 45, "type": "Python Mk II"},
            }), encoding="utf-8")
            controller = CockpitController.__new__(CockpitController)
            controller._data_dir = root
            controller._state = {
                "ships": ["Python Mk II"],
                "engineeringShipSlots": [{
                    "slot": "PowerPlant",
                    "moduleId": "int_powerplant_size6_class5",
                }],
            }
            controller._build_import_target = "Python Mk II"
            controller._build_import_preview = {
                "compatible": True,
                "shipType": "python_nx",
                "rows": [{
                    "status": "ready", "slotBound": True,
                    "slot": "PowerPlant", "planMode": "grade_only",
                    "blueprintGroup": "Power Plant␟Overcharged",
                    "grade": 1, "currentGrade": 0,
                    "desiredModule": "int_powerplant_size6_class5",
                    "moduleChange": False,
                }],
            }
            controller._blueprint_groups = {
                "Power Plant␟Overcharged": [{
                    "Type": "Power Plant", "Name": "Overcharged",
                    "Grade": 1, "Ingredients": [],
                }],
            }
            controller._experimentals = []
            controller._ship_catalog = [
                {"symbol": "Python_NX", "name": "Python Mk II"},
            ]
            controller.refresh = lambda: None
            controller.engineeringChanged = _Signal()

            controller.applyBuildImport()

            self.assertFalse(controller._build_import_preview.get("actionError"))
            tasks = json.loads(
                (root / "ship_blueprints.json").read_text(encoding="utf-8")
            )["Python Mk II"]
            self.assertEqual(len(tasks), 1)


if __name__ == "__main__":
    unittest.main()
