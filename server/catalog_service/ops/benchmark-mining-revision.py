"""Append after mining_revision.py and execute in an API Python process.

Read-only probe of the exact proposed SQL, without installing new code or
modifying schema/data. The static code hash is constant for SQL timing only.
"""
import time
from edframe_catalog.database import connection

static_revision = lambda: "read-only-sql-probe"
if globals().get("explain_only"):
    class ExplainConnection:
        def __init__(self, conn):
            self.conn = conn
        def execute(self, sql, values):
            print(json.dumps(self.conn.execute("EXPLAIN (FORMAT JSON) " + sql, values).fetchall()), flush=True)
            raise SystemExit(0)
    with connection() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        mining_revision(ExplainConnection(conn), dict(commodity="platinum", system="", max_age_days=3650,
                     x=110.9375, y=-113.0625, z=41.21875, max_distance=50,
                     limit=1000, include_ring_candidates=True, include_community_overlaps=True))
for radius in (50, 250, 500):
    with connection() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("SET LOCAL statement_timeout = '15s'")
        query = dict(commodity="platinum", system="", max_age_days=3650,
                     x=110.9375, y=-113.0625, z=41.21875, max_distance=radius,
                     limit=1000, include_ring_candidates=True, include_community_overlaps=True)
        start = time.monotonic()
        first = mining_revision(conn, query)
        seconds = time.monotonic() - start
        start = time.monotonic()
        second = mining_revision(conn, query)
        repeat = time.monotonic() - start
        assert first == second
        print(json.dumps(dict(radius=radius, seconds=round(seconds, 4),
                              repeatSeconds=round(repeat, 4), sameRevision=True)), flush=True)
        conn.rollback()
