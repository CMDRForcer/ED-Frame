"""Read-only PostgreSQL checks for exact, indexed catalog statistics."""
from __future__ import annotations

import json
import os
import time

from edframe_catalog.database import connection
from edframe_catalog.status_queries import COMMODITY_COUNT_SQL


def emit(**fields):
    print(json.dumps(fields), flush=True)


def main():
    assert "default_transaction_read_only=on" in os.environ.get("PGOPTIONS", ""), "Require read-only defaults"
    cases = {
        "empty": [],
        "only_null": [None, None],
        "single_repeated": ["platinum"] * 100,
        "duplicates_and_null": ["gold", "gold", None, "silver", "platinum", "silver"],
        "future_identifiers": ["newcommodity", "NEWCOMMODITY", "unknown/123", "", "ä", "z", "ä", None],
        "many_duplicates": [f"commodity_{i % 421:03}" for i in range(5000)],
    }
    with connection() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout = '10s'")
        conn.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        fixture_query = COMMODITY_COUNT_SQL.replace(
            "WITH RECURSIVE observed_commodities",
            "WITH RECURSIVE markets AS (SELECT unnest(%s::text[]) AS commodity), observed_commodities",
            1,
        )
        for name, values in cases.items():
            expected = conn.execute("SELECT COUNT(DISTINCT commodity) AS value FROM unnest(%s::text[]) commodity", (values,)).fetchone()["value"]
            actual = conn.execute(fixture_query, (values,)).fetchone()["value"]
            assert actual == expected, (name, actual, expected)
            emit(case=name, exactCount=actual, result="PASS")
        start = time.monotonic()
        count = conn.execute(COMMODITY_COUNT_SQL).fetchone()["value"]
        elapsed = time.monotonic() - start
        plan = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + COMMODITY_COUNT_SQL).fetchone()["QUERY PLAN"][0]
        encoded = json.dumps(plan)
        assert "markets_search_idx" in encoded, "Commodity index not used"
        assert '"Node Type": "Seq Scan"' not in encoded, "Commodity count scanned market rows"
        assert plan["Plan"]["Temp Written Blocks"] == 0, "Commodity count spilled to disk"
        assert elapsed < 5, "Commodity count exceeded five-second verification budget"
        emit(liveCommodityCount=count, seconds=round(elapsed, 6), executionMs=plan["Execution Time"], index="markets_search_idx", temporaryBlocks=plan["Plan"]["Temp Written Blocks"], result="PASS")


if __name__ == "__main__":
    main()
