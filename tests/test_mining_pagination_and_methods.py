import unittest
from unittest.mock import Mock
from ed_companion.navigation.mining_finder import fetch_edframe_mining_candidates
from ed_companion.phase14.controller_navigation import NavigationMixin


class Response:
    def __init__(self, data): self.data = data
    def raise_for_status(self): pass
    def json(self): return self.data


class MiningPaginationAndMethodsTests(unittest.TestCase):
    def test_pages_reach_later_system_and_preserve_references(self):
        get = Mock(side_effect=[
            Response({'results': [{'system': 'Early', 'ring': 'Early A Ring'}],
                      'communityReferences': [{'system': 'Reference', 'ring': 'Reference A Ring'}],
                      'hasMore': True, 'nextOffset': 200}),
            Response({'results': [{'system': 'BZ Ceti', 'ring': 'BZ Ceti 5 A Ring'}],
                      'hasMore': False, 'nextOffset': None}),
        ])
        diagnostics = {}
        rows = fetch_edframe_mining_candidates('Shanteneri', get, diagnostics=diagnostics)
        self.assertEqual({r['system'] for r in rows}, {'Early', 'Reference', 'BZ Ceti'})
        self.assertEqual(get.call_args_list[1].kwargs['params']['offset'], 200)
        self.assertEqual(diagnostics, {'count': 3, 'bounded': False, 'pages': 2})

    def test_invalid_cursor_does_not_loop(self):
        get = Mock(return_value=Response({'results': [], 'hasMore': True, 'nextOffset': 0}))
        with self.assertRaises(ValueError): fetch_edframe_mining_candidates('Test', get)
        self.assertEqual(get.call_count, 1)

    def test_safety_cap_is_explicit_not_reported_as_complete(self):
        def get(url, **kwargs):
            return Response({'results': [], 'hasMore': True,
                             'nextOffset': kwargs['params']['offset'] + 200})
        diagnostics = {}
        fetch_edframe_mining_candidates('Test', get, diagnostics=diagnostics)
        self.assertTrue(diagnostics['bounded'])
        self.assertEqual(diagnostics['pages'], 50)

    def test_platinum_hotspot_cannot_override_laser_ring_compatibility(self):
        class Probe(NavigationMixin): pass
        probe = Probe()
        probe._state = {'system': 'Test'}
        probe._mining_rows = Mock(return_value=[{
            'system': 'Test', 'ring': 'Test A Ring', 'distanceLy': 0,
            'ringType': kind, 'ringTypeName': kind,
            'evidence': 'LIVE_REPORTED',
            'hotspots': [{'commodity': 'platinum', 'count': 1}],
            'communityOverlapReports': [{'commodity': 'platinum', 'reportedResTypes': ['HIGH']}],
        } for kind in ('Metal Rich', 'eRingClass_Metalic')])
        laser = probe._mining_find_page('Platinum', 100, 'ALL EVIDENCE', 'ALL RESERVES', 'LASER')
        core = probe._mining_find_page('Platinum', 100, 'ALL EVIDENCE', 'ALL RESERVES', 'CORE')
        self.assertEqual([r['ringType'] for r in laser], ['eRingClass_Metalic'])
        self.assertEqual([r['ringType'] for r in core], ['Metal Rich'])
