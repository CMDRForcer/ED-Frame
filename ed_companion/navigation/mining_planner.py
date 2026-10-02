"""Pure scoring for the unified Mining Finder.

The planner never invents market or Powerplay facts.  Missing observations
remain explicitly unknown and therefore cannot earn profit or merit stars.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import sqrt
from typing import Any, Iterable

from .mining_commodities import mining_commodity_id
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
    for market in rows if isinstance(rows, list) else []:
        if not isinstance(market, dict):
            continue
        market_commodity = mining_commodity_id(
            market.get("commodity") or market.get("name")
        )
        if commodity_id and market_commodity != commodity_id:
            continue
        projected = dict(market)
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
    now: datetime,
) -> list[dict[str, Any]]:
    """Apply query-wide market filters once instead of once per ring."""
    result = []
    for source in markets or []:
        if not isinstance(source, dict) or not _pad_matches(source, landing_pad):
            continue
        market = dict(source)
        fresh, age = _market_is_fresh(market, max_market_age_hours, now)
        market["fresh"] = fresh
        market["ageSeconds"] = age
        if max_market_age_hours > 0 and not fresh:
            continue
        demand = int(market.get("demand", 0) or 0)
        if not market.get("demandInfinite") and demand < max(0, int(min_demand or 0)):
            continue
        if (
            max(0, int(max_demand or 0)) > 0
            and not market.get("demandInfinite")
            and demand > int(max_demand)
        ):
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
        return (
            market.get("meritScore") is None,
            -_number(market.get("meritScore")),
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
    source_catalog_power = _power_key(source.get("power"))
    controls_source = (
        source_controller == selected_power
        or (not source_controller and source_catalog_power == selected_power)
    )
    goal = str(power_goal or "").casefold()
    if goal == "reinforce":
        if source_system != target_system:
            return "NOT ELIGIBLE · MINE AND SELL IN THE SAME SYSTEM", 0.0, None
        if not source_state:
            return "UNKNOWN · SOURCE POWER STATE MISSING", None, None
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
    powerplay_catalog = _powerplay_index(powerplay_systems)
    shared_market_rows = _eligible_markets(
        _market_rows({}, commodity_id, markets),
        landing_pad=landing_pad,
        min_demand=min_demand,
        max_demand=max_demand,
        max_market_age_hours=max_market_age_hours,
        now=now,
    )
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
    shared_optimization_order = sorted(
        shared_market_rows,
        key=lambda item: _market_sort_key(item, optimization),
    )
    explicit_shared_merits = [
        market for market in shared_market_rows
        if market.get("meritEligible") is True
    ]
    acquire_spatial: dict[tuple[int, int, int], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for shared_market in shared_market_rows:
        target = _market_power_fact(shared_market, power, powerplay_catalog)
        if str(target.get("powerState") or "").casefold() != "unoccupied":
            continue
        cell = _spatial_cell(target.get("coordinates"))
        if cell is not None:
            acquire_spatial[cell].append(shared_market)

    requested_ring = str(ring_filter or "ANY RING").casefold()
    requested_state = str(system_state or "ANY").strip().casefold()
    goal = str(power_goal or "").casefold()
    same_system_sale_required = (
        optimization == OPTIMIZE_MERITS
        and goal in {"reinforce", "undermine"}
    )

    def annotate_market(
        row: dict[str, Any], source_market: dict[str, Any],
    ) -> dict[str, Any] | None:
        market = dict(source_market)
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
            source = _candidate_power_fact(row, power, powerplay_catalog)
            selected_power = _power_key(power)
            source_state = str(source.get("powerState") or "").casefold()
            source_controller = _power_key(source.get("controllingPower"))
            source_catalog_power = _power_key(source.get("power"))
            controls_source = (
                source_controller == selected_power
                or (
                    not source_controller
                    and source_catalog_power == selected_power
                )
            )
            radius = 20.0 if source_state == "fortified" else (
                30.0 if source_state in {"stronghold", "headquarters"} else 0.0
            )
            cell = _spatial_cell(source.get("coordinates"))
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

            # Without a confirmed target, preserve the original preference:
            # known ineligible evidence sorts ahead of unknown evidence.
            best_unknown = None
            for source_market in shared_fallback_order:
                market = annotate_market(row, source_market)
                if market is None:
                    continue
                if market.get("meritScore") is not None:
                    return market
                if best_unknown is None:
                    best_unknown = market
            return best_unknown
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
            "marketKnown": bool(market),
            "sameSystemSaleRequired": same_system_sale_required,
            "meritStatus": str(
                market.get("meritStatus") or missing_merit_status
            ),
            "meritKnown": market.get("meritScore") is not None,
            "mineToSellLy": market.get("mineToSellLy"),
        })
        yield_score = _yield_score(row)
        data_score = _data_score(row)
        secondary_ids = {
            mining_commodity_id(item.get("commodity"))
            for field in ("hotspots", "yieldStats")
            for item in row.get(field, [])
            if isinstance(item, dict) and mining_commodity_id(
                item.get("commodity")
            ) not in {"", commodity_id}
        }
        row["yieldScore"] = round(yield_score, 2)
        row["dataScore"] = round(data_score, 2)
        row["secondaryCommodityCount"] = len(secondary_ids)
        row["secondaryPreferred"] = bool(prefer_secondary and secondary_ids)
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
        profit_score = None
        if row["marketKnown"] and max_price > 0:
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
        row.get(score_key) is None,
        -_number(row.get(score_key), -1.0),
        -_number(row.get("overallScore")),
        not bool(row.get("resPreferred")),
        not bool(row.get("secondaryPreferred")),
        row.get("distanceLy") is None,
        _number(row.get("distanceLy")),
        str(row.get("system") or "").casefold(),
    ))
    limit = max(1, min(100, int(result_limit or 30)))
    return prepared[:limit]
