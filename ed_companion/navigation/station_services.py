"""Read-only regional station services from our public catalog."""
from datetime import datetime, timezone
import math
from .mining_market import EDFRAME_CATALOG_BASE, MiningMarketError
from .shipyard_finder import evaluate_station_access
from .state_find_catalog import state_find_region

# Values are the actual public StationServices identifiers, not trader subtypes.
SERVICES = (
    ("repair", "Repair"), ("refuel", "Refuel"), ("rearm", "Restock"),
    ("facilitator", "Interstellar Factors"), ("commodities", "Commodity market"),
    ("outfitting", "Outfitting"), ("shipyard", "Shipyard"),
    ("materialtrader", "Material trader · type unknown"),
    ("techBroker", "Technology broker · type unknown"),
    ("exploration", "Universal Cartographics"), ("vistagenomics", "Vista Genomics"),
    ("blackmarket", "Black market"),
)


def fetch_station_services(*, origin, service, radius_ly=100, pad="ANY",
                           exclude_carriers=True, get, timeout=20):
    region = state_find_region(origin, radius_ly)
    if not region or service not in dict(SERVICES) or pad not in {"ANY", "S", "M", "L"}:
        raise MiningMarketError("Invalid station-service search")
    params = dict(zip(("x", "y", "z"), region["origin"]))
    params.update(service=service, max_distance=radius_ly,
                  exclude_fleet_carriers=exclude_carriers, limit=100)
    if pad != "ANY":
        params["landing_pad"] = pad
    response = get(EDFRAME_CATALOG_BASE + "/v1/stations/nearby", params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise MiningMarketError("Invalid station-service response")
    if payload.get("region") != region:
        raise MiningMarketError("Server did not confirm station-service search region")
    rows = []
    ranks = {"S": 1, "M": 2, "L": 3}
    for item in payload["results"]:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        try:
            distance = float(row["distanceLy"])
        except (KeyError, TypeError, ValueError):
            continue
        services = row.get("services") or []
        if not isinstance(services, list) or service.casefold() not in {str(s).casefold() for s in services}:
            continue
        if not math.isfinite(distance) or not 0 <= distance <= float(radius_ly):
            continue
        if pad != "ANY" and ranks.get(row.get("landingPadSize"), 0) < ranks[pad]:
            continue
        if exclude_carriers and row.get("fleetCarrier"):
            continue
        row["distanceLy"] = distance
        rows.append(row)
    return {**payload, "results": rows}


def describe_station_services(rows, overview=None, permit_rules=None, now=None):
    now = now or datetime.now(timezone.utc)
    result = []
    for item in rows:
        row = {**item, **evaluate_station_access(item.get("system"), overview, permit_rules)}
        try:
            stamp = datetime.fromisoformat(str(row.get("observedAt")).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("Timezone missing")
            age = max(0, (now - stamp).total_seconds())
            row["ageHours"] = round(age / 3600, 1)
        except (TypeError, ValueError):
            row["ageHours"] = None
        # Carrier policy is not commander-specific docking permission.
        row["carrierWarning"] = bool(row.get("fleetCarrier"))
        result.append(row)
    return result
