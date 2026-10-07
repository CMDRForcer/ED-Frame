"""Read-only server query timing; no catalog mutations."""
import json
import time
from contextlib import contextmanager
from edframe_catalog import api

original_connection = api.connection
timings = []

@contextmanager
def profiled_connection():
    with original_connection() as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        conn.execute('SET LOCAL jit = off')
        conn.execute("SET LOCAL statement_timeout = '30000ms'")
        class Proxy:
            def execute(self, query, params=None):
                start = time.monotonic()
                cursor = conn.execute(query, params)
                timings.append({'query': str(query).strip()[:160], 'seconds': round(time.monotonic() - start, 3)})
                if 'selected_sites AS MATERIALIZED' in str(query):
                    explained = conn.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + query, params).fetchone()
                    plan = next(iter(explained.values()))[0]
                    def compact(node):
                        return {k: ([compact(p) for p in v] if k == 'Plans' else v)
                                for k, v in node.items() if k in ('Node Type', 'Relation Name', 'Index Name', 'Actual Total Time', 'Actual Rows', 'Actual Loops', 'Rows Removed by Filter', 'Filter', 'Index Cond', 'Plans', 'Shared Hit Blocks', 'Shared Read Blocks')}
                    print(json.dumps({'plan': compact(plan['Plan']), 'executionMs': plan['Execution Time']}, indent=2), flush=True)
                return cursor
        yield Proxy()

api.connection = profiled_connection
start = time.monotonic()
result = api.search_sites(commodity='platinum', x=110.9375, y=-113.0625, z=41.21875,
                         max_distance=250, max_age_days=3650, limit=1000, offset=0,
                         include_community_overlaps=True, include_ring_candidates=True)
print(json.dumps({'seconds': round(time.monotonic() - start, 3), 'count': len(result['results']), 'queries': timings}, indent=2, default=str))
