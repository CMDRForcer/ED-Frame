"""Compare indexed sync against the former SQL, in one consistent snapshot.

--synthetic requires a disposable edframe_sync_probe_* database and populates
only that database. --live-readonly never runs schema setup or writes facts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import random
import time
from unittest.mock import patch

from edframe_catalog import api
from edframe_catalog.database import connection, ensure_schema
from edframe_catalog.market_sync import market_sync_query
from ed_companion.navigation.mining_commodities import MINING_COMMODITIES
from psycopg.types.json import Jsonb


_LEGACY_SQL = '\n            WITH changed AS (\n                SELECT m.market_id, m.commodity,\n                       COALESCE(NULLIF(st.station_name, \'\'), m.station_name)\n                           AS station_name,\n                       COALESCE(NULLIF(st.system_name, \'\'), m.system_name)\n                           AS system_name,\n                       m.mean_price, m.buy_price, m.stock, m.stock_bracket,\n                       m.sell_price, m.demand, m.demand_bracket,\n                       m.status_flags, m.observed_at, m.received_at,\n                       s.x, s.y, s.z, m.source,\n                       st.station_type, st.system_address,\n                       st.landing_pad_size, st.distance_to_arrival_ls,\n                       st.services, st.economies, st.primary_economy,\n                       st.government, st.controlling_faction,\n                       st.fleet_carrier, st.carrier_docking_access,\n                       st.prohibited,\n                       GREATEST(\n                           m.received_at,\n                           COALESCE(st.received_at, m.received_at)\n                       ) AS sync_at\n                FROM markets m\n                LEFT JOIN systems s\n                  ON LOWER(s.name) = LOWER(m.system_name)\n                LEFT JOIN stations st ON st.market_id = m.market_id\n            )\n            SELECT market_id AS "marketId", commodity,\n                   station_name AS station, system_name AS system,\n                   mean_price AS "meanPrice", buy_price AS "buyPrice",\n                   stock, stock_bracket AS "stockBracket",\n                   sell_price AS "sellPrice", demand,\n                   demand_bracket AS "demandBracket",\n                   status_flags AS "statusFlags",\n                   observed_at AS "observedAt", received_at AS "receivedAt",\n                   x, y, z, source,\n                   station_type AS "stationType",\n                   system_address AS "systemAddress",\n                   landing_pad_size AS "landingPadSize",\n                   distance_to_arrival_ls AS "distanceToArrivalLs",\n                   services, economies, primary_economy AS "primaryEconomy",\n                   government, controlling_faction AS "controllingFaction",\n                   fleet_carrier AS "fleetCarrier",\n                   carrier_docking_access AS "carrierDockingAccess",\n                   prohibited, sync_at AS "syncAt"\n            FROM changed\n            WHERE (sync_at, market_id, commodity) > (%(cursor_at)s, %(cursor_market_id)s, %(cursor_commodity)s) {commodity_filter}\n            ORDER BY sync_at, market_id, commodity\n            LIMIT %(batch_size)s\n            '


def emit(**data):
    print(json.dumps(data, default=str), flush=True)


def legacy_query(params):
    return _LEGACY_SQL.format(
        commodity_filter="AND commodity = ANY(%(commodities)s)"
        if params["commodities"] else "",
    )


def compare(conn, cursor, commodities, batch_size):
    query, params = market_sync_query(*cursor, commodities, batch_size)
    start = time.monotonic()
    expected = conn.execute(legacy_query(params), params).fetchall()
    old_ms = (time.monotonic() - start) * 1000
    start = time.monotonic()
    actual = conn.execute(query, params).fetchall()
    new_ms = (time.monotonic() - start) * 1000
    assert actual == expected, (
        "Sync data or order changed", cursor, commodities, batch_size,
        len(expected), len(actual),
    )
    return actual, query, params, round(old_ms, 3), round(new_ms, 3)


def synthetic():
    with connection() as conn:
        name = conn.execute("SELECT current_database() AS name").fetchone()["name"]
        if not name.startswith("edframe_sync_probe_"):
            raise RuntimeError("Refuse to populate a retained catalog database")
    ensure_schema()
    base = datetime(2026, 10, 12, tzinfo=timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    with connection() as conn:
        cases = 0
        rows, *_ = compare(conn, (epoch, 0, ""), [], 501)
        assert rows == []
        cases += 1
        # NULL/absent metadata, empty-name fallback, equal receipts, old
        # observation times and carrier metadata. Equal receipts belong to
        # the market branch once; older facts still get newer station fields.
        conn.execute(
            "INSERT INTO systems(name,x,y,z) VALUES('Sync System',1,2,3)"
        )
        rng = random.Random(521)
        symbols = ("gold", "platinum", "silver", "lithiumhydroxide")
        for market_id in range(-2, 48):
            station_at = base + timedelta(seconds=rng.randrange(1, 8))
            if market_id % 7:
                conn.execute("""
                    INSERT INTO stations (
                        market_id, system_name, station_name, received_at,
                        observed_at, source, station_type, landing_pad_size,
                        fleet_carrier, carrier_docking_access, services,
                        economies, prohibited
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (market_id, "Sync System" if market_id % 3 else "",
                          f"Enriched {market_id}" if market_id % 4 else "",
                          station_at, base-timedelta(days=3), "synthetic",
                          "FleetCarrier" if market_id % 2 else "Orbis",
                          "L", bool(market_id % 2), "all", Jsonb(["Market"]),
                          Jsonb([{"name": "Industrial", "proportion": 1}]),
                          Jsonb(["slaves"])))
            for symbol in symbols:
                received = station_at if symbol == "silver" else (
                    base + timedelta(seconds=rng.randrange(1, 8))
                )
                conn.execute("""
                    INSERT INTO markets(
                        market_id, commodity, station_name, system_name,
                        sell_price, demand, mean_price, buy_price, stock,
                        stock_bracket, demand_bracket, status_flags,
                        observed_at, received_at, source
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (market_id, symbol, f"Retained {market_id}",
                          "Sync System" if market_id % 5 else "Unknown System",
                          rng.randrange(100, 1000), rng.randrange(1000),
                          300, 200, 123, 3, 2, Jsonb(["GalacticAverage"]),
                          base-timedelta(days=10), received, "synthetic"))
        # One station containing more rows than the maximum API page: exercise
        # the inner station limit and a cursor resuming inside that station.
        conn.execute("""
            INSERT INTO stations(market_id,system_name,station_name,
                                 received_at,observed_at,source)
            VALUES(9000,'Sync System','Large Carrier',%s,%s,'synthetic')
            """, (base+timedelta(seconds=4), base))
        conn.execute("""
            INSERT INTO markets(market_id,commodity,station_name,system_name,
                                sell_price,demand,observed_at,received_at)
            SELECT 9000,'synthetic'||lpad(i::text,4,'0'),'Large Carrier',
                   'Sync System',100,200,%s,%s
            FROM generate_series(1,1205) i
            """, (base, base))
        conn.commit()
        cursors = [
            (epoch, 0, ""),
            (base+timedelta(seconds=1), -2, "gold"),
            (base+timedelta(seconds=4), 9000, "synthetic0001"),
            (base+timedelta(seconds=4), 9000, "synthetic1001"),
            (base+timedelta(seconds=7), 47, "silver"),
            (base+timedelta(seconds=10), 0, ""),
        ]
        for cursor in cursors:
            for wanted in ([], ["platinum"], ["gold", "lithiumhydroxide"], ["absent"]):
                for batch in (1, 18, 501, 1001):
                    compare(conn, cursor, wanted, batch)
                    cases += 1

        # Walk every page; a page ending inside a station or at tied timestamps
        # must advance without lost or duplicated keys.
        pages = {}
        for wanted in ([], ["platinum"], ["gold", "lithiumhydroxide"]):
            initial = (epoch, 0, "")
            all_rows, *_ = compare(conn, initial, wanted, 10000)
            cursor, seen, count = initial, [], 0
            while True:
                rows, *_ = compare(conn, cursor, wanted, 18)
                cases += 1
                visible = rows[:17]
                if not visible:
                    break
                seen.extend(visible)
                last = visible[-1]
                cursor = (last["syncAt"], last["marketId"], last["commodity"])
                count += 1
                if len(rows) <= 17:
                    break
            assert seen == all_rows, "Paged stream lost or repeated facts"
            pages[",".join(wanted) or "ALL"] = count

        # A station-only update must re-emit every retained commodity with
        # enriched fields while preserving original price observation times.
        before, *_ = compare(conn, (epoch, 0, ""), [], 10000)
        latest = max(row["syncAt"] for row in before)
        conn.execute("""
            UPDATE stations SET received_at=%s,station_name='Changed Port',
                                carrier_docking_access='friends'
            WHERE market_id=1
            """, (latest+timedelta(seconds=1),))
        after, *_ = compare(conn, (latest, 999999, "zzzz"), [], 501)
        assert len(after) == 4
        assert all(row["marketId"] == 1 and row["station"] == "Changed Port"
                   and row["carrierDockingAccess"] == "friends"
                   and row["observedAt"] == base-timedelta(days=10)
                   for row in after)
        cases += 1
        # Actual endpoint pagination and opaque cursor on the SQL-backed data.
        with patch.object(api, "connection", return_value=connection()):
            page = api.sync_markets(None, " Platinum,platinum ", 3)
        assert len(page["results"]) == 3 and page["hasMore"]
        last = page["results"][-1]
        assert api._decode_market_cursor(page["nextCursor"]) == (
            last["syncAt"], last["marketId"], last["commodity"],
        )
        emit(mode="synthetic", comparisons=cases, pagedStreams=pages,
             stationOnlyUpdate="PASS", endpointCursor="PASS", result="PASS")


def live_readonly():
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    with connection() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        conn.execute("SET LOCAL statement_timeout = '35s'")
        conn.execute("SET LOCAL lock_timeout = '2s'")
        now = conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
        wanted = sorted(MINING_COMMODITIES)
        cases = [
            ("initial_app_1000", (epoch, 0, ""), wanted, 1001),
            ("recent_app_1000", (now-timedelta(hours=1), 0, ""), wanted, 1001),
            ("initial_platinum_500", (epoch, 0, ""), ["platinum"], 501),
            ("future_empty_all", (now+timedelta(days=1), 0, ""), [], 501),
            ("unknown_symbol", (now-timedelta(hours=1), 0, ""),
             ["__edframe_no_such_commodity__"], 501),
        ]
        initial_cursor = None
        for name, cursor, commodities, batch in cases:
            rows, query, params, old_ms, new_ms = compare(
                conn, cursor, commodities, batch,
            )
            plan = conn.execute(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query, params,
            ).fetchone()["QUERY PLAN"][0]
            root = plan["Plan"]
            assert root.get("Temp Written Blocks", 0) == 0, name
            emit(case=name, rows=len(rows), identical=True,
                 legacyMs=old_ms, indexedMs=new_ms,
                 explainedMs=plan["Execution Time"],
                 tempWrittenBytes=root.get("Temp Written Blocks", 0)*8192)
            if name == "initial_app_1000":
                last = rows[999]
                initial_cursor = (last["syncAt"], last["marketId"], last["commodity"])
        rows, query, params, old_ms, new_ms = compare(
            conn, initial_cursor, wanted, 1001,
        )
        emit(case="resumed_app_1000", rows=len(rows), identical=True,
             legacyMs=old_ms, indexedMs=new_ms)
    emit(mode="live-readonly", result="PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--synthetic", action="store_true")
    mode.add_argument("--live-readonly", action="store_true")
    args = parser.parse_args()
    synthetic() if args.synthetic else live_readonly()
