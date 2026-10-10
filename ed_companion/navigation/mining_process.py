"""Mining CPU isolation. Transfer a ring revision descriptor, not the galaxy."""
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
import os
import sqlite3
import threading
import time
import importlib
from ed_companion.compute_work import ComputeWork, ComputeStopped

from .mining_market_store import MarketCatalogStore


def worker_memory():
    if os.name != "nt":
        return {}
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("peak", "working", "peakPaged", "paged",
                "peakNonpaged", "nonpaged", "pagefile", "peakPagefile")]
    value = Counters()
    value.cb = ctypes.sizeof(value)
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.windll.psapi
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(value), value.cb):
        return {"miningWorkerRssMiB": round(value.working / 1024**2, 1),
                "miningWorkerPeakRssMiB": round(value.peak / 1024**2, 1)}
    return {}


class ReadOnlyMarkets(MarketCatalogStore):
    def __init__(self, path):
        self.path = Path(path)
        self._read_condition = threading.Condition()
        self._active_readers = 0
        self._read_maintenance_active = False

    def _recover(self):
        # The app owns maintenance. A child must never replace a live database.
        raise sqlite3.DatabaseError("Mining reader requires database recovery in the app")


def plan_in_process(payload):
    from ed_companion.phase14.controller_navigation import NavigationMixin
    from ed_companion.phase14.controller import CockpitController
    from .mining_ring_store import RingCatalogStore, RingCatalogView
    from .mining_planner import PowerplayIndexCache
    from .mining_geometry import MiningGeometryCache

    started = time.monotonic()
    descriptor = payload["rings"]
    store = RingCatalogStore(descriptor["path"], descriptor["profile"])
    rows = RingCatalogView(store, descriptor["head"], descriptor["overlay"])
    rows._signals = descriptor["signals"]
    facade = NavigationMixin()
    for name, value in payload["attributes"].items():
        setattr(facade, name, value)
    facade._mining_rows = lambda: rows
    facade._mining_catalog = {"candidates": rows}
    facade._network_threads_lock = True
    facade._valid_star_position = CockpitController._valid_star_position
    facade._system_coordinate_index = CockpitController._system_coordinate_index.__get__(facade)
    facade._mining_market_store = ReadOnlyMarkets(payload["markets"])
    facade._mining_powerplay_index_scope = payload["scope"]
    facade._mining_powerplay_index_cache = PowerplayIndexCache()
    facade._mining_geometry_cache = MiningGeometryCache()
    facade._mining_plan_market_rows = {}
    args = payload["args"]
    diagnostic_args = (args[0], args[1], args[2], args[8], args[9], args[10], args[16])
    # One calculation uses one clock across all evidence/age decisions.
    frozen = datetime.fromisoformat(payload["clock"])
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen.astimezone(tz) if tz else frozen.replace(tzinfo=None)
    with ExitStack() as stack:
        for module in ("mining_finder", "mining_planner", "mining_market_store", "mining_powerplay"):
            target = importlib.import_module("ed_companion.navigation." + module)
            stack.callback(setattr, target, "datetime", target.datetime)
            target.datetime = Clock
        target = importlib.import_module("ed_companion.phase14.controller_navigation")
        stack.callback(setattr, target, "datetime", target.datetime)
        target.datetime = Clock
        stack.callback(setattr, time, "time", time.time)
        time.time = lambda: frozen.timestamp()
        routes = facade._compute_mining_plan_routes(*args)
        diagnostics = facade.miningMarketDiagnostics(*diagnostic_args)
    return routes, diagnostic_args, diagnostics, {
        "miningWorkerPid": os.getpid(), "miningWorkerMode": "process",
        "miningComputeSeconds": round(time.monotonic()-started, 3),
        **worker_memory(),
    }


class MiningProcess:
    def __init__(self, service=None):
        self._service = service or ComputeWork()
        self._owns_service = service is None
        self._closed = False

    def compute(self, payload, fallback=None):
        if self._closed:
            raise ComputeStopped("Mining worker stopped")
        all_commodities = str(payload.get("args", ("", ""))[1]).replace(" ", "").lower() == "allcommodities"
        estimate = 3072 if all_commodities else 1024
        return self._service.compute("mining", plan_in_process, payload,
                                     memory_mb=estimate, priority=2, fallback=fallback)

    def close(self):
        self._closed = True
        if self._owns_service:
            self._service.close()
