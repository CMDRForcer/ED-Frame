"""Observed two-station trade loops, with cargo and cash conserved per leg."""
import math
import time
from datetime import datetime, timezone

from .commodity_search import commodity_reference, is_trade_commodity
from .mining_market import MiningMarketError


def trade_symbols():
    reference = commodity_reference()
    return sorted(symbol for symbol in reference if is_trade_commodity(symbol, reference))


def search_filters(origin, radius, leg_distance, capacity, budget, age_hours, pad,
                   exclude_carriers, commodity="ALL", sort_by="PROFIT"):
    try:
        xyz = [float(v) for v in origin]
        radius, leg_distance = float(radius), float(leg_distance)
        capacity, budget, age_hours = int(capacity), int(budget), int(age_hours)
    except (TypeError, ValueError, OverflowError):
        raise MiningMarketError("Invalid trading route search") from None
    commodity = str(commodity).strip().lower()
    if (len(xyz) != 3 or not all(math.isfinite(v) and abs(v) <= 1_000_000 for v in xyz)
            or not 0 < radius <= 500 or not 0 < leg_distance <= 500
            or not 1 <= capacity <= 100_000 or not 1 <= budget <= 1_000_000_000_000
            or not 1 <= age_hours <= 168 or pad not in {"ANY", "S", "M", "L"}
            or sort_by not in {"PROFIT", "UNIT_PROFIT", "DISTANCE"}
            or (commodity != "all" and not is_trade_commodity(commodity, commodity_reference()))):
        raise MiningMarketError("Invalid trading route search")
    return dict(origin=xyz, radiusLy=radius, maxLegLy=leg_distance, cargoTonnes=capacity,
                budgetCr=budget, maxAgeHours=age_hours, landingPad=pad,
                excludeCarriers=bool(exclude_carriers), commodity=commodity, sortBy=sort_by)


def valid_quote(item, filters, now=None):
    """Never infer unlimited supply/demand or use reference prices as offers."""
    now = now or datetime.now(timezone.utc)
    try:
        symbol = item["commodity"]
        stamp = item["observedAt"]
        observed = stamp if isinstance(stamp, datetime) else datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if observed.tzinfo is None or not 0 <= (now-observed).total_seconds() <= filters["maxAgeHours"] * 3600:
            return None
        numbers = {key: int(item.get(key) or 0) for key in ("buyPrice", "sellPrice", "stock", "demand")}
        if not is_trade_commodity(symbol, commodity_reference()) or any(v < 0 for v in numbers.values()):
            return None
        return dict(item, **numbers, observedAt=observed.isoformat())
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _leg_options(source, target, capacity, budget, commodity="all"):
    for symbol, buy in source.items():
        if commodity != "all" and symbol != commodity:
            continue
        sell = target.get(symbol)
        if not sell or buy["buyPrice"] <= 0 or sell["sellPrice"] <= buy["buyPrice"]:
            continue
        tonnes = min(capacity, buy["stock"], sell["demand"], budget // buy["buyPrice"])
        if tonnes < 1:
            continue
        spread = sell["sellPrice"] - buy["buyPrice"]
        yield symbol, buy, sell, tonnes, spread


def best_leg(source, target, capacity, budget, commodity="all", *, unit_profit=False):
    best = None
    best_key = None
    for option in _leg_options(source, target, capacity, budget, commodity):
        symbol, _buy, _sell, tonnes, spread = option
        key = (-spread, -tonnes * spread, symbol) if unit_profit else (-tonnes * spread, symbol)
        if best_key is None or key < best_key:
            best_key = key
            best = option
    if best is None:
        return None
    return _make_leg(best, budget)


def _make_leg(option, budget):
    symbol, buy, sell, tonnes, spread = option
    return dict(commodity=symbol, tonnes=tonnes, buyPrice=buy["buyPrice"], sellPrice=sell["sellPrice"],
        stock=buy["stock"], demand=sell["demand"], buyObservedAt=buy["observedAt"],
        sellObservedAt=sell["observedAt"], buySource=buy.get("source", ""), sellSource=sell.get("source", ""),
        purchaseCr=tonnes * buy["buyPrice"], proceedsCr=tonnes * sell["sellPrice"],
        profitCr=tonnes * spread, unitProfitCr=spread, budgetBeforeCr=budget,
        budgetAfterCr=budget + tonnes * spread)


def best_unit_loop_legs(source, target, capacity, budget, commodity="all"):
    """Maximize combined margin while funding the return with actual profits.

    An outbound with no greater margin and no greater profit is dominated:
    it cannot unlock a better return. Only the remaining frontier needs a
    return search, rather than checking every pair of commodities.
    """
    options = sorted(_leg_options(source, target, capacity, budget, commodity),
        key=lambda row: (-row[4], -row[3] * row[4], row[0]))
    best, best_key, largest_profit = None, None, -1
    for option in options:
        profit = option[3] * option[4]
        if profit <= largest_profit:
            continue
        largest_profit = profit
        inbound = best_leg(target, source, capacity, budget + profit, unit_profit=True)
        if inbound is None:
            continue
        key = (-option[4] - inbound["unitProfitCr"], -profit - inbound["profitCr"],
            option[0], inbound["commodity"])
        if best_key is None or key < best_key:
            best_key = key
            best = _make_leg(option, budget), inbound
    return best


def make_loop(a, b, outbound, inbound):
    distance = math.dist(a["coordinates"], b["coordinates"])
    return dict(id=f"{a['marketId']}:{b['marketId']}", stationA=a, stationB=b,
        outbound=outbound, inbound=inbound, legDistanceLy=distance, roundTripLy=2 * distance,
        approachLy=a["distanceLy"], totalDistanceLy=a["distanceLy"] + 2 * distance,
        profitCr=outbound["profitCr"] + inbound["profitCr"],
        unitProfitCr=outbound["unitProfitCr"] + inbound["unitProfitCr"],
        finalBudgetCr=inbound["budgetAfterCr"])


def rank_loops(stations, quotes, filters, limit=30, deadline=None):
    """Evaluate every quote for sampled stations, then rank complete loops."""
    now = datetime.now(timezone.utc)
    by_market = {}
    for item in quotes:
        row = valid_quote(item, filters, now)
        if row:
            by_market.setdefault(row["marketId"], {})[row["commodity"]] = row
    ranks = {"ANY":0, "S":1, "M":2, "L":3}
    eligible = []
    for item in stations:
        try:
            row = dict(item)
            xyz = [float(v) for v in row["coordinates"]]
            if len(xyz) != 3 or not all(math.isfinite(v) and abs(v) <= 1_000_000 for v in xyz):
                continue
            if ranks.get(row.get("landingPadSize"), 0) < ranks[filters["landingPad"]]:
                continue
            if filters["excludeCarriers"] and row.get("fleetCarrier"):
                continue
            row.update(coordinates=xyz, distanceLy=math.dist(filters["origin"], xyz))
            if row["marketId"] in by_market:
                eligible.append(row)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    results = []
    for a in eligible:
        if a["distanceLy"] > filters["radiusLy"] or not a.get("startCandidate", True):
            continue
        if deadline is not None and time.monotonic() > deadline:
            raise MiningMarketError("Trade route calculation timed out · narrow the search")
        for b in eligible:
            if a["marketId"] == b["marketId"] or math.dist(a["coordinates"], b["coordinates"]) > filters["maxLegLy"]:
                continue
            source, target = by_market[a["marketId"]], by_market[b["marketId"]]
            if filters["sortBy"] == "UNIT_PROFIT":
                pair = best_unit_loop_legs(source, target, filters["cargoTonnes"],
                    filters["budgetCr"], filters["commodity"])
                if pair:
                    results.append(make_loop(a, b, *pair))
            else:
                outbound = best_leg(source, target,
                    filters["cargoTonnes"], filters["budgetCr"], filters["commodity"])
                if not outbound:
                    continue
                inbound = best_leg(target, source,
                    filters["cargoTonnes"], outbound["budgetAfterCr"])
                if inbound:
                    results.append(make_loop(a, b, outbound, inbound))
    key = {"PROFIT":"profitCr", "UNIT_PROFIT":"unitProfitCr", "DISTANCE":"totalDistanceLy"}[filters["sortBy"]]
    results.sort(key=lambda row: (row[key] if key == "totalDistanceLy" else -row[key],
        -row["profitCr"], row["totalDistanceLy"], row["id"]))
    return dict(results=results[:limit], hasMore=len(results) > limit, matchedLoops=len(results))
