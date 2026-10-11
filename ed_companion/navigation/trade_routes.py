"""Validate public round-trip suggestions before publishing a UI snapshot."""
import math
from datetime import datetime, timezone

from .mining_market import EDFRAME_CATALOG_BASE, MiningMarketError
from .trade_route_model import search_filters, valid_quote, best_leg, make_loop
from .commodity_search import commodity_reference
from .shipyard_finder import evaluate_station_access


def _station(item):
    row = dict(item)
    xyz = [float(v) for v in row["coordinates"]]
    if (len(xyz) != 3 or not all(math.isfinite(v) and abs(v) <= 1_000_000 for v in xyz)
            or not isinstance(row.get("marketId"), int) or isinstance(row["marketId"], bool)
            or row["marketId"] <= 0 or not row.get("system") or not row.get("station")):
        raise ValueError("Invalid route station")
    row["coordinates"] = xyz
    return row


def _leg(item, filters, budget):
    symbol = item["commodity"]
    buy = valid_quote(dict(commodity=symbol,buyPrice=item["buyPrice"],stock=item["stock"],
        observedAt=item["buyObservedAt"],source=item.get("buySource", "")), filters)
    sell = valid_quote(dict(commodity=symbol,sellPrice=item["sellPrice"],demand=item["demand"],
        observedAt=item["sellObservedAt"],source=item.get("sellSource", "")), filters)
    if not buy or not sell:
        raise ValueError("Invalid route prices or age")
    result = best_leg({symbol:buy},{symbol:sell},filters["cargoTonnes"],budget)
    if not result or any(item.get(key) != result[key] for key in (
            "tonnes", "buyPrice", "sellPrice", "purchaseCr", "proceedsCr", "profitCr", "unitProfitCr",
            "budgetBeforeCr", "budgetAfterCr")):
        raise ValueError("Invalid route quantity, budget or profit")
    return result


def validate_trade_routes(payload, filters):
    if (not isinstance(payload, dict) or payload.get("filters") != filters
            or not isinstance(payload.get("results"), list) or len(payload["results"]) > 30):
        raise MiningMarketError("Server did not confirm trading route search")
    rows = []
    pads = {"ANY":0,"S":1,"M":2,"L":3}
    for item in payload["results"]:
        try:
            a,b = _station(item["stationA"]), _station(item["stationB"])
            for station in (a,b):
                station["distanceLy"] = math.dist(filters["origin"], station["coordinates"])
                if (pads.get(station.get("landingPadSize"),0) < pads[filters["landingPad"]]
                        or (filters["excludeCarriers"] and station.get("fleetCarrier"))):
                    raise ValueError("Station excluded by filters")
            if (a["marketId"] == b["marketId"] or a["distanceLy"] > filters["radiusLy"]
                    or math.dist(a["coordinates"],b["coordinates"]) > filters["maxLegLy"]):
                raise ValueError("Invalid round-trip geometry")
            outbound = _leg(item["outbound"], filters, filters["budgetCr"])
            if filters["commodity"] != "all" and outbound["commodity"] != filters["commodity"]:
                raise ValueError("Wrong outbound commodity")
            inbound = _leg(item["inbound"], filters, outbound["budgetAfterCr"])
            row = make_loop(a,b,outbound,inbound)
            if any(item.get(key) != row[key] for key in ("id","profitCr","unitProfitCr","finalBudgetCr")):
                raise ValueError("Invalid round-trip totals")
            for key in ("legDistanceLy","roundTripLy","approachLy","totalDistanceLy"):
                if not math.isclose(float(item[key]),row[key],rel_tol=1e-8,abs_tol=1e-7):
                    raise ValueError("Invalid route distance")
            rows.append(row)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    key = {"PROFIT":"profitCr","UNIT_PROFIT":"unitProfitCr","DISTANCE":"totalDistanceLy"}[filters["sortBy"]]
    rows.sort(key=lambda row:(row[key] if key == "totalDistanceLy" else -row[key],
        -row["profitCr"],row["totalDistanceLy"],row["id"]))
    return dict(payload,results=rows)


def fetch_trade_routes(*, origin, radius=50, leg_distance=100, capacity=100, budget=10000000,
                       age_hours=24, pad="ANY", exclude_carriers=False, commodity="ALL",
                       sort_by="PROFIT", refresh=False, get, timeout=30):
    filters = search_filters(origin,radius,leg_distance,capacity,budget,age_hours,pad,
        exclude_carriers,commodity,sort_by)
    params = dict(zip(("x","y","z"), filters["origin"]))
    params.update(max_distance=filters["radiusLy"],max_leg_distance=filters["maxLegLy"],
        cargo_tonnes=filters["cargoTonnes"],budget_cr=filters["budgetCr"],max_age_hours=filters["maxAgeHours"],
        landing_pad=filters["landingPad"],exclude_fleet_carriers=filters["excludeCarriers"],
        commodity=filters["commodity"],sort_by=filters["sortBy"],refresh=bool(refresh),limit=30)
    response = get(EDFRAME_CATALOG_BASE+"/v1/markets/trade-routes",params=params,timeout=timeout)
    if getattr(response,"status_code",None) == 404:
        raise MiningMarketError("Trading routes require a catalog server update")
    if getattr(response,"status_code",None) == 503:
        raise MiningMarketError("Trading route search busy or too large · narrow the radius or retry")
    response.raise_for_status()
    return validate_trade_routes(response.json(),filters)


def describe_trade_routes(rows, overview=None, permit_rules=None):
    reference = commodity_reference()
    now = datetime.now(timezone.utc)
    result = []
    for item in rows:
        row = dict(item)
        for key in ("stationA","stationB"):
            station = dict(row[key])
            station.update(evaluate_station_access(station["system"],overview,permit_rules))
            row[key] = station
        ages = []
        for key in ("outbound","inbound"):
            leg = dict(row[key]); leg["commodityName"] = reference.get(leg["commodity"],{}).get("name",leg["commodity"])
            for field in ("buyObservedAt","sellObservedAt"):
                ages.append(max(0,(now-datetime.fromisoformat(leg[field])).total_seconds()/3600))
            row[key] = leg
        row["oldestAgeHours"] = round(max(ages),1)
        row["accessWarning"] = any(row[k].get("accessTone") == "LOCKED" for k in ("stationA","stationB"))
        row["carrierWarning"] = any(row[k].get("fleetCarrier") for k in ("stationA","stationB"))
        row["prohibitedWarning"] = any(
            leg["commodity"] in {str(v).lower() for v in row[station].get("prohibited",[]) or []}
            for leg in (row["outbound"],row["inbound"]) for station in ("stationA","stationB")
            if isinstance(row[station].get("prohibited"),list))
        result.append(row)
    return result
