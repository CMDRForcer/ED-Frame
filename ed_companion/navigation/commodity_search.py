"""Commodity catalog labels and bounded observed station quotes, no guesses."""
import json
import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from .mining_market import EDFRAME_CATALOG_BASE, MiningMarketError
from .state_find_catalog import state_find_region
from .station_services import describe_station_services


# Normal station-market purchases only. Sell-only mining commodities, mission
# rewards, salvage and other cargo remain in the database for other finders.
STANDARD_MARKET_CATEGORIES = frozenset({
    "Chemicals", "Consumer Items", "Legal Drugs", "Foods", "Industrial Materials",
    "Machinery", "Medicines", "Metals", "Minerals", "Slavery", "Technology",
    "Textiles", "Waste", "Weapons",
})
NON_PURCHASABLE_CARGO = frozenset({
    "hydrogenperoxide", "rockforthfertiliser", "helium", "helium3", "bootlegliquor",
    "curatedcommodity", "articulationmotors", "modularterminals", "trinketsoffortune",
    "nanobreakers", "telemetrysuite", "microcontrollers", "diagnosticsensor",
    "hafnium178", "iridium", "osmium", "platinum", "praseodymium", "samarium",
    "alexandrite", "bastnasite", "benitoite", "bromellite", "deuterium", "diamond",
    "grandidierite", "jadeite", "lithiumhydroxide", "lowtemperaturediamond",
    "magnesite", "methaneclathrate", "methanolmonohydratecrystals", "moissanite",
    "monazite", "musgravite", "olivine", "painite", "periclasedunite",
    "quartzpyroxenite", "rhodplumsite", "ruby", "sapphire", "serendibite",
    "taaffeite", "thortveitite", "opal",
})


def is_standard_market_commodity(symbol, reference):
    known = reference.get(str(symbol).strip().lower(), {})
    # Rare goods are a positive purchase reference, including rare items whose
    # broad cargo category happens to be Salvage.
    return bool(known.get("rare") or (
        known.get("category") in STANDARD_MARKET_CATEGORIES
        and str(symbol).strip().lower() not in NON_PURCHASABLE_CARGO
    ))


@lru_cache(maxsize=1)
def commodity_reference():
    try:
        folder = Path(__file__).resolve().parents[2] / "ed_data"
        known = json.loads((folder / "commodity_reference.json").read_text(encoding="utf-8"))["commodities"]
        known.update(json.loads((folder / "rare_commodity_reference.json").read_text(encoding="utf-8")))
        return known
    except (OSError, ValueError, KeyError):
        return {}


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
        if not is_standard_market_commodity(symbol, reference):
            continue
        rows.append({"id": symbol, "name": known.get("name") or symbol,
                     "category": "Rare Goods" if known.get("rare") else known["category"],
                     "tradeCategory": known["category"], "rare": bool(known.get("rare"))})
    return sorted(rows, key=lambda r: (r["name"].casefold(), r["id"]))


def fetch_commodity_offers(*, commodity, direction, origin, radius=100, quantity=1,
                           age_hours=24, pad="ANY", exclude_carriers=True, commodities=None, get, timeout=20):
    region = state_find_region(origin, radius)
    commodity = str(commodity).strip().lower()
    if (not region or direction not in {"BUY", "SELL"} or pad not in {"ANY", "S", "M", "L"}
            or not 2 <= len(commodity) <= 80 or not 1 <= quantity <= 1000000
            or not 1 <= age_hours <= 2160):
        raise MiningMarketError("Invalid commodity search")
    reference = commodity_reference()
    symbols = sorted(set(commodities or [])) if commodity == "all_rare_goods" else [commodity]
    if (not symbols or len(symbols) > 200
            or any(not isinstance(s, str) or not is_standard_market_commodity(s, reference)
                   or (commodity == "all_rare_goods" and not reference.get(s, {}).get("rare")) for s in symbols)):
        raise MiningMarketError("Commodity is not a normal station-market purchase")
    params = dict(zip(("x", "y", "z"), region["origin"]))
    params.update(commodity=commodity, direction=direction, max_distance=radius,
                  min_quantity=quantity, max_age_hours=age_hours, limit=100,
                  exclude_fleet_carriers=exclude_carriers)
    if pad != "ANY":
        params["landing_pad"] = pad
    if commodity == "all_rare_goods":
        params["commodities"] = ",".join(symbols)
    response = get(EDFRAME_CATALOG_BASE + "/v1/markets/commodity-offers", params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if (not isinstance(payload, dict) or not isinstance(payload.get("results"), list)
            or payload.get("direction") != direction or payload.get("commodity") != commodity
            or payload.get("region") != region):
        raise MiningMarketError("Server did not confirm commodity search")
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
                or not 0 <= distance <= radius or row.get("commodity") not in symbols):
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
        row for row in rows if is_standard_market_commodity(row.get("commodity"), reference)
    ], overview, permit_rules)
    for row in result:
        row["commodityName"] = reference.get(row.get("commodity"), {}).get("name") or row.get("commodity", "")
        prohibited = row.get("prohibited")
        row["knownProhibited"] = isinstance(prohibited, list) and row.get("commodity", "").casefold() in {
            str(value).casefold() for value in prohibited
        }
    return result
