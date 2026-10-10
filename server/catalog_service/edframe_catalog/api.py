from __future__ import annotations

import base64
import binascii
from contextlib import asynccontextmanager, ExitStack
from datetime import datetime, timedelta, timezone
import json
import os
import threading
import time
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import ORJSONResponse
from psycopg.errors import UndefinedTable, QueryCanceled
from ed_companion.navigation.mining_commodities import MINING_COMMODITIES, mining_commodity_id

from . import __version__
from .merit_markets import MeritMarketQuery, search_merit_markets
from .mining_metadata import enrich_ring_metadata
from .mining_revision import mining_revision, static_revision
from .mining_region import regional_page_limit, regional_box_clause
from .mining_pages import (
    configured_pages, decode_cursor, FrozenUnavailable, FrozenExpired,
    MAX_ROWS as MINING_FROZEN_MAX_ROWS, CHUNK_ROWS as MINING_FROZEN_CHUNK_ROWS,
)
from .mining_overlaps import (
    attach_overlap_reports, catalog as overlap_catalog, overlap_site_identities,
    community_reference_candidates,
)
from .database import (
    connection,
    ensure_schema,
    upsert_station_offer_batch,
    upsert_yield_observations,
    upsert_state_find_batch,
    upsert_signal_systems,
)
from .projection import (
    project_station_offer_observations,
    project_yield_observations,
    project_state_signals,
)


# Explicit operator gate: install/backfill transactional markers before
# enabling. Ordinary deployments retain the legacy regional path by default.
MINING_SNAPSHOT_PROTOCOL_ENABLED = os.environ.get("EDFRAME_MINING_SNAPSHOT_PROTOCOL", "0") == "1"


def _snapshot_revision(conn, query):
    try:
        return mining_revision(conn, query)
    except (ValueError, UndefinedTable) as exc:
        # Never fall back to expensive content proofs or accept an unverified
        # cache. The client can use fresh legacy pages until installation.
        raise HTTPException(status_code=503, detail="Mining revision markers unavailable") from exc


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

_yield_rate_lock = threading.Lock()
_yield_rate_buckets: dict[str, list[float]] = {}
_signal_rate_lock = threading.Lock()
_signal_rate_buckets: dict[str, list[float]] = {}
_station_offer_rate_lock = threading.Lock()
_station_offer_rate_buckets: dict[str, list[float]] = {}
_powerplay_rate_lock = threading.Lock()
_powerplay_rate_buckets: dict[str, list[float]] = {}
_merit_rate_lock = threading.Lock()
_merit_rate_buckets: dict[str, list[float]] = {}


def _percent(part: int, whole: int) -> float:
    return round((part * 100.0 / whole), 1) if whole else 0.0


def _resolved_ship_offer(
    offer: dict | None, *, reference_price: int | None,
    reference_samples: int = 0, evidence: object = None,
) -> dict | None:
    """Describe an exact, inferred or global-default shipyard price."""
    if not isinstance(offer, dict):
        return offer
    result = dict(offer)
    if isinstance(reference_price, int) and reference_price > 0:
        result["referencePrice"] = reference_price
        result["referenceSamples"] = max(0, int(reference_samples or 0))
    exact = result.get("buyPrice")
    if isinstance(exact, int) and exact >= 0:
        result["priceType"] = "OBSERVED"
        result["priceConfidence"] = "OBSERVED"
        return result
    if not isinstance(reference_price, int) or reference_price <= 0:
        result["priceType"] = "UNKNOWN"
        result["priceConfidence"] = "UNKNOWN"
        return result

    discounts = []
    for row in evidence if isinstance(evidence, list) else []:
        if not isinstance(row, dict):
            continue
        price = row.get("price")
        base = row.get("reference")
        if (
            not isinstance(price, int) or price <= 0
            or not isinstance(base, int) or base <= 0
        ):
            continue
        discount = round((1.0 - price / base) * 10_000)
        if -2_500 <= discount <= 5_000:
            discounts.append(int(discount))
    if discounts:
        ordered = sorted(discounts)
        discount_bps = ordered[(len(ordered) - 1) // 2]
        matching = sum(
            1 for value in discounts if abs(value - discount_bps) <= 25
        )
        result["buyPrice"] = max(0, (
            reference_price * (10_000 - discount_bps) + 5_000
        ) // 10_000)
        result["discountBps"] = discount_bps
        result["discountEvidence"] = matching
        result["priceType"] = "INFERRED"
        result["priceConfidence"] = (
            "CONFIRMED" if matching >= 2 else "PROVISIONAL"
        )
        result["priceSource"] = "ED-Frame inferred station discount"
        return result

    # Keep the global hull value as explicitly separate metadata.  Returning
    # it as buyPrice would falsely present the same number as a purchase price
    # at every station that merely reported ship availability.
    result["priceType"] = "UNKNOWN"
    result["priceConfidence"] = "UNKNOWN"
    return result


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
        "stationOfferObservations": "/v1/station-offers/observations",
        "miningMeritMarkets": "/v1/mining/merit-markets",
        "stateFindSync": "/v1/sync/state-finds",
        "yieldObservations": "/v1/yields/observations",
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
              (SELECT COUNT(*) FROM mining_yield_samples) AS yield_samples,
              (SELECT COUNT(DISTINCT site_identity)
                 FROM mining_yield_samples) AS measured_sites,
              (SELECT COUNT(DISTINCT commodity)
                 FROM mining_yield_materials) AS measured_commodities,
              (SELECT COUNT(*) FROM station_outfitting) AS outfitting_stations,
              (SELECT COUNT(*) FROM station_shipyards) AS shipyard_stations,
              (SELECT COUNT(*) FROM station_module_offers) AS module_offers,
              (SELECT COUNT(*) FROM station_module_offers
                WHERE buy_price IS NOT NULL) AS priced_module_offers,
              (SELECT COUNT(*) FROM station_ship_offers) AS ship_offers,
              (SELECT COUNT(*) FROM station_ship_offers
                WHERE buy_price IS NOT NULL) AS priced_ship_offers,
              (SELECT COUNT(*) FROM module_catalog) AS catalog_modules,
              (SELECT COUNT(*) FROM ship_catalog) AS catalog_ships,
              (SELECT COUNT(*) FROM state_bgs_snapshots
                 WHERE observed_at >= NOW() - INTERVAL '24 hours')
                   AS state_bgs_snapshots,
              (SELECT COUNT(*) FROM state_signals
                 WHERE expires_at > NOW()) AS state_signals,
              (SELECT COUNT(*) FROM state_signal_sightings
                 WHERE observed_at >= NOW() - INTERVAL '24 hours') AS state_signal_sightings
            """
        ).fetchone()
        state = conn.execute(
            "SELECT * FROM collector_state WHERE source = 'EDDN'"
        ).fetchone()
        schema_metrics = conn.execute(
            """
            SELECT schema,
                   SUM(messages_total)::BIGINT AS messages,
                   SUM(used_messages_total)::BIGINT AS "usedMessages",
                   SUM(projected_rows_total)::BIGINT AS "projectedRows",
                   SUM(ignored_messages_total)::BIGINT AS "ignoredMessages",
                   SUM(errors_total)::BIGINT AS errors,
                   SUM(bytes_total)::BIGINT AS bytes,
                   MAX(last_received_at) AS "lastReceivedAt"
            FROM collector_schema_metrics_hourly
            WHERE bucket_start >= date_trunc('hour', NOW())
                - INTERVAL '23 hours'
            GROUP BY schema
            ORDER BY messages DESC, schema
            """
        ).fetchall()
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
    schema_rows = []
    for source in schema_metrics:
        row = dict(source)
        messages = int(row["messages"] or 0)
        used = int(row["usedMessages"] or 0)
        ignored = int(row["ignoredMessages"] or 0)
        errors = int(row["errors"] or 0)
        if used and (ignored or errors):
            usage_status = "PARTIAL"
        elif used:
            usage_status = "USED"
        elif errors and errors >= messages:
            usage_status = "ERROR"
        else:
            usage_status = "NOT_PROJECTED"
        row["usageStatus"] = usage_status
        row["usedPercent"] = _percent(used, messages)
        schema_rows.append(row)
    schema_totals = {
        key: sum(int(row[key] or 0) for row in schema_rows)
        for key in (
            "messages", "usedMessages", "projectedRows",
            "ignoredMessages", "errors", "bytes",
        )
    }
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
        "collector24h": {
            **schema_totals,
            "usedPercent": _percent(
                schema_totals["usedMessages"], schema_totals["messages"]
            ),
            "schemas": schema_rows,
        },
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
        clauses.append("mo.module_symbol = %s")
        values.append(normalized_module)
    if normalized_ship:
        clauses.append("so.ship_symbol = %s")
        values.append(normalized_ship)
    if normalized_module and normalized_ship:
        offer_tables = """
            FROM station_module_offers mo
            JOIN station_ship_offers so ON so.market_id = mo.market_id
        """
    elif normalized_module:
        offer_tables = """
            FROM station_module_offers mo
            LEFT JOIN station_ship_offers so ON FALSE
        """
    else:
        offer_tables = """
            FROM station_ship_offers so
            LEFT JOIN station_module_offers mo ON FALSE
        """
    if system:
        clauses.append(
            "LOWER(COALESCE(o.system_name, y.system_name, st.system_name)) "
            "= LOWER(%s)"
        )
        values.append(system.strip())
    values.append(limit)
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT COALESCE(mo.market_id, so.market_id) AS "marketId",
                   COALESCE(o.system_name, y.system_name, st.system_name) AS system,
                   COALESCE(o.station_name, y.station_name, st.station_name) AS station,
                   st.station_type AS "stationType",
                   st.landing_pad_size AS "landingPadSize",
                   st.distance_to_arrival_ls AS "distanceToArrivalLs",
                   st.services, sy.x, sy.y, sy.z,
                   CASE WHEN mo.module_symbol IS NULL THEN NULL::jsonb ELSE
                     jsonb_strip_nulls(jsonb_build_object(
                       'name', mo.module_symbol, 'id', mo.module_id,
                       'buyPrice', mo.buy_price,
                       'buyMercCoinsPrice', mo.buy_merc_coins_price,
                       'priceObservedAt', mo.price_observed_at,
                       'priceSource', mo.price_source
                     )) END AS "moduleOffer",
                   CASE WHEN so.ship_symbol IS NULL THEN NULL::jsonb ELSE
                     jsonb_strip_nulls(jsonb_build_object(
                       'name', so.ship_symbol, 'id', so.ship_id,
                       'buyPrice', so.buy_price,
                       'priceObservedAt', so.price_observed_at,
                       'priceSource', so.price_source
                     )) END AS "shipOffer",
                   sc.reference_price AS "shipReferencePrice",
                   sc.reference_price_samples AS "shipReferenceSamples",
                   ship_price_evidence.rows AS "shipPriceEvidence",
                   mo.observed_at AS "outfittingObservedAt",
                   so.observed_at AS "shipyardObservedAt"
            {offer_tables}
            LEFT JOIN station_outfitting o ON o.market_id = mo.market_id
            LEFT JOIN station_shipyards y ON y.market_id = so.market_id
            LEFT JOIN stations st
              ON st.market_id = COALESCE(mo.market_id, so.market_id)
            LEFT JOIN systems sy
              ON LOWER(sy.name) = LOWER(
                   COALESCE(o.system_name, y.system_name, st.system_name)
                 )
            LEFT JOIN ship_catalog sc ON sc.symbol = so.ship_symbol
            LEFT JOIN LATERAL (
                SELECT jsonb_agg(jsonb_build_object(
                           'price', evidence.buy_price,
                           'reference', evidence_catalog.reference_price
                       )) AS rows
                FROM station_ship_offers evidence
                JOIN ship_catalog evidence_catalog
                  ON evidence_catalog.symbol = evidence.ship_symbol
                WHERE evidence.market_id = so.market_id
                  AND evidence.buy_price IS NOT NULL
                  AND evidence_catalog.reference_price IS NOT NULL
            ) ship_price_evidence ON so.ship_symbol IS NOT NULL
            WHERE {' AND '.join(clauses)}
            ORDER BY GREATEST(
                COALESCE(mo.observed_at, '-infinity'::timestamptz),
                COALESCE(so.observed_at, '-infinity'::timestamptz)
            ) DESC
            LIMIT %s
            """,
            values,
        ).fetchall()
    results = []
    for source in rows:
        row = dict(source)
        row["shipOffer"] = _resolved_ship_offer(
            row.get("shipOffer"),
            reference_price=row.pop("shipReferencePrice", None),
            reference_samples=row.pop("shipReferenceSamples", 0),
            evidence=row.pop("shipPriceEvidence", None),
        )
        results.append(row)
    return {
        "generatedAt": _now(),
        "query": {
            "module": normalized_module or None,
            "ship": normalized_ship or None,
        },
        "results": results,
    }


@app.get("/v1/catalog/modules/suggest")
def suggest_modules(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict:
    term = q.strip().casefold()
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT c.symbol, c.display_name AS "displayName",
                   c.module_class AS "class", c.rating,
                   c.size_rating AS "sizeRating",
                   c.power_draw_mw AS "powerDrawMw", c.source,
                   COUNT(o.market_id) AS "knownStations",
                   COUNT(o.buy_price) AS "pricedStations",
                   MIN(o.buy_price) AS "lowestObservedPrice"
            FROM module_catalog c
            LEFT JOIN station_module_offers o
              ON o.module_symbol = c.symbol
            WHERE c.symbol LIKE %s OR LOWER(c.display_name) LIKE %s
            GROUP BY c.symbol, c.display_name, c.module_class, c.rating,
                     c.size_rating, c.power_draw_mw, c.source
            ORDER BY CASE WHEN c.symbol LIKE %s
                           OR LOWER(c.display_name) LIKE %s THEN 0 ELSE 1 END,
                     c.display_name, c.size_rating, c.symbol
            LIMIT %s
            """,
            (f"%{term}%", f"%{term}%", f"{term}%", f"{term}%", limit),
        ).fetchall()
    return {"generatedAt": _now(), "query": term, "results": rows}


@app.get("/v1/catalog/ships/suggest")
def suggest_ships(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict:
    term = q.strip().casefold()
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT c.symbol, c.display_name AS "displayName",
                   c.manufacturer, c.ship_size AS size,
                   c.maximum_speed AS "maximumSpeed",
                   c.boost_speed AS boost, c.specifications, c.source,
                   c.reference_price AS "referencePrice",
                   c.reference_price_observed_at AS "referencePriceObservedAt",
                   c.reference_price_source AS "referencePriceSource",
                   c.reference_price_samples AS "referencePriceSamples",
                   COUNT(o.market_id) AS "knownStations",
                   COUNT(o.buy_price) AS "pricedStations",
                   MIN(o.buy_price) AS "lowestObservedPrice"
            FROM ship_catalog c
            LEFT JOIN station_ship_offers o ON o.ship_symbol = c.symbol
            WHERE c.symbol LIKE %s OR LOWER(c.display_name) LIKE %s
            GROUP BY c.symbol, c.display_name, c.manufacturer, c.ship_size,
                     c.maximum_speed, c.boost_speed, c.specifications, c.source,
                     c.reference_price, c.reference_price_observed_at,
                     c.reference_price_source, c.reference_price_samples
            ORDER BY CASE WHEN c.symbol LIKE %s
                           OR LOWER(c.display_name) LIKE %s THEN 0 ELSE 1 END,
                     c.display_name, c.symbol
            LIMIT %s
            """,
            (f"%{term}%", f"%{term}%", f"{term}%", f"{term}%", limit),
        ).fetchall()
    return {"generatedAt": _now(), "query": term, "results": rows}


@app.post("/v1/station-offers/observations")
def receive_station_offer_observations(
    request: Request, payload: dict,
) -> dict:
    """Accept anonymous, exact prices observed in local station snapshots."""
    observations = payload.get("observations")
    if not isinstance(observations, list) or len(observations) > 20:
        raise HTTPException(
            status_code=422,
            detail="observations must be a list containing at most 20 items",
        )
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0]
    remote = forwarded.strip() or (
        request.client.host if request.client else "unknown"
    )
    now = time.monotonic()
    with _station_offer_rate_lock:
        if len(_station_offer_rate_buckets) > 4096:
            _station_offer_rate_buckets.clear()
        recent = [
            stamp for stamp in _station_offer_rate_buckets.get(remote, [])
            if now - stamp < 60.0
        ]
        if len(recent) >= 12:
            raise HTTPException(
                status_code=429,
                detail="station offer observation request budget exceeded",
            )
        recent.append(now)
        _station_offer_rate_buckets[remote] = recent
    received_at = _now()
    projected = project_station_offer_observations(payload, received_at)
    if observations and not projected:
        raise HTTPException(
            status_code=422,
            detail="no valid station offer observations in request",
        )
    with connection() as conn:
        accepted = upsert_station_offer_batch(conn, projected)
    return {
        "receivedAt": received_at,
        "accepted": accepted,
        "rejected": len(observations) - accepted,
    }


@app.get("/v1/sync/state-finds")
def sync_state_finds(
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    x: Annotated[float | None, Query(ge=-1000000, le=1000000)] = None,
    y: Annotated[float | None, Query(ge=-1000000, le=1000000)] = None,
    z: Annotated[float | None, Query(ge=-1000000, le=1000000)] = None,
    max_distance: Annotated[float, Query(gt=0, le=2000)] = 250,
) -> dict:
    """Return current public BGS snapshots and unexpired signal sightings."""
    cursor_at, cursor_kind, cursor_identity = _decode_state_cursor(cursor)
    regional = any(value is not None for value in (x, y, z))
    if regional and any(value is None for value in (x, y, z)):
        raise HTTPException(status_code=422, detail="x, y and z must be supplied together")
    region_clause = ""
    values = [cursor_at, cursor_kind, cursor_identity]
    if regional:
        # EXISTS avoids duplicates even when multiple names share an address.
        # Missing coordinates are not silently treated as zero-distance systems.
        region_clause = """
            AND EXISTS (
                SELECT 1 FROM systems s
                WHERE ((current_state.system_address IS NOT NULL
                        AND s.system_address = current_state.system_address)
                       OR (current_state.system_address IS NULL
                           AND LOWER(s.name) = LOWER(current_state.system_name)))
                  AND POWER(s.x - %s, 2) + POWER(s.y - %s, 2)
                      + POWER(s.z - %s, 2) <= POWER(%s, 2)
            )
        """
        values.extend((x, y, z, max_distance))
    values.append(limit + 1)
    with connection() as conn:
        rows = conn.execute(
            f"""
            WITH current_state AS (
                SELECT updated_at AS sync_at, 'BGS'::text AS kind,
                       identity, snapshot AS payload, system_address, system_name
                FROM state_bgs_snapshots
                WHERE observed_at >= NOW() - INTERVAL '24 hours'
                UNION ALL
                SELECT updated_at AS sync_at, 'SIGNAL'::text AS kind,
                       identity, observation AS payload, system_address, system_name
                FROM state_signals
                WHERE expires_at > NOW()
                UNION ALL
                SELECT updated_at AS sync_at, 'SIGHTING'::text AS kind,
                       identity, observation AS payload, system_address, system_name
                FROM state_signal_sightings
                WHERE observed_at >= NOW() - INTERVAL '24 hours'
            )
            SELECT sync_at AS "syncAt", kind, identity, payload
            FROM current_state
            WHERE (sync_at, kind, identity) > (%s, %s, %s)
            {region_clause}
            ORDER BY sync_at, kind, identity
            LIMIT %s
            """,
            tuple(values),
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
        "region": {"origin": [x, y, z], "radiusLy": max_distance} if regional else None,
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


@app.post("/v1/state-signals/observations")
def receive_state_signal_observations(request: Request, payload: dict) -> dict:
    """Opt-in public Journal signals, strictly allowlisted and rate bounded."""
    from ed_companion.navigation.signal_sharing import public_signal_observations
    observations = payload.get("observations")
    if not isinstance(observations, list) or not 1 <= len(observations) <= 100:
        raise HTTPException(status_code=422, detail="expected 1 to 100 observations")
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0]
    remote = forwarded.strip() or (request.client.host if request.client else "unknown")
    now = time.monotonic()
    with _signal_rate_lock:
        recent = [stamp for stamp in _signal_rate_buckets.get(remote, []) if now - stamp < 60]
        if len(recent) >= 6:
            raise HTTPException(status_code=429, detail="signal request budget exceeded")
        if len(_signal_rate_buckets) > 4096:
            _signal_rate_buckets.clear()
        _signal_rate_buckets[remote] = recent + [now]
    received = _now()
    rows = public_signal_observations(observations, now=datetime.now(timezone.utc), local_only=False)
    projected = []
    for row in rows:
        signal = {"timestamp": row["signal_timestamp"], "TimeRemaining": row["time_remaining"],
                  "SpawningFaction": row["faction"], "SpawningState": row["state"]}
        if row["find_type"] == "HGE":
            signal["USSType"] = "$USS_Type_VeryValuableSalvage;"
        else:
            signal["SignalName"] = {"CONFLICT_ZONE": "Conflict Zone",
                                    "SEEKING_MEDS": "$USS_Type_SeekingMeds;",
                                    "SEEKING_FOODS": "$USS_Type_SeekingFoods;"}[row["find_type"]]
        frame = {"$schemaRef": "https://eddn.edcd.io/schemas/fsssignaldiscovered/1",
                 "message": {"StarSystem": row["system"], "SystemAddress": row["system_address"],
                             "StarPos": row["star_pos"], "signals": [signal]}}
        for item in project_state_signals(frame, received):
            observation = json.loads(item["observation"])
            observation["source"] = "ED-Frame community Journal"
            observation["lifetime_verified"] = True
            item["observation"] = json.dumps(observation)
            projected.append(item)
    if not projected:
        raise HTTPException(status_code=422, detail="no valid unexpired public signals")
    with connection() as conn:
        upsert_signal_systems(conn, projected)
        accepted = upsert_state_find_batch(conn, [], projected)
    return {"receivedAt": received, "accepted": accepted, "rejected": len(observations)-accepted}


@app.post("/v1/yields/observations")
def receive_yield_observations(
    request: Request, payload: dict,
) -> dict:
    """Accept privacy-minimised, idempotent ProspectedAsteroid samples."""
    observations = payload.get("observations")
    if not isinstance(observations, list) or len(observations) > 100:
        raise HTTPException(
            status_code=422,
            detail="observations must be a list containing at most 100 items",
        )
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0]
    remote = forwarded.strip() or (
        request.client.host if request.client else "unknown"
    )
    now = time.monotonic()
    with _yield_rate_lock:
        if len(_yield_rate_buckets) > 4096:
            _yield_rate_buckets.clear()
        recent = [
            stamp for stamp in _yield_rate_buckets.get(remote, [])
            if now - stamp < 60.0
        ]
        if len(recent) >= 12:
            raise HTTPException(
                status_code=429,
                detail="yield observation request budget exceeded",
            )
        recent.append(now)
        _yield_rate_buckets[remote] = recent
    received_at = _now()
    projected = project_yield_observations(payload, received_at)
    if observations and not projected:
        raise HTTPException(
            status_code=422,
            detail="no valid yield observations in request",
        )
    with connection() as conn:
        accepted = upsert_yield_observations(conn, projected)
    return {
        "receivedAt": received_at,
        "accepted": accepted,
        "rejected": len(observations) - accepted,
    }


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


@app.post('/v1/mining/merit-markets')
def mining_merit_markets(request: Request, query: MeritMarketQuery) -> dict:
    remote = (request.headers.get('x-forwarded-for', '').split(',', 1)[0].strip()
              or (request.client.host if request.client else 'unknown'))
    now = time.monotonic()
    with _merit_rate_lock:
        if len(_merit_rate_buckets) > 4096:
            _merit_rate_buckets.clear()
        recent = [stamp for stamp in _merit_rate_buckets.get(remote, []) if now - stamp < 60]
        if len(recent) >= 16:
            raise HTTPException(status_code=429, detail='Mining market batch budget exceeded')
        _merit_rate_buckets[remote] = [*recent, now]
    try:
        return {'generatedAt': _now(), **search_merit_markets(query)}
    except QueryCanceled as exc:
        raise HTTPException(status_code=503, detail='Mining market batch timed out') from exc


@app.get("/v1/catalog/commodities")
def catalog_commodities() -> dict:
    # Loose index scan: one indexed step per symbol, not DISTINCT over millions
    # of market rows. Includes new/special commodities without a static whitelist.
    with connection() as conn:
        rows = conn.execute("""
            WITH RECURSIVE names AS (
                (SELECT commodity FROM markets ORDER BY commodity LIMIT 1)
                UNION ALL
                SELECT (SELECT commodity FROM markets WHERE commodity > names.commodity
                        ORDER BY commodity LIMIT 1)
                FROM names WHERE names.commodity IS NOT NULL
            )
            SELECT commodity FROM names WHERE commodity IS NOT NULL
        """).fetchall()
    return {"generatedAt": _now(), "results": [row["commodity"] for row in rows]}


@app.get("/v1/markets/commodity-offers")
def commodity_offers(
    commodity: Annotated[str, Query(min_length=2, max_length=80)],
    direction: Annotated[str, Query(pattern="^(BUY|SELL)$")],
    x: Annotated[float, Query(ge=-1000000, le=1000000)],
    y: Annotated[float, Query(ge=-1000000, le=1000000)],
    z: Annotated[float, Query(ge=-1000000, le=1000000)],
    max_distance: Annotated[float, Query(gt=0, le=2000)] = 100,
    min_quantity: Annotated[int, Query(ge=1, le=1000000)] = 1,
    max_age_hours: Annotated[int, Query(ge=1, le=2160)] = 24,
    landing_pad: Annotated[str | None, Query(pattern="^(S|M|L)$")] = None,
    exclude_fleet_carriers: bool = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    commodities: Annotated[str | None, Query(max_length=12000)] = None,
) -> dict:
    if direction not in {"BUY", "SELL"}:
        raise HTTPException(status_code=422, detail="direction must be BUY or SELL")
    symbols = sorted(set(commodities.strip().lower().split(","))) if commodities else None
    if symbols is not None and (len(symbols) > 200 or any(
            not 2 <= len(symbol) <= 80 or not all(c.isalnum() or c == "_" for c in symbol)
            for symbol in symbols)):
        raise HTTPException(status_code=422, detail="Invalid commodity group")
    price, quantity, ordering = (
        ("buy_price", "stock", "ASC") if direction == "BUY"
        else ("sell_price", "demand", "DESC")
    )
    clauses = [
        "m.commodity = ANY(%s)" if symbols else "m.commodity = LOWER(%s)", f"m.{price} > 0", f"m.{quantity} >= %s",
        "m.observed_at >= NOW() - (%s * INTERVAL '1 hour')",
        "POWER(s.x - %s, 2) + POWER(s.y - %s, 2) + POWER(s.z - %s, 2) <= POWER(%s, 2)",
    ]
    values = [x, y, z, symbols or commodity.strip(), min_quantity, max_age_hours, x, y, z, max_distance]
    if landing_pad:
        clauses.append("st.landing_pad_size = ANY(%s)")
        values.append({"S": ["S", "M", "L"], "M": ["M", "L"], "L": ["L"]}[landing_pad])
    if exclude_fleet_carriers:
        clauses.append("st.fleet_carrier IS NOT TRUE")
    values.append(limit + 1)
    with connection() as conn:
        rows = conn.execute(f"""
            SELECT m.market_id AS "marketId", m.commodity,
                   COALESCE(NULLIF(st.station_name, ''), m.station_name) AS station,
                   COALESCE(NULLIF(st.system_name, ''), m.system_name) AS system,
                   m.{price} AS price, m.{quantity} AS quantity,
                   m.buy_price AS "buyPrice", m.sell_price AS "sellPrice", m.mean_price AS "meanPrice",
                   m.stock, m.demand, m.observed_at AS "observedAt", m.source,
                   st.landing_pad_size AS "landingPadSize",
                   st.distance_to_arrival_ls AS "distanceToArrivalLs",
                   st.station_type AS "stationType", st.fleet_carrier AS "fleetCarrier",
                   st.carrier_docking_access AS "carrierDockingAccess", st.prohibited,
                   SQRT(POWER(s.x - %s, 2) + POWER(s.y - %s, 2) + POWER(s.z - %s, 2)) AS "distanceLy"
            FROM markets m LEFT JOIN stations st ON st.market_id = m.market_id
            JOIN LATERAL (
                SELECT sy.x, sy.y, sy.z FROM systems sy
                WHERE ((st.system_address IS NOT NULL AND sy.system_address = st.system_address)
                       OR (st.system_address IS NULL AND LOWER(sy.name) = LOWER(m.system_name)))
                  AND sy.x IS NOT NULL AND sy.y IS NOT NULL AND sy.z IS NOT NULL
                ORDER BY sy.observed_at DESC NULLS LAST, sy.name LIMIT 1
            ) s ON TRUE
            WHERE {' AND '.join(clauses)}
            ORDER BY m.{price} {ordering}, "distanceLy", st.distance_to_arrival_ls ASC NULLS LAST, m.market_id
            LIMIT %s
        """, tuple(values)).fetchall()
    return {
        "generatedAt": _now(), "results": rows[:limit], "hasMore": len(rows) > limit,
        "direction": direction, "commodity": commodity.strip().lower(),
        "commodities": symbols,
        "region": {"origin": [x, y, z], "radiusLy": max_distance},
    }


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


@app.get("/v1/stations/nearby")
def nearby_station_services(
    x: Annotated[float, Query(ge=-1000000, le=1000000)],
    y: Annotated[float, Query(ge=-1000000, le=1000000)],
    z: Annotated[float, Query(ge=-1000000, le=1000000)],
    service: Annotated[str, Query(min_length=1, max_length=80)],
    max_distance: Annotated[float, Query(gt=0, le=2000)] = 100,
    landing_pad: Annotated[str | None, Query(pattern="^(S|M|L)$")] = None,
    exclude_fleet_carriers: bool = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict:
    clauses = [
        "POWER(s.x - %s, 2) + POWER(s.y - %s, 2) + POWER(s.z - %s, 2) <= POWER(%s, 2)",
        """EXISTS (SELECT 1 FROM jsonb_array_elements_text(
            COALESCE(st.services, '[]'::jsonb)) item WHERE LOWER(item) = LOWER(%s))""",
    ]
    values = [x, y, z, x, y, z, max_distance, service.strip()]
    if landing_pad:
        clauses.append("st.landing_pad_size = ANY(%s)")
        values.append({"S": ["S", "M", "L"], "M": ["M", "L"], "L": ["L"]}[landing_pad])
    if exclude_fleet_carriers:
        clauses.append("st.fleet_carrier IS NOT TRUE")
    values.append(limit + 1)
    with connection() as conn:
        rows = conn.execute(f"""
            SELECT st.market_id AS "marketId", st.system_name AS system,
                   st.station_name AS station, st.station_type AS "stationType",
                   st.landing_pad_size AS "landingPadSize",
                   st.distance_to_arrival_ls AS "distanceToArrivalLs",
                   st.services, st.fleet_carrier AS "fleetCarrier",
                   st.carrier_docking_access AS "carrierDockingAccess",
                   st.observed_at AS "observedAt", st.source,
                   SQRT(POWER(s.x - %s, 2) + POWER(s.y - %s, 2)
                        + POWER(s.z - %s, 2)) AS "distanceLy"
            FROM stations st
            JOIN LATERAL (
                SELECT sy.x, sy.y, sy.z FROM systems sy
                WHERE ((st.system_address IS NOT NULL AND sy.system_address = st.system_address)
                       OR (st.system_address IS NULL AND LOWER(sy.name) = LOWER(st.system_name)))
                  AND sy.x IS NOT NULL AND sy.y IS NOT NULL AND sy.z IS NOT NULL
                ORDER BY sy.observed_at DESC NULLS LAST, sy.name LIMIT 1
            ) s ON TRUE
            WHERE {' AND '.join(clauses)}
            ORDER BY "distanceLy", st.distance_to_arrival_ls ASC NULLS LAST, st.market_id
            LIMIT %s
        """, tuple(values)).fetchall()
    return {
        "generatedAt": _now(), "results": rows[:limit], "hasMore": len(rows) > limit,
        "region": {"origin": [x, y, z], "radiusLy": max_distance},
    }


@app.get("/v1/mining/powerplay/lookup")
def lookup_mining_powerplay(request: Request, system: Annotated[list[str], Query()]) -> dict:
    """Supplement at most six exact systems from the fixed public Spansh source."""
    from .powerplay_lookup import lookup_powerplay_systems
    names = list(dict.fromkeys(name.strip().casefold() for name in system))
    if not names or len(system) > 6 or any(not name or len(name) > 100 for name in names):
        raise HTTPException(status_code=400, detail="Expected 1 to 6 system names")
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0]
    remote = forwarded.strip() or (request.client.host if request.client else "unknown")
    now = time.monotonic()
    with _powerplay_rate_lock:
        if len(_powerplay_rate_buckets) > 4096:
            _powerplay_rate_buckets.clear()
        recent = [stamp for stamp in _powerplay_rate_buckets.get(remote, []) if now - stamp < 60]
        if len(recent) >= 6:
            raise HTTPException(status_code=429, detail="Powerplay lookup request budget exceeded")
        _powerplay_rate_buckets[remote] = [*recent, now]
    return lookup_powerplay_systems(names)


@app.get("/v1/mining/powerplay")
def search_mining_powerplay(
    x: float, y: float, z: float,
    max_distance: Annotated[float, Query(gt=0, le=2000)] = 250,
    max_age_hours: Annotated[int, Query(ge=1, le=168)] = 24,
    limit: Annotated[int, Query(ge=1, le=200)] = 200,
    cursor: Annotated[str | None, Query(max_length=1024)] = None,
    system: Annotated[list[str] | None, Query()] = None,
    regional_page_size: Annotated[int | None, Query(ge=1, le=1000)] = None,
    include_coverage: bool = False,
    power: Annotated[str | None, Query(min_length=3, max_length=100)] = None,
    goal: Annotated[str | None, Query(pattern='^(REINFORCE|UNDERMINE|ACQUIRE)$')] = None,
) -> dict:
    limit = regional_page_limit(limit, regional_page_size,
                                regional=system is None, maximum=1000)
    clauses = ["observed_at >= NOW() - (%s * INTERVAL '1 hour')"]
    values: list[object] = [max_age_hours]
    names = list(dict.fromkeys(name.strip().casefold() for name in system or []))
    if system is not None:
        if not names or len(system) > 200 or any(not name or len(name) > 100 for name in names):
            raise HTTPException(status_code=400, detail="Expected 1 to 200 system names")
        clauses.append("identity = ANY(%s)")
        values.append(names)
    else:
        clauses.append("POWER(x - %s, 2) + POWER(y - %s, 2) + POWER(z - %s, 2) <= POWER(%s, 2)")
        values.extend((x, y, z, max_distance))
        if power and goal:
            # Filter before pagination so unrelated Powers cannot exhaust the
            # regional budget and hide older, still current observations.
            if goal == 'UNDERMINE':
                condition = "LOWER(f->>'controllingPower') <> LOWER(%s) AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(COALESCE(f->'powers', '[]'::jsonb)) p WHERE LOWER(p) = LOWER(%s))"
                values.extend((power.strip(), power.strip()))
            else:
                condition = "LOWER(f->>'controllingPower') = LOWER(%s)"
                values.append(power.strip())
                if goal == 'ACQUIRE':
                    condition = '(' + condition + " OR f->>'powerState' = 'Unoccupied')"
            clauses.append('EXISTS (SELECT 1 FROM jsonb_array_elements(facts) f WHERE ' + condition + ')')
    if cursor:
        stamp, kind, identity = _decode_state_cursor(cursor)
        if kind != "mining-powerplay" or not identity:
            raise HTTPException(status_code=400, detail="Invalid Powerplay cursor")
        clauses.append("(observed_at < %s OR (observed_at = %s AND identity > %s))")
        values.extend((stamp, stamp, identity))
    values.append(limit + 1)
    with connection() as conn:
        rows = conn.execute(f"""
            SELECT facts, observed_at, identity FROM mining_powerplay
            WHERE {' AND '.join(clauses)}
            ORDER BY observed_at DESC, identity
            LIMIT %s
        """, tuple(values)).fetchall()
        coverage_rows = (conn.execute("""
            SELECT identity, system_name, observed_at FROM mining_powerplay
            WHERE identity = ANY(%s)
        """, (names,)).fetchall() if include_coverage and system is not None else [])
    more = len(rows) > limit
    last = rows[limit - 1] if more else None
    result = {
        "generatedAt": _now(), "hasMore": more,
        "nextCursor": _encode_state_cursor(last["observed_at"], "mining-powerplay", last["identity"]) if last else None,
        "selection": "systems" if system is not None else "region",
        "systemCount": len(rows[:limit]),
        "results": [fact for row in rows[:limit] for fact in row["facts"]],
    }
    if include_coverage and system is not None:
        known = {row["identity"]: row for row in coverage_rows}
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        result["coverage"] = [{
            "system": known[name]["system_name"] if name in known else name,
            "state": ("CURRENT" if known[name]["observed_at"] >= cutoff else "STALE")
                if name in known else "MISSING",
            "observedAt": known[name]["observed_at"].isoformat() if name in known else None,
        } for name in names]
    return result


def _mining_sites_sql(clauses):
    # Both paths use exactly the same selection, projection and ordering.
    return f"""
        WITH selected_sites AS MATERIALIZED (
            SELECT * FROM mining_sites ms WHERE {' AND '.join(clauses)}
            ORDER BY ms.observed_at DESC, ms.identity DESC LIMIT %s OFFSET %s
        )
        SELECT ms.identity AS "siteIdentity", ms.system_address AS "systemAddress",
               ms.system_name AS system, ms.x, ms.y, ms.z,
               ms.body_id AS "bodyId", ms.body_name AS body,
               ms.ring_name AS ring, ms.ring_type AS "ringType",
               ms.reserve_level AS "reserveLevel",
               ms.distance_to_arrival_ls AS "distanceToArrivalLs",
               ms.hotspots, ms.evidence, ms.source,
               ms.observed_at AS "observedAt", ms.received_at AS "receivedAt",
               COALESCE(yield_data.sample_count, 0) AS "prospectorSampleCount",
               COALESCE(yield_data.stats, '[]'::jsonb) AS "yieldStats"
        FROM selected_sites ms
        LEFT JOIN LATERAL (
            SELECT (SELECT COUNT(*) FROM mining_yield_samples counted
                    WHERE counted.site_identity = ms.identity) AS sample_count,
                   (SELECT jsonb_agg(jsonb_build_object(
                        'commodity', grouped.commodity, 'prospectorHits', grouped.hits,
                        'proportionSamples', grouped.hits, 'proportionTotal', grouped.total,
                        'averageProportion', grouped.average, 'maxProportion', grouped.maximum,
                        'lastObservedAt', grouped.last_observed_at) ORDER BY grouped.commodity)
                    FROM (SELECT ym.commodity, COUNT(*) AS hits, SUM(ym.proportion) AS total,
                                 AVG(ym.proportion) AS average, MAX(ym.proportion) AS maximum,
                                 MAX(material_sample.observed_at) AS last_observed_at
                          FROM mining_yield_materials ym
                          JOIN mining_yield_samples material_sample
                            ON material_sample.sample_id = ym.sample_id
                          WHERE material_sample.site_identity = ms.identity
                          GROUP BY ym.commodity) grouped) AS stats
        ) yield_data ON TRUE
        ORDER BY ms.observed_at DESC, ms.identity DESC
    """


def _freeze_sites_search(query, clauses, values, *, ring_types, page_limit, known_revision,
                         snapshot_revision, snapshot_static, cursor, offset):
    pages = configured_pages()
    projection = static_revision()
    try:
        if snapshot_revision:
            # Continuations use ONLY the already published immutable projection,
            # not fresh counters/SQL. A rolling code deployment still fences it.
            if snapshot_static != projection:
                raise FrozenExpired("Mining projection changed; restart paging")
            token, cursor_offset = decode_cursor(cursor)
            if cursor_offset != offset:
                raise FrozenExpired("Mining cursor/offset mismatch")
            return {"generatedAt": _now(), **pages.page(token, query=query,
                    revision=snapshot_revision, projection=projection, offset=offset, limit=page_limit)}
        with ExitStack() as cleanup:
            with connection() as conn:
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                revision = _snapshot_revision(conn, query)
                if known_revision == revision:
                    return {"generatedAt": _now(), "snapshotProtocol": 1,
                            "revision": revision, "notModified": True,
                            "snapshotStatic": projection, "snapshotComplete": True,
                            "results": [], "communityReferences": [], "hasMore": False,
                            "nextCursor": None, "nextOffset": None}
                token = pages.find(query, revision, projection)
                if token:
                    return {"generatedAt": _now(), **pages.page(token, query=query,
                            revision=revision, projection=projection, offset=0, limit=page_limit)}
                build = cleanup.enter_context(pages.build(query, revision, projection))
                conn.execute("SELECT set_config('statement_timeout', %s, true)",
                             (str(build.remaining_ms()),))
                # Fetch the whole bounded search, not an optimistic fraction of
                # a server cursor. Release the PG cursor/transaction before any
                # snapshot is published and before the HTTP response is sent.
                conn.execute("SET LOCAL cursor_tuple_fraction = 1.0")
                if query["commodity"] and query["include_community_overlaps"]:
                    identities = overlap_site_identities(conn, query["commodity"])
                    if identities:
                        clauses[1] = '(' + clauses[1] + ' OR ms.identity = ANY(%s))'
                        values.insert(5 if ring_types else 3, identities)
                values[-2:] = [MINING_FROZEN_MAX_ROWS + 1, 0]
                first_rows = []
                truncated = False
                with conn.cursor(name="mining_frozen_pages") as stream:
                    stream.execute(_mining_sites_sql(clauses), values)
                    while True:
                        conn.execute("SELECT set_config('statement_timeout', %s, true)",
                                     (str(build.remaining_ms()),))
                        batch = stream.fetchmany(MINING_FROZEN_CHUNK_ROWS)
                        if not batch:
                            break
                        remaining = MINING_FROZEN_MAX_ROWS - build.rows
                        if len(batch) > remaining:
                            truncated = True
                            batch = batch[:remaining]
                        if batch:
                            conn.execute("SELECT set_config('statement_timeout', %s, true)",
                                         (str(build.remaining_ms()),))
                            batch = attach_overlap_reports(enrich_ring_metadata(conn, batch))
                            first_rows.extend(batch[:max(0, query["limit"] - len(first_rows))])
                            pages.append(build, batch)
                        if truncated:
                            break
                references = []
                if query["include_community_overlaps"]:
                    conn.execute("SELECT set_config('statement_timeout', %s, true)",
                                 (str(build.remaining_ms()),))
                    references = community_reference_candidates(conn, first_rows,
                        commodity=query["commodity"] or None, system=query["system"] or None,
                        origin=tuple(query[k] for k in ("x", "y", "z"))
                            if all(query[k] is not None for k in ("x", "y", "z")) else None,
                        radius=query["max_distance"], limit=query["limit"])
                # Report the actual RR transaction time, never re-date sources.
                conn.execute("SELECT set_config('statement_timeout', %s, true)",
                             (str(build.remaining_ms()),))
                snapshot_at = conn.execute("SELECT transaction_timestamp() AS stamp").fetchone()["stamp"]
            pages.publish(build, references=references, truncated=truncated, snapshot_at=snapshot_at)
            return {"generatedAt": _now(), **pages.page(build.token, query=query,
                    revision=revision, projection=projection, offset=0, limit=page_limit)}
    except FrozenExpired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FrozenUnavailable, QueryCanceled) as exc:
        raise HTTPException(status_code=503, detail="Frozen mining search temporarily unavailable") from exc


@app.get("/v1/sites/search")
def search_sites(
    commodity: Annotated[str | None, Query(max_length=80)] = None,
    system: Annotated[str | None, Query(max_length=100)] = None,
    max_age_days: Annotated[int, Query(ge=1, le=3650)] = 365,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    max_distance: Annotated[float | None, Query(gt=0, le=2000)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    include_community_overlaps: bool = False,
    include_ring_candidates: bool = False,
    offset: Annotated[int | None, Query(ge=0, le=100000)] = None,
    cursor: Annotated[str | None, Query(max_length=1024)] = None,
    snapshot_protocol: Annotated[int | None, Query(ge=1, le=1)] = None,
    known_revision: Annotated[str | None, Query(max_length=80)] = None,
    snapshot_revision: Annotated[str | None, Query(max_length=80)] = None,
    snapshot_static: Annotated[str | None, Query(max_length=64)] = None,
    regional_page_size: Annotated[int | None, Query(ge=1, le=5000)] = None,
) -> dict:
    if not MINING_SNAPSHOT_PROTOCOL_ENABLED:
        snapshot_protocol = known_revision = snapshot_revision = snapshot_static = None
    reference_page_limit = limit
    limit = regional_page_limit(limit, regional_page_size, regional=(not system and all(
        value is not None for value in (x, y, z, max_distance))), maximum=5000)
    revision_query = {
        "commodity": (commodity or "").strip().casefold(),
        "system": (system or "").strip(),
        "max_age_days": max_age_days, "x": x, "y": y, "z": z,
        # References depend on the original requested limit. Page size may
        # shrink on the last bounded client page without changing the query.
        "max_distance": max_distance, "limit": reference_page_limit,
        "include_community_overlaps": include_community_overlaps,
        "include_ring_candidates": include_ring_candidates,
    }
    if snapshot_protocol and (offset is None or (not system and not all(
            v is not None for v in (x, y, z, max_distance)))):
        raise HTTPException(status_code=400, detail="Snapshot protocol requires a paginated bounded query")
    if snapshot_protocol and ((known_revision and (offset or cursor or snapshot_revision))
                              or ((offset or cursor) and not snapshot_revision)):
        raise HTTPException(status_code=400, detail="Invalid snapshot continuation")
    if snapshot_protocol and snapshot_revision and not cursor:
        raise HTTPException(status_code=409, detail="Frozen mining cursor required; restart paging")
    clauses = ["ms.observed_at >= NOW() - (%s * INTERVAL '1 day')"]
    values: list[object] = [max_age_days]
    ring_types = []
    if commodity:
        clauses.append(
            "(EXISTS (SELECT 1 FROM jsonb_array_elements(ms.hotspots) h "
            "WHERE LOWER(h->>'commodity') = LOWER(%s)) OR EXISTS ("
            "SELECT 1 FROM mining_yield_samples ys "
            "JOIN mining_yield_materials ym "
            "ON ym.sample_id = ys.sample_id "
            "WHERE ys.site_identity = ms.identity "
            "AND LOWER(ym.commodity) = LOWER(%s)))"
        )
        values.append(commodity.strip())
        values.append(commodity.strip())
        if include_ring_candidates:
            ring_types = list(MINING_COMMODITIES.get(mining_commodity_id(commodity), {}).get('ringTypes', ()))
            if ring_types:
                aliases = ring_types + ['eRingClass_' + value.replace(' ', '') for value in ring_types]
                if 'Metallic' in ring_types:
                    aliases.append('eRingClass_Metalic')
                clauses[1] = '(' + clauses[1] + " OR (LOWER(ms.ring_name) LIKE '%% ring' AND (ms.ring_type = ANY(%s) OR EXISTS (" \
                    'SELECT 1 FROM ring_reference_metadata rm WHERE ' \
                    'LOWER(rm.system_name)=LOWER(ms.system_name) AND ' \
                    'LOWER(rm.ring_name)=LOWER(ms.ring_name) AND ' \
                    '(ms.system_address IS NULL OR rm.system_address=ms.system_address) ' \
                    'AND rm.ring_type = ANY(%s)))))'
                values.extend((aliases, ring_types))
    if system:
        clauses.append("LOWER(ms.system_name) = LOWER(%s)")
        values.append(system.strip())
    if all(value is not None for value in (x, y, z, max_distance)):
        clauses.append(
            "POWER(ms.x - %s, 2) + POWER(ms.y - %s, 2) + "
            "POWER(ms.z - %s, 2) <= POWER(%s, 2)"
        )
        values.extend((x, y, z, max_distance))
        box_clause, box_values = regional_box_clause(x, y, z, max_distance, alias="ms")
        clauses.append(box_clause)
        values.extend(box_values)
    if cursor and not snapshot_protocol:
        cursor_at, cursor_kind, cursor_identity = _decode_state_cursor(cursor)
        if cursor_kind != "mining-sites" or not cursor_identity:
            raise HTTPException(status_code=400, detail="Invalid mining sites cursor")
        clauses.append("(ms.observed_at, ms.identity) < (%s, %s)")
        values.extend((cursor_at, cursor_identity))
    paginated = offset is not None or bool(cursor)
    values.append(limit + 1 if paginated else limit)
    values.append(0 if cursor else offset or 0)
    if snapshot_protocol:
        return _freeze_sites_search(revision_query, clauses, values, ring_types=ring_types,
            page_limit=limit, known_revision=known_revision, snapshot_revision=snapshot_revision,
            snapshot_static=snapshot_static, cursor=cursor, offset=offset)
    with connection() as conn:
        if commodity and include_community_overlaps:
            identities = overlap_site_identities(conn, commodity.strip().casefold())
            if identities:
                clauses[1] = '(' + clauses[1] + ' OR ms.identity = ANY(%s))'
                values.insert(5 if ring_types else 3, identities)
        rows = conn.execute(_mining_sites_sql(clauses), values).fetchall()
        has_more = paginated and len(rows) > limit
        next_cursor = None
        if has_more:
            last = rows[limit - 1]
            next_cursor = _encode_state_cursor(last["observedAt"], "mining-sites", last["siteIdentity"])
        rows = enrich_ring_metadata(conn, rows[:limit])
        rows = attach_overlap_reports(rows)
        references = []
        if include_community_overlaps and not offset and not cursor:
            references = community_reference_candidates(
                conn, rows[:reference_page_limit], commodity=commodity, system=system,
                origin=(x, y, z) if all(v is not None for v in (x, y, z)) else None,
                radius=max_distance, limit=reference_page_limit,
            )
            # The explicit community opt-in must not starve missing references
            # behind a full page of ordinary observations. Keep the total bounded.
            if not paginated:
                rows = references + rows[:max(0, limit - len(references))]
    return {"generatedAt": _now(), "results": rows,
            "communityReferences": references if paginated else [],
            "hasMore": has_more,
            "nextCursor": next_cursor,
            "nextOffset": (offset or 0) + limit if has_more else None}


@app.get("/v1/mining/overlaps")
def community_mining_overlaps(
    system: Annotated[str | None, Query(max_length=100)] = None,
    commodity: Annotated[str | None, Query(max_length=80)] = None,
) -> dict:
    rows = [dict(row) for row in overlap_catalog()
            if (not system or row['system'].casefold() == system.strip().casefold())
            and (not commodity or row['commodity'] == commodity.strip().casefold())]
    return {"generatedAt": _now(), "status": "COMMUNITY_REPORTED_UNDATED",
            "verifiedCount": 0, "results": rows}
