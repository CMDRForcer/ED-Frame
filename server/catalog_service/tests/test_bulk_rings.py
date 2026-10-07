import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('bulk_rings', Path(__file__).parents[1] / 'ops/import-spansh-rings.py')
bulk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bulk)


class BulkRingTests(unittest.TestCase):
    def fixture(self):
        return {'name': 'Test', 'id64': 123, 'coords': {'x': 1, 'y': 2, 'z': 3},
                'bodies': [{'name': 'Test 1', 'bodyId': 4, 'updateTime': '2025-01-01T00:00:00Z',
                            'reserveLevel': 'Pristine', 'rings': [{'name': 'Test 1 A Ring', 'type': 'Metallic',
                            'signals': {'signals': {'Platinum': 2}, 'updateTime': '2024-01-01T00:00:00Z'}}],
                            'belts': [{'name': 'Test A Belt'}]}]}

    def test_source_times_and_hotspots_are_separate_without_overlap_claim(self):
        row = bulk.project_rings(self.fixture())[0]
        self.assertEqual(row['hotspots'][0]['commodity'], 'platinum')
        self.assertEqual(row['hotspots'][0]['count'], 2)
        self.assertEqual(row['ringMetadataObservedAt'], '2025-01-01T00:00:00Z')
        self.assertTrue(row['observedAt'].startswith('2024-01-01'))
        self.assertEqual(row['hotspots'][0]['observedAt'], '2024-01-01T00:00:00Z')
        self.assertNotIn('bodyId', row)
        self.assertNotIn('resType', row)
        self.assertNotIn('yieldStats', row)
        self.assertEqual(row['evidence'], 'CATALOG_CANDIDATE')

    def test_invalid_coordinates_timestamp_and_foreign_ring_are_skipped(self):
        for change in ('coords', 'time', 'name'):
            item = self.fixture()
            if change == 'coords': item['coords']['x'] = float('nan')
            if change == 'time': item['bodies'][0]['updateTime'] = None
            if change == 'name': item['bodies'][0]['rings'][0]['name'] = 'Other 1 A Ring'
            self.assertEqual(bulk.project_rings(item), [])

    def test_no_signals_does_not_invent_hotspot_or_include_belt(self):
        item = self.fixture()
        del item['bodies'][0]['rings'][0]['signals']
        rows = bulk.project_rings(item)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['hotspots'], [])

    def test_import_does_not_freshen_old_or_undated_hotspots(self):
        row = bulk.project_rings(self.fixture())[0]
        row['observedAt'] = row.pop('ringMetadataObservedAt')
        row['hotspots'].append({'commodity': 'painite', 'count': 3})
        normalized = bulk.normalize_snapshot_row(row)
        self.assertEqual(len(normalized['hotspots']), 1)
        self.assertTrue(normalized['observedAt'].startswith('2024-01-01'))
        self.assertTrue(normalized['ringMetadataObservedAt'].startswith('2025-01-01'))
