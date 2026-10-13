"""Read-only operator diagnostics; never exposed through the public API."""
from __future__ import annotations


class QueryPerformanceUnavailable(RuntimeError):
    pass


def read_query_performance(conn, *, limit=20, include_sql=False):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError("Diagnostic limit must be an integer from 1 to 50")
    conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SET LOCAL statement_timeout = '3s'")
    ready = conn.execute("SELECT to_regclass('public.pg_stat_statements') IS NOT NULL AS ready").fetchone()
    if not ready or not ready["ready"]:
        raise QueryPerformanceUnavailable("pg_stat_statements is not installed in this database")
    state = conn.execute("""SELECT clock_timestamp() AS checked_at,
        current_setting('shared_preload_libraries') AS libraries,
        current_setting('pg_stat_statements.track') AS track,
        current_setting('pg_stat_statements.track_planning') AS track_planning,
        current_setting('track_io_timing') AS io_timing,
        stats_reset, dealloc FROM pg_stat_statements_info""").fetchone()
    rows = conn.execute("""SELECT queryid::text AS query_id, calls,
        total_exec_time AS total_ms, mean_exec_time AS mean_ms,
        max_exec_time AS max_ms, rows, shared_blks_hit, shared_blks_read,
        shared_blk_read_time AS read_ms,
        temp_blks_written * current_setting('block_size')::bigint AS temp_written_bytes,
        wal_bytes::bigint AS wal_bytes, stats_since,
        split_part(ltrim(query), ' ', 1) AS operation,
        CASE WHEN %s THEN left(query, 500) ELSE NULL END AS sql
        FROM pg_stat_statements
        WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
          AND calls > 0 AND query NOT ILIKE '%%pg_stat_statements%%'
        ORDER BY total_exec_time DESC, queryid
        LIMIT %s""", (include_sql, limit)).fetchall()
    return {"collection": dict(state), "ranking": "cumulative execution time",
            "statements": [dict(row) for row in rows]}
