import json
from pathlib import Path
import unittest

from ed_companion.navigation.material_farms import (
    farm_entry_key, material_farm_rows, sanitize_farm_overrides,
)


CATALOG = Path(__file__).resolve().parents[1] / "ed_data" / "raw_materials_database.json"


class MaterialFarmCatalogTests(unittest.TestCase):
    def test_bundled_sites_have_materials_and_nearest_exact_distance_first(self):
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        origin = catalog["sites"]["hip_36601_c_1_a"]["star_pos"]
        rows, materials = material_farm_rows(catalog, origin, "HIP 36601")
        self.assertIn("polonium", [row["key"] for row in materials])
        polonium = [row for row in rows if row["materialKey"] == "polonium"]
        self.assertEqual(polonium[0]["siteId"], "hip_36601_c_1_a")
        self.assertEqual(polonium[0]["distanceLy"], 0.0)
        self.assertEqual((polonium[0]["latitude"], polonium[0]["longitude"]),
                         (-57.4599, 126.9543))
        self.assertGreater(polonium[1]["distanceLy"], 0)
        self.assertTrue(all(row["distanceLy"] is None for row in rows[-2:]))
        self.assertTrue(all(row["latitude"] is None for row in rows[-2:]))

    def test_missing_origin_does_not_invent_distances(self):
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        rows, _ = material_farm_rows(catalog, [float("nan"), 0, 0], "Unknown")
        self.assertTrue(rows)
        self.assertTrue(all(row["distanceLy"] is None for row in rows))

    def test_unverified_and_invalid_coordinates_cannot_become_waypoints(self):
        catalog = {"materials": {"iron": {
            "name": "Iron", "site_ids": ["valid", "unverified", "invalid"],
        }}, "sites": {
            "valid": {"verified": True, "system": "Sol", "body": "A 1",
                      "coordinates": "1 / -2", "star_pos": [0, 0, 0]},
            "unverified": {"verified": False, "system": "Sol", "body": "A 2",
                           "coordinates": "3 / 4", "star_pos": [0, 0, 0]},
            "invalid": {"verified": True, "system": "Sol", "body": "A 3",
                        "coordinates": "91 / 4", "star_pos": [0, 0, 0]},
        }}
        rows, materials = material_farm_rows(catalog, [0, 0, 0], "Sol")
        self.assertEqual([row["siteId"] for row in rows], ["valid", "invalid"])
        self.assertEqual((rows[0]["latitude"], rows[0]["longitude"]), (1, -2))
        self.assertIsNone(rows[1]["latitude"])
        self.assertEqual(materials, [{"key": "iron", "name": "Iron"}])

    def test_local_edit_changes_one_material_association_and_clears_stale_distance(self):
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        key = farm_entry_key("orrere_2_b", "tungsten")
        edits = {key: {
            "materialKey": "molybdenum", "system": "New System",
            "body": "B 2", "latitude": 1.25, "longitude": -2.5,
            "method": "Updated route",
        }}
        rows, materials = material_farm_rows(
            catalog, [0, 0, 0], "Sol", edits,
        )
        changed = next(row for row in rows if row["siteId"] == "orrere_2_b"
                       and row["sourceMaterialKey"] == "tungsten")
        untouched = next(row for row in rows if row["siteId"] == "orrere_2_b"
                         and row["sourceMaterialKey"] == "zirconium")
        self.assertEqual((changed["materialKey"], changed["system"], changed["body"]),
                         ("molybdenum", "New System", "B 2"))
        self.assertEqual((changed["latitude"], changed["longitude"]), (1.25, -2.5))
        self.assertIsNone(changed["distanceLy"])
        self.assertEqual(untouched["system"], "Orrere")
        self.assertIn("molybdenum", [row["key"] for row in materials])
        known_site = "hip_36601_c_1_a"
        known_key = farm_entry_key(known_site, "polonium")
        shifted, _ = material_farm_rows(catalog, [0, 0, 0], "Sol", {
            known_key: {
                "materialKey": "polonium", "system": "New System",
                "body": "C 1 A", "latitude": 1, "longitude": 2,
                "method": "Updated route",
            },
        })
        self.assertIsNone(next(row for row in shifted
                               if row["siteId"] == known_site)["distanceLy"])

    def test_deleted_entry_is_hidden_but_recoverable(self):
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        key = farm_entry_key("hip_36601_c_1_a", "polonium")
        edits = {key: {"deleted": True}}
        visible, _ = material_farm_rows(catalog, overrides=edits)
        all_rows, _ = material_farm_rows(catalog, overrides=edits,
                                         include_deleted=True)
        self.assertFalse(any(row["siteId"] == "hip_36601_c_1_a" for row in visible))
        self.assertTrue(next(row for row in all_rows
                             if row["siteId"] == "hip_36601_c_1_a")["deleted"])
        self.assertTrue(any(row["siteId"] == "hip_36601_c_1_a"
                            for row in material_farm_rows(catalog)[0]))

    def test_invalid_saved_edits_are_ignored(self):
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        key = farm_entry_key("hip_36601_c_1_a", "polonium")
        self.assertEqual(sanitize_farm_overrides(catalog, {
            key: {"materialKey": "polonium", "system": "HIP 36601", "body": "C 1 A",
                  "latitude": 91, "longitude": 1, "method": "bad"},
            "missing|polonium": {"deleted": True},
        }), {})


if __name__ == "__main__":
    unittest.main()
