import unittest
from unittest.mock import MagicMock, patch
from edframe_catalog.api import search_sites, search_mining_powerplay
from edframe_catalog.mining_region import regional_box_clause, regional_page_limit


class MiningRegionTests(unittest.TestCase):
    def test_opt_in_only_changes_regional_pages(self):
        self.assertEqual(regional_page_limit(200, 1000, regional=True, maximum=1000), 1000)
        self.assertEqual(regional_page_limit(200, None, regional=True, maximum=1000), 200)
        self.assertEqual(regional_page_limit(200, 1000, regional=False, maximum=1000), 200)

    def test_box_is_conservative_and_parameterized(self):
        clause, values = regional_box_clause(1, 2, 3, 250, alias='ms')
        self.assertEqual(values, (-249, -248, 251, 252, -247, 253))
        self.assertEqual(clause.count('%s'), 6)
        self.assertIn('point(ms.x, ms.y) <@ box(', clause)
        self.assertIn('ms.z BETWEEN', clause)

    def test_sites_keep_exact_sphere_and_stable_keyset_with_larger_page(self):
        factory = MagicMock()
        conn = factory.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = []
        with patch('edframe_catalog.api.connection', factory):
            result = search_sites(x=1, y=2, z=3, max_distance=250, offset=0,
                                  limit=1000, regional_page_size=5000)
        query, params = conn.execute.call_args.args
        self.assertIn('POWER(ms.x - %s', query)
        self.assertIn('point(ms.x, ms.y)', query)
        self.assertIn('ORDER BY ms.observed_at DESC, ms.identity DESC', query)
        self.assertEqual(query.count('%s'), len(params))
        self.assertEqual(params[-2:], [5001, 0])
        self.assertFalse(result['hasMore'])

    def test_reference_domain_keeps_legacy_first_page_semantics(self):
        factory = MagicMock()
        conn = factory.return_value.__enter__.return_value
        rows = [{'ring': 'R%s' % i} for i in range(10)]
        conn.execute.return_value.fetchall.return_value = rows
        with patch('edframe_catalog.api.connection', factory), \
             patch('edframe_catalog.api.enrich_ring_metadata', side_effect=lambda c, r: r), \
             patch('edframe_catalog.api.attach_overlap_reports', side_effect=lambda r: r), \
             patch('edframe_catalog.api.community_reference_candidates', return_value=[]) as refs:
            search_sites(x=1, y=2, z=3, max_distance=250, offset=0, limit=2,
                         regional_page_size=5000, include_community_overlaps=True)
        self.assertEqual(refs.call_args.args[1], rows[:2])
        self.assertEqual(refs.call_args.kwargs['limit'], 2)

    def test_powerplay_pages_are_bounded_and_exact_batches_keep_200(self):
        factory = MagicMock()
        conn = factory.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = []
        with patch('edframe_catalog.api.connection', factory):
            result = search_mining_powerplay(1, 2, 3, regional_page_size=1000)
            self.assertEqual(conn.execute.call_args.args[1][-1], 1001)
            self.assertEqual(result['systemCount'], 0)
            search_mining_powerplay(1, 2, 3, regional_page_size=1000, system=['Test'])
            self.assertEqual(conn.execute.call_args.args[1][-1], 201)
