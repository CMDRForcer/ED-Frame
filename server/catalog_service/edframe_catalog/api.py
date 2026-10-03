from __future__ import annotations

import base64
import binascii
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
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


def _encode_market_cursor(
    sync_at: datetime | str, market_id: int, commodity: str,
) -> str:
    stamp = (
        sync_at.astimezone(timezone.utc).isoformat()
        if isinstance(sync_at, datetime) else str(sync_at)
    )
    payload = json.dumps(
        [1, stamp, int(market_id), str(commodity)],
        ensure_ascii=True, separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_market_cursor(value: str | None) -> tuple[datetime, int, str]:
    if not value:
        return datetime(1970, 1, 1, tzinfo=timezone.utc), 0, ""
    try:
        text = str(value).strip()
        decoded = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        version, stamp, market_id, commodity = json.loads(decoded)
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if version != 1 or parsed.tzinfo is None or int(market_id) < 0:
            raise ValueError("invalid cursor fields")
        return (
            parsed.astimezone(timezone.utc), int(market_id), str(commodity),
        )
    except (
        binascii.Error, json.JSONDecodeError, TypeError, ValueError,
    ) as exc:
        raise HTTPException(status_code=400, detail="Invalid market cursor") from exc


def _encode_state_cursor(
    sync_at: datetime | str, kind: str, identity: str,
) -> str:
    stamp = (
        sync_at.astimezone(timezone.utc).isoformat()
        if isinstance(sync_at, datetime) else str(sync_at)
    )
    payload = json.dumps(
        [1, stamp, str(kind), str(identity)],
        ensure_ascii=True, separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_state_cursor(value: str | None) -> tuple[datetime, str, str]:
    if not value:
        return datetime(1970, 1, 1, tzinfo=timezone.utc), "", ""
    try:
        text = str(value).strip()
        decoded = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        version, stamp, kind, identity = json.loads(decoded)
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if version != 1 or parsed.tzinfo is None:
            raise ValueError("invalid cursor fields")
        return parsed.astimezone(timezone.utc), str(kind), str(identity)
    except (
        binascii.Error, json.JSONDecodeError, TypeError, ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400, detail="Invalid State Finds cursor"
        ) from exc


def _encode_offer_cursor(
    sync_at: datetime | str, kind: str, market_id: int,
) -> str:
    stamp = (
        sync_at.astimezone(timezone.utc).isoformat()
        if isinstance(sync_at, datetime) else str(sync_at)
    )
    payload = json.dumps(
        [1, stamp, str(kind), int(market_id)],
        ensure_ascii=True, separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_offer_cursor(value: str | None) -> tuple[datetime, str, int]:
    if not value:
        return datetime(1970, 1, 1, tzinfo=timezone.utc), "", 0
    try:
        text = str(value).strip()
        decoded = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        version, stamp, kind, market_id = json.loads(decoded)
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if version != 1 or parsed.tzinfo is None or int(market_id) < 0:
            raise ValueError("invalid cursor fields")
        return parsed.astimezone(timezone.utc), str(kind), int(market_id)
    except (
        binascii.Error, json.JSONDecodeError, TypeError, ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400, detail="Invalid station offer cursor"
        ) from exc


@app.get("/")
def root() -> dict:
    return {
        "service": "ED-Frame Public Catalog",
        "version": __version__,
        "status": "/v1/status",
        "health": "/healthz",
        "stations": "/v1/stations/search",
        "stationOffers": "/v1/station-offers/search",
        "marketSync": "/v1/sync/markets",
        "stationOfferSync": "/v1/sync/station-offers",
        "stateFindSync": "/v1/sync/state-finds",
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
              (SELECT COUNT(*) FROM mining_sites) AS sites,
              (SELECT COUNT(*) FROM station_outfitting) AS outfitting_stations,
              (SELECT COUNT(*) FROM station_shipyards) AS shipyard_stations,
              (SELECT COALESCE(SUM(jsonb_array_length(modules)), 0)
                 FROM station_outfitting) AS module_offers,
              (SELECT COALESCE(SUM(jsonb_array_length(ships)), 0)
                 FROM station_shipyards) AS ship_offers,
              (SELECT COUNT(*) FROM state_bgs_snapshots
                 WHERE observed_at >= NOW() - INTERVAL '24 hours')
                   AS state_bgs_snapshots,
              (SELECT COUNT(*) FROM state_signals
                 WHERE expires_at > NOW()) AS state_signals
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


@app.get("/v1/sync/station-offers")
def sync_station_offers(
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> dict:
    """Return a resumable stream of complete outfitting and shipyard lists."""
    cursor_at, cursor_kind, cursor_market_id = _decode_offer_cursor(cursor)
    with connection() as conn:
        rows = conn.execute(
            """
            WITH current_offers AS (
                SELECT updated_at AS sync_at, 'OUTFITTING'::text AS kind,
                       market_id, system_name, station_name,
                       modules AS items, horizons, odyssey, observed_at,
                       received_at, source
                FROM station_outfitting
                UNION ALL
                SELECT updated_at AS sync_at, 'SHIPYARD'::text AS kind,
                       market_id, system_name, station_name,
                       ships AS items, horizons, odyssey, observed_at,
                       received_at, source
                FROM station_shipyards
            )
            SELECT o.sync_at AS "syncAt", o.kind,
                   o.market_id AS "marketId", o.system_name AS system,
                   o.station_name AS station, o.items, o.horizons, o.odyssey,
                   o.observed_at AS "observedAt",
                   o.received_at AS "receivedAt", o.source,
                   s.system_address AS "systemAddress",
                   s.station_type AS "stationType",
                   s.landing_pad_size AS "landingPadSize",
                   s.distance_to_arrival_ls AS "distanceToArrivalLs",
                   s.services, sy.x, sy.y, sy.z
            FROM current_offers o
            LEFT JOIN stations s ON s.market_id = o.market_id
            LEFT JOIN systems sy ON LOWER(sy.name) = LOWER(o.system_name)
            WHERE (o.sync_at, o.kind, o.market_id) > (%s, %s, %s)
            ORDER BY o.sync_at, o.kind, o.market_id
            LIMIT %s
            """,
            (cursor_at, cursor_kind, cursor_market_id, limit + 1),
        ).fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = str(cursor or "")
    if page:
        last = page[-1]
        next_cursor = _encode_offer_cursor(
            last["syncAt"], last["kind"], last["marketId"]
        )
    return {
        "generatedAt": _now(),
        "results": page,
        "nextCursor": next_cursor,
        "hasMore": has_more,
    }


@app.get("/v1/station-offers/search")
def search_station_offers(
    module: Annotated[str | None, Query(min_length=2, max_length=160)] = None,
    ship: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    system: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict:
    if not module and not ship:
        raise HTTPException(
            status_code=400, detail="A module or ship identifier is required"
        )
    normalized_module = module.strip().casefold() if module else ""
    normalized_ship = ship.strip().casefold() if ship else ""
    clauses = []
    values: list[object] = []
    if normalized_module:
        clauses.append("o.modules @> %s::jsonb")
        values.append(json.dumps([normalized_module]))
    if normalized_ship:
        clauses.append("y.ships @> %s::jsonb")
        values.append(json.dumps([normalized_ship]))
    if system:
        clauses.append("LOWER(COALESCE(o.system_name, y.system_name)) = LOWER(%s)")
        values.append(system.strip())
    values.append(limit)
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT COALESCE(o.market_id, y.market_id) AS "marketId",
                   COALESCE(o.system_name, y.system_name) AS system,
                   COALESCE(o.station_name, y.station_name) AS station,
                   st.station_type AS "stationType",
                   st.landing_pad_size AS "landingPadSize",
                   st.distance_to_arrival_ls AS "distanceToArrivalLs",
                   st.services, sy.x, sy.y, sy.z,
                   o.observed_at AS "outfittingObservedAt",
                   y.observed_at AS "shipyardObservedAt"
            FROM station_outfitting o
            FULL OUTER JOIN station_shipyards y ON y.market_id = o.market_id
            LEFT JOIN stations st
              ON st.market_id = COALESCE(o.market_id, y.market_id)
            LEFT JOIN systems sy
              ON LOWER(sy.name) = LOWER(COALESCE(o.system_name, y.system_name))
            WHERE {' AND '.join(clauses)}
            ORDER BY GREATEST(
                COALESCE(o.observed_at, '-infinity'::timestamptz),
                COALESCE(y.observed_at, '-infinity'::timestamptz)
            ) DESC
            LIMIT %s
            """,
            values,
        ).fetchall()
    return {
        "generatedAt": _now(),
        "query": {
            "module": normalized_module or None,
            "ship": normalized_ship or None,
        },
        "results": rows,
    }


@app.get("/v1/sync/state-finds")
def sync_state_finds(
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> dict:
    """Return current public BGS snapshots and unexpired signal sightings."""
    cursor_at, cursor_kind, cursor_identity = _decode_state_cursor(cursor)
    with connection() as conn:
        rows = conn.execute(
            """
            WITH current_state AS (
                SELECT updated_at AS sync_at, 'BGS'::text AS kind,
                       identity, snapshot AS payload
                FROM state_bgs_snapshots
                WHERE observed_at >= NOW() - INTERVAL '24 hours'
                UNION ALL
                SELECT updated_at AS sync_at, 'SIGNAL'::text AS kind,
                       identity, observation AS payload
                FROM state_signals
                WHERE expires_at > NOW()
            )
            SELECT sync_at AS "syncAt", kind, identity, payload
            FROM current_state
            WHERE (sync_at, kind, identity) > (%s, %s, %s)
            ORDER BY sync_at, kind, identity
            LIMIT %s
            """,
            (cursor_at, cursor_kind, cursor_identity, limit + 1),
        ).fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    results = []
    for row in page:
        item = {
            "kind": row["kind"],
            "identity": row["identity"],
            "syncAt": row["syncAt"],
        }
        item["snapshot" if row["kind"] == "BGS" else "row"] = row["payload"]
        results.append(item)
    next_cursor = str(cursor or "")
    if page:
        last = page[-1]
        next_cursor = _encode_state_cursor(
            last["syncAt"], last["kind"], last["identity"]
        )
    return {
        "generatedAt": _now(),
        "results": results,
        "nextCursor": next_cursor,
        "hasMore": has_more,
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


@app.get("/v1/sync/markets")
def sync_markets(
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    commodities: Annotated[str | None, Query(max_length=2048)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> dict:
    """Return a resumable stream of changed market and station facts.

    The cursor advances over the newest of a market or its station metadata.
    A station update therefore enriches retained market rows even when the
    commodity price itself has not changed.
    """
    cursor_at, cursor_market_id, cursor_commodity = _decode_market_cursor(
        cursor
    )
    clauses = [
        "(sync_at, market_id, commodity) > (%s, %s, %s)",
    ]
    values: list[object] = [
        cursor_at, cursor_market_id, cursor_commodity,
    ]
    requested = sorted({
        item.strip().casefold()
        for item in str(commodities or "").split(",")
        if item.strip()
    })
    if requested:
        if len(requested) > 100:
            raise HTTPException(
                status_code=400, detail="Too many requested commodities",
            )
        clauses.append("commodity = ANY(%s)")
        values.append(requested)
    values.append(limit + 1)
    with connection() as conn:
        rows = conn.execute(
            f"""
            WITH changed AS (
                SELECT m.market_id, m.commodity,
                       COALESCE(NULLIF(st.station_name, ''), m.station_name)
                           AS station_name,
                       COALESCE(NULLIF(st.system_name, ''), m.system_name)
                           AS system_name,
                       m.mean_price, m.buy_price, m.stock, m.stock_bracket,
                       m.sell_price, m.demand, m.demand_bracket,
                       m.status_flags, m.observed_at, m.received_at,
                       s.x, s.y, s.z, m.source,
                       st.station_type, st.system_address,
                       st.landing_pad_size, st.distance_to_arrival_ls,
                       st.services, st.economies, st.primary_economy,
                       st.government, st.controlling_faction,
                       st.fleet_carrier, st.carrier_docking_access,
                       st.prohibited,
                       GREATEST(
                           m.received_at,
                           COALESCE(st.received_at, m.received_at)
                       ) AS sync_at
                FROM markets m
                LEFT JOIN systems s
                  ON LOWER(s.name) = LOWER(m.system_name)
                LEFT JOIN stations st ON st.market_id = m.market_id
            )
            SELECT market_id AS "marketId", commodity,
                   station_name AS station, system_name AS system,
                   mean_price AS "meanPrice", buy_price AS "buyPrice",
                   stock, stock_bracket AS "stockBracket",
                   sell_price AS "sellPrice", demand,
                   demand_bracket AS "demandBracket",
                   status_flags AS "statusFlags",
                   observed_at AS "observedAt", received_at AS "receivedAt",
                   x, y, z, source,
                   station_type AS "stationType",
                   system_address AS "systemAddress",
                   landing_pad_size AS "landingPadSize",
                   distance_to_arrival_ls AS "distanceToArrivalLs",
                   services, economies, primary_economy AS "primaryEconomy",
                   government, controlling_faction AS "controllingFaction",
                   fleet_carrier AS "fleetCarrier",
                   carrier_docking_access AS "carrierDockingAccess",
                   prohibited, sync_at AS "syncAt"
            FROM changed
            WHERE {' AND '.join(clauses)}
            ORDER BY sync_at, market_id, commodity
            LIMIT %s
            """,
            values,
        ).fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = str(cursor or "")
    if page:
        last = page[-1]
        next_cursor = _encode_market_cursor(
            last["syncAt"], last["marketId"], last["commodity"],
        )
    return {
        "generatedAt": _now(),
        "results": page,
        "nextCursor": next_cursor,
        "hasMore": has_more,
    }


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
                   COALESCE(NULLIF(st.station_name, ''), m.station_name)
                       AS station,
                   COALESCE(NULLIF(st.system_name, ''), m.system_name)
                       AS system,
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

