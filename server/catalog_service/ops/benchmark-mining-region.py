"""Run on an API container via stdin: read-only, bounded regional SQL probe.

Does not install source, migrate schema or restart services. Compare the exact
old and new result payloads within one repeatable-read transaction.
"""
import contextlib
import json
import time
from edframe_catalog import api
from edframe_catalog.database import connection


class Probe:
    def __init__(self, conn): self.conn = conn
    def execute(self, sql, params=None):
        if 'WITH selected_sites AS MATERIALIZED' not in sql:
            return self.conn.execute(sql, params)
        box = ('point(ms.x, ms.y) <@ box(point(%s, %s), point(%s, %s)) '
               'AND ms.z BETWEEN %s AND %s')
        original = list(params)
        if box in sql:
            sql = sql.replace(' AND '+box, '', 1)
            original = [*original[:-8], *original[-2:]]
        larger = [*original[:-2], 5001, original[-1]]
        marker = 'ORDER BY ms.observed_at DESC, ms.identity DESC'
        optimized = sql.replace(marker, 'AND '+box+'\n                '+marker, 1)
        x, y, z, radius = original[-6:-2]
        boxed = [*original[:-2], x-radius, y-radius, x+radius, y+radius,
                 z-radius, z+radius, 5001, original[-1]]
        baseline = []
        for label, query, values in (('legacy-1000', sql, original),
                                     ('legacy-5000', sql, larger),
                                     ('indexed-box-5000', optimized, boxed)):
            started = time.monotonic()
            rows = self.conn.execute(query, values).fetchall()
            equal = not baseline or (rows == baseline if len(baseline) > 1001 else rows[:len(baseline)] == baseline)
            print(json.dumps(dict(query=label, seconds=round(time.monotonic()-started, 4),
                                  rows=len(rows), equal=equal)), flush=True)
            assert equal, 'Regional query changed public facts or order'
            baseline = rows
        class Empty:
            def fetchall(self): return []
        return Empty()


@contextlib.contextmanager
def probe_connection():
    with connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        conn.execute("SET LOCAL statement_timeout='30s'")
        yield Probe(conn)


api.connection = probe_connection
api.enrich_ring_metadata = lambda conn, rows: rows
api.community_reference_candidates = lambda *args, **kwargs: []
api.search_sites(commodity='platinum', x=110.9375, y=-113.0625, z=41.21875,
                 max_distance=250, limit=1000, max_age_days=3650,
                 include_community_overlaps=True, include_ring_candidates=True, offset=0)
