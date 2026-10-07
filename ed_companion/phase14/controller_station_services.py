"""On-demand station finder; no background polling or external database fallback."""
import uuid
import requests
from PySide6.QtCore import Property, Signal, Slot
from ed_companion.navigation.station_services import (
    SERVICES, describe_station_services, fetch_station_services,
)
from ed_companion.navigation.state_find_catalog import state_find_region


class StationServicesMixin:
    stationServicesChanged = Signal()
    stationServicesFinished = Signal(object)

    @Property("QVariantList", notify=stationServicesChanged)
    def stationServiceChoices(self):
        return [{"key": key, "label": label} for key, label in SERVICES]

    @Property("QVariantList", notify=stationServicesChanged)
    def stationServiceRows(self):
        # A different Commander must never inherit a previous profile's access verdict.
        if getattr(self, "_station_services_rows_generation", -1) != getattr(self, "_profile_generation", 0):
            return []
        return describe_station_services(
            getattr(self, "_station_services_rows", []),
            getattr(self, "_state", {}).get("commanderOverview", {}),
            getattr(self, "_shipyard_permit_rules", {}),
        )

    @Property(bool, notify=stationServicesChanged)
    def stationServiceBusy(self):
        return bool(getattr(self, "_station_services_busy", False))

    @Property(str, notify=stationServicesChanged)
    def stationServiceStatus(self):
        status = getattr(self, "_station_services_status", "Choose a service and search · public ED-Frame catalog")
        generation = getattr(self, "_station_services_rows_generation", None)
        if generation is not None and generation != getattr(self, "_profile_generation", 0) and not self.stationServiceBusy:
            return "Profile changed · choose a service and search again"
        previous = getattr(self, "_station_services_result_region", None)
        if previous and not self.stationServiceBusy and previous != state_find_region(
            getattr(self, "_state", {}).get("currentPosition"), previous["radiusLy"]
        ):
            return "Previous location · search again · " + status
        return status

    @Slot(str, int, str, bool)
    def searchStationServices(self, service, radius, pad, exclude_carriers):
        if self.stationServiceBusy or getattr(self, "_shutdown_complete", False):
            return
        if not getattr(self, "_edframe_catalog_enabled", True):
            self._station_services_status = "ED-Frame server disabled · previous search retained"
            self.stationServicesChanged.emit()
            return
        region = state_find_region(getattr(self, "_state", {}).get("currentPosition"), radius)
        if not region:
            self._station_services_status = "Journal position unavailable · previous search retained"
            self.stationServicesChanged.emit()
            return
        query = {
            "id": uuid.uuid4().hex, "generation": getattr(self, "_profile_generation", 0),
            "region": region, "system": str(self._state.get("system") or ""),
            "service": service,
        }
        self._station_services_request = query
        self._station_services_busy = True
        self._station_services_status = "Searching ED-Frame catalog…"
        self.stationServicesChanged.emit()

        def worker():
            result = dict(query)
            try:
                result["payload"] = fetch_station_services(
                    origin=region["origin"], service=service, radius_ly=radius,
                    pad=pad, exclude_carriers=exclude_carriers, get=requests.get,
                )
                result["success"] = True
            except Exception as exc:
                result.update(success=False, error=f"{type(exc).__name__}: {exc}")
            self.stationServicesFinished.emit(result)

        if not self._start_network_worker(worker, "station-services"):
            self._station_services_request = None
            self._station_services_busy = False
            self._station_services_status = "Search paused during shutdown · previous search retained"
            self.stationServicesChanged.emit()

    @Slot(object)
    def _finish_station_services(self, result):
        query = getattr(self, "_station_services_request", None)
        if not query or query["id"] != result.get("id"):
            return
        self._station_services_request = None
        self._station_services_busy = False
        current = state_find_region(getattr(self, "_state", {}).get("currentPosition"),
                                    query["region"]["radiusLy"])
        if result.get("generation") != getattr(self, "_profile_generation", 0):
            self._station_services_rows = []
            self._station_services_status = "Profile changed · search again"
        elif current != query["region"]:
            self._station_services_status = "Location changed · previous search retained; search again"
        elif not getattr(self, "_edframe_catalog_enabled", True):
            self._station_services_status = "Server disabled · previous search retained"
        elif not result.get("success"):
            self._station_services_status = "Search failed · previous search retained · " + str(result.get("error") or "")
        else:
            payload = result["payload"]
            self._station_services_rows = payload["results"]
            self._station_services_rows_generation = result["generation"]
            self._station_services_result_region = query["region"]
            self._station_services_status = (
                f"{len(payload['results'])} matches · {dict(SERVICES).get(query['service'], query['service'])}"
                f" · around {query['system']} · {query['region']['radiusLy']:g} LY"
                + (" · first 100 nearest matches, more exist" if payload.get("hasMore") else "")
                + " · station metadata, not guaranteed docking access"
            )
        self.stationServicesChanged.emit()
