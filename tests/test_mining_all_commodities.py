"""Broad searches retain evidence precedence and method-specific compatibility."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from ed_companion.phase14.controller import CockpitController
from ed_companion.phase14 import controller_navigation as navigation


class AllCommodityTests(unittest.TestCase):
    def owner(self, rows):
        owner = navigation.NavigationMixin()
        owner._state = {'system': 'Mine', 'currentPosition': [0, 0, 0]}
        owner._network_threads_lock = True
        owner._valid_star_position = CockpitController._valid_star_position
        owner._mining_rows = lambda: rows
        owner._mining_rows_cache_key = 'synthetic'
        return owner

    def ring(self, ring_type='Metallic', **fields):
        return {'system': 'Mine', 'ring': 'A Ring', 'ringType': ring_type,
                'coordinates': [0, 0, 0], 'reserveLevel': 'PristineResources',
                'observedAt': '2026-10-09T18:00:00Z', 'hotspots': [], **fields}

    def search(self, owner, method='LASER'):
        owner._mining_find_cache_key = None
        return owner._mining_find_page('ALL COMMODITIES', 250, 'ALL EVIDENCE',
                                      'ALL RESERVES', method, 'Mine', True)

    def test_local_yield_precedes_hotspot_and_ring_rules_without_mutating_facts(self):
        rows = [self.ring(hotspots=[{'commodity': 'platinum'}, {'commodity': 'osmium'}],
            yieldStats=[{'commodity': 'platinum', 'prospectorHits': 2},
                        {'commodity': 'custommineral', 'refinedCount': 1},
                        {'commodity': 'painite', 'prospectorHits': 0}])]
        before = copy.deepcopy(rows)
        result = self.search(self.owner(rows))[0]['candidateCommodities']
        evidence = {item['id']: item['evidence'] for item in result}
        self.assertEqual(evidence['platinum'], 'LOCAL_YIELD')
        self.assertEqual(evidence['custommineral'], 'LOCAL_YIELD')
        self.assertEqual(evidence['osmium'], 'HOTSPOT')
        self.assertEqual(evidence['painite'], 'RING_TYPE')
        self.assertEqual([item['evidence'] for item in result[:2]], ['LOCAL_YIELD']*2)
        self.assertEqual(result[:2], sorted(result[:2], key=lambda item: item['name'].casefold()))
        self.assertEqual(rows, before)

    def test_unknown_ring_keeps_observed_evidence_and_method_change_rebuilds_rules(self):
        rows = [self.ring('Unknown', hotspots=[{'commodity': 'platinum'}]),
                self.ring('MetalRich', hotspots=[{'commodity': 'platinum'}])]
        owner = self.owner(rows)
        laser = self.search(owner)
        self.assertEqual(laser[0]['candidateCommodities'],
                         [{'id':'platinum','name':'Platinum','evidence':'HOTSPOT'}])
        self.assertNotIn('platinum', [item['id'] for item in laser[1]['candidateCommodities']])
        core = self.search(owner, 'CORE')
        self.assertIn('platinum', [item['id'] for item in core[1]['candidateCommodities']])

    def test_query_rules_are_bounded_and_result_dicts_belong_to_each_ring(self):
        rows = [self.ring(ring=f'{index} A Ring') for index in range(120)]
        owner = self.owner(rows)
        rule = Mock(wraps=navigation.mining_ring_types_for_method)
        with patch.object(navigation, 'mining_ring_types_for_method', rule):
            result = self.search(owner)
        self.assertLess(rule.call_count, 40)
        self.assertEqual(len(result), 120)
        self.assertEqual(result[0]['candidateCommodities'], result[-1]['candidateCommodities'])
        result[0]['candidateCommodities'][0]['name'] = 'Edited result'
        self.assertNotEqual(result[0]['candidateCommodities'], result[-1]['candidateCommodities'])
        self.assertNotIn('candidateCommodities', rows[0])

    def test_market_reuse_is_opt_in_to_one_worker_and_exact_query(self):
        owner = self.owner([])
        owner._known_mining_origin = lambda _: {'coordinates': [0,0,0]}
        owner._mining_market_store = Mock()
        owner._mining_market_store.nearby.return_value = []
        query = {'startSystem':'mine','commodity':'platinum','nearbyLy':250}
        owner._mining_market_rows_for_query(query)
        owner._mining_market_rows_for_query(query)
        self.assertEqual(owner._mining_market_store.nearby.call_count, 2)
        owner._mining_plan_market_rows = {}
        first = owner._mining_market_rows_for_query(query)
        self.assertIs(owner._mining_market_rows_for_query(dict(query)), first)
        self.assertEqual(owner._mining_market_store.nearby.call_count, 3)
        owner._mining_market_rows_for_query({**query, 'commodity':'allcommodities'})
        self.assertEqual(owner._mining_market_store.nearby.call_count, 4)
        del owner._mining_plan_market_rows
        owner._mining_market_rows_for_query(query)
        self.assertEqual(owner._mining_market_store.nearby.call_count, 5)

    def test_background_all_query_keeps_captured_free_text_origin(self):
        from ed_companion.navigation.mining_ring_store import RingCatalogStore
        with TemporaryDirectory() as directory:
            path = Path(directory)
            source = path / 'rings.json'
            source.write_text(json.dumps({'candidates':[
                self.ring(system='Target', coordinates=[10,20,30])]}),encoding='utf-8')
            view = RingCatalogStore(path/'rings.sqlite3','alpha').adopt(source)
            owner = CockpitController.__new__(CockpitController)
            owner._state = {'system':'Current','currentPosition':[0,0,0]}
            owner.profile_context = Mock(key='alpha')
            owner._profile_generation = 1
            owner.mining_catalog_file = path/'rings.json'
            owner._mining_catalog = {'candidates':view,'resetAt':''}
            owner._mining_rows = lambda: view
            owner._mining_plan_key = lambda args: ('scope',args)
            owner._mining_powerplay_index_context = lambda: 'scope'
            owner._mining_market_cache = {'origin':{'system':'Other','coordinates':[999,999,999]}}
            owner._mining_market_store = Mock()
            owner._mining_market_store.nearby.return_value = []
            owner._start_network_worker = Mock(return_value=True)
            owner.miningPlanReady = Mock()
            captured = []
            def compute(snapshot, *args):
                captured.append(snapshot)
                self.assertEqual(snapshot._known_mining_origin('Target')['coordinates'],[10,20,30])
                snapshot._mining_market_rows_for_query({'startSystem':'target',
                    'commodity':'allcommodities','nearbyLy':250,'minDemand':5000,
                    'maxMarketAgeHours':1,'landingPad':'L'})
                return []
            args=('Target','ALL COMMODITIES',250,'ALL RESERVES','ANY RING',True,
                'LASER','POWERPLAY MERITS',5000,500000,1,100,False,True,False,
                False,'L','Aisling Duval','REINFORCE','ANY','ANY')
            with patch.object(navigation.NavigationMixin,'_compute_mining_plan_routes',compute):
                owner._queue_mining_plan(args)
                # Replacing live inputs cannot change a dispatched worker.
                owner._mining_catalog = {'candidates':[]}
                owner._start_network_worker.call_args.args[0]()
            self.assertEqual(owner._mining_market_store.nearby.call_count,1)
            self.assertEqual(owner._mining_market_store.nearby.call_args.kwargs['origin_coordinates'],[10,20,30])
            self.assertFalse(hasattr(captured[0],'_mining_plan_market_rows'))
            self.assertEqual(owner.miningPlanReady.emit.call_args.args[0][-1],'')


if __name__ == '__main__':
    unittest.main()
