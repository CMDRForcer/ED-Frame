"""Explicit Spansh control remains separate from ring and market evidence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock, patch

from ed_companion.navigation.mining_powerplay import (
    SPANSH_POWERPLAY_SOURCE, project_spansh_powerplay, fetch_powerplay_targets,
)
from ed_companion.navigation.mining_planner import _powerplay_index, _merit_status
from tests.test_mining_powerplay_lookup import route, fact, response

NOW = datetime.now(timezone.utc)


def dump(**fields):
    return {'system': {'name': 'Mine', 'id64': 42, 'date': NOW.isoformat(),
        'coords': {'x': 1, 'y': 2, 'z': 3}, 'controllingPower': 'Aisling Duval',
        'powerState': 'Stronghold', 'powers': ['Aisling Duval'],
        'Commander': 'PRIVATE', 'stations': [{'name': 'PRIVATE'}], **fields}}


class SpanshPowerplayTests(unittest.TestCase):
    def test_projection_is_whitelisted_original_dated_and_can_confirm_control(self):
        rows = project_spansh_powerplay(dump(), 'mine', 42, now=NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source'], SPANSH_POWERPLAY_SOURCE)
        self.assertEqual(rows[0]['observedAt'], NOW.isoformat())
        self.assertNotIn('PRIVATE', str(rows))
        status, score, _ = _merit_status({'system': 'Mine'}, {'system': 'Mine'},
            'Aisling Duval', 'REINFORCE', 'ANY', _powerplay_index(rows), now=NOW)
        self.assertEqual(score, 5)
        self.assertIn('STRONGHOLD', status)

    def test_absence_of_control_is_not_inferred_to_be_unoccupied(self):
        for fields in ({'controllingPower': ''}, {'powerState': ''},
                       {'powerState': 'Unoccupied', 'controllingPower': 'Aisling Duval'}):
            self.assertEqual(project_spansh_powerplay(dump(**fields), 'Mine', 42, now=NOW), [])
        unoccupied = dump(powerState='Unoccupied', controllingPower='', powers=[])
        self.assertEqual(project_spansh_powerplay(unoccupied, 'Mine', 42, now=NOW)[0]['powerState'], 'Unoccupied')
        missing = dump()
        for key in ('controllingPower', 'powerState', 'powers'):
            missing['system'].pop(key)
        self.assertEqual(project_spansh_powerplay(missing, 'Mine', 42, now=NOW), [])

    def test_mismatched_identity_malformed_and_undated_snapshots_are_rejected(self):
        for fields in ({'name': 'Other'}, {'id64': 43}, {'id64': True}, {'id64': 42.5},
                       {'powerState': ['Stronghold']}, {'controllingPower': {}},
                       {'powers': 'Aisling Duval'}, {'powers': [{}]},
                       {'powers': ['x'] * 33}, {'controllingPower': 'x' * 101},
                       {'coords': {'x': float('nan'), 'y': 2, 'z': 3}},
                       {'coords': {'x': True, 'y': 2, 'z': 3}},
                       {'date': ''}, {'date': '2026-10-09T12:00:00'},
                       {'date': (NOW - timedelta(hours=24, seconds=1)).isoformat()},
                       {'date': (NOW + timedelta(minutes=6)).isoformat()}):
            with self.subTest(fields=fields):
                self.assertEqual(project_spansh_powerplay(dump(**fields), 'Mine', 42, now=NOW), [])

    def test_missing_participants_allow_reinforce_but_not_contesting_inference(self):
        payload = dump(controllingPower='Yuri Grom')
        payload['system'].pop('powers')
        rows = project_spansh_powerplay(payload, 'Mine', 42, now=NOW)
        self.assertFalse(rows[0]['powersKnown'])
        _, score, _ = _merit_status({'system': 'Mine'}, {'system': 'Mine'},
            'Aisling Duval', 'UNDERMINE', 'ANY', _powerplay_index(rows), now=NOW)
        self.assertIsNone(score)

    def test_six_missing_targets_are_supplemented_independently_of_retained_rings(self):
        targets = [{'system': f'Missing {i}'} for i in range(10)]
        added = fact('Missing 0', source=SPANSH_POWERPLAY_SOURCE)
        get = Mock(side_effect=[response(results=[], hasMore=False, selection='systems'),
            response(results=[added, fact('Unrequested')], selection='systems', lookup=[
                {'system': 'Missing 0', 'state': 'FETCHED', 'source': SPANSH_POWERPLAY_SOURCE,
                 'observedAt': NOW.isoformat(), 'PRIVATE': 'PRIVATE'},
                {'system': 'Unrequested', 'state': 'FETCHED'}])])
        result = fetch_powerplay_targets(targets, origin=[], get=get, enrich=True)
        self.assertEqual(get.call_count, 2)
        self.assertTrue(get.call_args.args[0].endswith('/powerplay/lookup'))
        self.assertEqual(get.call_args.kwargs['params']['system'], [f'Missing {i}' for i in range(6)])
        self.assertEqual(result['enrichmentDeferred'], [f'Missing {i}' for i in range(6, 10)])
        self.assertEqual([row['system'] for row in result['rows']], ['Missing 0'])
        self.assertIn(SPANSH_POWERPLAY_SOURCE, result['rows'][0]['source'])
        self.assertNotIn('PRIVATE', str(result))

    def test_current_control_avoids_spansh_but_presence_still_needs_it(self):
        get = Mock(side_effect=[response(results=[fact('Mine'), fact('Sale', controllingPower='')],
            hasMore=False, selection='systems'), response(results=[], selection='systems',
                lookup=[{'system': 'Sale', 'state': 'MISSING'}])])
        result = fetch_powerplay_targets([{'system': 'Mine'}, {'system': 'Sale'}], origin=[], get=get, enrich=True)
        self.assertEqual(get.call_args.kwargs['params']['system'], ['Sale'])
        self.assertEqual(len(result['rows']), 2)
        all_current = Mock(return_value=response(results=[fact('Mine')], hasMore=False, selection='systems'))
        fetch_powerplay_targets([{'system': 'Mine'}], origin=[], get=all_current, enrich=True)
        self.assertEqual(all_current.call_count, 1)

    def test_fallback_errors_preserve_server_facts_and_missing_status(self):
        get = Mock(side_effect=[response(results=[fact('Mine')], hasMore=False, selection='systems'),
                               TimeoutError('unavailable')])
        result = fetch_powerplay_targets([{'system': 'Mine'}, {'system': 'Sale'}], origin=[], get=get, enrich=True)
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['checked'], ['Mine', 'Sale'])
        self.assertEqual(result['enrichment'], [{'system': 'Sale', 'state': 'ERROR'}])
        self.assertEqual(result['enrichmentError'], 'TimeoutError')

    def test_new_fact_updates_coverage_without_mutating_original_response(self):
        first = {'results': [], 'hasMore': False, 'selection': 'systems',
                 'coverage': [{'system': 'Mine', 'state': 'MISSING', 'observedAt': None}]}
        original = deepcopy(first)
        get = Mock(side_effect=[response(**first), response(results=[fact('Mine', source=SPANSH_POWERPLAY_SOURCE)],
            selection='systems', lookup=[{'system': 'Mine', 'state': 'FETCHED'}])])
        result = fetch_powerplay_targets([{'system': 'Mine'}], origin=[], get=get, enrich=True)
        self.assertEqual(result['coverage'][0]['state'], 'CURRENT')
        self.assertEqual(first, original)

    def test_controller_requests_source_enrichment_without_any_ring_query(self):
        from tests.test_mining_powerplay_lookup import PowerplayLookupTests
        controller = PowerplayLookupTests().controller()
        controller.verifyMiningRoutes([route()], 'Origin')
        worker = controller._start_network_worker.call_args.args[0]
        with (patch('ed_companion.phase14.controller_navigation.fetch_powerplay_targets',
            return_value={'rows': [], 'checked': ['Mine', 'Sale'], 'failed': []}) as lookup,
            patch('ed_companion.phase14.controller_navigation.fetch_spansh_system_dump') as rings):
            worker()
        self.assertTrue(lookup.call_args.kwargs['enrich'])
        rings.assert_not_called()

    def test_source_failures_and_deferred_targets_get_short_retry_and_clear_status(self):
        from tests.test_mining_powerplay_lookup import PowerplayLookupTests
        controller = PowerplayLookupTests().controller()
        controller.verifyMiningRoutes([route()], 'Origin')
        request = dict(controller._active_mining_verification_request)
        controller._finish_mining_verification({**request, 'powerplayLookup': {
            'rows': [fact('Mine', source=SPANSH_POWERPLAY_SOURCE)],
            'checked': ['Mine', 'Sale', 'Deferred', 'Missing'], 'failed': [],
            'enrichment': [{'system': 'Mine', 'state': 'FETCHED'},
                           {'system': 'Sale', 'state': 'ERROR'},
                           {'system': 'Missing', 'state': 'MISSING'}],
            'enrichmentDeferred': ['Deferred'],
        }})
        cache = controller._mining_powerplay_lookup_cache
        self.assertGreater(cache['mine'], NOW.timestamp() + 3500)
        self.assertGreater(cache['missing'], NOW.timestamp() + 500)
        self.assertLess(cache['sale'], NOW.timestamp() + 200)
        self.assertLess(cache['deferred'], NOW.timestamp() + 200)
        self.assertIn('Spansh 2 checked, 1 supplemented', controller._mining_verification_status)
        self.assertIn('1 source checks temporarily unavailable', controller._mining_verification_status)
        self.assertIn('1 further source checks deferred', controller._mining_verification_status)

    def test_disabling_community_connection_prevents_enrichment_requests(self):
        from tests.test_mining_powerplay_lookup import PowerplayLookupTests
        controller = PowerplayLookupTests().controller()
        controller._edframe_catalog_enabled = False
        with patch('ed_companion.phase14.controller_navigation.fetch_powerplay_targets') as lookup:
            controller.verifyMiningRoutes([route()], 'Origin')
            if controller._start_network_worker.called:
                controller._start_network_worker.call_args.args[0]()
        lookup.assert_not_called()

    def test_deferred_source_checks_precede_expired_previously_checked_systems(self):
        from tests.test_mining_powerplay_lookup import PowerplayLookupTests
        controller = PowerplayLookupTests().controller()
        controller._mining_powerplay_source_pending = ['Mine 9', 'Mine 8']
        controller.verifyMiningRoutes([route(f'Mine {i}', 'Sale') for i in range(10)], 'Origin')
        targets = controller._active_mining_verification_request['powerplayLookupTargets']
        self.assertEqual([row['system'] for row in targets[:2]], ['Mine 9', 'Mine 8'])
        self.assertEqual(len(targets), 11)

    def test_late_profile_result_cannot_change_pending_source_queue(self):
        from tests.test_mining_powerplay_lookup import PowerplayLookupTests
        controller = PowerplayLookupTests().controller()
        controller._active_mining_verification_request = {'id': 'old'}
        controller._mining_powerplay_source_pending = ['Current profile']
        controller._finish_mining_verification({'id': 'old', 'profileKey': 'beta',
            'generation': 1, 'path': 'catalog.json', 'powerplayLookup': {
                'rows': [], 'enrichmentDeferred': ['Wrong profile']}})
        self.assertEqual(controller._mining_powerplay_source_pending, ['Current profile'])


if __name__ == '__main__':
    unittest.main()
