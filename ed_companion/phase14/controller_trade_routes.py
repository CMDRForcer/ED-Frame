"""Explicit, bounded round-trip requests; publish only completed snapshots."""
import time
import uuid
import requests
from PySide6.QtCore import Property, Signal, Slot

from ed_companion.navigation.state_find_catalog import state_find_region
from ed_companion.navigation.mining_market import fetch_edframe_system_coordinates, MiningMarketError
from ed_companion.navigation.trade_routes import fetch_trade_routes, describe_trade_routes
from ed_companion.navigation.trade_route_model import search_filters


def text(owner, key, fallback):
    return getattr(owner,"translate",lambda key,fallback:fallback)("trade."+key,fallback)


class TradeRoutesMixin:
    tradeRoutesChanged = Signal()
    tradeRoutesFinished = Signal(object)

    @Property(bool, notify=tradeRoutesChanged)
    def tradeRoutesBusy(self):
        return bool(getattr(self,"_trade_request",None))

    @Property("QVariantList", notify=tradeRoutesChanged)
    def tradeRouteRows(self):
        if getattr(self,"_trade_generation",-1) != getattr(self,"_profile_generation",0):
            return []
        return describe_trade_routes(getattr(self,"_trade_rows",[]),self._state.get("commanderOverview",{}),
            getattr(self,"_shipyard_permit_rules",{}))

    @Property(str, notify=tradeRoutesChanged)
    def tradeRouteStatus(self):
        status = getattr(self,"_trade_status",text(self,"idle","Choose filters, then find a round trip"))
        query = getattr(self,"_trade_last_query",{})
        if (query.get("origin_mode") == "JOURNAL" and query.get("region")
                and query["region"] != state_find_region(self._state.get("currentPosition"),query["radius"])):
            return text(self,"previous_location","Previous location · search again")+" · "+status
        return status

    @Property("QVariantMap", notify=tradeRoutesChanged)
    def tradeRouteSnapshot(self):
        if getattr(self,"_trade_generation",-1) != getattr(self,"_profile_generation",0):
            return {}
        return dict(getattr(self,"_trade_snapshot",{}))

    @Property(str, notify=tradeRoutesChanged)
    def selectedTradeRouteId(self):
        if getattr(self,"_trade_generation",-1) != getattr(self,"_profile_generation",0):
            return ""
        return getattr(self,"_trade_selected_id","")

    @Property("QVariantMap", notify=tradeRoutesChanged)
    def tradeRouteDefaults(self):
        stats = self._state.get("activeShipFitStats",{}) or {}
        credits = (self._state.get("commanderOverview",{}) or {}).get("credits",{}) or {}
        capacity = stats.get("cargoCapacity")
        budget = credits.get("value") if credits.get("known") else None
        return dict(capacity=max(1,min(100000,int(capacity))) if capacity else 100,
            budget=max(0,min(1_000_000_000_000,int(budget))) if budget is not None else 10000000,
            capacityKnown=bool(capacity),budgetKnown=budget is not None)

    @Slot(str, str, int, float, int, int, int, str, bool, str, bool)
    def searchTradeRoutes(self, origin_system, commodity, capacity, budget, radius, leg_distance,
                          age_hours, pad, exclude_carriers, sort_by, refresh=False):
        if self.tradeRoutesBusy or getattr(self,"_shutdown_complete",False):
            return
        if not getattr(self,"_edframe_catalog_enabled",True):
            self._trade_status = text(self,"disabled","Server disabled · previous routes retained")
            self.tradeRoutesChanged.emit(); return
        requested = str(origin_system).strip()
        mode = "MANUAL" if requested else "JOURNAL"
        system = requested or self._state.get("system","")
        region = state_find_region(self._state.get("currentPosition"),radius) if mode == "JOURNAL" or requested.casefold()==str(self._state.get("system","")).casefold() else None
        cached = getattr(self,"_trade_origin_cache",{})
        if region is None and cached.get("system","").casefold()==requested.casefold() and time.monotonic()-cached.get("resolvedAt",0)<3600:
            region = state_find_region(cached.get("coordinates"),radius)
            system = cached.get("system",system)
        try:
            if len(requested)>100 or (mode == "JOURNAL" and not region):
                raise ValueError("Journal position unavailable or invalid start system")
            search_filters(region["origin"] if region else [0,0,0],radius,leg_distance,capacity,budget,
                age_hours,pad,exclude_carriers,commodity,sort_by)
        except (ValueError,TypeError,OverflowError,MiningMarketError) as exc:
            self._trade_status = text(self,"invalid","Check the start system, cargo limit and budget")+" · "+str(exc)
            self.tradeRoutesChanged.emit(); return
        query = dict(id=uuid.uuid4().hex,generation=getattr(self,"_profile_generation",0),
            origin_mode=mode,origin_system=system,region=region,radius=radius,
            commodity=commodity,capacity=capacity,budget=budget,leg_distance=leg_distance,
            age_hours=age_hours,pad=pad,exclude_carriers=exclude_carriers,sort_by=sort_by,refresh=refresh)
        self._trade_request = query
        self._trade_status = text(self,"searching","Finding round trips…")
        self.tradeRoutesChanged.emit()
        def worker():
            result = dict(query)
            try:
                resolved = region
                if resolved is None:
                    location = fetch_edframe_system_coordinates(system,get=requests.get)
                    resolved = state_find_region(location["coordinates"],radius)
                    result["origin_system"] = location["system"]
                result["region"] = resolved
                args = {key:query[key] for key in ("radius","leg_distance","capacity","budget","age_hours",
                    "pad","exclude_carriers","commodity","sort_by","refresh")}
                result["payload"] = fetch_trade_routes(origin=resolved["origin"],get=requests.get,**args)
                result["success"] = True
            except Exception as exc:
                result.update(success=False,error=str(exc))
            self.tradeRoutesFinished.emit(result)
        if not self._start_network_worker(worker,"trade-routes"):
            self._trade_request = None
            self._trade_status = text(self,"paused","Search paused during shutdown")
            self.tradeRoutesChanged.emit()

    @Slot(object)
    def _finish_trade_routes(self, result):
        query = getattr(self,"_trade_request",None)
        if not query or result.get("id") != query["id"]:
            return
        self._trade_request = None
        if query["generation"] != getattr(self,"_profile_generation",0):
            self._trade_status = text(self,"profile_changed","Profile changed · search again")
        elif not getattr(self,"_edframe_catalog_enabled",True):
            self._trade_status = text(self,"disabled","Server disabled · previous routes retained")
        elif query["origin_mode"] == "JOURNAL" and query["region"] != state_find_region(self._state.get("currentPosition"),query["radius"]):
            self._trade_status = text(self,"location_changed","Location changed · search again")
        elif not result.get("success"):
            self._trade_status = text(self,"failed","Search failed · previous routes retained")+" · "+result.get("error","")
        else:
            payload = result["payload"]
            self._trade_rows = payload["results"]
            self._trade_generation = query["generation"]
            self._trade_last_query = {**query,"region":result["region"],"origin_system":result["origin_system"]}
            if query["origin_mode"] == "MANUAL":
                self._trade_origin_cache = dict(system=result["origin_system"],coordinates=result["region"]["origin"],resolvedAt=time.monotonic())
            self._trade_snapshot = dict(filters=payload["filters"],coverage=payload.get("coverage",{}),
                generatedAt=payload.get("generatedAt",""),cached=bool(payload.get("cached")),
                hasMore=bool(payload.get("hasMore")),system=result["origin_system"],count=len(self._trade_rows))
            ids = {row["id"] for row in self._trade_rows}
            if getattr(self,"_trade_selected_id","") not in ids:
                self._trade_selected_id = self._trade_rows[0]["id"] if self._trade_rows else ""
            self._trade_status = f"{len(self._trade_rows)} "+text(self,"matches","round-trip suggestions")+" · "+result["origin_system"]
            if payload.get("hasMore"):
                self._trade_status += " · "+text(self,"more","more routes exist")
        self.tradeRoutesChanged.emit()

    @Slot(str)
    def selectTradeRoute(self, route_id):
        if any(row["id"] == route_id for row in self.tradeRouteRows):
            self._trade_selected_id = route_id
            self.tradeRoutesChanged.emit()

    @Slot()
    def refreshTradeRoutes(self):
        query = getattr(self,"_trade_last_query",{})
        if not query or getattr(self,"_trade_generation",-1) != getattr(self,"_profile_generation",0):
            return
        self.searchTradeRoutes(query["origin_system"] if query["origin_mode"] == "MANUAL" else "",
            query["commodity"],query["capacity"],query["budget"],query["radius"],query["leg_distance"],
            query["age_hours"],query["pad"],query["exclude_carriers"],query["sort_by"],True)
