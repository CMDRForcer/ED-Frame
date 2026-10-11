"""Commodity catalog labels and observed station/carrier quotes, no guesses."""
import json
import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from .mining_market import EDFRAME_CATALOG_BASE, MiningMarketError
from .state_find_catalog import state_find_region
from .station_services import describe_station_services


# These trade categories also contain mined and mission-reward commodities.
# Ordinary stations need not sell them: actual price and stock/demand observations
# determine offers, including player-run carrier markets.
STANDARD_MARKET_CATEGORIES = frozenset({
    "Chemicals", "Consumer Items", "Legal Drugs", "Foods", "Industrial Materials",
    "Machinery", "Medicines", "Metals", "Minerals", "Slavery", "Technology",
    "Textiles", "Waste", "Weapons",
})


def is_trade_commodity(symbol, reference):
    known = reference.get(str(symbol).strip().lower(), {})
    # Rare goods are a positive purchase reference, including rare items whose
    # broad cargo category happens to be Salvage.
    return bool(known.get("rare") or known.get("category") in STANDARD_MARKET_CATEGORIES)


@lru_cache(maxsize=1)
def commodity_reference():
    try:
        folder = Path(__file__).resolve().parents[2] / "ed_data"
        known = json.loads((folder / "commodity_reference.json").read_text(encoding="utf-8"))["commodities"]
        known.update(json.loads((folder / "rare_commodity_reference.json").read_text(encoding="utf-8")))
        return known
    except (OSError, ValueError, KeyError):
        return {}


def commodity_search_region(origin, radius=100):
    """Keep origin identity even when zero selects a search without a radius."""
    region = state_find_region(origin, 100 if radius == 0 else radius)
    if region is not None and radius == 0:
        region["radiusLy"] = None
    return region


def fetch_commodity_catalog(*, get, timeout=20):
    response = get(EDFRAME_CATALOG_BASE + "/v1/catalog/commodities", timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise MiningMarketError("Invalid commodity catalog")
    reference = commodity_reference()
    rows = []
    for symbol in sorted({str(s).strip().lower() for s in payload["results"] if isinstance(s, str) and s.strip()}):
        known = reference.get(symbol, {})
        if not is_trade_commodity(symbol, reference):
            continue
        rows.append({"id": symbol, "name": known.get("name") or symbol,
                     "category": "Rare Goods" if known.get("rare") else known["category"],
                     "tradeCategory": known["category"], "rare": bool(known.get("rare"))})
    return sorted(rows, key=lambda r: (r["name"].casefold(), r["id"]))


def fetch_commodity_offers(*, commodity, direction, origin, radius=100, quantity=1,
                           age_hours=24, pad="ANY", exclude_carriers=False, commodities=None,
                           sort_by="PRICE", get, timeout=20):
    region = commodity_search_region(origin, radius)
    commodity = str(commodity).strip().lower()
    if (not region or direction not in {"BUY", "SELL"} or pad not in {"ANY", "S", "M", "L"}
            or not 2 <= len(commodity) <= 80 or not 1 <= quantity <= 1000000
            or not 1 <= age_hours <= 2160 or sort_by not in {"PRICE", "DISTANCE", "AGE"}):
        raise MiningMarketError("Invalid commodity search")
    reference = commodity_reference()
    symbols = sorted(set(commodities or [])) if commodity == "all_rare_goods" else [commodity]
    if (not symbols or len(symbols) > 200
            or any(not isinstance(s, str) or not is_trade_commodity(s, reference)
                   or (commodity == "all_rare_goods" and not reference.get(s, {}).get("rare")) for s in symbols)):
        raise MiningMarketError("Commodity is not a recognized trade commodity")
    params = dict(zip(("x", "y", "z"), region["origin"]))
    params.update(commodity=commodity, direction=direction, max_distance=region["radiusLy"] or 0,
                  min_quantity=quantity, max_age_hours=age_hours, limit=100,
                  exclude_fleet_carriers=exclude_carriers, sort_by=sort_by)
    if pad != "ANY":
        params["landing_pad"] = pad
    if commodity == "all_rare_goods":
        params["commodities"] = ",".join(symbols)
    response = get(EDFRAME_CATALOG_BASE + "/v1/markets/commodity-offers", params=params, timeout=timeout)
    if region["radiusLy"] is None and getattr(response, "status_code", None) == 422:
        raise MiningMarketError("Unlimited search requires a catalog server update · choose a finite radius")
    response.raise_for_status()
    payload = response.json()
    if (not isinstance(payload, dict) or not isinstance(payload.get("results"), list)
            or payload.get("direction") != direction or payload.get("commodity") != commodity
            or payload.get("region") != region):
        raise MiningMarketError("Server did not confirm commodity search")
    if payload.get("sortBy", "PRICE") != sort_by:
        raise MiningMarketError("Server did not confirm sorting · catalog server update required")
    if commodity == "all_rare_goods" and payload.get("commodities") != symbols:
        raise MiningMarketError("Server did not confirm rare goods group")
    price_field, amount_field = ("buyPrice", "stock") if direction == "BUY" else ("sellPrice", "demand")
    ranks = {"S": 1, "M": 2, "L": 3}
    rows = []
    for item in payload["results"]:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        try:
            price, amount = int(row[price_field]), int(row[amount_field])
            distance = float(row["distanceLy"])
            observed = datetime.fromisoformat(str(row["observedAt"]).replace("Z", "+00:00"))
            if observed.tzinfo is None:
                continue
            elapsed = (datetime.now(timezone.utc) - observed).total_seconds() / 3600
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if (price <= 0 or amount < quantity or not 0 <= elapsed <= age_hours or not math.isfinite(distance)
                or distance < 0 or (region["radiusLy"] is not None and distance > region["radiusLy"])
                or row.get("commodity") not in symbols):
            continue
        if pad != "ANY" and ranks.get(row.get("landingPadSize"), 0) < ranks[pad]:
            continue
        if exclude_carriers and row.get("fleetCarrier"):
            continue
        row.update(price=price, quantity=amount, direction=direction)
        rows.append(row)
    return {**payload, "results": rows}


def describe_commodity_offers(rows, overview=None, permit_rules=None):
    reference = commodity_reference()
    result = describe_station_services([
        row for row in rows if is_trade_commodity(row.get("commodity"), reference)
    ], overview, permit_rules)
    for row in result:
        row["commodityName"] = reference.get(row.get("commodity"), {}).get("name") or row.get("commodity", "")
        prohibited = row.get("prohibited")
        row["knownProhibited"] = isinstance(prohibited, list) and row.get("commodity", "").casefold() in {
            str(value).casefold() for value in prohibited
        }
    return result
