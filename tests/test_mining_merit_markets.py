from datetime import datetime, timedelta, timezone
import threading
import time
import unittest
from unittest.mock import Mock

from ed_companion.navigation.mining_merit_markets import (
    MeritMarketCache, fill_merit_markets, merit_market_targets,
)
from ed_companion.navigation.mining_planner import _powerplay_index, _merit_status, plan_mining_routes
from tests.test_mining_powerplay_evidence import fact, market, NOW

QUERY = {'commodity': 'platinum', 'minDemand': 5000, 'maxMarketAgeHours': 48,
         'landingPad': 'L', 'nearbyLy': 250, 'startSystem': 'Origin'}
CONTEXT = {'power': 'Aisling Duval', 'goal': 'REINFORCE', 'method': 'LASER'}


def ring(system='Mine', **fields):
    return {'system': system, 'ring': system + ' A Ring', 'ringType': 'Metallic',
            'coordinates': [0, 0, 0], 'distanceLy': 10, **fields}


class Session:
    def __init__(self, get):
        self.get = get

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def response(name='Mine', rows=None):
    result = Mock()
    result.json.return_value = {'results': rows if rows is not None else [
        {**market(name), 'marketId': 42, 'landingPadSize': 'L', 'x': 0, 'y': 0, 'z': 0}]}
    return result


class MeritMarketsTests(unittest.TestCase):
    def test_partial_regional_rings_do_not_hide_explicit_eligible_systems(self):
        context={**CONTEXT,'allCommodities':True,'_originCoordinates':[0,0,0]}
        self.assertIn('Missing Ring',merit_market_targets([ring()],
            [fact(),fact('Missing Ring',coordinates=[10,0,0])],[],QUERY,context,now=NOW))
        self.assertNotIn('Outside',merit_market_targets([ring()],
            [fact(),fact('Outside',coordinates=[500,0,0])],[],QUERY,context,now=NOW))

    def test_idle_deferred_plan_can_resume_without_a_qml_instance(self):
        from ed_companion.phase14.controller_navigation import NavigationMixin
        c=NavigationMixin();c._mining_plan_deferred=True;c._mining_plan_requested_args=('new-query',)
        c._mining_plan_inputs_pending=Mock(return_value=False);c._queue_mining_plan=Mock()
        self.assertFalse(c._mining_plan_is_busy())
        c._resume_deferred_mining_plan()
        c._queue_mining_plan.assert_called_once_with(('new-query',))
        c._active_mining_plan='active';c._queue_mining_plan.reset_mock()
        self.assertTrue(c._mining_plan_is_busy())
        c._resume_deferred_mining_plan();c._queue_mining_plan.assert_not_called()

    def test_powerplay_cache_is_scoped_to_power_and_goal(self):
        from ed_companion.navigation.mining_region_cache import MiningRegionCache
        origin={'coordinates':[0,0,0]}
        a={**QUERY,'_powerplayPower':'Aisling Duval','_powerplayGoal':'REINFORCE'}
        b={**a,'_powerplayPower':'Felicia Winters'}
        c={**a,'_powerplayGoal':'ACQUIRE'}
        self.assertNotEqual(MiningRegionCache._key('powerplay',a,origin),MiningRegionCache._key('powerplay',b,origin))
        self.assertNotEqual(MiningRegionCache._key('powerplay',a,origin),MiningRegionCache._key('powerplay',c,origin))

    def test_grouped_batches_fill_more_than_64_pairs_and_retain_source_facts(self):
        calls=[]
        class BatchSession(Session):
            def post(self,url,**kwargs):
                body=kwargs['json']; calls.append(body)
                rows=[{**market(target['system']), 'commodity':symbol,
                       'marketId':len(rows_seen)+1,'landingPadSize':'L'}
                      for target in body['targets'] for symbol in target['commodities']
                      for rows_seen in [calls]]
                result=response(rows=rows)
                result.status_code=200
                result.json.return_value.update(protocol=1,hasMore=False,
                    coverage=[{'system':target['system'],'queried':True} for target in body['targets']],
                    powerplay=[fact(body['targets'][0]['system'])])
                return result
        candidates=[ring(str(i)) for i in range(210)]
        facts=[fact(str(i)) for i in range(210)]
        rows,coverage=fill_merit_markets(candidates,facts,[],QUERY,CONTEXT,
            session_factory=lambda:BatchSession(Mock()))
        self.assertEqual(len(calls),2)
        self.assertLessEqual(max(len(body['targets']) for body in calls),200)
        self.assertEqual(coverage['checked'],210)
        self.assertEqual(len(rows),210)
        self.assertTrue(coverage['_powerplayFacts'])
        self.assertFalse(coverage['bounded'])

    def test_legacy_server_is_cached_and_uses_existing_exact_get_path(self):
        calls=[]
        class LegacySession(Session):
            def post(self,*args,**kwargs):
                calls.append('POST'); return Mock(status_code=404)
        cache=MeritMarketCache()
        for _ in range(2):
            rows,coverage=fill_merit_markets([ring()],[fact()],[],QUERY,CONTEXT,
                session_factory=lambda:LegacySession(lambda *a,**k:response()),cache=cache)
            self.assertEqual(coverage['checked'],1)
        self.assertEqual(calls,['POST'])

    def test_incomplete_batch_cannot_cache_absence(self):
        class BadSession(Session):
            def post(self,*args,**kwargs):
                result=response(rows=[]);result.status_code=200
                result.json.return_value.update(protocol=1,hasMore=True,coverage=[])
                return result
        rows,coverage=fill_merit_markets([ring()],[fact()],[],QUERY,CONTEXT,
            session_factory=lambda:BadSession(lambda *a,**k:response()))
        self.assertTrue(rows)
        self.assertEqual(coverage['checked'],1)

    def test_painite_laser_does_not_treat_metal_rich_core_hotspots_as_laser_evidence(self):
        query={**QUERY,'commodity':'painite'}
        self.assertEqual(merit_market_targets([ring(ringType='Metal Rich')],[fact()],[],query,CONTEXT,now=NOW),[])
        self.assertEqual(merit_market_targets([ring()],[fact()],[],query,CONTEXT,now=NOW),['Mine'])

    def test_all_search_checks_concrete_compatible_pairs_and_reuses_existing_quotes(self):
        calls=[]
        def get(_url, **kwargs):
            params=kwargs['params']
            calls.append(params)
            return response(params['system'],[{**market(params['system']),
                'commodity':params['commodity'],'marketId':len(calls),'landingPadSize':'L'}])
        cache=MeritMarketCache()
        candidates=[ring(),ring('Ice',ringType='Icy')]
        known=[market(commodity='osmium',landingPadSize='L',sellPrice=200000)]
        context={**CONTEXT,'allCommodities':True}
        def fill():
            return fill_merit_markets(candidates,[fact(),fact('Ice')],[],QUERY,context,
                session_factory=lambda:Session(get),cache=cache,known_markets=known)
        rows,coverage=fill()
        requested={(row['system'],row['commodity']) for row in calls}
        self.assertIn(('Ice','lowtemperaturediamond'),requested)
        self.assertIn(('Ice','bromellite'),requested)
        self.assertIn(('Mine','platinum'),requested)
        self.assertNotIn(('Mine','osmium'),requested)
        self.assertFalse(any(row['commodity'] in {'allcommodities','moissanite','alexandrite'} for row in calls))
        self.assertNotIn('osmium',{row['commodity'] for row in rows})
        count=len(calls)
        self.assertEqual(fill()[1]['cacheHits'],count)
        self.assertEqual(len(calls),count)

    def targets(self, candidates=None, powerplay=None, markets=(), **context):
        return merit_market_targets(candidates or [ring()], powerplay or [fact()],
            markets, QUERY, {**CONTEXT, **context}, now=NOW)

    def test_matching_control_and_method_are_required_without_inventing_presence(self):
        self.assertEqual(self.targets(), ['Mine'])
        for changed in ({'ringType': 'Metal Rich'}, {'ringType': 'Icy'}, {'miningSiteType': 'BELT'}):
            self.assertEqual(self.targets(candidates=[ring(**changed)]), [])
        for changed in ({'controllingPower': ''}, {'controllingPower': 'Yuri Grom'},
                        {'observedAt': (NOW-timedelta(days=15)).isoformat()}, {'observedAt': 'bad'}):
            self.assertEqual(self.targets(powerplay=[fact(**changed)]), [])
        self.assertEqual(self.targets(power='ANY'), [])

    def test_valid_existing_market_avoids_retrieval_but_filtered_one_does_not(self):
        valid = market(landingPadSize='L')
        self.assertEqual(self.targets(markets=[valid]), [])
        for changed in ({'landingPadSize': 'M'}, {'demand': 100},
                        {'observedAt': (NOW-timedelta(days=3)).isoformat()}):
            self.assertEqual(self.targets(markets=[{**valid, **changed}]), ['Mine'])

    def test_acquire_uses_unoccupied_target_and_distance_not_source_market(self):
        facts = [fact(), fact('Sale', power='', controllingPower='', powers=[],
                              powerState='Unoccupied', coordinates=[15, 0, 0]),
                 fact('Far', power='', controllingPower='', powers=[],
                      powerState='Unoccupied', coordinates=[100, 0, 0])]
        self.assertEqual(self.targets(powerplay=facts, goal='ACQUIRE'), ['Sale'])

    def test_undermine_requires_known_contesting_membership(self):
        opponent = fact(controllingPower='Yuri Grom', powers=['Yuri Grom', 'Aisling Duval'])
        self.assertEqual(self.targets(powerplay=[opponent], goal='UNDERMINE'), ['Mine'])
        self.assertEqual(self.targets(powerplay=[{**opponent, 'powers': ['Yuri Grom']}], goal='UNDERMINE'), [])

    def test_targeted_lower_price_survives_region_top_list_and_real_controller_pipeline(self):
        from ed_companion.phase14.controller import CockpitController
        from ed_companion.phase14.controller_navigation import NavigationMixin
        get = Mock(return_value=response())
        expensive = [market('Other', sellPrice=300000, landingPadSize='L')]
        rows, coverage = fill_merit_markets([ring()], [fact()], expensive, QUERY, CONTEXT,
            session_factory=lambda: Session(get))
        self.assertEqual(coverage['addedRows'], 1)
        self.assertEqual(get.call_args.kwargs['params']['system'], 'Mine')
        c = NavigationMixin()
        c._state = {'system': 'Origin', 'currentPosition': [0, 0, 0]}
        c._network_threads_lock = True
        c._mining_rows = lambda: [ring()]
        c._valid_star_position = CockpitController._valid_star_position
        c._known_mining_origin = lambda name: {'system': name, 'coordinates': [0, 0, 0]}
        c._mining_market_catalog = {'markets': rows}
        c._mining_powerplay_catalog = {}
        c._mining_powerplay_observations = [fact()]
        found = c._compute_mining_plan_routes('Origin', 'Platinum', 250, 'ALL RESERVES',
            'ANY RING', True, 'LASER', 'POWERPLAY MERITS', 5000, 0, 48, 30,
            False, False, False, False, 'L', 'Aisling Duval', 'REINFORCE', 'ANY', 'ANY')
        self.assertEqual(found[0]['sellSystem'], 'Mine')
        self.assertEqual(found[0]['verificationStatus'], 'VERIFIED')

    def test_successful_empty_checks_reuse_cache_and_filter_changes_force_new_check(self):
        clock = Mock(return_value=100)
        cache = MeritMarketCache(clock=clock)
        get = Mock(return_value=response(rows=[]))
        def fill(query=QUERY):
            return fill_merit_markets([ring()], [fact()], [], query, CONTEXT,
                cache=cache, session_factory=lambda: Session(get))
        self.assertEqual(fill()[1]['cacheHits'], 0)
        self.assertEqual(fill()[1]['cacheHits'], 1)
        self.assertEqual(get.call_count, 1)
        fill({**QUERY, 'minDemand': 7000})
        self.assertEqual(get.call_count, 2)
        clock.return_value = 701
        fill()
        self.assertEqual(get.call_count, 3)

    def test_failures_wrong_identity_and_cancellation_are_not_cached_as_absence(self):
        for bad_get in (Mock(side_effect=TimeoutError), Mock(return_value=response('Other'))):
            cache = MeritMarketCache()
            for _ in range(2):
                rows, coverage = fill_merit_markets([ring()], [fact()], [], QUERY, CONTEXT,
                    cache=cache, session_factory=lambda: Session(bad_get))
                self.assertEqual(rows, [])
                self.assertEqual(coverage['failed'], ['Mine'])
            self.assertEqual(bad_get.call_count, 2)
        get = Mock()
        fill_merit_markets([ring()], [fact()], [], QUERY, CONTEXT,
            session_factory=lambda: Session(get), is_current=lambda: False)
        get.assert_not_called()

    def test_concurrency_is_bounded_and_excess_targets_are_reported(self):
        lock = threading.Lock()
        active, highest = 0, 0
        def get(*args, **kwargs):
            nonlocal active, highest
            with lock:
                active += 1
                highest = max(highest, active)
            time.sleep(0.005)
            with lock:
                active -= 1
            return response(kwargs['params']['system'], rows=[])
        candidates = [ring(str(i)) for i in range(70)]
        facts = [fact(str(i)) for i in range(70)]
        _, coverage = fill_merit_markets(candidates, facts, [], QUERY, CONTEXT,
            session_factory=lambda: Session(get), max_workers=99)
        self.assertLessEqual(highest, 2)
        self.assertEqual(coverage['checked'], 64)
        self.assertEqual(len(coverage['deferred']), 6)
        self.assertTrue(coverage['bounded'])


class PowerplayAgePolicyTests(unittest.TestCase):
    def test_all_merit_search_prioritizes_sale_value_and_system_diversity(self):
        candidates=[{**ring('Cheap'),'ring':'Cheap '+str(i),'candidateCommodities':[{'id':'platinum'}]} for i in range(40)]
        candidates.append({**ring('Value'),'candidateCommodities':[{'id':'platinum'}]})
        rows=plan_mining_routes(candidates,'ALL COMMODITIES','POWERPLAY MERITS',
            power='Aisling Duval',power_goal='REINFORCE',powerplay_systems=[fact('Cheap'),fact('Value')],
            markets=[market('Cheap',sellPrice=50000),market('Value',sellPrice=100000)],now=NOW,result_limit=30)
        self.assertEqual(rows[0]['system'],'Value')
        self.assertEqual(rows[1]['system'],'Cheap')
        self.assertTrue(all(row['meritVerified'] for row in rows))

    def test_source_projects_history_with_original_date_without_verifying_or_refreshing_it(self):
        from ed_companion.navigation.mining_powerplay import fetch_edframe_powerplay, missing_powerplay_targets
        stamp = (NOW-timedelta(days=8)).isoformat()
        old = fact(observedAt=stamp)
        get = Mock(return_value=Mock(json=Mock(return_value={
            'selection': 'systems', 'systemCount': 1, 'hasMore': False,
            'results': [old], 'coverage': [{'system': 'Mine', 'state': 'CURRENT', 'observedAt': stamp}]})))
        diagnostics = {}
        rows = fetch_edframe_powerplay(origin=[0, 0, 0], max_distance=250,
                                      systems=['Mine'], get=get, diagnostics=diagnostics)
        self.assertEqual(rows[0]['observedAt'], stamp)
        self.assertEqual(diagnostics['coverage'][0]['state'], 'STALE')
        route = plan_mining_routes([ring()], 'Platinum', 'POWERPLAY MERITS', power='Aisling Duval',
            power_goal='REINFORCE', powerplay_systems=rows, markets=[market()], now=NOW)[0]
        self.assertEqual(route['verificationStatus'], 'PROVISIONAL')
        self.assertEqual(missing_powerplay_targets([route], rows, now=NOW)[0]['system'], 'Mine')

    def test_current_last_known_and_missing_boundaries(self):
        for hours, score, status in ((36, 5, 'CONFIRMED'), (48, 5, 'CONFIRMED'),
                                    (48.001, 3, 'PROVISIONAL'), (336, 3, 'PROVISIONAL'),
                                    (336.001, None, 'UNKNOWN')):
            with self.subTest(hours=hours):
                facts = [fact(observedAt=(NOW-timedelta(hours=hours)).isoformat())]
                value = _merit_status(ring(), {'system': 'Mine'}, 'Aisling Duval',
                                     'REINFORCE', 'ANY', _powerplay_index(facts), now=NOW)
                self.assertEqual(value[1], score)
                self.assertTrue(value[0].startswith(status), value)

    def test_current_beats_more_profitable_last_known_and_history_never_verifies(self):
        facts = [fact('Current'), fact('Old', observedAt=(NOW-timedelta(days=8)).isoformat())]
        rows = plan_mining_routes([ring('Old'), ring('Current')], 'Platinum', 'POWERPLAY MERITS',
            power='Aisling Duval', power_goal='REINFORCE', now=NOW,
            powerplay_systems=facts, markets=[market('Old', sellPrice=300000), market('Current', sellPrice=50000)])
        self.assertEqual(rows[0]['system'], 'Current')
        self.assertTrue(rows[0]['meritVerified'])
        self.assertEqual(rows[1]['verificationStatus'], 'PROVISIONAL')
        self.assertFalse(rows[1]['meritVerified'])
        self.assertEqual(rows[1]['powerplayObservations'][0]['observedAt'], facts[1]['observedAt'])

    def test_historical_acquire_checks_both_ends_without_relabeling_known_ineligible_routes(self):
        old = (NOW-timedelta(days=5)).isoformat()
        facts = [fact(observedAt=old), fact('Sale', power='', controllingPower='', powers=[],
                    powerState='Unoccupied', coordinates=[20, 0, 0], observedAt=old)]
        args = (ring(), {'system': 'Sale'}, 'Aisling Duval', 'ACQUIRE', 'ANY', _powerplay_index(facts))
        self.assertEqual(_merit_status(*args, now=NOW)[1], 3)
        facts[1]['coordinates'] = [40, 0, 0]
        result = _merit_status(*args[:-1], _powerplay_index(facts), now=NOW)
        self.assertIsNone(result[1])
        self.assertFalse(result[0].startswith('PROVISIONAL'))


if __name__ == '__main__':
    unittest.main()
