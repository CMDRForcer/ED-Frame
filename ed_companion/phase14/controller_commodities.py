"""Manual, bounded commodity searches on the community server."""
import uuid
import requests
from PySide6.QtCore import Property, Signal, Slot
from ed_companion.navigation.commodity_search import (
    fetch_commodity_catalog, fetch_commodity_offers, describe_commodity_offers,
)
from ed_companion.navigation.state_find_catalog import state_find_region


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

    @Property(str, notify=commoditiesChanged)
    def commodityStatus(self):
        status = getattr(self, "_commodity_status", "Load the commodity catalog to begin")
        region = getattr(self, "_commodity_region", None)
        if region and region != state_find_region(self._state.get("currentPosition"), region["radiusLy"]):
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
    def searchCommodities(self, commodity, direction, radius, quantity, age_hours, pad, exclude_carriers):
        commodities = None
        if commodity == "ALL_RARE_GOODS":
            commodities = sorted({row["id"] for row in self.commodityCatalog if row.get("rare")})
            if not commodities:
                self._commodity_status = "No rare goods in catalog · previous search retained"
                self.commoditiesChanged.emit()
                return
        region = state_find_region(self._state.get("currentPosition"), radius)
        if not region:
            self._commodity_status = "Journal position unavailable · previous search retained"
            self.commoditiesChanged.emit()
            return
        params = dict(commodity=commodity, direction=direction,
            origin=region["origin"], radius=radius, quantity=quantity, age_hours=age_hours,
            pad=pad, exclude_carriers=exclude_carriers, region=region)
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
                args = {k: v for k, v in params.items() if k != "region"}
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
        elif region and region != state_find_region(self._state.get("currentPosition"), region["radiusLy"]):
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
            self._commodity_rows = payload["results"]
            self._commodity_generation = result["generation"]
            self._commodity_region = region
            selection = "Rare Goods · ALL" if query["params"]["commodity"] == "ALL_RARE_GOODS" else query["params"]["commodity"]
            self._commodity_status = (f"{len(payload['results'])} matches · {query['params']['direction']}"
                f" · {selection} · around {query['system']} · {region['radiusLy']:g} LY"
                + (" · first 100 by price; more exist" if payload.get("hasMore") else ""))
        self.commoditiesChanged.emit()
