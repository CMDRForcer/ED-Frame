"""Add online indexes for regional paging; preserve all catalog records."""
from edframe_catalog.database import connection

with connection() as conn:
    conn.autocommit = True
    for query in (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS mining_sites_page_idx ON mining_sites (observed_at DESC, identity DESC)',
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ring_reference_ring_lower_idx ON ring_reference_metadata (LOWER(system_name), LOWER(ring_name))',
    ):
        conn.execute(query)
        print(query, flush=True)
