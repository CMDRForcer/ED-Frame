"""Conservative projection of an authenticated CAPI market to public EDDN facts."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime, timezone


CAPI_MARKET_MAX_AGE_SECONDS = 300
CAPI_MARKET_CONTEXT = {
    "gameversion": "CAPI-Live-market", "gamebuild": "",
    "schema_environment": "live",
}
_PRICE_FIELDS = (
    "meanPrice", "buyPrice", "stock", "stockBracket",
    "sellPrice", "demand", "demandBracket",
)


class FrontierMarketError(ValueError):
    """A public-safe reason why a response cannot be uploaded as a market."""


def market_timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def _positive_id(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _symbol(value):
    value = str(value or "").strip().casefold()
    if value.startswith("$") and value.endswith("_name;"):
        value = value[1:-6]
    return value if re.fullmatch(r"[a-z0-9_]+", value) else ""


def prepare_capi_market(profile_snapshot, market_snapshot, *, commander, context, now=None):
    """Reject ambiguous identity, absent inventories and partial rows, including on FCs.

    An explicit empty list is valid (orders were removed); an absent/null list
    is not. Never convert a failed or partial response into an empty market.
    """
    profile = (profile_snapshot or {}).get("payload")
    market = (market_snapshot or {}).get("payload")
    if not isinstance(profile, Mapping) or not isinstance(market, Mapping):
        raise FrontierMarketError("Frontier did not return a complete market document.")
    owner = profile.get("commander")
    owner = owner if isinstance(owner, Mapping) else {}
    if not commander or str(owner.get("name") or "").strip().casefold() != commander.strip().casefold():
        raise FrontierMarketError("Frontier account does not match the active Journal Commander.")
    if owner.get("docked") is not True:
        raise FrontierMarketError("Open the station market while docked, then refresh.")
    station = profile.get("lastStarport")
    station = station if isinstance(station, Mapping) else {}
    last_system = profile.get("lastSystem")
    last_system = last_system if isinstance(last_system, Mapping) else {}
    system = str(last_system.get("name") or "").strip()
    market_id = _positive_id(market.get("id"))
    if (not market_id or market_id != _positive_id(station.get("id"))
            or market_id != _positive_id(context.get("MarketID"))
            or not system or system.casefold() != str(context.get("StarSystem") or "").strip().casefold()):
        raise FrontierMarketError("Frontier market does not match the active Journal station.")
    name = str(market.get("name") or "").strip()
    if not name:
        raise FrontierMarketError("Frontier market station name is missing.")
    observed = market_timestamp(market_snapshot.get("observedAt"))
    profile_at = market_timestamp(profile_snapshot.get("observedAt"))
    current = now or datetime.now(timezone.utc)
    if (observed is None or profile_at is None
            or not -120 <= (current - observed).total_seconds() <= CAPI_MARKET_MAX_AGE_SECONDS
            or abs((observed - profile_at).total_seconds()) > CAPI_MARKET_MAX_AGE_SECONDS):
        raise FrontierMarketError("Frontier market timestamp is missing or too old; refresh again.")
    trigger = context.get("marketContext") or {}
    trigger = trigger if isinstance(trigger, Mapping) else {}
    journal_at = market_timestamp(trigger.get("timestamp"))
    if trigger.get("MarketID") == market_id and journal_at and journal_at > observed:
        raise FrontierMarketError("A newer Journal market is already available.")
    items = market.get("commodities")
    if not isinstance(items, list):
        raise FrontierMarketError("Frontier market inventory is unavailable; no empty market was sent.")
    commodities, prohibited, seen = [], set(), set()
    for item in items:
        if not isinstance(item, Mapping):
            raise FrontierMarketError("Frontier market contains an incomplete commodity row.")
        symbol = _symbol(item.get("name"))
        if not symbol or symbol in seen:
            raise FrontierMarketError("Frontier market contains an invalid or duplicate commodity.")
        seen.add(symbol)
        if item.get("legality"):
            prohibited.add(symbol)
            continue
        if "nonmarketable" in str(item.get("categoryname") or "").casefold():
            continue
        row = {"name": symbol}
        for field in _PRICE_FIELDS:
            value = item.get(field)
            if (isinstance(value, bool) or not isinstance(value, (float, int))
                    or not math.isfinite(value) or value < 0
                    or (field.endswith("Bracket") and (value != int(value) or value > 3))):
                raise FrontierMarketError("Frontier market contains incomplete price or quantity data.")
            row[field] = int(value)
        raw_flags = item.get("statusFlags")
        raw_flags = raw_flags if isinstance(raw_flags, list) else []
        flags = [flag for flag in ("Producer", "Consumer", "Rare") if flag in raw_flags]
        if flags:
            row["statusFlags"] = flags
        commodities.append(row)
    message = {
        "timestamp": observed.isoformat().replace("+00:00", "Z"),
        "systemName": system, "stationName": name, "marketId": market_id,
        "commodities": sorted(commodities, key=lambda row: row["name"]),
    }
    for field in ("horizons", "odyssey"):
        if isinstance(context.get(field), bool):
            message[field] = context[field]
    if context.get("StationType"):
        message["stationType"] = str(context["StationType"])
    if context.get("CarrierDockingAccess"):
        message["carrierDockingAccess"] = str(context["CarrierDockingAccess"])
    values = market.get("prohibited")
    for value in values.values() if isinstance(values, Mapping) else values if isinstance(values, list) else []:
        if isinstance(value, str) and (symbol := _symbol(value)):
            prohibited.add(symbol)
    if prohibited:
        message["prohibited"] = sorted(prohibited)
    return {"schema": "commodity/3", "message": message}


def market_content_key(prepared):
    """Economic contents, independent of timestamps and source-specific flags."""
    message = prepared.get("message") or {}
    rows = [{field: row.get(field) for field in ("name", *_PRICE_FIELDS)}
            for row in message.get("commodities") or []]
    content = {"marketId": message.get("marketId"),
               "system": str(message.get("systemName") or "").casefold(),
               "commodities": sorted(rows, key=lambda row: str(row.get("name")))}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def market_summary(prepared):
    message = prepared.get("message") or {}
    items = message.get("commodities") or []
    return {"station": message.get("stationName", ""),
            "observedAt": message.get("timestamp", ""),
            "marketId": message.get("marketId"), "commodities": len(items),
            "stockOrders": sum(row.get("stock", 0) > 0 for row in items),
            "demandOrders": sum(row.get("demand", 0) > 0 for row in items)}
