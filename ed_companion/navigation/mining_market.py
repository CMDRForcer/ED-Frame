"""Verified sell-market data for Mining Finder routes.

Ardent and EDData are read-only indexes built from public EDDN commodity
messages.  The adapter uses their importer endpoints and deliberately projects
only the station's ``sellPrice`` offer, demand and observation timestamp into
the planner.  No Commander identifier is sent.
"""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import quote

from .mining_commodities import mining_commodity_id


ARDENT_API_BASE = "https://api.ardent-insight.com/v2"
EDDATA_API_BASE = "https://api.eddata.dev/v2"
MARKET_API_BASES = (
    (ARDENT_API_BASE, "Ardent API · EDDN commodity/3"),
    (EDDATA_API_BASE, "EDData API · EDDN commodity/3"),
)
# Kept as the generic public adapter label for callers and old tests.
EDDATA_MARKET_SOURCE = "EDDN commodity market index"


class MiningMarketError(RuntimeError):
    """A concise, user-displayable market lookup failure."""


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
