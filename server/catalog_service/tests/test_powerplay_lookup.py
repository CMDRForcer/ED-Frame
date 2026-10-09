"""Source, concurrency and storage boundaries for targeted supplementation."""
from contextlib import contextmanager
import asyncio
from datetime import datetime, timedelta, timezone
import json
import threading
import unittest
from unittest.mock import MagicMock, Mock, patch

from fastapi import HTTPException
from starlette.requests import Request

from ed_companion.navigation.mining_powerplay import project_spansh_powerplay, SPANSH_POWERPLAY_SOURCE
from edframe_catalog import api
from edframe_catalog.database import upsert_powerplay_snapshot
from edframe_catalog.powerplay_lookup import (
    SpanshPowerplayLookup, current_control, lookup_powerplay_systems,
)

NOW = datetime.now(timezone.utc)


def dump(**fields):
    return {'system': {'name': 'Mine', 'id64': 42, 'date': NOW.isoformat(),
        'coords': {'x': 1, 'y': 2, 'z': 3}, 'controllingPower': 'Aisling Duval',
        'powerState': 'Stronghold', 'powers': ['Aisling Duval'],
        'Commander': 'PRIVATE', 'stations': [{'name': 'PRIVATE'}], **fields}}


def response(payload=None, *, chunks=None, status=200):
    return Mock(status_code=status, iter_content=Mock(return_value=iter(
        chunks if chunks is not None else [json.dumps(payload or dump()).encode()])))


def snapshot(rows):
    row = rows[0]
    return {'identity': row['system'].casefold(), 'system_name': row['system'],
        'system_address': row['systemAddress'], 'observed_at': row['observedAt'], 'facts': rows}


class SourceLookupTests(unittest.TestCase):
    def test_fixed_source_original_time_and_positive_cache(self):
        clock = [0.0]
        lookup = SpanshPowerplayLookup(clock=lambda: clock[0])
        original = (NOW - timedelta(hours=1)).isoformat()
        upstream = response(dump(date=original))
        get = Mock(return_value=upstream)
        first = lookup.lookup('mine', 42, get=get, now=NOW)
        self.assertEqual(first['state'], 'FETCHED')
        self.assertEqual(first['rows'][0]['observedAt'], original)
        self.assertNotIn('PRIVATE', str(first))
        self.assertEqual(get.call_args.args, ('https://spansh.co.uk/api/dump/42',))
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
        self.assertEqual(get.call_args.kwargs['timeout'], (3, 5))
        self.assertNotIn('params', get.call_args.kwargs)
        upstream.close.assert_called_once()
        clock[0] = 3599
        self.assertEqual(lookup.lookup('MINE', 42, get=get, now=NOW), first)
        get.assert_called_once()

    def test_negative_error_and_positive_cooldowns_expire(self):
        for payload, exception, ttl in ((dump(controllingPower=''), None, 600),
                                       (None, TimeoutError('PRIVATE'), 120),
                                       (dump(), None, 3600)):
            with self.subTest(ttl=ttl):
                clock = [0.0]
                lookup = SpanshPowerplayLookup(clock=lambda: clock[0])
                get = Mock(side_effect=exception) if exception else Mock(side_effect=lambda *a, **k: response(payload))
                first = lookup.lookup('Mine', 42, get=get, now=NOW)
                clock[0] = ttl - 1
                self.assertEqual(lookup.lookup('Mine', 42, get=get, now=NOW), first)
                self.assertEqual(get.call_count, 1)
                clock[0] = ttl
                lookup.lookup('Mine', 42, get=get, now=NOW)
                self.assertEqual(get.call_count, 2)
                self.assertNotIn('PRIVATE', str(first))

    def test_cached_control_cannot_extend_its_source_freshness(self):
        lookup = SpanshPowerplayLookup(clock=lambda: 0.0)
        get = Mock(side_effect=lambda *a, **k: response(dump(date=(NOW - timedelta(hours=24)).isoformat())))
        self.assertEqual(lookup.lookup('Mine', 42, get=get, now=NOW)['state'], 'FETCHED')
        later = lookup.lookup('Mine', 42, get=get, now=NOW + timedelta(seconds=1))
        self.assertEqual(get.call_count, 2)
        self.assertEqual(later['state'], 'STALE')
        self.assertEqual(later['rows'], [])

    def test_stale_requires_matched_explicit_snapshot_and_keeps_only_original_date(self):
        stamp = (NOW - timedelta(hours=25)).isoformat()
        for fields, expected in (({}, 'STALE'), ({'name': 'Other'}, 'MISSING'),
                                 ({'id64': 99}, 'MISSING'), ({'controllingPower': ''}, 'MISSING'),
                                 ({'powerState': ['Stronghold']}, 'MISSING')):
            with self.subTest(fields=fields):
                result = SpanshPowerplayLookup().lookup('Mine', 42, now=NOW,
                    get=Mock(return_value=response(dump(date=stamp, **fields))))
                self.assertEqual(result['state'], expected)
                self.assertEqual(result['rows'], [])
                self.assertEqual(result['observedAt'], stamp if expected == 'STALE' else None)

    def test_missing_address_never_makes_an_outbound_request(self):
        get = Mock()
        for address in (None, True, False, 0, -1, 2**64, '42', 42.5):
            result = SpanshPowerplayLookup().lookup('Mine', address, get=get, now=NOW)
            self.assertEqual(result['state'], 'NO_ADDRESS')
        get.assert_not_called()

    def test_invalid_oversize_slow_or_redirected_responses_release_lane_and_close(self):
        clock = [0.0]
        def slow_chunks():
            clock[0] = 9
            yield b'{}'
        slow = response()
        slow.iter_content.return_value = slow_chunks()
        for upstream in (response(chunks=[b'x' * (2 * 1024**2 + 1)]),
                         response(chunks=[b'not json']), response(status=302), slow):
            with self.subTest(upstream=upstream):
                clock[0] = 0
                lookup = SpanshPowerplayLookup(clock=lambda: clock[0])
                result = lookup.lookup('Mine', 42, get=Mock(return_value=upstream), now=NOW)
                self.assertEqual(result['state'], 'ERROR')
                upstream.close.assert_called_once()
                self.assertEqual(lookup.active, set())
                self.assertTrue(lookup.slots.acquire(blocking=False))
                self.assertTrue(lookup.slots.acquire(blocking=False))
                self.assertFalse(lookup.slots.acquire(blocking=False))
                lookup.slots.release()
                lookup.slots.release()

    def test_single_flight_and_two_outbound_lanes_across_requests(self):
        lookup = SpanshPowerplayLookup()
        release = threading.Event()
        entered = [threading.Event(), threading.Event()]
        def get(url, **_kwargs):
            entered[0 if url.endswith('/42') else 1].set()
            if not release.wait(3):
                raise TimeoutError('test release missing')
            return response()
        jobs = [threading.Thread(target=lookup.lookup,
                    args=(name, address), kwargs={'get': get, 'now': NOW})
                for name, address in [('Mine', 42), ('Other', 43)]]
        try:
            for job in jobs:
                job.start()
            self.assertTrue(all(event.wait(2) for event in entered))
            no_get = Mock()
            self.assertEqual(lookup.lookup('MINE', 42, get=no_get, now=NOW)['state'], 'BUSY')
            self.assertEqual(lookup.lookup('Third', 44, get=no_get, now=NOW)['state'], 'BUSY')
            no_get.assert_not_called()
        finally:
            release.set()
            for job in jobs:
                job.join(3)
        self.assertTrue(all(not job.is_alive() for job in jobs))
        self.assertEqual(lookup.active, set())

    def test_cache_capacity_evicts_oldest_without_dropping_active_jobs(self):
        lookup = SpanshPowerplayLookup(capacity=2)
        get = Mock(side_effect=lambda *a, **k: response(dump(controllingPower='')))
        for name, address in [('One', 1), ('Two', 2), ('Three', 3)]:
            lookup.lookup(name, address, get=get, now=NOW)
        self.assertEqual(len(lookup.cache), 2)
        lookup.lookup('One', 1, get=get, now=NOW)
        self.assertEqual(get.call_count, 4)

    def test_stored_presence_malformed_or_old_facts_do_not_skip_source_lookup(self):
        valid = project_spansh_powerplay(dump(), 'Mine', 42, now=NOW)[0]
        self.assertTrue(current_control([valid], NOW))
        for rows in (None, {}, ['not a row'], [{**valid, 'powerState': []}],
                     [{**valid, 'controllingPower': ' '}], [{**valid, 'controllingPower': {}}],
                     [{**valid, 'coordinates': [True, 2, 3]}], [{**valid, 'coordinates': None}],
                     [{**valid, 'powerState': 'Unoccupied'}],
                     [{**valid, 'observedAt': (NOW - timedelta(hours=25)).isoformat()}]):
            with self.subTest(rows=rows):
                self.assertFalse(current_control(rows, NOW))


class StorageLookupTests(unittest.TestCase):
    def run_service(self, *, initial=(), final=(), addresses=(), upstream=None):
        conn = MagicMock()
        conn.execute.return_value.fetchall.side_effect = [list(initial), list(addresses), list(final)]
        active = [False]
        @contextmanager
        def connection():
            self.assertFalse(active[0])
            active[0] = True
            try:
                yield conn
            finally:
                active[0] = False
        lookup = Mock()
        def fetch(*args, **kwargs):
            self.assertFalse(active[0], 'No PostgreSQL transaction may stay open during HTTP')
            return upstream or {'state': 'MISSING', 'rows': []}
        lookup.lookup.side_effect = fetch
        with (patch('edframe_catalog.powerplay_lookup.connection', connection),
              patch('edframe_catalog.powerplay_lookup.upsert_powerplay_snapshot') as save):
            result = lookup_powerplay_systems(['mine'], lookup=lookup, now=NOW)
        return result, lookup, save, conn

    def test_current_control_is_reused_without_outbound_lookup_or_write(self):
        rows = project_spansh_powerplay(dump(), 'Mine', 42, now=NOW)
        result, lookup, save, _ = self.run_service(initial=[snapshot(rows)], final=[snapshot(rows)])
        lookup.lookup.assert_not_called()
        save.assert_not_called()
        self.assertEqual(result['results'], rows)
        self.assertEqual(result['lookup'][0]['state'], 'CURRENT')

    def test_ambiguous_public_address_does_not_choose_an_arbitrary_system(self):
        addresses = [{'name': 'Mine', 'system_address': 42}, {'name': 'MINE', 'system_address': 43}]
        result, lookup, save, _ = self.run_service(addresses=addresses)
        self.assertEqual(lookup.lookup.call_args.args, ('mine', None))
        save.assert_not_called()
        self.assertEqual(result['results'], [])

    def test_validated_snapshot_is_written_with_original_date_and_re_read(self):
        stamp = (NOW - timedelta(hours=1)).isoformat()
        rows = project_spansh_powerplay(dump(date=stamp), 'Mine', 42, now=NOW)
        result, lookup, save, conn = self.run_service(final=[snapshot(rows)],
            addresses=[{'name': 'Mine', 'system_address': 42}],
            upstream={'state': 'FETCHED', 'rows': rows})
        self.assertEqual(lookup.lookup.call_args.args, ('mine', 42))
        stored = save.call_args.args[1]
        self.assertEqual(stored['observed_at'], stamp)
        self.assertEqual(stored['received_at'], NOW.isoformat())
        self.assertNotIn('PRIVATE', str(stored))
        self.assertEqual(json.loads(stored['facts']), rows)
        self.assertFalse(save.call_args.kwargs['allow_equal'])
        self.assertEqual(result['lookup'][0]['state'], 'FETCHED')
        self.assertEqual(result['results'], rows)
        for call in conn.execute.call_args_list:
            if 'ANY(%s)' in call.args[0]:
                self.assertEqual(call.args[1], (['mine'],))

    def test_concurrent_newer_control_or_equal_eddn_snapshot_remains_authoritative(self):
        fetched = project_spansh_powerplay(dump(date=(NOW - timedelta(hours=1)).isoformat()), 'Mine', 42, now=NOW)
        for stamp in (NOW.isoformat(), fetched[0]['observedAt']):
            retained = [{**fetched[0], 'observedAt': stamp, 'controllingPower': 'Yuri Grom',
                         'power': 'Yuri Grom', 'source': 'EDDN journal/1'}]
            result, _, _, _ = self.run_service(final=[snapshot(retained)],
                upstream={'state': 'FETCHED', 'rows': fetched})
            self.assertEqual(result['results'], retained)
            self.assertEqual(result['lookup'][0]['state'], 'CURRENT')
            self.assertEqual(result['lookup'][0]['source'], 'EDDN journal/1')

    def test_newer_presence_does_not_return_older_fetched_control_as_current(self):
        fetched = project_spansh_powerplay(dump(), 'Mine', 42, now=NOW)
        retained = [{**fetched[0], 'observedAt': (NOW + timedelta(seconds=1)).isoformat(),
                     'controllingPower': '', 'source': 'EDDN journal/1'}]
        result, _, _, _ = self.run_service(final=[snapshot(retained)],
            upstream={'state': 'FETCHED', 'rows': fetched})
        self.assertEqual(result['results'], [])
        self.assertEqual(result['lookup'][0]['state'], 'MISSING')

    def test_unknown_or_stale_source_never_writes_control(self):
        for state in ('MISSING', 'STALE', 'ERROR', 'BUSY', 'NO_ADDRESS'):
            result, _, save, _ = self.run_service(upstream={'state': state, 'rows': []})
            save.assert_not_called()
            self.assertEqual(result['results'], [])
            self.assertEqual(result['lookup'][0]['state'], state)

    def test_spansh_storage_has_atomic_strictly_newer_guard(self):
        conn = Mock()
        upsert_powerplay_snapshot(conn, {'identity': 'mine'}, allow_equal=False)
        sql, params = conn.execute.call_args.args
        self.assertIn('WHERE EXCLUDED.observed_at > mining_powerplay.observed_at', sql)
        self.assertNotIn('>= mining_powerplay.observed_at', sql)
        self.assertEqual(params, {'identity': 'mine'})


class EndpointLookupTests(unittest.TestCase):
    def setUp(self):
        api._powerplay_rate_buckets.clear()
        self.request = Request({'type': 'http', 'headers': [], 'client': ('local-test', 1)})

    def tearDown(self):
        api._powerplay_rate_buckets.clear()

    def test_bounded_normalized_names_and_rate_limit_before_source_lookup(self):
        with patch('edframe_catalog.powerplay_lookup.lookup_powerplay_systems', return_value={'results': []}) as fetch:
            api.lookup_mining_powerplay(self.request, [" Mine ", 'MINE', "Sale's Hub"])
            fetch.assert_called_once_with(['mine', "sale's hub"])
            for _ in range(5):
                api.lookup_mining_powerplay(self.request, ['Mine'])
            with self.assertRaises(HTTPException) as caught:
                api.lookup_mining_powerplay(self.request, ['Mine'])
            self.assertEqual(caught.exception.status_code, 429)
            self.assertEqual(fetch.call_count, 6)

    def test_invalid_query_does_not_consume_rate_budget_or_access_source(self):
        with patch('edframe_catalog.powerplay_lookup.lookup_powerplay_systems') as fetch:
            for names in ([], [' '], ['x' * 101], ['x'] * 7):
                with self.subTest(names=names), self.assertRaises(HTTPException) as caught:
                    api.lookup_mining_powerplay(self.request, names)
                self.assertEqual(caught.exception.status_code, 400)
            fetch.assert_not_called()
            self.assertEqual(api._powerplay_rate_buckets, {})

    def test_http_route_serializes_public_projection_without_startup_database(self):
        rows = project_spansh_powerplay(dump(), 'Mine', 42, now=NOW)
        payload = {'selection': 'systems', 'hasMore': False, 'results': rows,
                   'lookup': [{'system': 'Mine', 'state': 'FETCHED', 'source': SPANSH_POWERPLAY_SOURCE}]}
        messages = []
        request_sent = [False]
        async def receive():
            if request_sent[0]:
                await asyncio.Event().wait()
            request_sent[0] = True
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        async def send(message):
            messages.append(message)
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'}, 'http_version': '1.1',
                 'method': 'GET', 'scheme': 'http', 'path': '/v1/mining/powerplay/lookup',
                 'query_string': b'system=Mine', 'root_path': '', 'headers': [],
                 'server': ('local-test', 80), 'client': ('local-test', 1)}
        with patch('edframe_catalog.powerplay_lookup.lookup_powerplay_systems', return_value=payload) as fetch:
            async def run():
                await asyncio.wait_for(api.app(scope, receive, send), timeout=5)
            asyncio.run(run())
        self.assertEqual(messages[0]['status'], 200)
        body = b''.join(message.get('body', b'') for message in messages)
        self.assertEqual(json.loads(body), payload)
        self.assertNotIn(b'PRIVATE', body)
        fetch.assert_called_once_with(['mine'])
