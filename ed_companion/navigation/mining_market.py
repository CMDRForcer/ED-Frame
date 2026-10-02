"""Verified sell-market data for Mining Finder routes.

Ardent and EDData are read-only indexes built from public EDDN commodity
messages.  The adapter uses their importer endpoints and deliberately projects
only the station's ``sellPrice`` offer, demand and observation timestamp into
the planner.  No Commander identifier is sent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any
from urllib.parse import quote

from ed_companion import APP_VERSION

from .mining_commodities import mining_commodity_id
from .mining_commodities import MINING_COMMODITIES


ARDENT_API_BASE = "https://api.ardent-insight.com/v2"
EDDATA_API_BASE = "https://api.eddata.dev/v2"
EDSM_SYSTEM_URL = "https://www.edsm.net/api-v1/system"
MARKET_API_BASES = (
    (ARDENT_API_BASE, "Ardent API · EDDN commodity/3"),
    (EDDATA_API_BASE, "EDData API · EDDN commodity/3"),
)
# Kept as the generic public adapter label for callers and old tests.
EDDATA_MARKET_SOURCE = "EDDN commodity market index"
MARKET_CATALOG_SCHEMA_VERSION = 1
MARKET_CATALOG_RETENTION_DAYS = 30
MARKET_CATALOG_MAX_ROWS = 20000


class MiningMarketError(RuntimeError):
    """A concise, user-displayable market lookup failure."""


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


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


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
            if current is None or observed >= current[0]:
                latest[key] = (observed, dict(source))
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
        if not isinstance(source, dict) or mining_commodity_id(
            source.get("commodity")
        ) != commodity_id:
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


def fetch_market_imports(
    start_system: str,
    commodity: str,
    *,
    max_distance: int,
    max_days_ago: int,
    get: Any,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    """Fetch nearby sell markets without sending Commander-identifying data."""
    system = str(start_system or "").strip()
    commodity_id = mining_commodity_id(commodity)
    if not system or not commodity_id:
        raise MiningMarketError("Start system and commodity are required")
    distance = max(1, min(1000, int(max_distance or 1)))
    days = max(1, min(14, int(max_days_ago or 1)))
    errors = []
    for base_url, source_label in MARKET_API_BASES:
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
            return project_market_imports(
                response.json(), commodity_id,
                source=source_label, source_url=base_url,
            )
        except Exception as exc:
            errors.append(f"{source_label}: {type(exc).__name__}")
    raise MiningMarketError(
        "EDDN market lookup failed via all providers (" + ", ".join(errors) + ")"
    )
