"""Manual commodity searches with bounded results on the community server."""
import uuid
import time
import requests
from PySide6.QtCore import Property, Signal, Slot
from ed_companion.navigation.commodity_search import (
    fetch_commodity_catalog, fetch_commodity_offers, describe_commodity_offers,
    commodity_search_region,
)
from ed_companion.navigation.mining_market import fetch_edframe_system_coordinates


class CommoditiesMixin:
    commoditiesChanged = Signal()
    commoditiesFinished = Signal(object)

    @Property("QVariantList", notify=commoditiesChanged)
    def commodityCatalog(self):
        return getattr(self, "_commodity_catalog", [])

    @Property("QVariantList", notify=commoditiesChanged)
    def commodityRows(self):
        if getattr(self, "_commodity_generation", -1) != getattr(self, "_profile_generation", 0):
            return []
        return describe_commodity_offers(getattr(self, "_commodity_rows", []),
            self._state.get("commanderOverview", {}), getattr(self, "_shipyard_permit_rules", {}))

    @Property(bool, notify=commoditiesChanged)
    def commodityBusy(self):
        return bool(getattr(self, "_commodity_request", None))

    @Property("QVariantMap", notify=commoditiesChanged)
    def commodityLastSearch(self):
        if getattr(self, "_commodity_generation", -1) != getattr(self, "_profile_generation", 0):
            return {}
        return dict(getattr(self, "_commodity_last_search", {}))

    @Property(str, notify=commoditiesChanged)
    def commodityStatus(self):
        status = getattr(self, "_commodity_status", "Load the commodity catalog to begin")
        region = getattr(self, "_commodity_region", None)
        if (getattr(self, "_commodity_origin_mode", "JOURNAL") == "JOURNAL" and region
                and region != commodity_search_region(self._state.get("currentPosition"), region["radiusLy"] or 0)):
            return "Previous location · search again · " + status
        return status

    @Slot()
    def loadCommodityCatalog(self):
        if not self.commodityCatalog:
            self.refreshCommodityCatalog()

    @Slot()
    def refreshCommodityCatalog(self):
        self._launch_commodity_request("catalog", {})

    @Slot(str, str, int, int, int, str, bool)
    @Slot(str, str, int, int, int, str, bool, str, str)
    def searchCommodities(self, commodity, direction, radius, quantity, age_hours, pad, exclude_carriers,
                          origin_system="", sort_by="PRICE"):
        requested = str(origin_system).strip()
        if len(requested) > 100 or sort_by not in {"PRICE", "DISTANCE", "AGE"}:
            self._commodity_status = "Invalid start system or sorting · previous search retained"
            self.commoditiesChanged.emit()
            return
        commodities = None
        if commodity == "ALL_RARE_GOODS":
            commodities = sorted({row["id"] for row in self.commodityCatalog if row.get("rare")})
            if not commodities:
                self._commodity_status = "No rare goods in catalog · previous search retained"
                self.commoditiesChanged.emit()
                return
        mode = "MANUAL" if requested else "JOURNAL"
        system = requested or self._state.get("system", "")
        region = None
        if mode == "JOURNAL" or requested.casefold() == str(self._state.get("system", "")).casefold():
            region = commodity_search_region(self._state.get("currentPosition"), radius)
        cached = getattr(self, "_commodity_origin_cache", {})
        if (region is None and mode == "MANUAL" and cached.get("system", "").casefold() == requested.casefold()
                and time.monotonic() - cached.get("resolvedAt", 0) < 3600):
            region = commodity_search_region(cached.get("coordinates"), radius)
            system = cached["system"]
        if not region and mode == "JOURNAL":
            self._commodity_status = "Journal position unavailable · previous search retained"
            self.commoditiesChanged.emit()
            return
        params = dict(commodity=commodity, direction=direction,
            origin=region["origin"] if region else None, radius=radius, quantity=quantity, age_hours=age_hours,
            pad=pad, exclude_carriers=exclude_carriers, region=region, sort_by=sort_by,
            origin_system=system, origin_mode=mode)
        if commodities is not None:
            params["commodities"] = commodities
        self._launch_commodity_request("offers", params)

    def _launch_commodity_request(self, kind, params):
        if self.commodityBusy or getattr(self, "_shutdown_complete", False):
            return
        if not getattr(self, "_edframe_catalog_enabled", True):
            self._commodity_status = "Server disabled · previous search retained"
            self.commoditiesChanged.emit()
            return
        query = dict(id=uuid.uuid4().hex, kind=kind, params=params,
            generation=getattr(self, "_profile_generation", 0), system=self._state.get("system", ""))
        self._commodity_request = query
        self._commodity_status = "Searching ED-Frame catalog…"
        self.commoditiesChanged.emit()
        def worker():
            result = dict(query)
            try:
                resolved = dict(params)
                if kind == "offers" and resolved["origin"] is None:
                    location = fetch_edframe_system_coordinates(resolved["origin_system"], get=requests.get)
                    resolved.update(origin=location["coordinates"], origin_system=location["system"],
                        region=commodity_search_region(location["coordinates"], resolved["radius"]))
                result["params"] = resolved
                args = {k: v for k, v in resolved.items() if k not in {"region", "origin_system", "origin_mode"}}
                result["payload"] = (fetch_commodity_catalog(get=requests.get) if kind == "catalog"
                    else fetch_commodity_offers(get=requests.get, **args))
                result["success"] = True
            except Exception as exc:
                result.update(success=False, error=f"{type(exc).__name__}: {exc}")
            self.commoditiesFinished.emit(result)
        if not self._start_network_worker(worker, "commodity-search"):
            self._commodity_request = None
            self._commodity_status = "Search paused during shutdown · previous search retained"
            self.commoditiesChanged.emit()

    @Slot(object)
    def _finish_commodities(self, result):
        query = getattr(self, "_commodity_request", None)
        if not query or query["id"] != result.get("id"):
            return
        self._commodity_request = None
        region = query["params"].get("region")
        if result["generation"] != getattr(self, "_profile_generation", 0):
            self._commodity_status = "Profile changed · search again"
        elif (query["params"].get("origin_mode", "JOURNAL") == "JOURNAL" and region
                and region != commodity_search_region(self._state.get("currentPosition"), region["radiusLy"] or 0)):
            self._commodity_status = "Location changed · previous search retained; search again"
        elif not getattr(self, "_edframe_catalog_enabled", True):
            self._commodity_status = "Server disabled · previous search retained"
        elif not result.get("success"):
            self._commodity_status = "Search failed · previous search retained · " + result.get("error", "")
        elif query["kind"] == "catalog":
            self._commodity_catalog = result["payload"]
            self._commodity_status = f"{len(self._commodity_catalog)} commodities · choose BUY or SELL"
        else:
            payload = result["payload"]
            params = result.get("params", query["params"])
            region = params["region"]
            self._commodity_rows = payload["results"]
            self._commodity_generation = result["generation"]
            self._commodity_region = region
            self._commodity_origin_mode = params.get("origin_mode", "JOURNAL")
            origin_name = params.get("origin_system", query["system"])
            if self._commodity_origin_mode == "MANUAL":
                self._commodity_origin_cache = dict(system=origin_name, coordinates=region["origin"],
                    resolvedAt=time.monotonic())
            self._commodity_last_search = dict(
                system=origin_name, originMode=self._commodity_origin_mode, radius=region["radiusLy"],
                commodity=params["commodity"], direction=params["direction"],
                quantity=params.get("quantity", 1), ageHours=params.get("age_hours", 24),
                pad=params.get("pad", "ANY"), excludeCarriers=params.get("exclude_carriers", False),
                sortBy=params.get("sort_by", "PRICE"), count=len(payload["results"]),
                hasMore=bool(payload.get("hasMore")))
            selection = "Rare Goods · ALL" if query["params"]["commodity"] == "ALL_RARE_GOODS" else query["params"]["commodity"]
            distance_scope = "unlimited" if region["radiusLy"] is None else f"{region['radiusLy']:g} LY"
            self._commodity_status = (f"{len(payload['results'])} matches · {query['params']['direction']}"
                f" · {selection} · around {origin_name} · {distance_scope}"
                + (" · first 100; more exist" if payload.get("hasMore") else ""))
        self.commoditiesChanged.emit()
