"""Pure scoring for the unified Mining Finder.

The planner never invents market or Powerplay facts.  Missing observations
remain explicitly unknown and therefore cannot earn profit or merit stars.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import sqrt
from typing import Any, Iterable

from .mining_commodities import mining_commodity_id, mining_commodity_name
from .mining_finder import is_belt_candidate


OPTIMIZE_MERITS = "POWERPLAY MERITS"
OPTIMIZE_YIELD = "BEST YIELD"
OPTIMIZE_PROFIT = "HIGHEST PROFIT"
OPTIMIZE_DISTANCE = "SHORTEST ROUTE"
OPTIMIZATION_MODES = (
    OPTIMIZE_MERITS,
    OPTIMIZE_YIELD,
    OPTIMIZE_PROFIT,
    OPTIMIZE_DISTANCE,
)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _timestamp(value: Any) -> datetime | None:
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


def _stars(value: float | None) -> str:
    if value is None:
        return "—"
    rounded = max(0, min(5, int(round(value))))
    return "★" * rounded + "☆" * (5 - rounded)


def _reserve_score(value: Any) -> float:
    text = str(value or "").casefold()
    if "pristine" in text:
        return 5.0
    if "major" in text:
        return 4.0
    if "common" in text:
        return 3.0
    if "low" in text:
        return 2.0
    if "depleted" in text:
        return 1.0
    return 2.5


def _yield_score(row: dict[str, Any]) -> float:
    target = str(row.get("targetMatch") or "")
    base = {
        "LOCAL_YIELD": 5.0,
        "HOTSPOT": 4.5,
        "PLANETARY_MINING_LOCATION": 3.5,
        "RING_TYPE": 2.5,
        "ANY": 2.0,
    }.get(target, 2.0)
    reserve = _reserve_score(row.get("reserveLevel") or row.get("reserveName"))
    return max(1.0, min(5.0, base * 0.75 + reserve * 0.25))


def _data_score(row: dict[str, Any]) -> float:
    evidence = str(row.get("sourceEvidence") or row.get("evidence") or "")
    base = {
        "LOCAL_CONFIRMED": 5.0,
        "LIVE_REPORTED": 4.0,
        "CATALOG_CANDIDATE": 3.0,
    }.get(evidence, 2.0)
    if row.get("stale"):
        base -= 1.5
    if not row.get("observedAt"):
        base -= 0.5
    return max(1.0, min(5.0, base))


def _market_rows(
    row: dict[str, Any], commodity_id: str,
    shared_markets: Iterable[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    rows = [
        *(row.get("markets") or []),
        *(shared_markets or []),
    ]
    result = []
    all_commodities = commodity_id in {"", "allcommodities"}
    for market in rows if isinstance(rows, list) else []:
        if not isinstance(market, dict):
            continue
        market_commodity = mining_commodity_id(
            market.get("commodity") or market.get("name")
        )
        if not all_commodities and market_commodity != commodity_id:
            continue
        projected = dict(market)
        projected["commodity"] = market_commodity
        projected["sellPrice"] = max(0, int(_number(
            market.get("sellPrice") or market.get("sell_price")
        )))
        projected["demand"] = max(0, int(_number(market.get("demand"))))
        projected["demandInfinite"] = bool(market.get("demandInfinite"))
        projected["observedAt"] = str(
            market.get("observedAt") or market.get("updateTime") or ""
        )
        projected["station"] = str(
            market.get("station") or market.get("stationName") or ""
        )
        projected["system"] = str(
            market.get("system") or row.get("system") or ""
        )
        result.append(projected)
    if not result and any(key in row for key in ("sellPrice", "demand", "station")):
        result.append({
            "commodity": commodity_id,
            "sellPrice": max(0, int(_number(row.get("sellPrice")))),
            "demand": max(0, int(_number(row.get("demand")))),
            "observedAt": str(row.get("marketObservedAt") or ""),
            "station": str(row.get("station") or ""),
            "system": str(row.get("sellSystem") or row.get("system") or ""),
            "landingPadSize": str(row.get("landingPadSize") or ""),
            "controllingPower": str(row.get("controllingPower") or ""),
            "powerState": str(row.get("powerState") or ""),
            "distanceToArrivalLs": row.get("stationDistanceLs"),
        })
    return result


def _pad_matches(market: dict[str, Any], requested: str) -> bool:
    requested = str(requested or "ANY").upper()
    if requested in {"", "ANY"}:
        return True
    actual = str(
        market.get("landingPadSize") or market.get("landing_pad_size") or ""
    ).upper()
    if not actual:
        return False
    ranks = {
        "1": 1, "S": 1, "SMALL": 1,
        "2": 2, "M": 2, "MEDIUM": 2,
        "3": 3, "L": 3, "LARGE": 3,
    }
    return ranks.get(actual, 0) >= ranks.get(requested, 0)


def _market_is_fresh(
    market: dict[str, Any], max_age_hours: int, now: datetime,
) -> tuple[bool, int | None]:
    observed = _timestamp(market.get("observedAt"))
    if observed is None:
        return False, None
    age = max(0, int((now - observed).total_seconds()))
    return max_age_hours <= 0 or age <= max_age_hours * 3600, age


def _eligible_markets(
    markets: Iterable[dict[str, Any]], *, landing_pad: str,
    min_demand: int, max_demand: int, max_market_age_hours: int,
    now: datetime, enforce_age: bool = True,
    enforce_demand: bool = True,
) -> list[dict[str, Any]]:
    """Apply query-wide market filters once instead of once per ring."""
    result = []
    for source in markets or []:
        if not isinstance(source, dict) or source.get("fleetCarrier") is True \
                or not _pad_matches(source, landing_pad):
            continue
        market = dict(source)
        fresh, age = _market_is_fresh(market, max_market_age_hours, now)
        market["fresh"] = fresh
        market["ageSeconds"] = age
        demand = int(market.get("demand", 0) or 0)
        demand_matches = bool(market.get("demandInfinite")) or (
            demand >= max(0, int(min_demand or 0))
            and (
                max(0, int(max_demand or 0)) <= 0
                or demand <= int(max_demand)
            )
        )
        market["matchesAge"] = fresh
        market["matchesDemand"] = demand_matches
        market["matchesFilters"] = fresh and demand_matches
        if enforce_age and max_market_age_hours > 0 and not fresh:
            continue
        if enforce_demand and not demand_matches:
            continue
        result.append(market)
    return result


def market_filter_diagnostics(
    markets: Iterable[dict[str, Any]], commodity: str, *, landing_pad: str,
    min_demand: int, max_demand: int, max_market_age_hours: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Explain globally why verified market rows do or do not qualify."""
    now = now or datetime.now(timezone.utc)
    commodity_id = mining_commodity_id(commodity)
    projected = _market_rows({}, commodity_id, markets)
    eligible = _eligible_markets(
        projected,
        landing_pad=landing_pad,
        min_demand=min_demand,
        max_demand=max_demand,
        max_market_age_hours=max_market_age_hours,
        now=now,
    )
    rejected_pad = 0
    rejected_age = 0
    rejected_min_demand = 0
    rejected_max_demand = 0
    ages = []
    for market in projected:
        if not _pad_matches(market, landing_pad):
            rejected_pad += 1
        fresh, age = _market_is_fresh(
            market, max_market_age_hours, now,
        )
        if age is not None:
            ages.append(age)
        if max_market_age_hours > 0 and not fresh:
            rejected_age += 1
        demand = int(market.get("demand", 0) or 0)
        if not market.get("demandInfinite"):
            if demand < max(0, int(min_demand or 0)):
                rejected_min_demand += 1
            if max(0, int(max_demand or 0)) > 0 and demand > int(max_demand):
                rejected_max_demand += 1

    total = len(projected)
    eligible_count = len(eligible)
    if not total:
        summary = "NO VERIFIED SELL MARKETS LOADED"
        reason = "NO_DATA"
    elif eligible_count:
        summary = (
            f"{total} VERIFIED SELL MARKETS · "
            f"{eligible_count} MATCH ACTIVE FILTERS"
        )
        reason = "MATCHES"
    elif rejected_age == total:
        summary = (
            f"{total} VERIFIED SELL MARKETS · 0 MATCH · ALL OUTSIDE "
            f"THE {max_market_age_hours} H AGE LIMIT"
        )
        reason = "AGE"
    elif rejected_pad == total:
        summary = (
            f"{total} VERIFIED SELL MARKETS · 0 MATCH · "
            f"NONE SUPPORT {str(landing_pad or 'ANY').upper()} PAD"
        )
        reason = "PAD"
    elif rejected_min_demand == total:
        summary = (
            f"{total} VERIFIED SELL MARKETS · 0 MATCH · "
            f"ALL BELOW {max(0, int(min_demand or 0)):,} T DEMAND"
        )
        reason = "MIN_DEMAND"
    elif rejected_max_demand == total:
        summary = (
            f"{total} VERIFIED SELL MARKETS · 0 MATCH · "
            f"ALL ABOVE {max(0, int(max_demand or 0)):,} T DEMAND"
        )
        reason = "MAX_DEMAND"
    else:
        summary = (
            f"{total} VERIFIED SELL MARKETS · 0 MATCH ACTIVE FILTERS · "
            f"AGE {rejected_age} · PAD {rejected_pad} · "
            f"LOW DEMAND {rejected_min_demand} · "
            f"HIGH DEMAND {rejected_max_demand}"
        )
        reason = "COMBINED"
    return {
        "total": total,
        "eligible": eligible_count,
        "excludedByAge": rejected_age,
        "excludedByPad": rejected_pad,
        "excludedByMinDemand": rejected_min_demand,
        "excludedByMaxDemand": rejected_max_demand,
        "freshestAgeSeconds": min(ages) if ages else None,
        "reason": reason,
        "summary": summary,
    }


def _market_sort_key(market: dict[str, Any], optimization: str) -> tuple:
    if optimization == OPTIMIZE_MERITS:
        merit_score = market.get("meritScore")
        verification_rank = (
            0 if _number(merit_score, -1.0) > 0
            else 1 if merit_score is None
            else 2
        )
        return (
            verification_rank,
            not bool(market.get("matchesFilters")),
            -_number(merit_score),
            -int(market.get("sellPrice", 0) or 0),
            -int(market.get("demand", 0) or 0),
        )
    if optimization == OPTIMIZE_DISTANCE:
        return (
            market.get("distanceToArrivalLs") is None,
            _number(market.get("distanceToArrivalLs"), float("inf")),
            -int(market.get("sellPrice", 0) or 0),
        )
    return (
        -int(market.get("sellPrice", 0) or 0),
        -int(market.get("demand", 0) or 0),
    )


def _spatial_cell(coordinates: Any, size: float = 30.0) -> tuple[int, int, int] | None:
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 3:
        return None
    try:
        return tuple(int(float(value) // size) for value in coordinates)
    except (TypeError, ValueError):
        return None


def _candidate_commodity_ids(
    row: dict[str, Any], requested: str,
) -> list[str]:
    """Return concrete mineable commodities in evidence-preference order."""
    cached = row.get("_candidateCommodityIds")
    if isinstance(cached, list):
        return cached
    requested_id = mining_commodity_id(requested)
    if requested_id not in {"", "allcommodities"}:
        return [requested_id]
    result = []
    seen = set()
    sources = [
        *(row.get("candidateCommodities") or []),
        *(row.get("yieldStats") or []),
        *(row.get("hotspots") or []),
    ]
    for source in sources:
        value = source.get("id") or source.get("commodity") \
            if isinstance(source, dict) else source
        commodity_id = mining_commodity_id(value)
        if commodity_id and commodity_id != "allcommodities" \
                and commodity_id not in seen:
            result.append(commodity_id)
            seen.add(commodity_id)
    return result


def _same_market_location(
    left: dict[str, Any], right: dict[str, Any],
) -> bool:
    """Return whether two observations describe the same sell station."""
    if not left or not right:
        return False
    left_market = int(_number(left.get("marketId")))
    right_market = int(_number(right.get("marketId")))
    if left_market > 0 and right_market > 0:
        return left_market == right_market
    return (
        _system_key(left.get("system")) == _system_key(right.get("system"))
        and str(left.get("station") or "").strip().casefold()
        == str(right.get("station") or "").strip().casefold()
        and bool(str(left.get("station") or "").strip())
    )


def _market_station_key(market: dict[str, Any]) -> tuple[str, str] | None:
    system = _system_key(market.get("system"))
    station = str(market.get("station") or "").strip().casefold()
    return (system, station) if system and station else None


def _secondary_resources(
    row: dict[str, Any], primary_commodity: str,
    route_market: dict[str, Any], eligible_markets: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build evidence-backed secondary resources and same-station sales.

    Ring-type possibilities are deliberately excluded: MORE RESOURCES must
    only claim a secondary commodity when a hotspot or local Journal sample
    actually supports it. Market facts are attached only when the selected
    sell station has a qualifying observation for that exact commodity.
    """
    primary_id = mining_commodity_id(primary_commodity)
    resources: dict[str, dict[str, Any]] = {}

    def resource(identifier: str) -> dict[str, Any]:
        return resources.setdefault(identifier, {
            "id": identifier,
            "name": mining_commodity_name(identifier),
            "hotspot": False,
            "localYield": False,
            "prospectorHits": 0,
            "refinedCount": 0,
            "averageProportion": None,
        })

    for source in row.get("yieldStats") or []:
        if not isinstance(source, dict):
            continue
        identifier = mining_commodity_id(source.get("commodity"))
        if not identifier or identifier == primary_id:
            continue
        item = resource(identifier)
        item["localYield"] = True
        item["prospectorHits"] = max(
            int(item["prospectorHits"]),
            int(_number(source.get("prospectorHits"))),
        )
        item["refinedCount"] = max(
            int(item["refinedCount"]),
            int(_number(source.get("refinedCount"))),
        )
        proportion = source.get("averageProportion")
        if proportion is not None:
            item["averageProportion"] = max(
                _number(item.get("averageProportion")), _number(proportion),
            )

    for source in row.get("hotspots") or []:
        if not isinstance(source, dict):
            continue
        identifier = mining_commodity_id(source.get("commodity"))
        if not identifier or identifier == primary_id:
            continue
        resource(identifier)["hotspot"] = True

    markets_by_commodity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if route_market:
        for source in eligible_markets or []:
            if not isinstance(source, dict) or not _same_market_location(
                source, route_market,
            ):
                continue
            identifier = mining_commodity_id(source.get("commodity"))
            if identifier:
                markets_by_commodity[identifier].append(source)

    result = []
    for identifier, item in resources.items():
        evidence = []
        if item["localYield"]:
            evidence.append("LOCAL YIELD")
        if item["hotspot"]:
            evidence.append("HOTSPOT")
        matching_markets = markets_by_commodity.get(identifier, [])
        matching_markets.sort(key=lambda market: (
            -int(market.get("sellPrice", 0) or 0),
            -int(market.get("demand", 0) or 0),
        ))
        market = matching_markets[0] if matching_markets else {}
        item.update({
            "evidence": evidence,
            "evidenceLabel": " + ".join(evidence),
            "marketKnown": bool(market),
            "sellPrice": int(market.get("sellPrice", 0) or 0),
            "demand": int(market.get("demand", 0) or 0),
            "demandInfinite": bool(market.get("demandInfinite")),
            "marketAgeSeconds": market.get("ageSeconds"),
        })
        result.append(item)

    result.sort(key=lambda item: (
        not bool(item.get("localYield")),
        not bool(item.get("hotspot")),
        str(item.get("name") or "").casefold(),
    ))
    return result


def _power_key(value: Any) -> str:
    key = str(value or "").strip().casefold()
    aliases = {
        "arissa lavigny-duval": "a. lavigny-duval",
        "a lavigny-duval": "a. lavigny-duval",
    }
    return aliases.get(key, key)


def _system_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def _coordinate_distance(left: Any, right: Any) -> float | None:
    if not (
        isinstance(left, (list, tuple)) and len(left) == 3
        and isinstance(right, (list, tuple)) and len(right) == 3
    ):
        return None
    try:
        return sqrt(sum(
            (float(a) - float(b)) ** 2 for a, b in zip(left, right)
        ))
    except (TypeError, ValueError):
        return None


def _powerplay_index(
    rows: Iterable[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    result = {}
    for source in rows or []:
        if not isinstance(source, dict):
            continue
        system = _system_key(source.get("system") or source.get("name"))
        power = _power_key(source.get("power") or source.get("controllingPower"))
        if system and power:
            result[(system, power)] = dict(source)
    return result


def _candidate_power_fact(
    candidate: dict[str, Any], power: str,
    catalog: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    system = _system_key(candidate.get("system"))
    fact = dict(catalog.get((system, _power_key(power))) or {})
    controlling = str(candidate.get("controllingPower") or "").strip()
    state = str(candidate.get("powerState") or "").strip()
    if controlling:
        fact["controllingPower"] = controlling
    if state:
        fact["powerState"] = state
    if candidate.get("coordinates"):
        fact["coordinates"] = candidate.get("coordinates")
    candidate_powers = candidate.get("powers")
    if isinstance(candidate_powers, list):
        fact["powers"] = list(candidate_powers)
    fact.setdefault("system", str(candidate.get("system") or ""))
    return fact


def _market_power_fact(
    market: dict[str, Any], power: str,
    catalog: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    system = _system_key(market.get("system"))
    fact = dict(catalog.get((system, _power_key(power))) or {})
    if market.get("coordinates"):
        fact["coordinates"] = market.get("coordinates")
    fact.setdefault("system", str(market.get("system") or ""))
    return fact


def _route_system_state(
    candidate: dict[str, Any], market: dict[str, Any], power: str,
    catalog: dict[tuple[str, str], dict[str, Any]],
) -> str:
    """Return the target/sale system state used by MeritMiner's filter."""
    target = _market_power_fact(market, power, catalog)
    value = market.get("systemState") or target.get("systemState")
    if not value and _system_key(candidate.get("system")) == _system_key(
        market.get("system")
    ):
        value = candidate.get("systemState")
    return str(value or "").strip()


def _merit_status(
    candidate: dict[str, Any], market: dict[str, Any], power: str,
    power_goal: str, opposing_power: str,
    catalog: dict[tuple[str, str], dict[str, Any]],
) -> tuple[str, float | None, float | None]:
    """Apply the same route relationships explained by MeritMiner.

    Reinforce/Undermine require mining and sale in one system.  Acquisition
    requires an unoccupied sale system within 20 ly of a fortified source or
    30 ly of a stronghold source.  Unknown evidence never becomes a claim.
    """
    explicit = market.get("meritEligible")
    if explicit is True:
        return "CONFIRMED", 5.0, _coordinate_distance(
            candidate.get("coordinates"), market.get("coordinates")
        )
    if explicit is False:
        return "NOT ELIGIBLE", 0.0, None
    selected_power = _power_key(power)
    if not selected_power or selected_power in {"any", "unconfirmed"}:
        return "SELECT A POWER", None, None
    source = _candidate_power_fact(candidate, power, catalog)
    target = _market_power_fact(market, power, catalog)
    source_system = _system_key(candidate.get("system"))
    target_system = _system_key(market.get("system"))
    source_state = str(source.get("powerState") or "").strip()
    source_controller = _power_key(source.get("controllingPower"))
    # EDSM's daily dump contains one row for every Power present in a system.
    # Presence is useful for contesting/range context but is not proof of
    # control.  Only an explicit ControllingPower may confirm the source.
    controls_source = source_controller == selected_power
    goal = str(power_goal or "").casefold()
    if goal == "reinforce":
        if source_system != target_system:
            return "NOT ELIGIBLE · MINE AND SELL IN THE SAME SYSTEM", 0.0, None
        if not source_state:
            return "UNKNOWN · SOURCE POWER STATE MISSING", None, None
        if not source_controller:
            return "UNKNOWN · CONTROLLING POWER MISSING", None, None
        if not controls_source:
            return "NOT ELIGIBLE · POWER DOES NOT CONTROL SOURCE", 0.0, None
        if source_state.casefold() == "headquarters":
            return "NOT ELIGIBLE · HEADQUARTERS CANNOT BE REINFORCED", 0.0, None
        if source_state.casefold() not in {"exploited", "fortified", "stronghold"}:
            return f"NOT ELIGIBLE · {source_state.upper()}", 0.0, None
        return f"CONFIRMED · REINFORCE · {source_state.upper()}", 5.0, 0.0

    if goal == "undermine":
        if source_system != target_system:
            return "NOT ELIGIBLE · MINE AND SELL IN THE SAME SYSTEM", 0.0, None
        if not source_state or not source_controller:
            return "UNKNOWN · OPPOSING POWER STATE MISSING", None, None
        if source_state.casefold() == "headquarters":
            return "NOT ELIGIBLE · HEADQUARTERS CANNOT BE UNDERMINED", 0.0, None
        wanted_opponent = _power_key(opposing_power)
        if source_controller == selected_power:
            return "NOT ELIGIBLE · THIS IS YOUR POWER'S SYSTEM", 0.0, None
        if wanted_opponent not in {"", "any"} and source_controller != wanted_opponent:
            return "NOT ELIGIBLE · OPPOSING POWER MISMATCH", 0.0, None
        powers = {_power_key(item) for item in source.get("powers") or []}
        if powers and selected_power not in powers:
            return "NOT ELIGIBLE · YOUR POWER IS NOT CONTESTING", 0.0, None
        if not powers:
            return "UNKNOWN · CONTESTING POWERS MISSING", None, None
        return (
            "CONFIRMED · UNDERMINE · "
            + str(source.get("controllingPower") or opposing_power).upper(),
            5.0, 0.0,
        )

    if goal == "acquire":
        if not source_state:
            return "UNKNOWN · SOURCE POWER STATE MISSING", None, None
        if not source_controller:
            return "UNKNOWN · CONTROLLING POWER MISSING", None, None
        if not controls_source:
            return "NOT ELIGIBLE · POWER DOES NOT CONTROL SOURCE", 0.0, None
        source_state_key = source_state.casefold()
        radius = 20.0 if source_state_key == "fortified" else (
            30.0 if source_state_key in {"stronghold", "headquarters"} else 0.0
        )
        if not radius:
            return "NOT ELIGIBLE · SOURCE MUST BE FORTIFIED OR STRONGHOLD", 0.0, None
        target_state = str(target.get("powerState") or "").strip()
        if not target_state:
            return "UNKNOWN · TARGET POWER STATE MISSING", None, None
        if target_state.casefold() != "unoccupied":
            return f"NOT ELIGIBLE · TARGET IS {target_state.upper()}", 0.0, None
        distance = _coordinate_distance(
            source.get("coordinates"), target.get("coordinates")
        )
        if distance is None:
            return "UNKNOWN · MINE-TO-TARGET DISTANCE MISSING", None, None
        if distance > radius:
            return (
                f"NOT ELIGIBLE · {distance:.1f} LY EXCEEDS {radius:.0f} LY",
                0.0, distance,
            )
        return (
            f"CONFIRMED · ACQUIRE · {distance:.1f}/{radius:.0f} LY",
            5.0, distance,
        )

    return "UNKNOWN · POWERPLAY GOAL MISSING", None, None


def plan_mining_routes(
    candidates: Iterable[dict[str, Any]], commodity: str, optimization: str,
    *, min_demand: int = 0, max_market_age_hours: int = 0,
    result_limit: int = 30, require_hotspot: bool = False,
    prefer_res: bool = False, ring_filter: str = "ANY RING",
    prefer_secondary: bool = False, require_system_state: bool = False,
    rings_only: bool = False,
    landing_pad: str = "ANY", power: str = "", power_goal: str = "",
    opposing_power: str = "ANY", max_demand: int = 0,
    system_state: str = "ANY",
    markets: Iterable[dict[str, Any]] = (),
    powerplay_systems: Iterable[dict[str, Any]] = (),
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Annotate and rank already-filtered mining candidates.

    Market and merit scores stay unavailable when no supporting observation
    exists.  This keeps a plain mining search useful without falsely claiming
    a profitable or merit-eligible sale route.
    """
    now = now or datetime.now(timezone.utc)
    optimization = str(optimization or OPTIMIZE_YIELD).upper()
    if optimization not in OPTIMIZATION_MODES:
        optimization = OPTIMIZE_YIELD
    commodity_id = mining_commodity_id(commodity)
    all_commodities = commodity_id in {"", "allcommodities"}
    requested_commodity_name = (
        "" if all_commodities else mining_commodity_name(commodity_id)
    )
    powerplay_catalog = _powerplay_index(powerplay_systems)
    projected_shared_markets = _market_rows({}, commodity_id, markets)
    shared_market_rows = _eligible_markets(
        projected_shared_markets,
        landing_pad=landing_pad,
        min_demand=min_demand,
        max_demand=max_demand,
        max_market_age_hours=max_market_age_hours,
        now=now,
    )
    if prefer_secondary:
        projected_secondary_markets = (
            projected_shared_markets if all_commodities
            else _market_rows({}, "allcommodities", markets)
        )
        secondary_shared_markets = _eligible_markets(
            projected_secondary_markets,
            landing_pad=landing_pad,
            min_demand=min_demand,
            max_demand=max_demand,
            max_market_age_hours=max_market_age_hours,
            now=now,
        )
    else:
        secondary_shared_markets = []
    secondary_market_index: dict[
        tuple[str, str], list[dict[str, Any]]
    ] = defaultdict(list)
    for secondary_market in secondary_shared_markets:
        station_key = _market_station_key(secondary_market)
        if station_key is not None:
            secondary_market_index[station_key].append(secondary_market)
    shared_by_system: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shared_market in shared_market_rows:
        shared_by_system[_system_key(shared_market.get("system"))].append(
            shared_market
        )
    shared_fallback_order = sorted(
        shared_market_rows,
        key=lambda item: (
            -int(item.get("sellPrice", 0) or 0),
            -int(item.get("demand", 0) or 0),
        ),
    )
    shared_fallback_rank = {
        id(market): index
        for index, market in enumerate(shared_fallback_order)
    }
    shared_optimization_order = sorted(
        shared_market_rows,
        key=lambda item: _market_sort_key(item, optimization),
    )
    explicit_shared_merits = [
        market for market in shared_market_rows
        if market.get("meritEligible") is True
    ]
    goal = str(power_goal or "").casefold()
    acquire_spatial: dict[tuple[int, int, int], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    acquire_unknown_targets = []
    acquire_unknown_without_source_coordinates = []
    if optimization == OPTIMIZE_MERITS and goal == "acquire":
        for shared_market in shared_market_rows:
            target = _market_power_fact(
                shared_market, power, powerplay_catalog
            )
            explicit = shared_market.get("meritEligible")
            target_state = str(target.get("powerState") or "").casefold()
            if explicit is None and (
                not target_state
                or (
                    target_state == "unoccupied"
                    and _spatial_cell(target.get("coordinates")) is None
                )
            ):
                acquire_unknown_targets.append(shared_market)
            if explicit is None and target_state in {"", "unoccupied"}:
                acquire_unknown_without_source_coordinates.append(
                    shared_market
                )
            if target_state != "unoccupied":
                continue
            cell = _spatial_cell(target.get("coordinates"))
            if cell is not None:
                acquire_spatial[cell].append(shared_market)
        acquire_unknown_targets.sort(
            key=lambda market: shared_fallback_rank[id(market)]
        )
        acquire_unknown_without_source_coordinates.sort(
            key=lambda market: shared_fallback_rank[id(market)]
        )
        explicit_shared_merits.sort(
            key=lambda market: _market_sort_key(market, OPTIMIZE_MERITS)
        )

    requested_ring = str(ring_filter or "ANY RING").casefold()
    requested_state = str(system_state or "ANY").strip().casefold()
    same_system_sale_required = (
        optimization == OPTIMIZE_MERITS
        and goal in {"reinforce", "undermine"}
    )

    def market_pool_indexes(rows):
        by_commodity = defaultdict(list)
        by_commodity_state = defaultdict(list)
        members = set()
        rank = {}
        for index, market in enumerate(rows):
            members.add(id(market))
            rank[id(market)] = index
            market_commodity = mining_commodity_id(market.get("commodity"))
            if not market_commodity:
                continue
            by_commodity[market_commodity].append(market)
            target = _market_power_fact(market, power, powerplay_catalog)
            route_state = str(
                market.get("systemState") or target.get("systemState") or ""
            ).strip().casefold()
            if route_state:
                by_commodity_state[(market_commodity, route_state)].append(
                    market
                )
        return by_commodity, by_commodity_state, members, rank

    empty_market_indexes = ({}, {}, set(), {})
    if optimization == OPTIMIZE_MERITS and goal == "acquire":
        fallback_indexes = market_pool_indexes(shared_fallback_order)
        explicit_merit_indexes = market_pool_indexes(explicit_shared_merits)
        unknown_target_indexes = market_pool_indexes(acquire_unknown_targets)
        unknown_no_source_indexes = market_pool_indexes(
            acquire_unknown_without_source_coordinates
        )
    else:
        fallback_indexes = empty_market_indexes
        explicit_merit_indexes = empty_market_indexes
        unknown_target_indexes = empty_market_indexes
        unknown_no_source_indexes = empty_market_indexes

    def annotate_market(
        row: dict[str, Any], source_market: dict[str, Any],
    ) -> dict[str, Any] | None:
        market = dict(source_market)
        candidate_commodities = set(_candidate_commodity_ids(row, commodity))
        market_commodity = mining_commodity_id(market.get("commodity"))
        if all_commodities and (
            not market_commodity or market_commodity not in candidate_commodities
        ):
            return None
        if same_system_sale_required:
            mine_system = _system_key(row.get("system"))
            sell_system = _system_key(market.get("system"))
            if not mine_system or sell_system != mine_system:
                return None
        status, merit_score, route_distance = _merit_status(
            row, market, power, power_goal, opposing_power,
            powerplay_catalog,
        )
        if route_distance is None:
            mine_system = _system_key(row.get("system"))
            sell_system = _system_key(market.get("system"))
            if mine_system and mine_system == sell_system:
                route_distance = 0.0
            else:
                route_distance = _coordinate_distance(
                    row.get("coordinates"), market.get("coordinates")
                )
        route_state = _route_system_state(
            row, market, power, powerplay_catalog,
        )
        if requested_state not in {"", "any"} and (
            route_state.casefold() != requested_state
        ):
            return None
        market["meritStatus"] = status
        market["meritScore"] = merit_score
        market["mineToSellLy"] = route_distance
        market["systemState"] = route_state
        return market

    def first_indexed_market(
        row: dict[str, Any], indexes,
    ) -> dict[str, Any] | None:
        """Return the best compatible fallback without rescanning the catalog."""
        by_commodity, by_commodity_state, members, rank = indexes
        commodity_ids = _candidate_commodity_ids(row, commodity)
        candidates = {}
        for candidate_commodity in commodity_ids:
            bucket = (
                by_commodity.get(candidate_commodity, ())
                if requested_state in {"", "any"}
                else by_commodity_state.get(
                    (candidate_commodity, requested_state), ()
                )
            )
            if bucket:
                candidates[id(bucket[0])] = bucket[0]

        # A market without its own state may inherit the candidate's state
        # when mining and selling in one system.  Preserve that edge case
        # without making every route scan the complete market catalog.
        if requested_state not in {"", "any"} and str(
            row.get("systemState") or ""
        ).strip().casefold() == requested_state:
            for source_market in shared_by_system.get(
                _system_key(row.get("system")), ()
            ):
                if id(source_market) in members:
                    candidates[id(source_market)] = source_market

        for source_market in sorted(
            candidates.values(),
            key=lambda market: rank.get(
                id(market), len(rank)
            ),
        ):
            market = annotate_market(row, source_market)
            if market is not None:
                return market
        return None

    def best_shared_market(row: dict[str, Any]) -> dict[str, Any] | None:
        if not shared_market_rows:
            return None
        if optimization != OPTIMIZE_MERITS:
            for source_market in shared_optimization_order:
                market = annotate_market(row, source_market)
                if market is not None:
                    return market
            return None

        candidate_pool: list[dict[str, Any]] = []
        source_system = _system_key(row.get("system"))
        if goal in {"reinforce", "undermine"}:
            candidate_pool.extend(shared_by_system.get(source_system, ()))
        elif goal == "acquire":
            candidate_pool.extend(explicit_shared_merits)
            explicit_market = first_indexed_market(
                row, explicit_merit_indexes
            )
            if explicit_market is not None:
                return explicit_market
            source = _candidate_power_fact(row, power, powerplay_catalog)
            selected_power = _power_key(power)
            source_state = str(source.get("powerState") or "").casefold()
            source_controller = _power_key(source.get("controllingPower"))
            controls_source = source_controller == selected_power
            radius = 20.0 if source_state == "fortified" else (
                30.0 if source_state in {"stronghold", "headquarters"} else 0.0
            )
            cell = _spatial_cell(source.get("coordinates"))
            # Source-side failures do not depend on the target market.  One
            # indexed compatible market is enough to produce the exact same
            # status; the previous full fallback scan made ACQUIRE O(rings ×
            # markets) and could block the GUI for more than a minute.
            if not source_state or not controls_source or not radius:
                return first_indexed_market(row, fallback_indexes)
            if controls_source and radius and cell is not None:
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for dz in (-1, 0, 1):
                            candidate_pool.extend(acquire_spatial.get(
                                (cell[0] + dx, cell[1] + dy, cell[2] + dz),
                                (),
                            ))

            annotated = [
                market for source_market in candidate_pool
                if (market := annotate_market(row, source_market)) is not None
            ]
            confirmed = [
                market for market in annotated
                if _number(market.get("meritScore"), -1.0) > 0
            ]
            if confirmed:
                confirmed.sort(key=lambda item: _market_sort_key(
                    item, OPTIMIZE_MERITS
                ))
                return confirmed[0]

            # A route whose evidence can still be completed is more useful
            # than one that is already known to be ineligible.
            unknown_indexes = (
                unknown_target_indexes if cell is not None
                else unknown_no_source_indexes
            )
            best_unknown = first_indexed_market(row, unknown_indexes)
            return best_unknown or first_indexed_market(
                row, fallback_indexes
            )
        else:
            candidate_pool.extend(explicit_shared_merits)
            candidate_pool.extend(shared_fallback_order[:1])

        annotated = [
            market for source_market in candidate_pool
            if (market := annotate_market(row, source_market)) is not None
        ]
        if not annotated:
            return None
        annotated.sort(key=lambda item: _market_sort_key(
            item, OPTIMIZE_MERITS
        ))
        return annotated[0]

    prepared: list[dict[str, Any]] = []
    for source in candidates or []:
        if not isinstance(source, dict):
            continue
        if rings_only and is_belt_candidate(source):
            continue
        row = dict(source)
        row["_candidateCommodityIds"] = (
            _candidate_commodity_ids(row, commodity)
            if all_commodities else [commodity_id]
        )
        if requested_state in {"", "any"} and require_system_state and not (
            row.get("systemState") or row.get("systemStates")
            or row.get("states")
        ):
            continue
        if requested_ring not in {"", "any", "any ring", "all rings"}:
            actual_ring = str(
                row.get("ringTypeName") or row.get("ringType") or ""
            ).casefold().replace("-", " ")
            requested = requested_ring.replace("-", " ").replace(" ring", "")
            if requested not in actual_ring:
                continue
        if require_hotspot and row.get("targetMatch") not in {
            "HOTSPOT", "LOCAL_YIELD",
        }:
            continue
        candidate_markets = []
        local_markets = _eligible_markets(
            _market_rows(row, commodity_id),
            landing_pad=landing_pad,
            min_demand=min_demand,
            max_demand=max_demand,
            max_market_age_hours=max_market_age_hours,
            now=now,
        )
        for source_market in local_markets:
            market = annotate_market(row, source_market)
            if market is not None:
                candidate_markets.append(market)
        shared_market = best_shared_market(row)
        if shared_market is not None:
            candidate_markets.append(shared_market)
        candidate_markets.sort(key=lambda item: _market_sort_key(
            item, optimization
        ))
        market = candidate_markets[0] if candidate_markets else {}
        candidate_commodities = _candidate_commodity_ids(row, commodity)
        selected_commodity = (
            mining_commodity_id(market.get("commodity"))
            if all_commodities else commodity_id
        ) or (candidate_commodities[0] if candidate_commodities else "")
        missing_merit_status = (
            "UNKNOWN · SAME-SYSTEM SELL MARKET NOT VERIFIED"
            if same_system_sale_required else "UNKNOWN"
        )
        row.update({
            "optimization": optimization,
            "station": str(market.get("station") or ""),
            "sellSystem": str(market.get("system") or ""),
            "sellPrice": int(market.get("sellPrice", 0) or 0),
            "demand": int(market.get("demand", 0) or 0),
            "demandInfinite": bool(market.get("demandInfinite")),
            "marketObservedAt": str(market.get("observedAt") or ""),
            "marketSource": str(market.get("source") or ""),
            "marketAgeSeconds": market.get("ageSeconds"),
            "stationDistanceLs": market.get("distanceToArrivalLs"),
            "stationType": str(market.get("stationType") or ""),
            "landingPadSize": str(market.get("landingPadSize") or ""),
            "stationServices": list(market.get("services") or []),
            "stationEconomies": list(market.get("economies") or []),
            "primaryEconomy": str(market.get("primaryEconomy") or ""),
            "stationGovernment": str(market.get("government") or ""),
            "controllingFaction": str(
                market.get("controllingFaction") or ""
            ),
            "fleetCarrier": market.get("fleetCarrier"),
            "carrierDockingAccess": str(
                market.get("carrierDockingAccess") or ""
            ),
            "marketReceivedAt": str(market.get("receivedAt") or ""),
            "marketStatusFlags": list(market.get("statusFlags") or []),
            "marketKnown": bool(market),
            "marketMatchesFilters": bool(market.get("matchesFilters")),
            "marketPriceFresh": bool(market.get("fresh")),
            "marketReliabilityState": (
                "CURRENT" if market.get("matchesFilters")
                else "KNOWN" if market else "MISSING"
            ),
            "marketQualityStatus": (
                "CURRENT PRICE AND DEMAND VERIFIED"
                if market.get("matchesFilters")
                else "MARKET KNOWN · PRICE OR DEMAND OUTSIDE ACTIVE LIMITS"
                if market else "MARKET CHECK PENDING"
            ),
            "selectedCommodity": selected_commodity,
            "selectedCommodityName": (
                mining_commodity_name(selected_commodity)
                if all_commodities
                else requested_commodity_name
                if selected_commodity else "Unknown commodity"
            ),
            "candidateCommodities": candidate_commodities,
            "sameSystemSaleRequired": same_system_sale_required,
            "meritStatus": str(
                market.get("meritStatus") or missing_merit_status
            ),
            "meritKnown": market.get("meritScore") is not None,
            "mineToSellLy": market.get("mineToSellLy"),
        })
        yield_score = _yield_score(row)
        data_score = _data_score(row)
        station_key = _market_station_key(market)
        secondary_route_markets = list(
            secondary_market_index.get(station_key, ())
            if station_key is not None else ()
        )
        if prefer_secondary and row.get("markets"):
            secondary_route_markets = [
                *secondary_route_markets,
                *_eligible_markets(
                    _market_rows(row, "allcommodities"),
                    landing_pad=landing_pad,
                    min_demand=min_demand,
                    max_demand=max_demand,
                    max_market_age_hours=max_market_age_hours,
                    now=now,
                ),
            ]
        secondary_resources = _secondary_resources(
            row, selected_commodity, market, secondary_route_markets,
        )
        secondary_evidence_score = sum(
            (2 if item.get("localYield") else 0)
            + (1 if item.get("hotspot") else 0)
            for item in secondary_resources
        )
        row["yieldScore"] = round(yield_score, 2)
        row["dataScore"] = round(data_score, 2)
        row["secondaryCommodities"] = secondary_resources
        row["secondaryCommodityNames"] = [
            item["name"] for item in secondary_resources
        ]
        row["secondaryCommodityCount"] = len(secondary_resources)
        row["secondaryMarketCount"] = sum(
            bool(item.get("marketKnown")) for item in secondary_resources
        )
        row["secondaryEvidenceScore"] = secondary_evidence_score
        row["secondaryPreferred"] = bool(
            prefer_secondary and secondary_resources
        )
        row["_meritScore"] = market.get("meritScore")
        prepared.append(row)

    max_price = max((row["sellPrice"] for row in prepared), default=0)
    max_demand = max((row["demand"] for row in prepared), default=0)
    distances = [
        _number(row.get("distanceLy")) for row in prepared
        if row.get("distanceLy") is not None
    ]
    max_distance = max(distances, default=1.0) or 1.0
    for row in prepared:
        row.pop("_candidateCommodityIds", None)
        profit_score = None
        if row["marketKnown"] and row["marketMatchesFilters"] and max_price > 0:
            price_part = row["sellPrice"] / max_price
            demand_part = row["demand"] / max_demand if max_demand else 0.0
            profit_score = max(0.0, min(5.0, 5.0 * (
                price_part * 0.75 + demand_part * 0.25
            )))
        distance = row.get("distanceLy")
        distance_score = 2.5 if distance is None else max(
            1.0, 5.0 * (1.0 - _number(distance) / (max_distance * 1.25))
        )
        merit_score = row.pop("_meritScore")
        if optimization == OPTIMIZE_MERITS:
            if _number(merit_score, -1.0) > 0:
                if row.get("marketMatchesFilters"):
                    verification_state = "VERIFIED"
                    verification_label = "POWERPLAY VERIFIED"
                    verification_rank = 0
                else:
                    verification_state = "KNOWN"
                    verification_label = (
                        "POWERPLAY ROUTE KNOWN · MARKET DATA LIMITED"
                    )
                    verification_rank = 1
            elif merit_score is None:
                verification_state = "PENDING"
                verification_label = "MARKET CHECK PENDING"
                verification_rank = 2
            else:
                verification_state = "INELIGIBLE"
                verification_label = "MINING ONLY · NOT POWERPLAY ELIGIBLE"
                verification_rank = 3
        else:
            verification_state = "NOT_APPLICABLE"
            verification_label = "MINING ROUTES"
            verification_rank = 0
        score_parts = {
            "yield": row["yieldScore"], "data": row["dataScore"],
            "profit": profit_score, "merit": merit_score,
            "distance": distance_score,
        }
        weights = {
            OPTIMIZE_MERITS: {"merit": .40, "yield": .25, "profit": .20, "data": .15},
            OPTIMIZE_PROFIT: {"profit": .45, "yield": .25, "data": .20, "distance": .10},
            OPTIMIZE_DISTANCE: {"distance": .55, "yield": .20, "data": .15, "profit": .10},
            OPTIMIZE_YIELD: {"yield": .55, "data": .25, "distance": .10, "profit": .10},
        }[optimization]
        known_weight = sum(
            weight for key, weight in weights.items()
            if score_parts[key] is not None
        )
        overall = sum(
            score_parts[key] * weight for key, weight in weights.items()
            if score_parts[key] is not None
        ) / known_weight if known_weight else 0.0
        row.update({
            "profitScore": round(profit_score, 2) if profit_score is not None else None,
            "meritScore": round(merit_score, 2) if merit_score is not None else None,
            "distanceScore": round(distance_score, 2),
            "overallScore": round(overall, 2),
            "yieldStars": _stars(row["yieldScore"]),
            "profitStars": _stars(profit_score),
            "meritStars": _stars(merit_score),
            "dataStars": _stars(row["dataScore"]),
            "overallStars": _stars(overall),
            "powerplayVerificationState": verification_state,
            "powerplayVerificationLabel": verification_label,
            "powerplayVerificationRank": verification_rank,
            "resPreferred": bool(prefer_res and (
                row.get("resType") or row.get("resourceExtractionSite")
            )),
        })

    score_key = {
        OPTIMIZE_MERITS: "meritScore",
        OPTIMIZE_PROFIT: "profitScore",
        OPTIMIZE_DISTANCE: "distanceScore",
        OPTIMIZE_YIELD: "yieldScore",
    }[optimization]
    prepared.sort(key=lambda row: (
        int(row.get("powerplayVerificationRank", 0) or 0)
        if optimization == OPTIMIZE_MERITS else 0,
        row.get(score_key) is None,
        -_number(row.get(score_key), -1.0),
        not bool(row.get("marketMatchesFilters")),
        -_number(row.get("overallScore")),
        not bool(row.get("resPreferred")),
        not bool(row.get("secondaryPreferred")),
        -_number(row.get("secondaryMarketCount"))
        if prefer_secondary else 0.0,
        -_number(row.get("secondaryEvidenceScore"))
        if prefer_secondary else 0.0,
        row.get("distanceLy") is None,
        _number(row.get("distanceLy")),
        str(row.get("system") or "").casefold(),
    ))
    limit = max(1, min(100, int(result_limit or 30)))
    return prepared[:limit]
