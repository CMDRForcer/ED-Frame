import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ed_companion.material_integrity import (
    compare_ingredient_costs,
    material_monitor_snapshot,
)
from ed_companion.phase14.state_engineering import (
    apply_engineer_craft,
    build_engineering_plan,
    required_materials,
)


class MaterialMonitorTests(unittest.TestCase):
    @staticmethod
    def _plan(engineer_rank=5):
        return build_engineering_plan(
            [{
                "Type": "Multi-cannon",
                "Name": "High Capacity Magazine",
                "Grade": 1,
                "Engineers": ["Tod McQuinn"],
                "Ingredients": [{"Name": "Mechanical Scrap", "Size": 1}],
            }],
            0, 1, ship_id=37, slot="MediumHardpoint1",
            module_id="hpt_multicannon_gimbal_medium",
            engineer_rank=engineer_rank,
        )

    @staticmethod
    def _event(*, quality=1.0, ingredients=None):
        return {
            "timestamp": "2026-09-24T12:00:00Z",
            "event": "EngineerCraft",
            "ShipID": 37,
            "Slot": "MediumHardpoint1",
            "Module": "hpt_multicannon_gimbal_medium",
            "Engineer": "Tod 'The Blaster' McQuinn",
            "BlueprintID": 128673500,
            "BlueprintName": "Weapon_HighCapacity",
            "Level": 1,
            "Quality": quality,
            "Ingredients": ingredients or [
                {"Name": "mechanicalscrap", "Count": 1},
            ],
        }

    def test_ingredient_comparison_uses_stable_material_ids(self):
        comparison = compare_ingredient_costs(
            [{"Name": "Mechanical Scrap", "Size": 1}],
            [{"Name": "mechanicalscrap", "Count": 1}],
        )

        self.assertTrue(comparison["matches"])
        self.assertEqual(comparison["differences"], {})

    def test_matching_roll_is_recorded_as_verified(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ship_blueprints.json"
            path.write_text(
                json.dumps({"Krait Mk II": [self._plan()]}), encoding="utf-8"
            )

            result = apply_engineer_craft(
                path, "Krait Mk II", self._event(), ship_id=37,
            )
            rows = json.loads(
                (path.parent / "engineering_material_monitor.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(result["status"], "applied")
        self.assertEqual(rows[-1]["kind"], "verified")
        self.assertFalse(rows[-1]["blocking"])
        self.assertEqual(rows[-1]["inventoryDelta"], {"mechanicalscrap": -1})

    def test_recipe_change_updates_plan_and_records_non_blocking_adaptation(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ship_blueprints.json"
            path.write_text(
                json.dumps({"Krait Mk II": [self._plan()]}), encoding="utf-8"
            )
            event = self._event(
                ingredients=[{"Name": "nickel", "Count": 2}]
            )

            result = apply_engineer_craft(
                path, "Krait Mk II", event, ship_id=37,
            )
            saved = json.loads(path.read_text(encoding="utf-8"))
            rows = json.loads(
                (path.parent / "engineering_material_monitor.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(result["status"], "applied")
        self.assertEqual(
            saved["Krait Mk II"][0][0]["Ingredients"],
            [{"Name": "nickel", "Size": 2}],
        )
        self.assertEqual(rows[-1]["kind"], "recipe_adapted")
        self.assertTrue(rows[-1]["recipeChanged"])
        self.assertFalse(rows[-1]["blocking"])

    def test_incomplete_target_after_budget_reserves_next_roll_and_warns(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ship_blueprints.json"
            path.write_text(
                json.dumps({"Krait Mk II": [self._plan()]}), encoding="utf-8"
            )

            result = apply_engineer_craft(
                path, "Krait Mk II", self._event(quality=0.5), ship_id=37,
            )
            saved = json.loads(path.read_text(encoding="utf-8"))
            task = saved["Krait Mk II"][0]
            rows = json.loads(
                (path.parent / "engineering_material_monitor.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(result["status"], "applied")
        self.assertEqual(required_materials([task]), {"mechanicalscrap": 1})
        self.assertEqual(rows[-1]["kind"], "roll_budget_extended")
        self.assertTrue(rows[-1]["rollBudgetExtended"])
        self.assertEqual(rows[-1]["remainingRollsAfter"], 1)
        self.assertFalse(rows[-1]["blocking"])

    def test_early_completion_releases_unneeded_rolls_and_materials(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ship_blueprints.json"
            path.write_text(
                json.dumps({"Krait Mk II": [self._plan(engineer_rank=0)]}),
                encoding="utf-8",
            )

            result = apply_engineer_craft(
                path, "Krait Mk II", self._event(quality=1.0), ship_id=37,
            )
            saved = json.loads(path.read_text(encoding="utf-8"))
            task = saved["Krait Mk II"][0]
            rows = json.loads(
                (path.parent / "engineering_material_monitor.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(result["status"], "applied")
        self.assertEqual(required_materials([task]), {})
        self.assertEqual(rows[-1]["kind"], "requirement_reduced")
        self.assertTrue(rows[-1]["requirementReduced"])
        self.assertEqual(rows[-1]["rollsReleased"], 4)
        self.assertEqual(rows[-1]["releasedMaterialUnits"], 4)
        self.assertEqual(
            rows[-1]["releasedIngredients"], {"mechanicalscrap": 4}
        )
        self.assertFalse(rows[-1]["blocking"])

    def test_snapshot_is_scoped_to_selected_ship_and_never_blocks(self):
        rows = [
            {"shipId": "37", "kind": "verified"},
            {
                "shipId": "37", "kind": "recipe_adapted",
                "recipeChanged": True, "blocking": False,
            },
            {
                "shipId": "99", "kind": "roll_budget_extended",
                "rollBudgetExtended": True, "blocking": False,
            },
            {
                "shipId": "37", "kind": "requirement_reduced",
                "requirementReduced": True, "releasedMaterialUnits": 3,
                "blocking": False,
            },
        ]

        snapshot = material_monitor_snapshot(rows, 37, "Krait Mk II")

        self.assertEqual(snapshot["status"], "ADAPTED")
        self.assertEqual(snapshot["observedCount"], 3)
        self.assertEqual(snapshot["adaptationCount"], 1)
        self.assertEqual(snapshot["recipeChangeCount"], 1)
        self.assertEqual(snapshot["rollBudgetExtensionCount"], 0)
        self.assertEqual(snapshot["requirementReductionCount"], 1)
        self.assertEqual(snapshot["releasedMaterialUnits"], 3)
        self.assertTrue(snapshot["latest"]["requirementReduced"])
        self.assertFalse(snapshot["blocking"])

    def test_snapshot_shows_only_current_open_plan_observations(self):
        rows = [{
            "shipId": "45", "slot": "LargeHardpoint1",
            "planId": "completed-plan", "timestamp": "2026-09-26T12:00:00Z",
            "kind": "roll_budget_extended", "rollBudgetExtended": True,
        }, {
            "shipId": "45", "slot": "LargeHardpoint2",
            "planId": "open-plan", "timestamp": "2026-09-26T12:10:00Z",
            "kind": "verified",
        }, {
            # Legacy rows did not yet persist planId.  The immutable Journal
            # boundary keeps an old same-slot run out of a newly pinned plan.
            "shipId": "45", "slot": "LargeHardpoint2",
            "timestamp": "2026-09-26T11:50:00Z", "kind": "recipe_adapted",
            "recipeChanged": True,
        }]

        snapshot = material_monitor_snapshot(rows, 45, "Python Mk II", [{
            "planId": "open-plan", "slot": "LargeHardpoint2",
            "baselineTimestamp": "2026-09-26T12:05:00Z",
        }])

        self.assertEqual(snapshot["status"], "VERIFIED")
        self.assertEqual(snapshot["observedCount"], 1)
        self.assertEqual(snapshot["adaptationCount"], 0)

    def test_snapshot_with_no_open_plans_drops_completed_run_warning(self):
        snapshot = material_monitor_snapshot([{
            "shipId": "45", "slot": "LargeHardpoint1",
            "planId": "completed-plan", "timestamp": "2026-09-26T12:00:00Z",
            "kind": "roll_budget_extended", "rollBudgetExtended": True,
        }], 45, "Python Mk II", [])

        self.assertEqual(snapshot["status"], "WAITING")
        self.assertEqual(snapshot["observedCount"], 0)
        self.assertEqual(snapshot["adaptationCount"], 0)


if __name__ == "__main__":
    unittest.main()
