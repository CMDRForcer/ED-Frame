"""Run local lookup sources in an ephemeral process and isolated PostgreSQL schema.

JSON sources arrive through stdin. Only synthetic facts are written; installed
files, services and public tables are untouched. Drop the exact owned schema in
finally. Invoke main(sources) from the container stdin wrapper.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import secrets
import sys
import threading
import types

from edframe_catalog import database
from psycopg import sql


def main(sources):
    schema = 'edframe_powerplay_test_' + secrets.token_hex(8)
    original_connection = database.connection
    active = [0]
    lock = threading.Lock()
    checks = []
    now = datetime.now(timezone.utc)

    @contextmanager
    def connect():
        with original_connection() as conn:
            conn.execute(sql.SQL('SET search_path TO {}, pg_catalog').format(sql.Identifier(schema)))
            conn.execute("SET LOCAL statement_timeout='10s'")
            conn.execute("SET LOCAL lock_timeout='3s'")
            with lock:
                active[0] += 1
            try:
                yield conn
            finally:
                with lock:
                    active[0] -= 1

    def check(name, value):
        assert value, name
        checks.append(name)

    projector = types.ModuleType('ed_companion.navigation.mining_powerplay')
    exec(compile(sources['projector'], '<local-projector>', 'exec'), projector.__dict__)
    sys.modules[projector.__name__] = projector
    exec(compile(sources['upsert'], '<local-upsert>', 'exec'), database.__dict__)
    lookup = types.ModuleType('edframe_catalog.powerplay_lookup')
    sys.modules[lookup.__name__] = lookup
    exec(compile(sources['lookup'], '<local-lookup>', 'exec'), lookup.__dict__)
    lookup.connection = connect

    def dump(name='Mine', address=42, stamp=None, **fields):
        return {'system': {'name': name, 'id64': address,
            'date': (stamp or now - timedelta(hours=1)).isoformat(),
            'coords': {'x': 1, 'y': 2, 'z': 3}, 'powerState': 'Stronghold',
            'controllingPower': 'Aisling Duval', 'powers': ['Aisling Duval'],
            'Commander': 'PRIVATE', 'stations': [{'name': 'PRIVATE'}], **fields}}

    def stored(name):
        with connect() as conn:
            return conn.execute('SELECT * FROM mining_powerplay WHERE identity=%s', (name,)).fetchone()

    def insert(name, stamp, source='EDDN Journal', controller='Aisling Duval'):
        rows = projector.project_spansh_powerplay(dump(name, stamp=stamp,
            controllingPower=controller), name, 42, now=now)
        rows[0]['source'] = source
        with connect() as conn:
            database.upsert_powerplay_snapshot(conn, {'identity': name,
                'system_name': name, 'system_address': 42, 'x': 1, 'y': 2, 'z': 3,
                'observed_at': stamp.isoformat(), 'received_at': now.isoformat(),
                'facts': json.dumps(rows)})
        return rows

    class Response:
        status_code = 200
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): pass
        def iter_content(self, size): yield json.dumps(self.payload).encode()
        def close(self): pass

    class Upstream:
        def __init__(self, payload, race=None):
            self.payload, self.race, self.calls = payload, race, 0
            self.worker = lookup.SpanshPowerplayLookup()
        def lookup(self, name, address, **kwargs):
            def get(url, **options):
                check('HTTP outside PostgreSQL transaction', active[0] == 0)
                self.calls += 1
                if self.race: self.race()
                return Response(self.payload)
            return self.worker.lookup(name, address, get=get, **kwargs)

    with original_connection() as admin:
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    try:
        with connect() as conn:
            conn.execute('CREATE TABLE systems (LIKE public.systems INCLUDING ALL)')
            conn.execute('CREATE TABLE mining_powerplay (LIKE public.mining_powerplay INCLUDING ALL)')
            conn.execute("INSERT INTO systems(name,system_address) VALUES ('Mine',42),('Missing',43),('Stale',44),('Invalid',45)")
        source = Upstream(dump())
        value = lookup.lookup_powerplay_systems(['mine'], lookup=source, now=now)
        row = stored('mine')
        check('New source persisted in real PostgreSQL', value['lookup'][0]['state'] == 'FETCHED' and row is not None)
        check('Original timestamp retained', row['observed_at'] == now - timedelta(hours=1))
        check('Only public projected facts', 'PRIVATE' not in json.dumps(row['facts']))
        check('API result equals canonical JSONB facts', value['results'] == row['facts'])
        check('Coordinates and address retained', (row['x'],row['y'],row['z'],row['system_address']) == (1,2,3,42))
        value = lookup.lookup_powerplay_systems(['mine'], lookup=source, now=now)
        check('Current control skips upstream', source.calls == 1 and value['lookup'][0]['state'] == 'CURRENT')
        for identity, payload, expected in (
            ('missing', dump('Missing',43, controllingPower=''), 'MISSING'),
            ('stale', dump('Stale',44,stamp=now-timedelta(hours=25)), 'STALE'),
            ('invalid', dump('Other',45), 'MISSING'),
            ('no address', dump('No address',46), 'NO_ADDRESS')):
            provider = Upstream(payload)
            value = lookup.lookup_powerplay_systems([identity], lookup=provider, now=now)
            check(identity + ' stays unknown and is not written', not value['results'] and stored(identity) is None and value['lookup'][0]['state'] == expected)
        for label, stamp in (('newer', now), ('equal', now-timedelta(hours=1))):
            with connect() as conn: conn.execute('DELETE FROM mining_powerplay WHERE identity=%s',('mine',))
            expected = []
            provider = Upstream(dump(), race=lambda: expected.extend(insert('mine',stamp,controller='Zemina Torval')))
            value = lookup.lookup_powerplay_systems(['mine'],lookup=provider,now=now)
            check(label + ' concurrent EDDN wins', value['results'] == expected and stored('mine')['facts'] == expected)
            check(label + ' race returns CURRENT', value['lookup'][0]['state'] == 'CURRENT')
        # Existing collector contract still accepts equal-time EDDN updates.
        expected = insert('mine', now-timedelta(hours=1), controller='Aisling Duval')
        check('Equal-time ordinary upsert preserved', stored('mine')['facts'] == expected)
        # Exercise the actual local handler in this ephemeral API process.
        from edframe_catalog import api
        from starlette.requests import Request
        api._powerplay_rate_lock = threading.Lock()
        api._powerplay_rate_buckets = {}
        exec(compile(sources['handler'],'<local-handler>','exec'),api.__dict__)
        lookup.LOOKUP = source
        request = Request({'type':'http','method':'GET','path':'/v1/mining/powerplay/lookup',
                           'headers':[],'client':('isolated-test',1),'query_string':b''})
        value = api.lookup_mining_powerplay(request,[' MINE ', 'mine'])
        check('Local API handler reads canonical PostgreSQL', len(value['lookup']) == 1 and value['results'] == expected)
        from fastapi import HTTPException
        try: api.lookup_mining_powerplay(request,['mine']*7)
        except HTTPException as exc: check('Six-name API bound',exc.status_code == 400)
        else: raise AssertionError('Missing API bound')
    finally:
        with original_connection() as admin:
            admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        with original_connection() as admin:
            check('Isolated schema removed', admin.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s',(schema,)).fetchone() is None)
    print(json.dumps({'status':'PASS','checks':len(checks),'passed':checks,
                      'scope':'synthetic isolated schema; no public writes or deployment'}),flush=True)
