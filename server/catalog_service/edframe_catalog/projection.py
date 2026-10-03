from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from ed_companion.navigation.mining_commodities import mining_commodity_id
from ed_companion.navigation.mining_finder import project_eddn_mining_candidates
from ed_companion.navigation.hge import (
    extract_signal_finds,
    extract_system_bgs_snapshot,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def schema_name(payload: dict[str, Any]) -> str:
    value = str(payload.get("$schemaRef") or "").rstrip("/")
    parts = value.split("/")
    return "/".join(parts[-2:]).casefold() if len(parts) >= 2 else ""


def _message(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("message")
    return value if isinstance(value, dict) else {}


def _coordinates(value: Any) -> tuple[float | None, float | None, float | None]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None, None, None
    try:
        return float(value[0]), float(value[1]), float(value[2])
    except (TypeError, ValueError):
        return None, None, None


def _integer(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    result = str(value or "").strip()
    return result or None


def _list(value: Any) -> list[Any] | None:
    return list(value) if isinstance(value, list) else None


def _field(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None


def _landing_pad_size(message: dict[str, Any]) -> str | None:
    direct = _text(
        message.get("maxLandingPadSize")
        or message.get("MaxLandingPadSize")
        or message.get("LandingPadSize")
    )
    if direct:
        initial = direct[0].upper()
        return initial if initial in {"S", "M", "L"} else None
    pads = message.get("LandingPads")
    if not isinstance(pads, dict):
        return None
    for name, size in (("Large", "L"), ("Medium", "M"), ("Small", "S")):
        if (_integer(pads.get(name)) or 0) > 0:
            return size
    return None


def _station_faction(message: dict[str, Any]) -> str | None:
    faction = message.get("StationFaction")
    if isinstance(faction, dict):
        return _text(faction.get("Name") or faction.get("name"))
    return _text(faction)


def _station_economies(message: dict[str, Any]) -> list[dict[str, Any]] | None:
    source = message.get("economies") or message.get("StationEconomies")
    if not isinstance(source, list):
        return None
    rows = []
    for row in source:
        if not isinstance(row, dict):
            continue
        name = _text(row.get("name") or row.get("Name"))
        if not name:
            continue
        projected = {"name": name}
        proportion = _number(_field(row, "proportion", "Proportion"))
        if proportion is not None:
            projected["proportion"] = proportion
        rows.append(projected)
    return rows


def project_stations(
    payload: dict[str, Any], received_at: str,
) -> list[dict[str, Any]]:
    """Project anonymous public station facts from commodity or Journal frames."""
    schema = schema_name(payload)
    if schema not in {"commodity/3", "journal/1"}:
        return []
    message = _message(payload)
    event = str(message.get("event") or "")
    if schema == "journal/1" and event not in {"Docked", "Location", "CarrierJump"}:
        return []
    system = _text(message.get("systemName") or message.get("StarSystem"))
    station = _text(message.get("stationName") or message.get("StationName"))
    market_id = _integer(message.get("marketId") or message.get("MarketID"))
    if not system or not station or not market_id or market_id <= 0:
        return []
    station_type = _text(message.get("stationType") or message.get("StationType"))
    carrier_access = _text(
        message.get("carrierDockingAccess")
        or message.get("CarrierDockingAccess")
    )
    fleet_carrier = None
    if station_type or carrier_access:
        fleet_carrier = bool(
            (station_type and station_type.casefold() == "fleetcarrier")
            or carrier_access
        )
    primary_economy = _text(
        message.get("primaryEconomy")
        or message.get("StationEconomy")
    )
    return [{
        "market_id": market_id,
        "system_name": system,
        "station_name": station,
        "system_address": _integer(message.get("SystemAddress")),
        "station_type": station_type,
        "landing_pad_size": _landing_pad_size(message),
        "distance_to_arrival_ls": _number(message.get("DistFromStarLS")),
        "services": _list(message.get("StationServices")),
        "economies": _station_economies(message),
        "primary_economy": primary_economy,
        "government": _text(message.get("StationGovernment")),
        "controlling_faction": _station_faction(message),
        "fleet_carrier": fleet_carrier,
        "carrier_docking_access": carrier_access,
        "prohibited": _list(message.get("prohibited")),
        "observed_at": str(message.get("timestamp") or received_at),
        "received_at": received_at,
        "source": f"EDDN {schema}" + (f":{event}" if event else ""),
    }]


def project_system(payload: dict[str, Any]) -> dict[str, Any] | None:
    if schema_name(payload) != "journal/1":
        return None
    message = _message(payload)
    name = str(message.get("StarSystem") or "").strip()
    if not name:
        return None
    x, y, z = _coordinates(message.get("StarPos"))
    return {
        "name": name,
        "system_address": message.get("SystemAddress"),
        "x": x,
        "y": y,
        "z": z,
        "observed_at": str(message.get("timestamp") or utc_now()),
    }


def projected_systems(
    primary: dict[str, Any] | None,
    markets: list[dict[str, Any]],
    sites: list[dict[str, Any]],
    stations: Iterable[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Derive autocomplete/system rows from every accepted public message.

    Commodity frames do not carry coordinates, but their system name is still
    useful immediately.  A later Journal or ring observation enriches the same
    row without overwriting known coordinates with null values.
    """
    rows: dict[str, dict[str, Any]] = {}

    def retain(row: dict[str, Any]) -> None:
        name = str(row.get("name") or "").strip()
        if not name:
            return
        key = name.casefold()
        current = rows.get(key)
        if current is None:
            rows[key] = row
            return
        for field in ("system_address", "x", "y", "z"):
            if row.get(field) is not None:
                current[field] = row[field]
        if str(row.get("observed_at") or "") > str(current.get("observed_at") or ""):
            current["observed_at"] = row["observed_at"]

    if primary:
        retain(dict(primary))
    for site in sites:
        retain({
            "name": site.get("system_name"),
            "system_address": site.get("system_address"),
            "x": site.get("x"),
            "y": site.get("y"),
            "z": site.get("z"),
            "observed_at": site.get("observed_at"),
        })
    for market in markets:
        retain({
            "name": market.get("system_name"),
            "system_address": None,
            "x": None,
            "y": None,
            "z": None,
            "observed_at": market.get("observed_at"),
        })
    for station in stations:
        retain({
            "name": station.get("system_name"),
            "system_address": station.get("system_address"),
            "x": None,
            "y": None,
            "z": None,
            "observed_at": station.get("observed_at"),
        })
    return list(rows.values())


def project_markets(
    payload: dict[str, Any], received_at: str,
) -> list[dict[str, Any]]:
    if schema_name(payload) != "commodity/3":
        return []
    message = _message(payload)
    system = str(message.get("systemName") or "").strip()
    station = str(message.get("stationName") or "").strip()
    try:
        market_id = int(message.get("marketId") or 0)
    except (TypeError, ValueError):
        return []
    observed_at = str(message.get("timestamp") or received_at)
    if not system or not station or market_id <= 0:
        return []
    result = []
    for commodity in message.get("commodities") or []:
        if not isinstance(commodity, dict):
            continue
        identifier = mining_commodity_id(
            commodity.get("name") or commodity.get("Name")
        )
        if not identifier:
            continue
        mean_price = _integer(_field(commodity, "meanPrice", "MeanPrice"))
        buy_price = _integer(_field(commodity, "buyPrice", "BuyPrice"))
        stock = _integer(_field(commodity, "stock", "Stock"))
        stock_bracket = _integer(
            _field(commodity, "stockBracket", "StockBracket")
        )
        sell_price = _integer(_field(commodity, "sellPrice", "SellPrice"))
        demand = _integer(_field(commodity, "demand", "Demand"))
        demand_bracket = _integer(
            _field(commodity, "demandBracket", "DemandBracket")
        )
        if None in {mean_price, buy_price, stock, sell_price, demand}:
            continue
        result.append({
            "market_id": market_id,
            "commodity": identifier,
            "station_name": station,
            "system_name": system,
            "mean_price": max(0, mean_price),
            "buy_price": max(0, buy_price),
            "stock": max(0, stock),
            "stock_bracket": stock_bracket,
            "sell_price": max(0, sell_price),
            "demand": max(0, demand),
            "demand_bracket": demand_bracket,
            "status_flags": _list(
                _field(commodity, "statusFlags", "StatusFlags")
            ),
            "observed_at": observed_at,
            "received_at": received_at,
        })
    return result


def project_sites(
    payload: dict[str, Any], received_at: str,
) -> list[dict[str, Any]]:
    result = []
    for row in project_eddn_mining_candidates(payload, received_at):
        system = str(row.get("system") or "").strip()
        ring = str(row.get("ring") or row.get("body") or "").strip()
        if not system or not ring:
            continue
        coordinates = row.get("coordinates") or []
        x, y, z = _coordinates(coordinates)
        identity_source = "|".join((
            str(row.get("systemAddress") or system).casefold(),
            str(row.get("bodyId") or ""),
            ring.casefold(),
        ))
        result.append({
            "identity": hashlib.sha256(identity_source.encode("utf-8")).hexdigest(),
            "system_address": row.get("systemAddress"),
            "system_name": system,
            "x": x,
            "y": y,
            "z": z,
            "body_id": row.get("bodyId"),
            "body_name": str(row.get("body") or ""),
            "ring_name": ring,
            "ring_type": str(row.get("ringType") or ""),
            "reserve_level": str(row.get("reserveLevel") or ""),
            "distance_to_arrival_ls": row.get("distanceToArrivalLs"),
            "hotspots": json.dumps(row.get("hotspots") or []),
            "evidence": str(row.get("evidence") or "LIVE_REPORTED"),
            "source": str(row.get("source") or "EDDN"),
            "observed_at": str(row.get("observedAt") or received_at),
            "received_at": received_at,
        })
    return result


def _state_identity(system_address: Any, system_name: Any) -> str:
    address = _integer(system_address)
    if address is not None:
        return f"address:{address}"
    return f"name:{str(system_name or '').strip().casefold()}"


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def project_state_bgs_snapshot(
    payload: dict[str, Any], received_at: str,
) -> dict[str, Any] | None:
    """Project the complete public BGS subset for one system."""
    snapshot = extract_system_bgs_snapshot(payload, received_at)
    if not snapshot:
        return None
    system = str(snapshot.get("system") or "").strip()
    if not system:
        return None
    observations = [
        row for row in snapshot.get("observations") or []
        if isinstance(row, dict)
    ]
    return {
        "identity": _state_identity(snapshot.get("system_address"), system),
        "system_address": snapshot.get("system_address"),
        "system_name": system,
        "observed_at": str(snapshot.get("observed_at") or received_at),
        "received_at": received_at,
        "snapshot": json.dumps({
            "system": system,
            "system_address": snapshot.get("system_address"),
            "observed_at": str(snapshot.get("observed_at") or received_at),
            "observations": observations,
        }),
    }


def project_state_signals(
    payload: dict[str, Any], received_at: str,
) -> list[dict[str, Any]]:
    """Project only currently useful public signals with honest expiry."""
    result = []
    received = _timestamp(received_at) or datetime.now(timezone.utc)
    for observation in extract_signal_finds(payload, received_at):
        lifetime = max(0, _integer(observation.get("time_remaining")) or 0)
        observed = _timestamp(observation.get("signal_timestamp")) or received
        expires = observed + timedelta(seconds=lifetime)
        if lifetime <= 0 or expires <= received:
            continue
        identity_source = "|".join((
            _state_identity(
                observation.get("system_address"), observation.get("system")
            ),
            observed.isoformat(),
            str(observation.get("faction") or "").casefold(),
            str(observation.get("state") or "").casefold(),
            str(observation.get("find_type") or "").casefold(),
            str(observation.get("intensity") or "").casefold(),
        ))
        result.append({
            "identity": hashlib.sha256(
                identity_source.encode("utf-8")
            ).hexdigest(),
            "system_address": observation.get("system_address"),
            "system_name": str(observation.get("system") or "").strip(),
            "observed_at": observed.isoformat(),
            "received_at": received_at,
            "expires_at": expires.isoformat(),
            "observation": json.dumps(observation),
        })
    return result

