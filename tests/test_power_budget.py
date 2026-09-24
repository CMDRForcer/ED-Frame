import unittest

from ed_companion.phase14.state import (
    pending_power_plan_targets,
    power_modifier_multiplier,
    ship_power_budget,
    ship_power_plan,
    slot_power_mw,
)


def _slot(
    slot, module_id, priority_group=1, powered_on=True,
    engineering_grade=0, engineering_blueprint="", experimental_effect="",
    empty=False,
):
    return {
        "slot": slot,
        "moduleId": module_id,
        "empty": empty,
        "engineeringGrade": engineering_grade,
        "engineeringBlueprint": engineering_blueprint,
        "experimentalEffect": experimental_effect,
        "priorityGroup": priority_group,
        "poweredOn": powered_on,
        "module": "Test Module",
    }


class PowerModifierMultiplierTests(unittest.TestCase):
    def test_unengineered_module_has_no_modifier(self):
        self.assertEqual(
            power_modifier_multiplier("int_powerplant_size6_class5", "", 0), 1.0,
        )

    def test_known_grade_blueprint_applies_percent(self):
        # Power Plant "Armoured" Grade 3 -> Power Generation +8%
        self.assertAlmostEqual(
            power_modifier_multiplier(
                "int_powerplant_size6_class5", "Armoured", 3,
            ),
            1.08,
        )

    def test_known_experimental_effect_applies_percent(self):
        # Multi-cannon "Flow Control" experimental -> Power Draw -10%
        self.assertAlmostEqual(
            power_modifier_multiplier(
                "hpt_multicannon_gimbal_medium", "", 0,
                experimental_effect="Flow Control",
            ),
            0.90,
        )

    def test_grade_and_experimental_stack_multiplicatively(self):
        # Efficient Weapon Grade 3 (-24%) combined with Flow Control (-10%)
        # must multiply, not add: 0.76 * 0.90, not 1 - 0.24 - 0.10.
        self.assertAlmostEqual(
            power_modifier_multiplier(
                "hpt_multicannon_gimbal_medium", "Efficient Weapon", 3,
                experimental_effect="Flow Control",
            ),
            0.76 * 0.90,
        )

    def test_unrecognized_blueprint_name_never_guesses_a_modifier(self):
        self.assertEqual(
            power_modifier_multiplier(
                "int_powerplant_size6_class5", "Not A Real Blueprint", 3,
            ),
            1.0,
        )


class SlotPowerMwTests(unittest.TestCase):
    def test_known_module_returns_base_draw(self):
        draw, generated = slot_power_mw(_slot("Slot01", "hpt_pulselaser_fixed_small"))
        self.assertAlmostEqual(draw, 0.39)
        self.assertIsNone(generated)

    def test_known_power_plant_returns_generation(self):
        draw, generated = slot_power_mw(_slot("PowerPlant", "int_powerplant_size2_class3"))
        self.assertIsNone(draw)
        self.assertAlmostEqual(generated, 8.0)

    def test_unknown_module_returns_none_none(self):
        self.assertEqual(
            slot_power_mw(_slot("Slot01", "int_totally_unknown_module")),
            (None, None),
        )

    def test_empty_slot_returns_none_none(self):
        self.assertEqual(
            slot_power_mw(_slot("Slot01", "", empty=True)),
            (None, None),
        )

    def test_engineered_module_scales_base_draw(self):
        draw, _generated = slot_power_mw(_slot(
            "Slot01", "hpt_multicannon_gimbal_medium",
            engineering_grade=3, engineering_blueprint="Efficient Weapon",
        ))
        self.assertAlmostEqual(draw, 0.64 * 0.76)


class ShipPowerBudgetTests(unittest.TestCase):
    def _base_slots(self):
        return [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            _slot("FrameShiftDrive", "int_hyperdrive_size2_class3", priority_group=5),
            _slot("Slot01_Size2", "int_shieldgenerator_size2_class3", priority_group=2),
            _slot("MediumHardpoint1", "hpt_multicannon_gimbal_medium", priority_group=1),
            _slot("MediumHardpoint2", "hpt_multicannon_gimbal_medium", priority_group=1),
            _slot("MediumHardpoint3", "hpt_multicannon_gimbal_medium", priority_group=1),
            _slot("Slot02_Size7", "int_shieldgenerator_size7_class5", priority_group=4),
        ]

    def test_under_capacity_nothing_is_shed(self):
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            _slot("FrameShiftDrive", "int_hyperdrive_size2_class3", priority_group=5),
            _slot("Slot01_Size2", "int_shieldgenerator_size2_class3", priority_group=2),
        ]
        budget = ship_power_budget(slots)
        self.assertEqual(budget["capacityMW"], 8.0)
        self.assertTrue(budget["capacityKnown"])
        self.assertAlmostEqual(budget["totalDrawMW"], 0.2 + 1.5)
        self.assertFalse(budget["overloaded"])
        self.assertEqual(budget["groups"][4]["shedByCascade"], False)  # priority 5 entry
        for consumer in budget["consumers"]:
            self.assertFalse(consumer["shutDown"])


    def test_no_plan_matches_installed_ship_and_has_no_forecast(self):
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            _slot("Slot01", "int_shieldgenerator_size2_class3"),
        ]
        actual = ship_power_budget(slots)
        planned = ship_power_plan(slots)
        self.assertFalse(planned["hasPlan"])
        self.assertEqual(planned["totalDrawMW"], actual["totalDrawMW"])
        self.assertEqual(planned["reserveMW"], actual["reserveMW"])

    def test_wishlist_replacement_uses_stock_draw_and_assumes_powered_on(self):
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            {**_slot("Slot01", "int_shieldgenerator_size2_class3", powered_on=False),
             "desiredModuleId": "int_shieldgenerator_size7_class5"},
        ]
        planned = ship_power_plan(slots)
        self.assertTrue(planned["hasPlan"])
        self.assertEqual(planned["changedSlots"], ["Slot01"])
        self.assertEqual(planned["assumedStockSlots"], ["Slot01"])
        self.assertEqual(planned["poweredOffSlots"], [])
        self.assertAlmostEqual(planned["totalDrawMW"], 4.9)
        self.assertAlmostEqual(planned["reserveMW"], 8.0 - 4.9)

    def test_planned_power_plant_engineering_increases_capacity(self):
        slots = [
            {**_slot("PowerPlant", "int_powerplant_size2_class3"),
             "planPending": True, "planModuleId": "int_powerplant_size2_class3",
             "planMode": "grade_only", "planTargetGrade": 3,
             "planBlueprint": "Armoured"},
            _slot("Slot01", "int_shieldgenerator_size2_class3"),
        ]
        planned = ship_power_plan(slots)
        self.assertAlmostEqual(planned["capacityMW"], 8.0 * 1.08)
        self.assertAlmostEqual(planned["capacityDeltaMW"], 0.64)
        self.assertEqual(planned["unknownEngineeringSlots"], [])

    def test_standalone_experimental_keeps_installed_grade_and_blueprint(self):
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            {**_slot("MediumHardpoint1", "hpt_multicannon_gimbal_medium",
                     engineering_grade=3,
                     engineering_blueprint="Efficient Weapon"),
             "planPending": True,
             "planModuleId": "hpt_multicannon_gimbal_medium",
             "planMode": "experimental_only", "planTargetGrade": 0,
             "planBlueprint": "Flow Control",
             "planExperimental": "Flow Control"},
        ]
        planned = ship_power_plan(slots)
        self.assertAlmostEqual(planned["totalDrawMW"], 0.64 * 0.76 * 0.90)
        self.assertEqual(planned["unknownEngineeringSlots"], [])

    def test_grade_and_standalone_experimental_plans_merge_per_ship_slot(self):
        module_id = "hpt_multicannon_gimbal_medium"
        grade = [{"Name": "Efficient Weapon", "_Planner": {
            "slot": "MediumHardpoint1", "module_id": module_id,
            "plan_mode": "grade_only", "target_grade": 3,
        }}]
        experimental = [{"Name": "Flow Control", "_Planner": {
            "slot": "MediumHardpoint1", "module_id": module_id,
            "plan_mode": "experimental_only", "target_grade": 0,
            "experimental_id": "flow_control",
            "experimental_name": "Flow Control",
        }}]
        targets = pending_power_plan_targets([grade, experimental])
        self.assertEqual(targets["MediumHardpoint1"]["planBlueprint"], "Efficient Weapon")
        self.assertEqual(targets["MediumHardpoint1"]["planExperimental"], "Flow Control")
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            {**_slot("MediumHardpoint1", module_id), **targets["MediumHardpoint1"]},
        ]
        self.assertAlmostEqual(
            ship_power_plan(slots)["totalDrawMW"], 0.64 * 0.76 * 0.90,
        )

    def test_conflicting_slot_plans_are_marked_unresolved(self):
        first = [{"Name": "Efficient Weapon", "_Planner": {
            "slot": "MediumHardpoint1",
            "module_id": "hpt_multicannon_gimbal_medium",
            "plan_mode": "grade_only", "target_grade": 3,
        }}]
        second = [{"Name": "Overcharged Weapon", "_Planner": {
            "slot": "MediumHardpoint1",
            "module_id": "hpt_pulselaser_fixed_small",
            "plan_mode": "grade_only", "target_grade": 5,
        }}]
        targets = pending_power_plan_targets([first, second])
        self.assertTrue(targets["MediumHardpoint1"]["planConflict"])
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            {**_slot("MediumHardpoint1", "hpt_multicannon_gimbal_medium"),
             **targets["MediumHardpoint1"]},
        ]
        planned = ship_power_plan(slots)
        self.assertEqual(planned["unresolvedPlanSlots"], ["MediumHardpoint1"])
        self.assertAlmostEqual(planned["totalDrawMW"], 0.64)

    def test_bound_plan_on_replacement_uses_desired_module_and_grade(self):
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            {**_slot("MediumHardpoint1", "hpt_multicannon_gimbal_medium"),
             "desiredModuleId": "hpt_pulselaser_fixed_small",
             "planPending": True,
             "planModuleId": "hpt_pulselaser_fixed_small",
             "planMode": "grade_only", "planTargetGrade": 3,
             "planBlueprint": "Efficient Weapon"},
        ]
        planned = ship_power_plan(slots)
        expected, _ = slot_power_mw({
            "moduleId": "hpt_pulselaser_fixed_small",
            "engineeringBlueprint": "Efficient Weapon",
            "engineeringGrade": 3,
        })
        self.assertAlmostEqual(planned["totalDrawMW"], expected)
        self.assertEqual(planned["assumedStockSlots"], [])

    def test_mismatched_and_unknown_plan_data_are_not_silently_applied(self):
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            {**_slot("Slot01", "int_shieldgenerator_size2_class3"),
             "desiredModuleId": "int_shieldgenerator_size7_class5",
             "planPending": True, "planModuleId": "int_shieldgenerator_size2_class3",
             "planMode": "grade_only", "planTargetGrade": 5,
             "planBlueprint": "Not a recipe"},
        ]
        planned = ship_power_plan(slots)
        self.assertEqual(planned["unresolvedPlanSlots"], ["Slot01"])
        self.assertEqual(planned["assumedStockSlots"], ["Slot01"])
        self.assertAlmostEqual(planned["totalDrawMW"], 4.9)

    def test_bound_plan_module_can_replace_a_redundant_current_desired_entry(self):
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            {**_slot("Slot01", "int_shieldgenerator_size2_class3"),
             "desiredModuleId": "int_shieldgenerator_size2_class3",
             "planPending": True,
             "planModuleId": "int_shieldgenerator_size7_class5",
             "planTargetGrade": 0,
             "planMode": "experimental_only"},
        ]
        planned = ship_power_plan(slots)
        self.assertIn("Slot01", planned["changedSlots"])
        self.assertAlmostEqual(planned["totalDrawMW"], 4.9)

    def test_unknown_new_module_is_reported_and_not_treated_as_zero(self):
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            {**_slot("Slot01", "", empty=True),
             "desiredModuleId": "int_totally_unknown_module"},
        ]
        planned = ship_power_plan(slots)
        self.assertEqual(planned["unknownModuleSlots"], ["Slot01"])
        self.assertEqual(planned["assumedStockSlots"], ["Slot01"])

    def test_unbound_plan_does_not_change_installed_power_draw(self):
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            {**_slot("MediumHardpoint1", "hpt_multicannon_gimbal_medium"),
             "planPending": True, "planBindingRequired": True,
             "planModuleId": "hpt_multicannon_gimbal_medium",
             "planTargetGrade": 3, "planBlueprint": "Efficient Weapon"},
        ]
        planned = ship_power_plan(slots)
        self.assertAlmostEqual(planned["totalDrawMW"], 0.64)
        self.assertEqual(planned["unresolvedPlanSlots"], ["MediumHardpoint1"])

    def test_unknown_engineering_recipe_is_flagged(self):
        slots = [
            {**_slot("PowerPlant", "int_powerplant_size2_class3"),
             "planPending": True, "planModuleId": "int_powerplant_size2_class3",
             "planTargetGrade": 5, "planBlueprint": "Not a recipe"},
        ]
        planned = ship_power_plan(slots)
        self.assertEqual(planned["capacityMW"], 8.0)
        self.assertEqual(planned["unknownEngineeringSlots"], ["PowerPlant"])

    def test_planned_overload_uses_before_shutdown_draw_for_negative_reserve(self):
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            _slot("FrameShiftDrive", "int_hyperdrive_size2_class3", priority_group=5),
            _slot("MediumHardpoint1", "hpt_multicannon_gimbal_medium"),
            _slot("MediumHardpoint2", "hpt_multicannon_gimbal_medium"),
            _slot("MediumHardpoint3", "hpt_multicannon_gimbal_medium"),
            _slot("Slot02", "int_shieldgenerator_size2_class3", priority_group=2),
            {**_slot("Slot01", "", empty=True, priority_group=4),
             "desiredModuleId": "int_shieldgenerator_size7_class5"},
        ]
        planned = ship_power_plan(slots)
        self.assertTrue(planned["overloaded"])
        self.assertLess(planned["reserveMW"], 0)
        self.assertGreater(planned["totalDrawMW"], planned["usedDrawMW"])

    def test_unknown_planned_power_plant_keeps_reserve_unknown(self):
        slots = [
            {**_slot("PowerPlant", "int_powerplant_size2_class3"),
             "desiredModuleId": "int_totally_unknown_module"},
            _slot("Slot01", "int_shieldgenerator_size2_class3"),
        ]
        planned = ship_power_plan(slots)
        self.assertFalse(planned["capacityKnown"])
        self.assertIsNone(planned["reserveMW"])

    def test_existing_powered_off_module_stays_off_and_is_disclosed(self):
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            _slot("Slot01", "int_shieldgenerator_size7_class5", powered_on=False),
            {**_slot("MediumHardpoint1", "", empty=True),
             "desiredModuleId": "hpt_multicannon_gimbal_medium"},
        ]
        planned = ship_power_plan(slots)
        self.assertEqual(planned["poweredOffSlots"], ["Slot01"])
        self.assertAlmostEqual(planned["totalDrawMW"], 0.64)

    def test_different_ship_slots_yield_independent_global_forecasts(self):
        small = ship_power_plan([
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            {**_slot("Slot01", "", empty=True),
             "desiredModuleId": "int_shieldgenerator_size7_class5"},
        ])
        large = ship_power_plan([
            _slot("PowerPlant", "int_powerplant_size6_class5"),
            {**_slot("Slot01", "", empty=True),
             "desiredModuleId": "int_shieldgenerator_size7_class5"},
        ])
        self.assertNotEqual(small["capacityMW"], large["capacityMW"])
        self.assertEqual(small["totalDrawMW"], large["totalDrawMW"])

    def test_overload_sheds_lowest_priority_groups_first(self):
        budget = ship_power_budget(self._base_slots())
        expected_total = 0.2 + 1.5 + 3 * 0.64 + 4.9
        self.assertAlmostEqual(budget["totalDrawMW"], expected_total)
        self.assertTrue(budget["overloaded"])
        shed = {g["priorityGroup"] for g in budget["groups"] if g["shedByCascade"]}
        self.assertEqual(shed, {4, 5})
        self.assertLessEqual(budget["usedDrawMW"], budget["capacityMW"])
        shut_down_slots = {
            row["slot"] for row in budget["consumers"] if row["shutDown"]
        }
        self.assertEqual(shut_down_slots, {"FrameShiftDrive", "Slot02_Size7"})
        # Priority 1 and 2 must survive the cascade.
        surviving_slots = {
            row["slot"] for row in budget["consumers"] if not row["shutDown"]
        }
        self.assertEqual(
            surviving_slots,
            {"Slot01_Size2", "MediumHardpoint1", "MediumHardpoint2", "MediumHardpoint3"},
        )

    def test_manually_powered_off_module_is_excluded_from_draw(self):
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            _slot(
                "Slot01_Size2", "int_shieldgenerator_size7_class5",
                priority_group=1, powered_on=False,
            ),
        ]
        budget = ship_power_budget(slots)
        self.assertAlmostEqual(budget["totalDrawMW"], 0.0)
        self.assertFalse(budget["overloaded"])
        self.assertEqual(budget["consumers"][0]["poweredOn"], False)
        self.assertFalse(budget["consumers"][0]["shutDown"])

    def test_unknown_module_is_reported_not_assumed_zero(self):
        slots = [
            _slot("PowerPlant", "int_powerplant_size2_class3"),
            _slot("Slot01_Size2", "int_totally_unknown_module"),
        ]
        budget = ship_power_budget(slots)
        self.assertEqual(budget["unknownModuleSlots"], ["Slot01_Size2"])
        self.assertAlmostEqual(budget["totalDrawMW"], 0.0)

    def test_missing_power_plant_leaves_capacity_unknown(self):
        slots = [
            _slot("PowerPlant", "", empty=True),
            _slot("Slot01_Size2", "int_shieldgenerator_size7_class5"),
        ]
        budget = ship_power_budget(slots)
        self.assertFalse(budget["capacityKnown"])
        self.assertEqual(budget["capacityMW"], 0.0)
        self.assertFalse(budget["overloaded"])
        for consumer in budget["consumers"]:
            self.assertFalse(consumer["shutDown"])


if __name__ == "__main__":
    unittest.main()
