"""Pure projection helpers for the Shipyard & Outfitting finder.

The UI deliberately consumes a small, honest projection: availability is
separate from price confidence and unknown coordinates/prices stay unknown.
"""

from __future__ import annotations

import math
from typing import Any, Iterable


def build_module_catalog(payload: Any) -> list[dict[str, Any]]:
    modules = payload.get("modules", {}) if isinstance(payload, dict) else {}
    rows = []
    for symbol, value in modules.items():
        if not isinstance(value, (list, tuple)) or not value:
            continue
        folded_symbol = str(symbol).casefold()
        mount = (
            "FIXED" if "_fixed_" in folded_symbol else
            "GIMBALLED" if "_gimbal_" in folded_symbol else
            "TURRETED" if "_turret_" in folded_symbol else ""
        )
        rows.append({
            "symbol": folded_symbol,
            "displayName": str(value[0] or symbol).strip(),
            "sizeRating": str(value[1] if len(value) > 1 else "").strip(),
            "mount": mount,
            "kind": "MODULES",
        })
    return sorted(rows, key=lambda row: (
        row["displayName"].casefold(), row["sizeRating"], row["symbol"],
    ))


def build_ship_catalog(
    payload: Any, reference_prices: Any = None,
) -> list[dict[str, Any]]:
    price_rows = (
        reference_prices.get("ships", {})
        if isinstance(reference_prices, dict) else {}
    )
    rows = []
    for source in payload if isinstance(payload, list) else []:
        if not isinstance(source, dict):
            continue
        symbol = str(source.get("symbol") or "").strip()
        name = str(source.get("name") or symbol).strip()
        if not symbol or not name:
            continue
        price_row = price_rows.get(symbol.casefold())
        price_row = price_row if isinstance(price_row, dict) else {}
        reference_price = _integer(price_row.get("referencePrice"))
        row = {
            "symbol": symbol.casefold(),
            "assetSymbol": symbol,
            "schematicSource": f"assets/ships/{symbol}.svg",
            "displayName": name,
            "manufacturer": str(source.get("manufacturer") or "").strip(),
            "size": str(source.get("size") or "").strip().upper(),
            "maximumSpeed": source.get("maximumSpeed"),
            "boost": source.get("boost"),
            "kind": "SHIPS",
        }
        if reference_price is not None and reference_price > 0:
            row.update({
                "referencePrice": reference_price,
                "referencePriceSource": str(
                    price_row.get("source") or "ED-Frame reference catalog"
                ),
                "referencePriceCapturedAt": str(
                    reference_prices.get("capturedAt") or ""
                ),
            })
        rows.append(row)
    return sorted(rows, key=lambda row: row["displayName"].casefold())


def catalog_suggestions(
    catalog: Iterable[dict[str, Any]], query: str, *, limit: int = 12,
) -> list[dict[str, Any]]:
    term = str(query or "").strip().casefold()
    if not term:
        return [dict(row) for row in list(catalog)[:max(1, int(limit))]]
    ranked = []
    for row in catalog:
        name = str(row.get("displayName") or "").casefold()
        symbol = str(row.get("symbol") or "").casefold()
        manufacturer = str(row.get("manufacturer") or "").casefold()
        if term not in name and term not in symbol and term not in manufacturer:
            continue
        score = 0 if name.startswith(term) else 1 if term in name else 2
        ranked.append((score, name, symbol, dict(row)))
    return [entry[-1] for entry in sorted(ranked)[:max(1, int(limit))]]


def _coordinates(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _pad_rank(value: Any) -> int:
    normalized = str(value or "").strip().casefold()
    if normalized in {"l", "large"}:
        return 3
    if normalized in {"m", "medium"}:
        return 2
    if normalized in {"s", "small"}:
        return 1
    return 0


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_permit_rules(engineers: Any) -> dict[str, dict[str, Any]]:
    """Project the small, sourced permit subset from the unlock catalog."""
    rules: dict[str, dict[str, Any]] = {}
    for record in (engineers or {}).values() if isinstance(engineers, dict) else []:
        if not isinstance(record, dict):
            continue
        permit = record.get("permit")
        if not isinstance(permit, dict):
            continue
        system = str(permit.get("system") or record.get("system") or "").strip()
        if not system:
            continue
        rules[system.casefold()] = {
            "system": system,
            "name": str(permit.get("name") or f"{system} permit"),
            "method": str(permit.get("method") or "Permit evidence required"),
            "rule": dict(permit.get("rule") or {}),
        }
    return rules


def _overview_ranks(overview: Any) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    rows = overview.get("ranks", []) if isinstance(overview, dict) else []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "")
        result[key] = _integer(row.get("rank")) if row.get("known") else None
    return result


def evaluate_station_access(
    system: str, commander_overview: Any, permit_rules: Any,
) -> dict[str, Any]:
    """Describe access without treating missing Journal proof as denial."""
    name = str(system or "").strip()
    overview = commander_overview if isinstance(commander_overview, dict) else {}
    permits = {
        str(value).strip().casefold()
        for value in overview.get("permits", [])
        if str(value).strip()
    }
    visited = {
        str(value).strip().casefold()
        for value in overview.get("visitedSystems", [])
        if str(value).strip()
    }
    rule = (
        permit_rules.get(name.casefold())
        if isinstance(permit_rules, dict) else None
    )
    if not isinstance(rule, dict):
        return {
            "accessStatus": "OPEN",
            "accessTone": "OPEN",
            "accessReason": "No known permit restriction",
            "accessRank": 1,
        }
    permit_name = str(rule.get("name") or "Permit")
    if name.casefold() in visited:
        return {
            "accessStatus": "CONFIRMED",
            "accessTone": "CONFIRMED",
            "accessReason": f"Journal confirms a visit to {name}",
            "accessRank": 0,
        }
    if name.casefold() in permits or permit_name.casefold() in permits:
        return {
            "accessStatus": "CONFIRMED",
            "accessTone": "CONFIRMED",
            "accessReason": f"Journal confirms {permit_name}",
            "accessRank": 0,
        }
    ranks = _overview_ranks(overview)
    condition = rule.get("rule")
    condition = condition if isinstance(condition, dict) else {}
    condition_type = str(condition.get("type") or "")
    minimum = _integer(condition.get("minimum")) or 0
    if condition_type == "rank":
        field = str(condition.get("field") or "")
        value = ranks.get(field)
        if value is not None and value >= minimum:
            return {
                "accessStatus": "CONFIRMED",
                "accessTone": "CONFIRMED",
                "accessReason": f"{field} rank {value} satisfies {permit_name}",
                "accessRank": 0,
            }
        if value is not None:
            return {
                "accessStatus": "PERMIT MISSING",
                "accessTone": "LOCKED",
                "accessReason": f"{permit_name} requires {field} rank {minimum}; Journal shows {value}",
                "accessRank": 3,
            }
    elif condition_type == "anyRank":
        fields = [str(value) for value in condition.get("fields", [])]
        known = [ranks.get(field) for field in fields if ranks.get(field) is not None]
        if any(value >= minimum for value in known):
            return {
                "accessStatus": "CONFIRMED",
                "accessTone": "CONFIRMED",
                "accessReason": f"Elite career rank satisfies {permit_name}",
                "accessRank": 0,
            }
        if len(known) == len(fields) and fields:
            return {
                "accessStatus": "PERMIT MISSING",
                "accessTone": "LOCKED",
                "accessReason": f"{permit_name} requires Elite rank in one recognised career",
                "accessRank": 3,
            }
    return {
        "accessStatus": "PERMIT UNCONFIRMED",
        "accessTone": "UNKNOWN",
        "accessReason": str(rule.get("method") or f"No Journal proof for {permit_name}"),
        "accessRank": 2,
    }
def rank_station_offers(
    rows: Iterable[dict[str, Any]], *, kind: str,
    origin_coordinates: Any = None, max_distance_ly: int = 0,
    pad_filter: str = "ANY", item: dict[str, Any] | None = None,
    commander_overview: Any = None, permit_rules: Any = None,
    access_filter: str = "SAFE + UNKNOWN",
) -> list[dict[str, Any]]:
    """Filter, enrich and rank station offers without inventing facts."""
    kind = str(kind or "MODULES").upper()
    origin = _coordinates(origin_coordinates)
    requested_pad = _pad_rank(pad_filter)
    if kind == "SHIPS":
        requested_pad = max(requested_pad, _pad_rank((item or {}).get("size")))
    distance_limit = max(0, int(max_distance_ly or 0))
    projected: list[dict[str, Any]] = []
    for source in rows:
        if not isinstance(source, dict):
            continue
        station = str(source.get("station") or "").strip()
        system = str(source.get("system") or "").strip()
        if not station or not system:
            continue
        available_pad = _pad_rank(source.get("landingPadSize"))
        if requested_pad and available_pad and available_pad < requested_pad:
            continue
        coordinates = _coordinates(source.get("coordinates"))
        distance = None
        if origin is not None and coordinates is not None:
            distance = round(math.sqrt(sum(
                (left - right) ** 2 for left, right in zip(origin, coordinates)
            )), 1)
        if distance_limit and (distance is None or distance > distance_limit):
            continue
        offer_key = "moduleOffer" if kind == "MODULES" else "shipOffer"
        offer = source.get(offer_key)
        offer = dict(offer) if isinstance(offer, dict) else {}
        price = _integer(offer.get("buyPrice", source.get("buyPrice")))
        confidence = str(offer.get("priceConfidence") or "").upper()
        price_type = str(offer.get("priceType") or "").upper()
        price_observed_at = str(offer.get("priceObservedAt") or "").strip()
        if (
            kind == "SHIPS" and price is not None
            and price_type == "BASE_PRICE" and not price_observed_at
        ):
            # A manufacturer/global base value is useful in the selected-ship
            # panel, but it is not a purchase price observed at this market.
            price = None
            price_status = "UNKNOWN"
        elif price is None:
            price_status = "UNKNOWN"
        elif (
            kind == "MODULES" or price_type == "OBSERVED"
            or confidence == "OBSERVED" or price_observed_at
        ):
            price_status = "OBSERVED"
        elif price_type == "INFERRED":
            price_status = "ESTIMATED"
        else:
            price_status = "UNKNOWN" if kind == "SHIPS" else "REFERENCE"
        observed_at = str(
            price_observed_at
            or source.get("outfittingObservedAt" if kind == "MODULES" else "shipyardObservedAt")
            or source.get("observedAt") or ""
        )
        price_source = str(
            offer.get("priceSource") or source.get("priceSource") or source.get("source") or ""
        )
        arrival = source.get("distanceToArrivalLs")
        access = evaluate_station_access(system, commander_overview, permit_rules)
        if str(access_filter or "").upper() == "CONFIRMED ONLY" and access["accessRank"] > 1:
            continue
        projected.append({
            "marketId": source.get("marketId"),
            "system": system,
            "station": station,
            "stationType": str(source.get("stationType") or "UNKNOWN"),
            "landingPadSize": str(source.get("landingPadSize") or "UNKNOWN").upper(),
            "distanceLy": distance,
            "distanceKnown": distance is not None,
            "distanceToArrivalLs": arrival,
            "price": price,
            "priceKnown": price is not None,
            "priceStatus": price_status,
            "priceSource": price_source,
            "observedAt": observed_at,
            **access,
            "reason": "Availability observed"
                      + (f" · {price_status.lower()} price" if price_status != "UNKNOWN" else " · price unknown"),
        })
    projected.sort(key=lambda row: (
        row["accessRank"],
        0 if row["priceStatus"] == "OBSERVED" else
        1 if row["priceStatus"] == "ESTIMATED" else
        2 if row["priceKnown"] else 3,
        row["price"] if row["priceKnown"] else 10**18,
        row["distanceLy"] if row["distanceKnown"] else 10**9,
        float(row["distanceToArrivalLs"] or 10**12),
        row["system"].casefold(), row["station"].casefold(),
    ))
    return projected
