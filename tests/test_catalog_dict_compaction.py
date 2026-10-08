"""Exact dictionary semantics and bounded, local catalog layout reuse."""
import copy
import json
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
import unittest

from ed_companion.navigation.catalog_json import (
    CatalogDictFactory, iter_catalog_json, load_catalog_json,
)
from ed_companion.navigation.mining_batch import prepare_mining_batch
from ed_companion.persistence import atomic_write_chunks


class CatalogDictCompactionTests(unittest.TestCase):
    def test_plain_dict_semantics_order_special_keys_and_independent_values(self):
        factory = CatalogDictFactory()
        records = [factory.copy_record({
            "__dict__": index, "__class__": None, "": False, "Ä": [index],
            "nullable": None, "nested": {"value": index},
        }) for index in range(50)]
        for index, record in enumerate(records):
            self.assertIs(type(record), dict)
            self.assertEqual(tuple(record), (
                "__dict__", "__class__", "", "Ä", "nullable", "nested",
            ))
            self.assertEqual(record, copy.deepcopy(record))
            self.assertEqual(record, json.loads(json.dumps(record)))
            self.assertEqual(record, {**record})
            self.assertEqual(record, dict(record.items()))
            self.assertEqual(record["Ä"], [index])
        records[0].pop("__class__")
        records[0]["new"] = 42
        records[0]["Ä"].append(7)
        self.assertIn("__class__", records[1])
        self.assertNotIn("new", records[1])
        self.assertEqual(records[1]["Ä"], [1])

    def test_factory_shapes_are_bounded_and_oversized_records_are_not_truncated(self):
        factory = CatalogDictFactory()
        for index in range(factory.MAX_SHAPES * 3):
            value = {f"field-{index}": index}
            self.assertEqual(factory.copy_record(value), value)
        self.assertEqual(len(factory._shapes), factory.MAX_SHAPES)
        large = {f"field-{index}": index for index in range(100)}
        self.assertEqual(factory.copy_record(large), large)
        self.assertEqual(factory.copy_record({}), {})
        self.assertEqual(factory.copy_record(large, exclude={"field-7"}), {
            key: value for key, value in large.items() if key != "field-7"
        })

    def test_json_duplicate_keys_nested_values_and_roundtrip_are_exact(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            original = {"candidates": [{
                "ring": f"Test {index}", "system": "Same",
                "hotspots": [{"commodity": "platinum", "count": 1}],
                "observations": [{"source": "Synthetic", "observedAt": ""}],
                "empty": [], "none": None,
            } for index in range(100)]}
            atomic_write_chunks(path, iter_catalog_json(original))
            loaded = load_catalog_json(path, {})
            self.assertEqual(loaded, original)
            loaded["candidates"][0]["hotspots"][0]["count"] = 17
            self.assertEqual(loaded["candidates"][1]["hotspots"][0]["count"], 1)
            # JSON last-value-wins and first insertion order must not change.
            atomic_write_chunks(path, ['[{"x":1,"y":2,"x":3}]'])
            value = load_catalog_json(path, [])
            self.assertEqual(value, [{"x": 3, "y": 2}])
            self.assertEqual(tuple(value[0]), ("x", "y"))

    @unittest.skipUnless(platform.python_implementation() == "CPython", "CPython optimization")
    def test_repeated_layouts_use_less_dict_storage_without_losing_fields(self):
        factory = CatalogDictFactory()
        original = {f"field-{index}": index for index in range(25)}
        records = [factory.copy_record(original) for _ in range(500)]
        self.assertTrue(all(record == original for record in records))
        self.assertLess(sum(map(sys.getsizeof, records)), 0.75 * 500 * sys.getsizeof(original))

    def test_merge_compacts_only_new_rows_and_keeps_inputs_and_history_exact(self):
        original = [{"system": "Test", "ring": "Test A Ring", "note": "old"},
                    {"system": "Test", "ring": "Test B Ring", "note": "untouched"}]
        additions = [{"system": "Test", "ring": "Test A Ring", "note": "new",
                      "ageSeconds": 123, "hotspots": []}]
        frozen = copy.deepcopy((original, additions))
        captured = {}

        class Archive:
            def archive(self, category, rows, **_kwargs):
                captured[category] = copy.deepcopy(rows)

        result = prepare_mining_batch(original, additions, archive=Archive(),
                                      transient_fields={"ageSeconds"})
        self.assertEqual((original, additions), frozen)
        self.assertIs(result["candidates"][1], original[1])
        self.assertTrue(all(type(row) is dict for row in result["candidates"]))
        self.assertNotIn("ageSeconds", result["candidates"][0])
        self.assertEqual(captured["mining_observations"], additions)
        self.assertEqual(captured["mining_catalog"], [original[0]])


if __name__ == "__main__":
    unittest.main()
