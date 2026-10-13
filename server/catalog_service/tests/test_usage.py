"""Real ASGI contracts and executed SQL, with an isolated SQLite test store.

The three-column DDL and all usage INSERT/SELECT/DELETE queries are portable.
Only PostgreSQL's SET LOCAL/transaction settings and parameter binding are
adapted here; no production connection, schema setup or lifespan is run.
"""
from datetime import date, timedelta
import json
from pathlib import Path
import re
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from edframe_catalog import api, usage


class Store:
    def __init__(self):
        self.db = sqlite3.connect(':memory:', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        schema = Path(usage.__file__).with_name('schema.sql').read_text()
        ddl = re.search(r'CREATE TABLE IF NOT EXISTS usage_pings \(.*?\);', schema, re.S)[0]
        self.db.execute(ddl)
    def __enter__(self):
        return self
    def __exit__(self, kind, value, trace):
        self.db.rollback() if kind else self.db.commit()
    def execute(self, sql, params=()):
        if sql.lstrip().startswith('SET '):
            return self.db.execute('SELECT 1')
        values = tuple(str(value) if not isinstance(value, (int, float)) else value for value in params)
        return self.db.execute(sql.replace('%s', '?'), values)


def call(method, path, payload=None, headers=None):
    async def run():
        messages = []
        body = json.dumps(payload).encode() if payload is not None else b''
        async def receive():
            return {'type': 'http.request', 'body': body, 'more_body': False}
        async def send(message):
            messages.append(message)
        scope = dict(type='http', asgi={'version':'3.0'}, http_version='1.1',
            method=method, scheme='http', path=path, raw_path=path.encode(),
            query_string=b'', root_path='', client=('internal-caddy', 1000), server=('test', 80),
            headers=[(k.lower().encode(), v.encode()) for k,v in
                     {'Content-Type':'application/json', **(headers or {})}.items()])
        await api.app(scope, receive, send)
        start = next(row for row in messages if row['type']=='http.response.start')
        data = b''.join(row.get('body',b'') for row in messages if row['type']=='http.response.body')
        return start['status'], json.loads(data), dict(start['headers'])
    async def inline_worker(function, *args, **kwargs):
        return function(*args)
    # No event-loop socketpair or HTTP connection is needed for these ASGI
    # requests. Only thread dispatch is stubbed; validation/routing/responses
    # and the actual INSERT/SELECT/DELETE SQL still run normally.
    with patch('starlette.concurrency.anyio.to_thread.run_sync', inline_worker):
        coroutine = run()
        try:
            coroutine.send(None)
        except StopIteration as completed:
            return completed.value
        finally:
            coroutine.close()
        raise AssertionError('Unexpected asynchronous I/O in isolated ASGI test')


class UsageContracts(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.addCleanup(self.store.db.close)
        self.today = date(2026, 10, 13)
        self.identity = str(uuid4())
        self.connection = patch.object(api, 'connection', return_value=self.store)
        self.factory = self.connection.start()
        self.addCleanup(self.connection.stop)
        self.clock = patch.object(usage, 'utc_today', return_value=self.today)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.env = patch.dict('os.environ', {'EDFRAME_ADMIN_TOKEN':'private-test-token', 'EDFRAME_USAGE_EXCLUDED_IDS':''})
        self.env.start()
        self.addCleanup(self.env.stop)
        api._usage_rate_buckets.clear()

    def ping(self, identity=None, version='1.0.9', **extra):
        return call('POST', '/v1/usage/ping', {
            'install_id': identity or self.identity, 'app_version':version, **extra})
    def stats(self, token='private-test-token'):
        return call('GET', '/v1/usage/stats', headers={'X-EDFrame-Admin-Token':token})

    def test_duplicate_ping_counts_once_and_preserves_first_version(self):
        self.assertEqual(self.ping()[0], 200)
        self.assertEqual(self.ping(version='1.1')[0], 200)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM usage_pings').fetchone()[0], 1)
        self.assertEqual(self.stats()[1], dict(dau=1, wau=1, mau=1, by_version_30d={'1.0.9':1}))

    def test_invalid_uuid_returns_422_without_database_access(self):
        self.assertEqual(self.ping(identity='invalid')[0], 422)
        self.factory.assert_not_called()

    def test_version_is_limited_and_extra_commander_fields_rejected(self):
        for version in ('', 'x'*33, 123):
            self.assertEqual(self.ping(version=version)[0], 422)
        self.assertEqual(self.ping(Commander='PRIVATE', FID='PRIVATE')[0], 422)
        self.factory.assert_not_called()
        self.assertEqual(self.ping(version='x'*32)[0], 200)

    def test_excluded_id_not_stored_and_invalid_exclusions_ignored(self):
        with patch.dict('os.environ', {'EDFRAME_USAGE_EXCLUDED_IDS':'invalid, '+self.identity.upper()}):
            self.assertEqual(self.ping()[0], 200)
            self.factory.assert_not_called()
            self.assertEqual(self.ping(identity=str(uuid4()))[0], 200)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM usage_pings').fetchone()[0], 1)

    def test_missing_wrong_or_unconfigured_token_returns_401(self):
        self.assertEqual(call('GET','/v1/usage/stats')[0], 401)
        self.assertEqual(self.stats('wrong')[0], 401)
        with patch.dict('os.environ', {'EDFRAME_ADMIN_TOKEN':''}):
            self.assertEqual(self.stats()[0], 401)
        self.factory.assert_not_called()

    def test_valid_token_constant_time_check_private_response_no_cors(self):
        with patch.object(api.secrets, 'compare_digest', wraps=api.secrets.compare_digest) as compare:
            status, data, headers = call('GET','/v1/usage/stats',headers={
                'X-EDFrame-Admin-Token':'private-test-token', 'Origin':'https://cmdrforcer.github.io'})
        self.assertEqual(status, 200)
        self.assertEqual(data, dict(dau=0,wau=0,mau=0,by_version_30d={}))
        compare.assert_called_once_with(b'private-test-token', b'private-test-token')
        self.assertEqual(headers[b'cache-control'], b'no-store')
        self.assertNotIn(b'access-control-allow-origin', headers)

    def test_rolling_utc_windows_and_latest_version_count_each_id_once(self):
        for offset, version in ((-29,'old'),(-6,'1.0.8'),(0,'1.0.9')):
            usage.record_ping(self.store, usage.UsagePingPayload(install_id=self.identity,app_version=version), self.today+timedelta(days=offset))
        for offset,version in ((-7,'1.0.8'),(-30,'outside'),(1,'future')):
            usage.record_ping(self.store, usage.UsagePingPayload(install_id=uuid4(),app_version=version), self.today+timedelta(days=offset))
        self.assertEqual(self.stats()[1], dict(dau=1,wau=1,mau=2,by_version_30d={'1.0.8':1,'1.0.9':1}))

    def test_retention_deletes_only_older_than_90_days(self):
        for offset in (0,-90,-91):
            usage.record_ping(self.store, usage.UsagePingPayload(install_id=uuid4(),app_version='1.0.9'), self.today+timedelta(days=offset))
        self.assertEqual(usage.purge_old_pings(self.store, self.today), 1)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM usage_pings').fetchone()[0], 2)

    def test_retention_runs_once_daily_and_after_downtime(self):
        maintenance = usage.UsageRetention(lambda:self.store)
        self.assertTrue(maintenance.run_due(self.today))
        self.assertFalse(maintenance.run_due(self.today))
        self.assertTrue(maintenance.run_due(self.today+timedelta(days=2)))

    def test_in_memory_rate_limit_has_no_ip_key(self):
        for _ in range(6):
            self.assertEqual(self.ping()[0],200)
        self.assertEqual(self.ping()[0],429)
        self.assertEqual(set(api._usage_rate_buckets),{self.identity})
        columns = {row[1] for row in self.store.db.execute('PRAGMA table_info(usage_pings)')}
        self.assertEqual(columns, {'install_id','day','app_version'})

    def test_usage_not_added_to_public_status_or_caddy_cors(self):
        root = Path(usage.__file__).parents[1]
        caddy = (root/'Caddyfile').read_text()
        self.assertNotIn('/v1/usage', caddy)
        source = Path(api.__file__).read_text()
        status = source.split('@app.get("/v1/status")',1)[1].split('@app.',1)[0]
        for private_field in ('usage_pings', 'usage_stats', 'by_version_30d', '"dau"'):
            self.assertNotIn(private_field, status)
