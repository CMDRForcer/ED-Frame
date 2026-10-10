"""A public mining identity can supplement an older server's address resolver."""
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import Mock

from ed_companion.navigation.mining_powerplay import (
    fetch_powerplay_targets, fetch_spansh_powerplay_target, missing_powerplay_targets,
)
from tests.test_mining_powerplay_lookup import route, response, fact

NOW = datetime.now(timezone.utc)
ADDRESS = 1384900446587


def dump(**fields):
    return {'system': {'name': 'Mine', 'id64': ADDRESS, 'date': NOW.isoformat(),
        'coords': {'x': 1, 'y': 2, 'z': 3}, 'controllingPower': 'Aisling Duval',
        'powerState': 'Exploited', 'powers': ['Aisling Duval'],
        'Commander': 'PRIVATE', **fields}}


def streamed(payload=None, chunks=None, status=200):
    return Mock(status_code=status, iter_content=Mock(return_value=iter(
        chunks if chunks is not None else [json.dumps(payload or dump()).encode()])))


class PowerplayAddressFallbackTests(unittest.TestCase):
    def test_route_identity_survives_qml_number_and_conflicts_are_not_guessed(self):
        for address in (ADDRESS, float(ADDRESS)):
            targets = missing_powerplay_targets([route(systemAddress=address)])
            self.assertEqual(targets[0]['systemAddress'], ADDRESS)
            self.assertNotIn('systemAddress', targets[1])
        targets = missing_powerplay_targets([route(systemAddress=ADDRESS), route(systemAddress=ADDRESS+1)])
        self.assertNotIn('systemAddress', targets[0])
        for address in (True, '42', -1, 2**64, float(2**53), 42.5, float('nan')):
            self.assertNotIn('systemAddress', missing_powerplay_targets([route(systemAddress=address)])[0])

    def test_no_address_server_fallback_returns_recent_matched_control_and_original_time(self):
        original = (NOW - timedelta(hours=1)).isoformat()
        stream = streamed(dump(date=original))
        get = Mock(side_effect=[response(results=[fact('Sale')], selection='systems', hasMore=False),
            response(results=[], selection='systems', lookup=[{'system': 'Mine', 'state': 'NO_ADDRESS'}]),
            stream])
        result = fetch_powerplay_targets(missing_powerplay_targets([route(systemAddress=ADDRESS)]),
                                        origin=[], get=get, enrich=True)
        self.assertEqual({row['system'] for row in result['rows']}, {'Mine', 'Sale'})
        self.assertEqual(result['enrichment'][0]['state'], 'FETCHED')
        self.assertEqual(result['enrichment'][0]['observedAt'], original)
        self.assertEqual(get.call_args.args, (f'https://spansh.co.uk/api/dump/{ADDRESS}',))
        self.assertEqual(get.call_args.kwargs['timeout'], (3, 5))
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
        self.assertNotIn('PRIVATE', str(result))
        stream.close.assert_called_once()

    def test_older_than_history_limit_provides_only_diagnostic_time(self):
        stamp = (NOW - timedelta(days=15)).isoformat()
        result = fetch_spansh_powerplay_target('Mine', ADDRESS,
            get=Mock(return_value=streamed(dump(date=stamp))), now=NOW)
        self.assertEqual(result['state'], 'STALE')
        self.assertEqual(result['observedAt'], stamp)
        self.assertEqual(result['rows'], [])
        for fields in ({'name': 'Other'}, {'id64': ADDRESS+1}, {'controllingPower': ''},
                       {'powerState': None}, {'date': (NOW+timedelta(minutes=6)).isoformat()}):
            result = fetch_spansh_powerplay_target('Mine', ADDRESS,
                get=Mock(return_value=streamed(dump(**{'date': stamp, **fields}))), now=NOW)
            self.assertEqual(result['state'], 'MISSING')
            self.assertIsNone(result['observedAt'])
            self.assertEqual(result['rows'], [])

    def test_missing_or_busy_source_and_unknown_address_do_not_trigger_direct_fetch(self):
        for state, address in (('MISSING', ADDRESS), ('BUSY', ADDRESS), ('ERROR', ADDRESS),
                               ('NO_ADDRESS', None)):
            get = Mock(side_effect=[response(results=[], selection='systems', hasMore=False),
                response(results=[], selection='systems', lookup=[{'system': 'Mine', 'state': state}])])
            targets = [{'system': 'Mine', 'systemAddress': address}]
            result = fetch_powerplay_targets(targets, origin=[], get=get, enrich=True)
            self.assertEqual(get.call_count, 2)
            self.assertEqual(result['rows'], [])

    def test_source_errors_and_budget_limits_close_response_and_preserve_retained_facts(self):
        for source in (streamed(chunks=[b'x'*(2*1024**2+1)]), streamed(chunks=[b'{']),
                       streamed(status=302)):
            result = fetch_spansh_powerplay_target('Mine', ADDRESS,
                get=Mock(return_value=source), now=NOW)
            self.assertEqual(result['state'], 'ERROR')
            self.assertEqual(result['rows'], [])
            source.close.assert_called_once()
        source = streamed()
        clock = iter([0, 9])
        result = fetch_spansh_powerplay_target('Mine', ADDRESS,
            get=Mock(return_value=source), now=NOW, clock=lambda: next(clock))
        self.assertEqual(result['state'], 'ERROR')
        source.close.assert_called_once()
        get = Mock(side_effect=[response(results=[fact('Sale')], selection='systems', hasMore=False),
            response(results=[], selection='systems', lookup=[{'system': 'Mine', 'state': 'NO_ADDRESS'}]),
            TimeoutError('PRIVATE')])
        result = fetch_powerplay_targets([{'system': 'Mine', 'systemAddress': ADDRESS}, {'system': 'Sale'}],
                                        origin=[], get=get, enrich=True)
        self.assertEqual([row['system'] for row in result['rows']], ['Sale'])
        self.assertEqual(result['enrichment'][0]['state'], 'ERROR')
        self.assertNotIn('PRIVATE', str(result))


if __name__ == '__main__':
    unittest.main()
