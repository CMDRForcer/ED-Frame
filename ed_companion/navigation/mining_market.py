"""Verified sell-market data for Mining Finder routes.

Ardent and EDData are read-only indexes built from public EDDN commodity
messages.  The adapter uses their importer endpoints and deliberately projects
only the station's ``sellPrice`` offer, demand and observation timestamp into
the planner.  No Commander identifier is sent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
from typing import Any
from urllib.parse import quote

from ed_companion import APP_VERSION

from .mining_commodities import mining_commodity_id
from .mining_commodities import MINING_COMMODITIES


ARDENT_API_BASE = "https://api.ardent-insight.com/v2"
EDDATA_API_BASE = "https://api.eddata.dev/v2"
EDSM_SYSTEM_URL = "https://www.edsm.net/api-v1/system"
EDFRAME_CATALOG_BASE = "https://vps-20b25c36.vps.ovh.net"
EDFRAME_STATION_OFFER_OBSERVATIONS_URL = (
    f"{EDFRAME_CATALOG_BASE}/v1/station-offers/observations"
)
MARKET_API_BASES = (
    (ARDENT_API_BASE, "Ardent", "Ardent API · EDDN commodity/3"),
    (EDDATA_API_BASE, "EDData", "EDData API · EDDN commodity/3"),
)
# Kept as the generic public adapter label for callers and old tests.
EDDATA_MARKET_SOURCE = "EDDN commodity market index"
MARKET_CATALOG_SCHEMA_VERSION = 1
MARKET_CATALOG_RETENTION_DAYS = 30
MARKET_CATALOG_MAX_ROWS = 20000


class MiningMarketError(RuntimeError):
    """A concise, user-displayable market lookup failure."""


def _market_provider_error(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status:
        return f"HTTP {status}"
    name = type(exc).__name__
    if "timeout" in name.casefold():
        return "TIMEOUT"
    return name


def market_provider_status_summary(statuses: Any) -> str:
    """Return a stable, user-readable status for each market source."""
    values = statuses if isinstance(statuses, dict) else {}
    return " · ".join(
        f"{name} {str(values.get(name) or 'NOT CHECKED')}"
        for name in ("ED-Frame", "Ardent", "EDData")
    )


def fetch_edframe_catalog_health(*, get: Any, timeout: int = 5) -> dict[str, Any]:
    """Return the catalog service's lightweight liveness response."""
    response = get(f"{EDFRAME_CATALOG_BASE}/healthz", timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise MiningMarketError("ED-Frame returned an invalid health response")
    return payload


def fetch_edframe_catalog_status(*, get: Any, timeout: int = 30) -> dict[str, Any]:
    """Return the anonymous central catalog's potentially expensive summary."""
    response = get(f"{EDFRAME_CATALOG_BASE}/v1/status", timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise MiningMarketError("ED-Frame returned an invalid status response")
    return payload


def fetch_edframe_market_delta(
    *, cursor: str = "", get: Any, timeout: int = 20, limit: int = 1000,
) -> dict[str, Any]:
    """Fetch one anonymous, resumable page for the local offline catalog."""
    bounded_limit = max(1, min(1000, int(limit or 1000)))
    params = {
        "commodities": ",".join(sorted(MINING_COMMODITIES)),
        "limit": bounded_limit,
    }
    if str(cursor or "").strip():
        params["cursor"] = str(cursor).strip()
    response = get(
        f"{EDFRAME_CATALOG_BASE}/v1/sync/markets",
        params=params, timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise MiningMarketError("ED-Frame returned an invalid sync response")
    rows = project_edframe_catalog_markets(payload, "")
    next_cursor = str(payload.get("nextCursor") or "").strip()
    has_more = bool(payload.get("hasMore"))
    if rows and not next_cursor:
        raise MiningMarketError("ED-Frame sync response has no resume cursor")
    if has_more and (not rows or next_cursor == str(cursor or "").strip()):
        raise MiningMarketError("ED-Frame sync cursor did not advance")
    return {
        "rows": rows,
        "nextCursor": next_cursor,
        "hasMore": has_more,
        "generatedAt": str(payload.get("generatedAt") or ""),
    }


def fetch_edframe_station_offer_delta(
    *, cursor: str = "", get: Any, timeout: int = 20, limit: int = 500,
) -> dict[str, Any]:
    """Fetch one resumable page of public outfitting/shipyard inventories."""
    bounded_limit = max(1, min(1000, int(limit or 500)))
    params: dict[str, Any] = {"limit": bounded_limit}
    if str(cursor or "").strip():
        params["cursor"] = str(cursor).strip()
    response = get(
        f"{EDFRAME_CATALOG_BASE}/v1/sync/station-offers",
        params=params, timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise MiningMarketError(
            "ED-Frame station offer sync returned an invalid response"
        )
    rows = [row for row in payload["results"] if isinstance(row, dict)]
    next_cursor = str(payload.get("nextCursor") or "").strip()
    has_more = bool(payload.get("hasMore"))
    if rows and not next_cursor:
        raise MiningMarketError("ED-Frame station offer sync has no resume cursor")
    if has_more and (not rows or next_cursor == str(cursor or "").strip()):
        raise MiningMarketError("ED-Frame station offer cursor did not advance")
    return {
        "rows": rows,
        "nextCursor": next_cursor,
        "hasMore": has_more,
        "generatedAt": str(payload.get("generatedAt") or ""),
    }


def project_local_shipyard_observation(
    snapshot: Any, station_message: Any, *, personal_discount_bps: int = 0,
) -> dict[str, Any] | None:
    """Keep exact public ship prices without Commander or filesystem data."""
    if not isinstance(snapshot, dict):
        return None
    identity = station_message if isinstance(station_message, dict) else {}
    try:
        market_id = int(
            identity.get("marketId") or snapshot.get("MarketID") or 0
        )
    except (TypeError, ValueError):
        market_id = 0
    system = str(
        identity.get("systemName") or snapshot.get("StarSystem") or ""
    ).strip()
    station = str(
        identity.get("stationName") or snapshot.get("StationName") or ""
    ).strip()
    observed_at = str(
        snapshot.get("timestamp") or identity.get("timestamp") or ""
    ).strip()
    if market_id <= 0 or not system or not station or not observed_at:
        return None
    ships = {}
    for source in snapshot.get("PriceList") or []:
        if not isinstance(source, dict):
            continue
        name = str(source.get("ShipType") or "").strip()
        display_name = str(
            source.get("ShipType_Localised") or source.get("ShipType") or ""
        ).strip()
        try:
            ship_id = int(source.get("id"))
            buy_price = int(source.get("ShipPrice"))
        except (TypeError, ValueError):
            continue
        if not name or ship_id < 0 or buy_price < 0:
            continue
        key = name.casefold()
        ships[key] = {
            "name": key,
            "displayName": display_name,
            "id": ship_id,
            "buyPrice": buy_price,
            "priceObservedAt": observed_at,
            "priceSource": "ED-Frame Journal · Shipyard.json",
        }
    if not ships:
        return None
    result = {
        "kind": "SHIPYARD",
        "marketId": market_id,
        "system": system,
        "station": station,
        "observedAt": observed_at,
        "ships": [ships[key] for key in sorted(ships)],
    }
    station_type = str(
        identity.get("stationType") or identity.get("StationType") or ""
    ).strip()
    if station_type:
        result["stationType"] = station_type
        result["fleetCarrier"] = (
            station_type.casefold().replace(" ", "") == "fleetcarrier"
        )
    if personal_discount_bps == 250:
        # Only the public discount amount is shared.  No rank, Commander or
        # account identifier leaves the app.  The server uses it to restore
        # the station price before the Commander's galaxy-wide Elite rebate.
        result["personalDiscountBps"] = 250
    for direct, source in (("horizons", "Horizons"), ("odyssey", "Odyssey")):
        value = identity.get(direct, snapshot.get(source))
        if isinstance(value, bool):
            result[direct] = value
    return result


def project_local_outfitting_observation(
    snapshot: Any, station_message: Any, *, personal_discount_bps: int = 0,
) -> dict[str, Any] | None:
    """Keep exact public module prices without Commander or filesystem data."""
    if not isinstance(snapshot, dict):
        return None
    identity = station_message if isinstance(station_message, dict) else {}
    try:
        market_id = int(
            identity.get("marketId") or snapshot.get("MarketID") or 0
        )
    except (TypeError, ValueError):
        market_id = 0
    system = str(
        identity.get("systemName") or snapshot.get("StarSystem") or ""
    ).strip()
    station = str(
        identity.get("stationName") or snapshot.get("StationName") or ""
    ).strip()
    observed_at = str(
        snapshot.get("timestamp") or identity.get("timestamp") or ""
    ).strip()
    if market_id <= 0 or not system or not station or not observed_at:
        return None
    modules = {}
    for source in snapshot.get("Items") or []:
        if not isinstance(source, dict):
            continue
        name = str(source.get("Name") or "").strip()
        try:
            module_id = int(source.get("id"))
            buy_price = int(source.get("BuyPrice"))
            merc_price = int(source.get("BuyMercCoinsPrice", 0))
        except (TypeError, ValueError):
            continue
        if (
            not name or module_id < 0 or buy_price < 0 or merc_price < 0
        ):
            continue
        key = name.casefold()
        modules[key] = {
            "name": key,
            "id": module_id,
            "buyPrice": buy_price,
            "buyMercCoinsPrice": merc_price,
            "priceObservedAt": observed_at,
            "priceSource": "ED-Frame Journal · Outfitting.json",
        }
    if not modules:
        return None
    result = {
        "kind": "OUTFITTING",
        "marketId": market_id,
        "system": system,
        "station": station,
        "observedAt": observed_at,
        "modules": [modules[key] for key in sorted(modules)],
    }
    station_type = str(
        identity.get("stationType") or identity.get("StationType") or ""
    ).strip()
    if station_type:
        result["stationType"] = station_type
        result["fleetCarrier"] = (
            station_type.casefold().replace(" ", "") == "fleetcarrier"
        )
    if personal_discount_bps == 250:
        result["personalDiscountBps"] = 250
    for direct, source in (("horizons", "Horizons"), ("odyssey", "Odyssey")):
        value = identity.get(direct, snapshot.get(source))
        if isinstance(value, bool):
            result[direct] = value
    return result


def commander_personal_discount_bps(overview: Any) -> int:
    """Return Elite's public 2.5% purchase rebate without exposing rank data."""
    source = overview if isinstance(overview, dict) else {}
    ranks = source.get("ranks")
    if not isinstance(ranks, list):
        return 0
    eligible = {"combat", "trade", "explore", "cqc"}
    for row in ranks:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip().casefold()
        rank = row.get("rank")
        if (
            key in eligible
            and isinstance(rank, (int, float))
            and not isinstance(rank, bool)
            and int(rank) >= 8
        ):
            return 250
    return 0


def station_offer_observation_key(observation: Any) -> str:
    source = observation if isinstance(observation, (dict, list)) else {}
    payload = json.dumps(
        source,
        sort_keys=True, ensure_ascii=True, separators=(",", ":"),
    )
    import hashlib
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def send_edframe_station_offer_observations(
    observations: Any, post: Any, timeout: int = 20,
) -> dict[str, Any]:
    rows = [dict(row) for row in observations if isinstance(row, dict)]
    if len(rows) > 20:
        raise ValueError("A station offer upload may contain at most 20 observations")
    response = post(
        EDFRAME_STATION_OFFER_OBSERVATIONS_URL,
        json={"observations": rows}, timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise MiningMarketError(
            "ED-Frame station offer service returned invalid data"
        )
    return payload


def fetch_edframe_system_coordinates(
    system: str, *, get: Any, timeout: int = 12,
) -> dict[str, Any]:
    """Resolve a public system through the central catalog."""
    requested = str(system or "").strip()
    if not requested:
        raise MiningMarketError("Start system is required")
    response = get(
        f"{EDFRAME_CATALOG_BASE}/v1/systems/suggest",
        params={"q": requested, "limit": 5}, timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("results") if isinstance(payload, dict) else []
    exact = next((
        row for row in rows if isinstance(row, dict)
        and str(row.get("name") or "").strip().casefold()
        == requested.casefold()
    ), None)
    coordinates = (
        [_finite(exact.get(axis)) for axis in ("x", "y", "z")]
        if isinstance(exact, dict) else []
    )
    if not coordinates or not all(value is not None for value in coordinates):
        raise MiningMarketError("ED-Frame has no coordinates for the start system")
    return {
        "system": str(exact.get("name") or requested).strip(),
        "coordinates": coordinates,
        "source": "ED-Frame live catalog",
    }


def fetch_edsm_system_coordinates(
    system: str, *, get: Any, timeout: int = 12,
) -> dict[str, Any]:
    """Resolve one freely entered origin without Commander identification."""
    requested = str(system or "").strip()
    if not requested:
        raise MiningMarketError("Start system is required")
    response = get(
        EDSM_SYSTEM_URL,
        params={"systemName": requested, "showCoordinates": 1},
        headers={
            "User-Agent": (
                f"ED-Frame/{APP_VERSION} "
                "(+https://github.com/CMDRForcer/ED-Frame)"
            ),
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    coordinates = payload.get("coords") if isinstance(payload, dict) else None
    if not isinstance(coordinates, dict):
        raise MiningMarketError("EDSM has no coordinates for the start system")
    values = [_finite(coordinates.get(axis)) for axis in ("x", "y", "z")]
    if not all(value is not None for value in values):
        raise MiningMarketError("EDSM returned invalid start-system coordinates")
    return {
        "system": str(payload.get("name") or requested).strip(),
        "coordinates": values,
        "source": "EDSM Systems API",
    }


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_nonnegative_integer(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _observed_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _market_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        mining_commodity_id(row.get("commodity") or row.get("name")),
        str(row.get("system") or "").strip().casefold(),
        str(row.get("station") or "").strip().casefold(),
    )


def latest_market_rows(*groups: Any) -> list[dict[str, Any]]:
    """Merge public market observations without letting stale rows win."""
    latest: dict[tuple[str, str, str], tuple[datetime, dict[str, Any]]] = {}
    for group in groups:
        for source in group if isinstance(group, list) else []:
            if not isinstance(source, dict):
                continue
            key = _market_key(source)
            observed = _observed_at(source.get("observedAt"))
            if not all(key) or observed is None:
                continue
            current = latest.get(key)
            if current is None:
                latest[key] = (observed, dict(source))
                continue
            older, newer = (
                (current[1], source) if observed >= current[0]
                else (source, current[1])
            )
            merged = dict(older)
            merged.update({
                field: value for field, value in newer.items()
                if value not in (None, "", [], {})
            })
            latest[key] = (max(observed, current[0]), merged)
    return [
        row for _observed, row in sorted(
            latest.values(), key=lambda item: item[0], reverse=True,
        )
    ]


def merge_market_catalog(
    catalog: Any, observations: Any, *, now: datetime | None = None,
    retention_days: int = MARKET_CATALOG_RETENTION_DAYS,
    max_rows: int = MARKET_CATALOG_MAX_ROWS,
) -> dict[str, Any]:
    """Accumulate bounded market knowledge, keeping the newest fact per port."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    existing = catalog.get("markets", []) if isinstance(catalog, dict) else []
    cutoff = now - timedelta(days=max(1, int(retention_days or 1)))
    merged = [
        row for row in latest_market_rows(existing, observations)
        if (_observed_at(row.get("observedAt")) or cutoff) >= cutoff
    ][:max(1, int(max_rows or 1))]
    return {
        "schemaVersion": MARKET_CATALOG_SCHEMA_VERSION,
        "updatedAt": now.isoformat(timespec="seconds"),
        "retentionDays": max(1, int(retention_days or 1)),
        "markets": merged,
    }


def nearby_catalog_markets(
    catalog: Any, commodity: str, *, origin_system: str = "",
    origin_coordinates: Any = None, max_distance: int = 0,
) -> list[dict[str, Any]]:
    """Select reusable catalog rows inside the active search sphere."""
    rows = catalog.get("markets", []) if isinstance(catalog, dict) else []
    commodity_id = mining_commodity_id(commodity)
    all_commodities = commodity_id in {"", "allcommodities"}
    origin_key = str(origin_system or "").strip().casefold()
    coordinates = (
        [_finite(value) for value in origin_coordinates]
        if isinstance(origin_coordinates, (list, tuple))
        and len(origin_coordinates) == 3 else []
    )
    coordinates_known = len(coordinates) == 3 and all(
        value is not None for value in coordinates
    )
    radius = max(0.0, float(max_distance or 0))
    result = []
    for source in rows if isinstance(rows, list) else []:
        if not isinstance(source, dict) or (
            not all_commodities and mining_commodity_id(
                source.get("commodity")
            ) != commodity_id
        ):
            continue
        if str(source.get("system") or "").strip().casefold() == origin_key:
            result.append(dict(source))
            continue
        target = source.get("coordinates")
        if not coordinates_known or not isinstance(target, (list, tuple)) \
                or len(target) != 3:
            continue
        target_coordinates = [_finite(value) for value in target]
        if not all(value is not None for value in target_coordinates):
            continue
        distance = math.sqrt(sum(
            (left - right) ** 2
            for left, right in zip(coordinates, target_coordinates)
        ))
        if radius <= 0 or distance <= radius:
            result.append(dict(source))
    return result


def project_local_market_snapshot(
    snapshot: Any, *, coordinates: Any = None,
) -> list[dict[str, Any]]:
    """Project the Commander's local ``Market.json`` without identity data.

    Frontier writes this snapshot after the market is opened.  It is the most
    direct observation available to the app, so the local catalog should learn
    from it even when community upload is disabled or the network is offline.
    """
    if not isinstance(snapshot, dict):
        return []
    system = str(snapshot.get("StarSystem") or "").strip()
    station = str(snapshot.get("StationName") or "").strip()
    observed_at = str(snapshot.get("timestamp") or "").strip()
    market_id = _integer(snapshot.get("MarketID"))
    items = snapshot.get("Items")
    if not system or not station or not observed_at or not isinstance(items, list):
        return []
    position = (
        [_finite(value) for value in coordinates]
        if isinstance(coordinates, (list, tuple)) and len(coordinates) == 3
        else []
    )
    if not all(value is not None for value in position):
        position = []
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        commodity = mining_commodity_id(
            item.get("Name") or item.get("Name_Localised")
        )
        sell_price = max(0, _integer(item.get("SellPrice")))
        if commodity not in MINING_COMMODITIES or sell_price <= 0:
            continue
        demand = max(0, _integer(item.get("Demand")))
        demand_bracket = max(0, _integer(item.get("DemandBracket")))
        rows.append({
            "commodity": commodity,
            "marketId": market_id,
            "station": station,
            "system": system,
            "systemAddress": _integer(snapshot.get("SystemAddress")),
            "stationType": str(snapshot.get("StationType") or ""),
            "landingPadSize": str(
                snapshot.get("MaxLandingPadSize") or ""
            ).upper(),
            "distanceToArrivalLs": _finite(
                snapshot.get("DistanceFromStarLS")
            ),
            "coordinates": position,
            "sellPrice": sell_price,
            "demand": demand,
            "demandInfinite": demand == 0 and demand_bracket > 0,
            "demandBracket": demand_bracket,
            "observedAt": observed_at,
            "source": "Local Journal Market.json",
            "sourceUrl": "",
            "meritEligible": None,
        })
    return rows


def project_market_imports(
    payload: Any, commodity: str, *, source: str = EDDATA_MARKET_SOURCE,
    source_url: str = EDDATA_API_BASE,
) -> list[dict[str, Any]]:
    """Validate an EDData response and project only usable public market facts."""
    if isinstance(payload, dict):
        if str(payload.get("status") or "").casefold() in {"error", "unavailable"}:
            raise MiningMarketError(
                str(payload.get("message") or "EDDN market index unavailable")
            )
        rows = payload.get("results") or payload.get("commodities") or []
    else:
        rows = payload
    if not isinstance(rows, list):
        raise MiningMarketError("EDDN market index returned an invalid response")

    commodity_id = mining_commodity_id(commodity)
    result: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    source_label = source
    for source_row in rows:
        if not isinstance(source_row, dict):
            continue
        if mining_commodity_id(source_row.get("commodityName")) != commodity_id:
            continue
        station = str(source_row.get("stationName") or "").strip()
        system = str(source_row.get("systemName") or "").strip()
        observed_at = str(source_row.get("updatedAt") or "").strip()
        market_id = _integer(source_row.get("marketId"))
        # In Frontier/EDDN market vocabulary SellPrice is the price offered
        # when the Commander sells; importer endpoints therefore rank it.
        price = max(0, _integer(source_row.get("sellPrice")))
        demand = max(0, _integer(source_row.get("demand")))
        demand_bracket = max(0, _integer(source_row.get("demandBracket")))
        if not station or not system or not observed_at or not market_id or not price:
            continue
        key = (market_id, commodity_id)
        if key in seen:
            continue
        seen.add(key)
        coordinates = [
            _finite(source_row.get("systemX")),
            _finite(source_row.get("systemY")),
            _finite(source_row.get("systemZ")),
        ]
        pad = str(source_row.get("maxLandingPadSize") or "").upper()
        pad = {"1": "S", "2": "M", "3": "L"}.get(pad, pad)
        result.append({
            "commodity": commodity_id,
            "marketId": market_id,
            "station": station,
            "system": system,
            "systemAddress": _integer(source_row.get("systemAddress")),
            "stationType": str(source_row.get("stationType") or ""),
            "landingPadSize": pad,
            "distanceToArrivalLs": _finite(source_row.get("distanceToArrival")),
            "coordinates": coordinates if all(
                value is not None for value in coordinates
            ) else [],
            "sellPrice": price,
            "demand": demand,
            # EDData documents demand=0 with a positive bracket as infinite.
            "demandInfinite": demand == 0 and demand_bracket > 0,
            "demandBracket": demand_bracket,
            "observedAt": observed_at,
            "source": source_label,
            "sourceUrl": source_url,
            # A commodity order proves no Powerplay merit rule by itself.
            "meritEligible": None,
        })
    return result


def project_edframe_catalog_markets(
    payload: Any, commodity: str = "",
) -> list[dict[str, Any]]:
    """Project the central ED-Frame read-only catalog into local rows."""
    rows = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise MiningMarketError("ED-Frame catalog returned an invalid response")
    commodity_id = mining_commodity_id(commodity)
    result = []
    for source_row in rows:
        if not isinstance(source_row, dict):
            continue
        row_commodity = mining_commodity_id(source_row.get("commodity"))
        if row_commodity not in MINING_COMMODITIES or (
            commodity_id and row_commodity != commodity_id
        ):
            continue
        station = str(source_row.get("station") or "").strip()
        system = str(source_row.get("system") or "").strip()
        observed_at = str(source_row.get("observedAt") or "").strip()
        market_id = _integer(source_row.get("marketId"))
        sell_price = max(0, _integer(source_row.get("sellPrice")))
        if not station or not system or not observed_at or not market_id \
                or not sell_price:
            continue
        coordinates = [
            _finite(source_row.get("x")),
            _finite(source_row.get("y")),
            _finite(source_row.get("z")),
        ]
        demand = max(0, _integer(source_row.get("demand")))
        demand_bracket = max(0, _integer(source_row.get("demandBracket")))
        result.append({
            "commodity": row_commodity,
            "marketId": market_id,
            "station": station,
            "system": system,
            "systemAddress": _integer(source_row.get("systemAddress")),
            "stationType": str(source_row.get("stationType") or ""),
            "landingPadSize": str(
                source_row.get("landingPadSize") or ""
            ).upper(),
            "distanceToArrivalLs": _finite(
                source_row.get("distanceToArrivalLs")
            ),
            "coordinates": coordinates if all(
                value is not None for value in coordinates
            ) else [],
            "meanPrice": _optional_nonnegative_integer(
                source_row.get("meanPrice")
            ),
            "buyPrice": _optional_nonnegative_integer(
                source_row.get("buyPrice")
            ),
            "stock": _optional_nonnegative_integer(source_row.get("stock")),
            "stockBracket": _optional_nonnegative_integer(
                source_row.get("stockBracket")
            ),
            "sellPrice": sell_price,
            "demand": demand,
            "demandInfinite": demand == 0 and demand_bracket > 0,
            "demandBracket": demand_bracket,
            "statusFlags": _list(source_row.get("statusFlags")),
            "services": _list(source_row.get("services")),
            "economies": _list(source_row.get("economies")),
            "primaryEconomy": str(source_row.get("primaryEconomy") or ""),
            "government": str(source_row.get("government") or ""),
            "controllingFaction": str(
                source_row.get("controllingFaction") or ""
            ),
            "fleetCarrier": _optional_bool(source_row.get("fleetCarrier")),
            "carrierDockingAccess": str(
                source_row.get("carrierDockingAccess") or ""
            ),
            "prohibited": _list(source_row.get("prohibited")),
            "observedAt": observed_at,
            "receivedAt": str(source_row.get("receivedAt") or ""),
            "source": "ED-Frame live catalog · EDDN commodity/3",
            "sourceUrl": EDFRAME_CATALOG_BASE,
            "meritEligible": None,
        })
    return result


def _fetch_edframe_catalog_markets(
    system: str, commodity: str, *, max_distance: int, max_days_ago: int,
    landing_pad: str, get: Any, timeout: int,
) -> list[dict[str, Any]]:
    origin = fetch_edframe_system_coordinates(
        system, get=get, timeout=timeout,
    )
    coordinates = origin["coordinates"]
    pad = str(landing_pad or "ANY").strip().upper()
    pad = {"SMALL": "S", "MEDIUM": "M", "LARGE": "L"}.get(pad, pad)
    response = get(
        f"{EDFRAME_CATALOG_BASE}/v1/markets/search",
        params={
            "commodity": commodity,
            "max_age_hours": max(1, max_days_ago) * 24,
            "x": coordinates[0],
            "y": coordinates[1],
            "z": coordinates[2],
            "max_distance": max_distance,
            "landing_pad": pad if pad in {"S", "M", "L"} else None,
            "exclude_fleet_carriers": True,
            "limit": 200,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return project_edframe_catalog_markets(response.json(), commodity)


def fetch_market_imports(
    start_system: str,
    commodity: str,
    *,
    max_distance: int,
    max_days_ago: int,
    get: Any,
    timeout: int = 20,
    include_edframe: bool = True,
    landing_pad: str = "ANY",
    provider_status: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch nearby sell markets without sending Commander-identifying data."""
    system = str(start_system or "").strip()
    commodity_id = mining_commodity_id(commodity)
    if not system or not commodity_id:
        raise MiningMarketError("Start system and commodity are required")
    distance = max(1, min(1000, int(max_distance or 1)))
    days = max(1, min(14, int(max_days_ago or 1)))
    statuses = provider_status if provider_status is not None else {}
    statuses.clear()
    statuses.update({
        "ED-Frame": "NOT CHECKED" if include_edframe else "DISABLED",
        "Ardent": "NOT CHECKED",
        "EDData": "NOT CHECKED",
    })
    central_rows = []
    central_succeeded = False
    if include_edframe:
        try:
            central_rows = _fetch_edframe_catalog_markets(
                system, commodity_id, max_distance=distance,
                max_days_ago=days, landing_pad=landing_pad,
                get=get, timeout=timeout,
            )
            central_succeeded = True
            statuses["ED-Frame"] = f"OK ({len(central_rows)} rows)"
        except Exception as exc:
            statuses["ED-Frame"] = (
                f"UNAVAILABLE ({_market_provider_error(exc)})"
            )
    for index, (base_url, provider_name, source_label) in enumerate(
        MARKET_API_BASES
    ):
        url = (
            f"{base_url}/system/name/{quote(system, safe='')}"
            f"/commodity/name/{quote(commodity_id, safe='')}/nearby/imports"
        )
        try:
            response = get(
                url,
                params={
                    # Keep infinite-demand rows in the response and apply the
                    # exact UI threshold locally after their semantics are known.
                    "minVolume": 1,
                    "minPrice": 1,
                    "fleetCarriers": "false",
                    "maxDistance": distance,
                    "maxDaysAgo": days,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            provider_rows = project_market_imports(
                response.json(), commodity_id,
                source=source_label, source_url=base_url,
            )
            statuses[provider_name] = f"OK ({len(provider_rows)} rows)"
            for _, remaining_name, _ in MARKET_API_BASES[index + 1:]:
                statuses[remaining_name] = "NOT NEEDED"
            return latest_market_rows(central_rows, provider_rows)
        except Exception as exc:
            statuses[provider_name] = (
                f"UNAVAILABLE ({_market_provider_error(exc)})"
            )
    if central_succeeded:
        return central_rows
    raise MiningMarketError(
        "Community market lookup failed · "
        + market_provider_status_summary(statuses)
    )
