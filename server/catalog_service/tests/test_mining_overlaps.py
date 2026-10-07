import unittest
from unittest.mock import MagicMock, patch
from edframe_catalog.mining_overlaps import (
    catalog, ring_key, attach_overlap_reports, community_reference_candidates, imported_system_positions,
)


class MiningOverlapTests(unittest.TestCase):
    def test_paginated_sites_have_stable_order_and_next_offset(self):
        from edframe_catalog.api import search_sites
        connection = MagicMock()
        conn = connection.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = [
            {'system': 'Test', 'ring': 'Test A Ring', 'ringType': 'Metallic', 'reserveLevel': 'Pristine'},
            {'system': 'Test', 'ring': 'Test B Ring', 'ringType': 'Metallic', 'reserveLevel': 'Pristine'},
            {'system': 'Test', 'ring': 'Test C Ring', 'ringType': 'Metallic', 'reserveLevel': 'Pristine'},
        ]
        with patch('edframe_catalog.api.connection', connection):
            result = search_sites(system='Test', limit=2, offset=200)
        query, values = conn.execute.call_args.args
        self.assertIn('ORDER BY ms.observed_at DESC, ms.identity', query)
        self.assertIn('selected_sites AS MATERIALIZED', query)
        self.assertLess(query.index('LIMIT %s OFFSET %s'), query.index('LEFT JOIN LATERAL'))
        self.assertEqual(values[-2:], [3, 200])
        self.assertEqual(len(result['results']), 2)
        self.assertTrue(result['hasMore'])
        self.assertEqual(result['nextOffset'], 202)

    def test_ring_candidates_and_community_parameters_stay_in_sql_order(self):
        from edframe_catalog.api import search_sites
        connection = MagicMock()
        conn = connection.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.side_effect = [
            [{'identity': 'site', 'system': 'Dubbuennel', 'ring': 'Dubbuennel 3 A Ring'}], [], [],
        ]
        with patch('edframe_catalog.api.connection', connection):
            search_sites(commodity='platinum', system='Dubbuennel',
                         include_ring_candidates=True, include_community_overlaps=True, limit=20)
        query, parameters = conn.execute.call_args_list[1].args
        self.assertEqual(query.count('%s'), len(parameters))
        self.assertIn('Metallic', parameters[3])
        self.assertEqual(parameters[5], ['site'])
        self.assertEqual(parameters[6:], ['Dubbuennel', 20, 0])

    def test_community_search_keeps_sql_parameters_in_order(self):
        from edframe_catalog.api import search_sites
        connection = MagicMock()
        conn = connection.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.side_effect = [
            [{'identity': 'site', 'system': 'Dubbuennel', 'ring': 'Dubbuennel 3 A Ring'}],
            [{'system': 'Dubbuennel', 'ring': 'Dubbuennel 3 A Ring',
              'ringType': 'Metallic', 'reserveLevel': 'Pristine'}],
            [],
        ]
        with patch('edframe_catalog.api.connection', connection):
            result = search_sites(commodity='platinum', system='Dubbuennel',
                                  include_community_overlaps=True, limit=20)
        query, parameters = conn.execute.call_args_list[1].args
        self.assertEqual(query.count('%s'), len(parameters))
        self.assertEqual(parameters, [365, 'platinum', 'platinum', ['site'], 'Dubbuennel', 20, 0])
        self.assertTrue(result['results'][0]['communityOverlapReports'])

    def test_position_anchors_reference_without_inventing_ring_metadata(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [{
            'name': 'Lalande 34968', 'system_address': 123,
            'x': 3., 'y': 0., 'z': 0., 'observed_at': '2026-10-01',
        }]
        rows = community_reference_candidates(conn, [], system='Lalande 34968',
                    commodity='platinum', origin=(0, 0, 0), radius=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['ring'], 'Lalande 34968 AB 8 A Ring')
        self.assertEqual(rows[0]['evidence'], 'CATALOG_CANDIDATE')
        self.assertIsNone(rows[0]['observedAt'])
        self.assertIsNone(rows[0]['ringType'])
        self.assertEqual(rows[0]['hotspots'], [])
        self.assertEqual(rows[0]['prospectorSampleCount'], 0)
        self.assertEqual(community_reference_candidates(conn, rows,
                          system='Lalande 34968', commodity='platinum'), [])
        self.assertEqual(community_reference_candidates(conn, [],
                          system='Lalande 34968', origin=(0, 0, 0), radius=1), [])

    def test_missing_position_is_not_assumed_to_be_origin(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [{
            'name': 'Lalande 34968', 'x': None, 'y': 0., 'z': 0.,
        }]
        with patch('edframe_catalog.mining_overlaps.imported_system_positions', return_value={}):
            self.assertEqual(community_reference_candidates(conn, [], system='Lalande 34968'), [])

    def test_all_22_coordinate_imports_have_separate_provenance(self):
        positions = imported_system_positions()
        self.assertEqual(len(positions), 22)
        self.assertIsNone(positions['hun nik']['positionEvidence']['observedAt'])
        self.assertIsNone(positions['hun nik']['positionEvidence']['dumpSha256'])
        self.assertTrue(positions['lalande 34968']['positionEvidence']['dumpSha256'])

    def test_import_locates_reference_without_confirming_ring(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        rows = community_reference_candidates(conn, [], system='Hun Nik',
                    origin=(155.6875, 107.125, -78.65625), radius=1)
        self.assertTrue(rows)
        self.assertEqual(rows[0]['distanceLy'], 0)
        self.assertIsNone(rows[0]['ringType'])
        self.assertIsNone(rows[0]['observedAt'])
        self.assertEqual(rows[0]['ringAssociationStatus'], 'COMMUNITY_REFERENCE_ONLY')

    def test_snapshot_has_provenance_without_fabricated_verification(self):
        rows = catalog()
        self.assertGreater(len(rows), 80)
        for row in rows:
            self.assertIsNone(row['verifiedAt'])
            self.assertEqual(row['status'], 'COMMUNITY_REPORTED_UNDATED')
            self.assertIn('/b5680d18', row['sourceUrl'])
            self.assertIn('2025-01-05', row['sourceFileModifiedAt'])
            self.assertNotIn('yieldStats', row)

    def test_ring_aliases_are_exact_after_normalization(self):
        self.assertEqual(ring_key('Lalande 34968', 'AB8 Ring A'),
                         ring_key('Lalande 34968', 'Lalande 34968 AB 8 A Ring'))
        self.assertNotEqual(ring_key('Test', '2 A Ring'), ring_key('Test', '2 B Ring'))

    def test_other_commodities_not_promoted_to_platinum(self):
        rows = catalog()
        self.assertTrue(any(r['commodity'] == 'tritium' for r in rows))
        self.assertTrue(any(r['commodity'] == 'painite' for r in rows))
        wrong = next(r for r in rows if r['system'] == 'HIP 52780' and '3' in r['ring'])
        self.assertEqual(wrong['commodity'], 'painite')

    def test_duplicate_reports_preserved_without_affecting_measurements(self):
        row = {'system': 'Lalande 34968', 'ring': 'Lalande 34968 AB 8 A Ring',
               'observedAt': '2026-10-01', 'yieldStats': [], 'evidence': 'LIVE_REPORTED'}
        attach_overlap_reports([row])
        self.assertGreaterEqual(len(row['communityOverlapReports']), 2)
        self.assertEqual(row['observedAt'], '2026-10-01')
        self.assertEqual(row['yieldStats'], [])
        self.assertNotIn('resType', row)
        self.assertEqual(row['evidence'], 'LIVE_REPORTED')
