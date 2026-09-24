import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from PySide6.QtCore import QObject

from ed_companion.surface_nav import parse_coordinate, surface_guidance
from ed_companion.phase14.controller import CockpitController


class SurfaceGuidanceTests(unittest.TestCase):
    def test_north_and_east_bearings_follow_elite_heading(self):
        status = {
            "Latitude": 0, "Longitude": 0, "Heading": 90,
            "PlanetRadius": 1_000_000,
        }
        north = surface_guidance(status, {"latitude": 1, "longitude": 0})
        east = surface_guidance(status, {"latitude": 0, "longitude": 1})
        self.assertEqual(north["bearingDeg"], 0)
        self.assertEqual(north["turnDeg"], -90)
        self.assertEqual(east["bearingDeg"], 90)
        self.assertEqual(east["turnDeg"], 0)
        self.assertAlmostEqual(east["distanceM"], 17453, delta=1)

    def test_short_route_crosses_the_date_line(self):
        result = surface_guidance(
            {"Latitude": 0, "Longitude": 179.9, "Heading": 0,
             "PlanetRadius": 1_000_000},
            {"latitude": 0, "longitude": -179.9},
        )
        self.assertEqual(result["bearingDeg"], 90)
        self.assertAlmostEqual(result["distanceM"], 3491, delta=1)

    def test_coordinates_accept_decimal_comma_and_reject_out_of_range(self):
        self.assertEqual(parse_coordinate("-12,5", 90), -12.5)
        for value in ("", "91", "nan", "inf"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_coordinate(value, 90)

    def test_missing_radius_or_heading_preserves_available_guidance(self):
        result = surface_guidance(
            {"Latitude": 0, "Longitude": 0},
            {"latitude": 0, "longitude": 1},
        )
        self.assertEqual(result, {"bearingDeg": 90})


class SurfaceTargetPersistenceTests(unittest.TestCase):
    @staticmethod
    def controller(directory):
        controller = CockpitController.__new__(CockpitController)
        QObject.__init__(controller)
        controller.config_dir = Path(directory)
        controller._state = {"system": "Sol"}
        controller._init_surface_nav()
        return controller

    def test_saved_target_survives_reload_and_wrong_body_disables_guidance(self):
        with TemporaryDirectory() as directory:
            status_file = Path(directory) / "Status.json"
            status_file.write_text(json.dumps({
                "BodyName": "Sol A 1", "Latitude": 0, "Longitude": 0,
                "Heading": 0, "PlanetRadius": 1_000_000,
            }), encoding="utf-8")
            with mock.patch(
                "ed_companion.phase14.controller_surface_nav.journal_dir",
                return_value=Path(directory),
            ):
                first = self.controller(directory)
                self.assertTrue(first.saveSurfaceTarget("Base", "0", "1"))
                self.assertEqual(first._surface_nav["guidance"]["turnDeg"], 90)
                second = self.controller(directory)
                self.assertEqual(second._surface_nav["targets"][0]["name"], "Base")
                self.assertEqual(second._surface_nav["guidance"]["turnDeg"], 90)
                status_file.write_text(json.dumps({
                    "BodyName": "Sol A 2", "Latitude": 0, "Longitude": 0,
                    "Heading": 0, "PlanetRadius": 1_000_000,
                }), encoding="utf-8")
                second._poll_surface_nav()
                self.assertEqual(second._surface_nav["guidance"], {"wrongBody": True})

    def test_invalid_input_and_failed_save_leave_saved_targets_intact(self):
        with TemporaryDirectory() as directory:
            status_file = Path(directory) / "Status.json"
            status_file.write_text(json.dumps({
                "BodyName": "Sol A 1", "Latitude": 0, "Longitude": 0,
            }), encoding="utf-8")
            with mock.patch(
                "ed_companion.phase14.controller_surface_nav.journal_dir",
                return_value=Path(directory),
            ):
                controller = self.controller(directory)
                self.assertFalse(controller.saveSurfaceTarget("Bad", "91", "0"))
                with mock.patch.object(controller, "_persist_json", return_value=False):
                    self.assertFalse(controller.saveSurfaceTarget("Base", "0", "1"))
                self.assertEqual(controller._surface_nav["targets"], [])

    def test_current_position_can_be_renamed_without_changing_destination(self):
        with TemporaryDirectory() as directory:
            (Path(directory) / "Status.json").write_text(json.dumps({
                "BodyName": "Sol A 1", "Latitude": 12.5, "Longitude": -43.25,
                "Heading": 90, "PlanetRadius": 1_000_000,
            }), encoding="utf-8")
            with mock.patch(
                "ed_companion.phase14.controller_surface_nav.journal_dir",
                return_value=Path(directory),
            ):
                controller = self.controller(directory)
                self.assertTrue(controller.saveCurrentSurfacePosition())
                original = controller._surface_nav["targets"][0].copy()
                self.assertTrue(controller.renameSurfaceTarget(original["id"], "  Mein Fundort  "))
                renamed = controller._surface_nav["targets"][0]
                self.assertEqual(renamed, {**original, "name": "Mein Fundort"})
                self.assertEqual(controller._surface_nav["activeId"], original["id"])
                reloaded = self.controller(directory)
                self.assertEqual(reloaded._surface_nav["targets"], [renamed])
                self.assertEqual(reloaded._surface_nav["activeId"], original["id"])

    def test_invalid_or_failed_rename_preserves_saved_target(self):
        with TemporaryDirectory() as directory:
            (Path(directory) / "Status.json").write_text(json.dumps({
                "BodyName": "Sol A 1", "Latitude": 0, "Longitude": 0,
            }), encoding="utf-8")
            with mock.patch(
                "ed_companion.phase14.controller_surface_nav.journal_dir",
                return_value=Path(directory),
            ):
                controller = self.controller(directory)
                self.assertTrue(controller.saveSurfaceTarget("Base", "0", "1"))
                original = controller._surface_nav["targets"][0].copy()
                self.assertFalse(controller.renameSurfaceTarget(original["id"], "   "))
                self.assertFalse(controller.renameSurfaceTarget(original["id"], "x" * 81))
                self.assertFalse(controller.renameSurfaceTarget("missing", "New name"))
                with mock.patch.object(controller, "_persist_json", return_value=False):
                    self.assertFalse(controller.renameSurfaceTarget(original["id"], "New name"))
                self.assertEqual(controller._surface_nav["targets"], [original])
                self.assertEqual(self.controller(directory)._surface_nav["targets"], [original])

    def test_catalog_farm_becomes_persistent_waypoint_without_duplicates(self):
        with TemporaryDirectory() as directory:
            status_file = Path(directory) / "Status.json"
            status_file.write_text(json.dumps({
                "BodyName": "Sol A 1", "Latitude": 0, "Longitude": 0,
            }), encoding="utf-8")
            with mock.patch(
                "ed_companion.phase14.controller_surface_nav.journal_dir",
                return_value=Path(directory),
            ):
                controller = self.controller(directory)
                self.assertTrue(controller.activateMaterialFarmSite(
                    "hip_36601_c_1_a", "polonium",
                ))
                target = controller._surface_nav["targets"][0]
                self.assertEqual(target["body"], "HIP 36601 C 1 A")
                self.assertEqual(target["catalogId"], "hip_36601_c_1_a")
                self.assertEqual(controller._surface_nav["guidance"], {"wrongBody": True})
                self.assertTrue(controller.activateMaterialFarmSite(
                    "hip_36601_c_1_a", "polonium",
                ))
                self.assertEqual(len(controller._surface_nav["targets"]), 1)
                self.assertFalse(controller.activateMaterialFarmSite(
                    "orrere_2_b", "zirconium",
                ))
                self.assertEqual(len(controller._surface_nav["targets"]), 1)
                reloaded = self.controller(directory)
                self.assertEqual(reloaded._surface_nav["targets"], [target])
                self.assertEqual(reloaded._surface_nav["activeId"], target["id"])
                before_distance = next(row["distanceLy"] for row in
                                       reloaded._surface_nav["farmSites"]
                                       if row["siteId"] == "hip_36601_c_1_a")
                self.assertIsNone(before_distance)
                reloaded._state["system"] = "HIP 36601"
                reloaded._state["currentPosition"] = reloaded._farm_catalog[
                    "sites"]["hip_36601_c_1_a"]["star_pos"]
                status_file.write_text(json.dumps({
                    "BodyName": "HIP 36601 C 1 a", "Latitude": -57.4599,
                    "Longitude": 126.9543, "Heading": 45,
                    "PlanetRadius": 1_000_000,
                }), encoding="utf-8")
                reloaded._poll_surface_nav()
                self.assertTrue(reloaded._surface_nav["guidance"]["arrived"])
                after_distance = next(row["distanceLy"] for row in
                                      reloaded._surface_nav["farmSites"]
                                      if row["siteId"] == "hip_36601_c_1_a")
                self.assertEqual(after_distance, 0.0)

    def test_farm_edit_delete_restore_survive_reload_and_refresh_waypoint(self):
        with TemporaryDirectory() as directory:
            with mock.patch(
                "ed_companion.phase14.controller_surface_nav.journal_dir",
                return_value=Path(directory),
            ):
                controller = self.controller(directory)
                site_id, source = "hip_36601_c_1_a", "polonium"
                self.assertTrue(controller.activateMaterialFarmSite(site_id, source))
                target_id = controller._surface_nav["activeId"]
                self.assertTrue(controller.editMaterialFarmSite(
                    site_id, source, "selenium", "New System", "A 1",
                    "1,25", "-2.5", "Updated farm route",
                ))
                changed = next(row for row in controller._surface_nav["farmSites"]
                               if row["siteId"] == site_id)
                self.assertEqual(changed["materialKey"], "selenium")
                self.assertEqual(changed["distanceLy"], None)
                self.assertTrue(controller.activateMaterialFarmSite(site_id, source))
                self.assertEqual(len(controller._surface_nav["targets"]), 1)
                target = controller._surface_nav["targets"][0]
                self.assertEqual(target["id"], target_id)
                self.assertEqual((target["system"], target["latitude"]),
                                 ("New System", 1.25))
                reloaded = self.controller(directory)
                self.assertEqual(next(row for row in reloaded._surface_nav["farmSites"]
                                      if row["siteId"] == site_id)["method"],
                                 "Updated farm route")
                self.assertTrue(reloaded.removeMaterialFarmSite(site_id, source))
                self.assertFalse(any(row["siteId"] == site_id
                                     for row in reloaded._surface_nav["farmSites"]))
                self.assertEqual(len(reloaded._surface_nav["farmDeletedSites"]), 1)
                self.assertFalse(reloaded.activateMaterialFarmSite(site_id, source))
                restored = self.controller(directory)
                self.assertEqual(len(restored._surface_nav["farmDeletedSites"]), 1)
                self.assertTrue(restored.restoreMaterialFarmSite(site_id, source))
                original = next(row for row in restored._surface_nav["farmSites"]
                                if row["siteId"] == site_id)
                self.assertEqual(original["system"], "HIP 36601")
                self.assertEqual(original["materialKey"], "polonium")
                self.assertEqual(restored._surface_nav["targets"][0]["id"], target_id)

    def test_failed_farm_save_preserves_list_and_rejects_bad_coordinates(self):
        with TemporaryDirectory() as directory:
            with mock.patch(
                "ed_companion.phase14.controller_surface_nav.journal_dir",
                return_value=Path(directory),
            ):
                controller = self.controller(directory)
                site_id, source = "hip_36601_c_1_a", "polonium"
                original = list(controller._surface_nav["farmSites"])
                self.assertFalse(controller.editMaterialFarmSite(
                    site_id, source, source, "HIP 36601", "C 1 A", "91", "0", "notes",
                ))
                with mock.patch.object(controller, "_persist_json", return_value=False):
                    self.assertFalse(controller.removeMaterialFarmSite(site_id, source))
                self.assertEqual(controller._surface_nav["farmSites"], original)
                self.assertEqual(controller._farm_edits, {})


if __name__ == "__main__":
    unittest.main()
