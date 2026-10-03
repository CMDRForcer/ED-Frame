from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.responses import ORJSONResponse

from . import __version__
from .database import connection, ensure_schema


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_schema()
    yield


app = FastAPI(
    title="ED-Frame Public Catalog",
    version=__version__,
    docs_url=None,
    redoc_url=None,
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)


def _percent(part: int, whole: int) -> float:
    return round((part * 100.0 / whole), 1) if whole else 0.0


@app.get("/")
def root() -> dict:
    return {
        "service": "ED-Frame Public Catalog",
        "version": __version__,
        "status": "/v1/status",
        "health": "/healthz",
        "stations": "/v1/stations/search",
    }


@app.get("/healthz")
def health() -> dict:
    with connection() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"status": "ok", "version": __version__, "time": _now()}


@app.get("/v1/status")
def status() -> dict:
    with connection() as conn:
        counts = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM systems) AS systems,
              (SELECT COUNT(*) FROM stations) AS stations,
              (SELECT COUNT(*) FROM markets) AS markets,
              (SELECT COUNT(*) FROM mining_sites) AS sites
            """
        ).fetchone()
        state = conn.execute(
            "SELECT * FROM collector_state WHERE source = 'EDDN'"
        ).fetchone()
        commodities = conn.execute(
            "SELECT COUNT(DISTINCT commodity) AS value FROM markets"
        ).fetchone()
        market_quality = conn.execute(
            """
            SELECT COUNT(*) FILTER (
                       WHERE m.observed_at >= NOW() - INTERVAL '1 hour'
                   ) AS fresh_1h,
                   COUNT(*) FILTER (
                       WHERE m.observed_at >= NOW() - INTERVAL '24 hours'
                   ) AS fresh_24h,
                   COUNT(*) FILTER (
                       WHERE s.x IS NOT NULL AND s.y IS NOT NULL AND s.z IS NOT NULL
                   ) AS with_coordinates
            FROM markets m
            LEFT JOIN systems s ON LOWER(s.name) = LOWER(m.system_name)
            """
        ).fetchone()
        site_quality = conn.execute(
            """
            SELECT COUNT(*) FILTER (
                       WHERE x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL
                   ) AS with_coordinates,
                   COUNT(*) FILTER (WHERE hotspots <> '[]'::jsonb) AS with_hotspots
            FROM mining_sites
            """
        ).fetchone()
        station_quality = conn.execute(
            """
            SELECT COUNT(*) FILTER (WHERE station_type IS NOT NULL) AS with_type,
                   COUNT(*) FILTER (WHERE landing_pad_size IS NOT NULL) AS with_pad,
                   COUNT(*) FILTER (
                       WHERE distance_to_arrival_ls IS NOT NULL
                   ) AS with_distance,
                   COUNT(*) FILTER (WHERE services IS NOT NULL) AS with_services,
                   COUNT(*) FILTER (WHERE economies IS NOT NULL) AS with_economies
            FROM stations
            """
        ).fetchone()
        market_detail = conn.execute(
            """
            SELECT COUNT(*) FILTER (
                       WHERE mean_price IS NOT NULL
                         AND buy_price IS NOT NULL
                         AND stock IS NOT NULL
                         AND demand_bracket IS NOT NULL
                   ) AS complete
            FROM markets
            """
        ).fetchone()
    market_count = int(counts["markets"])
    site_count = int(counts["sites"])
    station_count = int(counts["stations"])
    return {
        "generatedAt": _now(),
        "counts": {
            **dict(counts),
            "commodities": int(commodities["value"]),
        },
        "completeness": {
            "freshMarkets1h": int(market_quality["fresh_1h"]),
            "freshMarkets24h": int(market_quality["fresh_24h"]),
            "marketsWithCoordinates": int(market_quality["with_coordinates"]),
            "marketCoordinatePercent": _percent(
                int(market_quality["with_coordinates"]), market_count
            ),
            "marketsWithFullCommodityData": int(market_detail["complete"]),
            "marketDetailPercent": _percent(
                int(market_detail["complete"]), market_count
            ),
            "stationsWithType": int(station_quality["with_type"]),
            "stationTypePercent": _percent(
                int(station_quality["with_type"]), station_count
            ),
            "stationsWithLandingPad": int(station_quality["with_pad"]),
            "stationLandingPadPercent": _percent(
                int(station_quality["with_pad"]), station_count
            ),
            "stationsWithDistance": int(station_quality["with_distance"]),
            "stationDistancePercent": _percent(
                int(station_quality["with_distance"]), station_count
            ),
            "stationsWithServices": int(station_quality["with_services"]),
            "stationServicesPercent": _percent(
                int(station_quality["with_services"]), station_count
            ),
            "stationsWithEconomies": int(station_quality["with_economies"]),
            "stationEconomiesPercent": _percent(
                int(station_quality["with_economies"]), station_count
            ),
            "sitesWithCoordinates": int(site_quality["with_coordinates"]),
            "siteCoordinatePercent": _percent(
                int(site_quality["with_coordinates"]), site_count
            ),
            "sitesWithHotspots": int(site_quality["with_hotspots"]),
            "siteHotspotPercent": _percent(
                int(site_quality["with_hotspots"]), site_count
            ),
        },
        "collector": dict(state) if state else None,
    }


@app.get("/v1/systems/suggest")
def suggest_systems(
    q: Annotated[str, Query(min_length=2, max_length=80)],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> dict:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT name, system_address, x, y, z, observed_at
            FROM systems
            WHERE LOWER(name) LIKE LOWER(%s)
            ORDER BY
              CASE WHEN LOWER(name) = LOWER(%s) THEN 0 ELSE 1 END,
              LENGTH(name), name
            LIMIT %s
            """,
            (f"{q.strip()}%", q.strip(), limit),
        ).fetchall()
    return {"generatedAt": _now(), "results": rows}


@app.get("/v1/markets/search")
def search_markets(
    commodity: Annotated[str, Query(min_length=2, max_length=80)],
    system: Annotated[str | None, Query(max_length=100)] = None,
    min_demand: Annotated[int, Query(ge=0)] = 0,
    max_age_hours: Annotated[int, Query(ge=1, le=24 * 90)] = 168,
    landing_pad: Annotated[
        str | None, Query(pattern="^(S|M|L)$")
    ] = None,
    exclude_fleet_carriers: bool = True,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    max_distance: Annotated[float | None, Query(gt=0, le=2000)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict:
    clauses = [
        "m.commodity = LOWER(%s)",
        "m.sell_price > 0",
        "m.demand >= %s",
        "m.observed_at >= NOW() - (%s * INTERVAL '1 hour')",
    ]
    values: list[object] = [commodity.strip(), min_demand, max_age_hours]
    if system:
        clauses.append("LOWER(m.system_name) = LOWER(%s)")
        values.append(system.strip())
    if landing_pad:
        accepted = {
            "S": ("S", "M", "L"),
            "M": ("M", "L"),
            "L": ("L",),
        }[landing_pad]
        placeholders = ", ".join(("%s",) * len(accepted))
        clauses.append(f"st.landing_pad_size IN ({placeholders})")
        values.extend(accepted)
    if exclude_fleet_carriers:
        clauses.append("st.fleet_carrier IS NOT TRUE")
    if all(value is not None for value in (x, y, z, max_distance)):
        clauses.append(
            "POWER(s.x - %s, 2) + POWER(s.y - %s, 2) + "
            "POWER(s.z - %s, 2) <= POWER(%s, 2)"
        )
        values.extend((x, y, z, max_distance))
    values.append(limit)
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT m.market_id AS "marketId", m.commodity,
                   m.station_name AS station, m.system_name AS system,
                   m.mean_price AS "meanPrice", m.buy_price AS "buyPrice",
                   m.stock, m.stock_bracket AS "stockBracket",
                   m.sell_price AS "sellPrice", m.demand,
                   m.demand_bracket AS "demandBracket",
                   m.status_flags AS "statusFlags",
                   m.observed_at AS "observedAt", m.received_at AS "receivedAt",
                   s.x, s.y, s.z, m.source,
                   st.station_type AS "stationType",
                   st.system_address AS "systemAddress",
                   st.landing_pad_size AS "landingPadSize",
                   st.distance_to_arrival_ls AS "distanceToArrivalLs",
                   st.services, st.economies,
                   st.primary_economy AS "primaryEconomy",
                   st.government,
                   st.controlling_faction AS "controllingFaction",
                   st.fleet_carrier AS "fleetCarrier",
                   st.carrier_docking_access AS "carrierDockingAccess",
                   st.prohibited
            FROM markets m
            LEFT JOIN systems s ON LOWER(s.name) = LOWER(m.system_name)
            LEFT JOIN stations st ON st.market_id = m.market_id
            WHERE {' AND '.join(clauses)}
            ORDER BY m.sell_price DESC, m.demand DESC, m.observed_at DESC
            LIMIT %s
            """,
            values,
        ).fetchall()
    return {"generatedAt": _now(), "results": rows}


@app.get("/v1/stations/search")
def search_stations(
    system: Annotated[str | None, Query(max_length=100)] = None,
    service: Annotated[str | None, Query(max_length=80)] = None,
    landing_pad: Annotated[
        str | None, Query(pattern="^(S|M|L)$")
    ] = None,
    exclude_fleet_carriers: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict:
    clauses = ["TRUE"]
    values: list[object] = []
    if system:
        clauses.append("LOWER(st.system_name) = LOWER(%s)")
        values.append(system.strip())
    if service:
        clauses.append(
            "EXISTS (SELECT 1 FROM jsonb_array_elements_text("
            "COALESCE(st.services, '[]'::jsonb)) item "
            "WHERE LOWER(item) = LOWER(%s))"
        )
        values.append(service.strip())
    if landing_pad:
        clauses.append("st.landing_pad_size = %s")
        values.append(landing_pad)
    if exclude_fleet_carriers:
        clauses.append("st.fleet_carrier IS NOT TRUE")
    values.append(limit)
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT st.market_id AS "marketId", st.system_name AS system,
                   st.station_name AS station, st.system_address AS "systemAddress",
                   st.station_type AS "stationType",
                   st.landing_pad_size AS "landingPadSize",
                   st.distance_to_arrival_ls AS "distanceToArrivalLs",
                   st.services, st.economies,
                   st.primary_economy AS "primaryEconomy", st.government,
                   st.controlling_faction AS "controllingFaction",
                   st.fleet_carrier AS "fleetCarrier",
                   st.carrier_docking_access AS "carrierDockingAccess",
                   st.prohibited, st.observed_at AS "observedAt",
                   st.received_at AS "receivedAt", st.source
            FROM stations st
            WHERE {' AND '.join(clauses)}
            ORDER BY st.observed_at DESC
            LIMIT %s
            """,
            values,
        ).fetchall()
    return {"generatedAt": _now(), "results": rows}


@app.get("/v1/sites/search")
def search_sites(
    commodity: Annotated[str | None, Query(max_length=80)] = None,
    system: Annotated[str | None, Query(max_length=100)] = None,
    max_age_days: Annotated[int, Query(ge=1, le=3650)] = 365,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    max_distance: Annotated[float | None, Query(gt=0, le=2000)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict:
    clauses = ["observed_at >= NOW() - (%s * INTERVAL '1 day')"]
    values: list[object] = [max_age_days]
    if commodity:
        clauses.append(
            "EXISTS (SELECT 1 FROM jsonb_array_elements(hotspots) h "
            "WHERE LOWER(h->>'commodity') = LOWER(%s))"
        )
        values.append(commodity.strip())
    if system:
        clauses.append("LOWER(system_name) = LOWER(%s)")
        values.append(system.strip())
    if all(value is not None for value in (x, y, z, max_distance)):
        clauses.append(
            "POWER(x - %s, 2) + POWER(y - %s, 2) + "
            "POWER(z - %s, 2) <= POWER(%s, 2)"
        )
        values.extend((x, y, z, max_distance))
    values.append(limit)
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT system_address AS "systemAddress", system_name AS system,
                   x, y, z, body_id AS "bodyId", body_name AS body,
                   ring_name AS ring, ring_type AS "ringType",
                   reserve_level AS "reserveLevel",
                   distance_to_arrival_ls AS "distanceToArrivalLs",
                   hotspots, evidence, source,
                   observed_at AS "observedAt", received_at AS "receivedAt"
            FROM mining_sites
            WHERE {' AND '.join(clauses)}
            ORDER BY observed_at DESC
            LIMIT %s
            """,
            values,
        ).fetchall()
    return {"generatedAt": _now(), "results": rows}

