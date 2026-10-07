import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('system_extract', Path(__file__).parents[1] / 'ops' / 'extract-system-positions.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SystemPositionExtractionTests(unittest.TestCase):
    def row(self, name, x=1, address=123):
        return json.dumps({'name': name, 'id64': address, 'coords': {'x': x, 'y': 2, 'z': 3},
                           'updateTime': '2026-10-01T00:00:00Z'}) + ','

    def test_exact_names_and_source_time(self):
        rows = module.extract_lines(['[', self.row('Test'), self.row('Test Extra'), ']'], ['test', 'Missing'])
        self.assertTrue(rows[0]['resolved'])
        self.assertEqual(rows[0]['data']['updateTime'], '2026-10-01T00:00:00Z')
        self.assertFalse(rows[1]['resolved'])

    def test_invalid_coordinates_and_conflicts_not_accepted(self):
        rows = module.extract_lines([self.row('Bad', float('nan')), self.row('Conflict'),
                                     self.row('Conflict', 5)], ['Bad', 'Conflict'])
        self.assertFalse(any(r['resolved'] for r in rows))
        self.assertEqual(rows[1]['status'], 'CONFLICT')

    def test_corrupt_dump_does_not_silently_skip_records(self):
        with self.assertRaises(json.JSONDecodeError):
            module.extract_lines(['broken'], ['Test'])
