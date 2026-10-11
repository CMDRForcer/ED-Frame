"""Bounded regional market snapshots for observed A -> B -> A suggestions."""
import threading
import time
from datetime import datetime, timezone

from fastapi import HTTPException
from psycopg.errors import LockNotAvailable, QueryCanceled
from ed_companion.navigation.mining_market import MiningMarketError
from ed_companion.navigation.trade_route_model import rank_loops, trade_symbols
from .database import connection

MAX_STATIONS = 320
MAX_STARTS = 80
MAX_QUOTES = 120_000
_gate = threading.BoundedSemaphore(1)
_cache_lock = threading.Lock()
_cache = {}


def search_trade_routes(filters, limit=30, refresh=False):
    key = tuple((name, tuple(value) if isinstance(value, list) else value) for name,value in sorted(filters.items())) + (("limit",limit),)
    with _cache_lock:
        cached = _cache.get(key)
        if not refresh and cached and time.monotonic()-cached[0] < 60:
            return dict(cached[1], cached=True)
    if not _gate.acquire(blocking=False):
        raise HTTPException(503, "Trade route search busy · retry shortly")
    try:
        result = _search(filters, limit)
        with _cache_lock:
            if len(_cache) >= 8:
                _cache.pop(min(_cache, key=lambda k:_cache[k][0]))
            _cache[key] = (time.monotonic(), result)
        return dict(result, cached=False)
    finally:
        _gate.release()


def _search(filters, limit):
    x,y,z = filters["origin"]
    reach = filters["radiusLy"] + filters["maxLegLy"]
    symbols = trade_symbols()
    pad = filters["landingPad"]
    clauses = ["SQRT(POWER(s.x - %s,2) + POWER(s.y - %s,2) + POWER(s.z - %s,2)) <= %s",
        "EXISTS (SELECT 1 FROM markets m WHERE m.market_id=st.market_id AND m.commodity=ANY(%s)"
        " AND m.observed_at >= NOW()-(%s*INTERVAL '1 hour')"
        " AND ((m.buy_price>0 AND m.stock>0) OR (m.sell_price>0 AND m.demand>0)))"]
    values = [x,y,z, x,y,z,reach, symbols, filters["maxAgeHours"]]
    if pad != "ANY":
        clauses.append("st.landing_pad_size=ANY(%s)")
        values.append({"S":["S","M","L"],"M":["M","L"],"L":["L"]}[pad])
    if filters["excludeCarriers"]:
        clauses.append("st.fleet_carrier IS NOT TRUE")
    values.extend([filters["radiusLy"],MAX_STATIONS])
    with connection() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout = '10s'")
        conn.execute("SET LOCAL lock_timeout = '2s'")
        # Coordinate competing heavy searches across the two API workers.
        if not conn.execute("SELECT pg_try_advisory_xact_lock(%s) AS acquired", (45444652615,)).fetchone()["acquired"]:
            raise HTTPException(503, "Trade route search busy · retry shortly")
        try:
            stations = conn.execute(f"""
                WITH nearby AS MATERIALIZED (
                    SELECT st.market_id AS "marketId", st.station_name AS station, st.system_name AS system,
                           st.landing_pad_size AS "landingPadSize", st.fleet_carrier AS "fleetCarrier",
                           st.carrier_docking_access AS "carrierDockingAccess", st.prohibited,
                           st.distance_to_arrival_ls AS "distanceToArrivalLs", st.station_type AS "stationType",
                           ARRAY[s.x,s.y,s.z] AS coordinates,
                           SQRT(POWER(s.x - %s,2) + POWER(s.y - %s,2) + POWER(s.z - %s,2)) AS "distanceLy"
                    FROM stations st
                    JOIN LATERAL (
                        SELECT sy.x,sy.y,sy.z FROM systems sy
                        WHERE ((st.system_address IS NOT NULL AND sy.system_address=st.system_address)
                            OR (st.system_address IS NULL AND LOWER(sy.name)=LOWER(st.system_name)))
                          AND sy.x IS NOT NULL AND sy.y IS NOT NULL AND sy.z IS NOT NULL
                        ORDER BY sy.observed_at DESC NULLS LAST,sy.name LIMIT 1
                    ) s ON TRUE
                    WHERE {' AND '.join(clauses)}
                )
                SELECT *, COUNT(*) OVER() AS "availableStations",
                    COUNT(*) FILTER(WHERE "distanceLy" <= %s) OVER() AS "availableStarts"
                FROM nearby ORDER BY "distanceLy", "marketId" LIMIT %s
            """, tuple(values)).fetchall()
            available = int(stations[0]["availableStations"]) if stations else 0
            available_starts = int(stations[0]["availableStarts"]) if stations else 0
            starts = 0
            for row in stations:
                row.pop("availableStations", None); row.pop("availableStarts", None)
                row["startCandidate"] = row["distanceLy"] <= filters["radiusLy"] and starts < MAX_STARTS
                starts += int(row["startCandidate"])
            quotes = []
            if stations:
                quotes = conn.execute("""
                    SELECT market_id AS "marketId", commodity, buy_price AS "buyPrice", sell_price AS "sellPrice",
                        stock, demand, observed_at AS "observedAt", source
                    FROM markets WHERE market_id=ANY(%s) AND commodity=ANY(%s)
                        AND observed_at >= NOW()-(%s*INTERVAL '1 hour')
                        AND ((buy_price>0 AND stock>0) OR (sell_price>0 AND demand>0))
                    ORDER BY market_id,commodity LIMIT %s
                """, ([r["marketId"] for r in stations],symbols,filters["maxAgeHours"],MAX_QUOTES+1)).fetchall()
            if len(quotes) > MAX_QUOTES:
                raise HTTPException(503, "Trade route snapshot too large · narrow the search")
            loops = rank_loops(stations,quotes,filters,limit,deadline=time.monotonic()+5)
        except (LockNotAvailable, QueryCanceled, MiningMarketError) as exc:
            raise HTTPException(503, "Trade route search timed out · narrow the radius or quote age") from exc
    return dict(loops, filters=filters, generatedAt=datetime.now(timezone.utc).isoformat(), coverage=dict(stations=len(stations), starts=starts,
        availableStations=available, availableStarts=available_starts, quotes=len(quotes),
        sampled=available>len(stations) or available_starts>starts))
