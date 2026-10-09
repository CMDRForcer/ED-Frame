"""Offline JSON/SQLite experiment with frozen public copies and fresh workers.

No live profile instantiation, networking, uploads, history edits or migration.
--source reads only four named public JSONs. --output must be a NEW .test-tmp
directory. The app does not import or use the experimental store.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import hashlib
from itertools import zip_longest
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.mining_ring_store_prototype import (
    PrototypeRingStore, StoreScope, build_store, encode, file_digest, iter_catalog,
)
from tools.benchmark_mining_baseline import memory
from ed_companion.navigation.mining_ring_store import RingCatalogStore, TRANSIENT_FIELDS

NAMES = ("mining_finder_catalog.json", "mining_market_cache.json",
         "mining_powerplay_catalog.json", "mining_powerplay_observations.json")
SCOPE = StoreScope("synthetic-ring-store-benchmark", "frozen-input-1")
ORIGIN = [110.9375, -113.0625, 41.21875]
SYSTEM = "Shanteneri"


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 10, 9, 12, tzinfo=timezone.utc)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


def digest(rows):
    checksum = hashlib.sha256()
    count = 0
    for row in rows:
        checksum.update(json.dumps(row, sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":")).encode())
        count += 1
    return {"count": count, "sha256": checksum.hexdigest()}


def query(args):
    from ed_companion.navigation.catalog_json import load_catalog_snapshot
    from ed_companion.navigation.mining_geometry import MiningGeometryCache, nearby_rows
    from ed_companion.navigation.mining_planner import PowerplayIndexCache
    from ed_companion.navigation.mining_powerplay import catalog_rows
    from ed_companion.phase14.controller import CockpitController
    from ed_companion.phase14.controller_navigation import NavigationMixin
    import requests

    def reject_http(*_args, **_kwargs):
        raise RuntimeError("Ring-store replay forbids all networking")
    requests.Session.request = reject_http
    prepared = args.prepared or args.output
    fixture = prepared / "fixture"
    started = time.perf_counter()
    initial_memory = memory()
    if args.worker == "json":
        root = load_catalog_snapshot(fixture / NAMES[0], {})
        rows = root["candidates"]
        if args.production:
            for row in rows:
                for field in TRANSIENT_FIELDS:
                    row.pop(field,None)
        ring_open = time.perf_counter() - started
        selection_started = time.perf_counter()
        selected = [rows[i] for i, _ in nearby_rows(
            rows, SYSTEM, ORIGIN, args.radius, CockpitController._valid_star_position)]
    else:
        store = (RingCatalogStore(args.output / "rings.sqlite3", SCOPE.profile).view()
                 if args.production else PrototypeRingStore(prepared / "rings.sqlite3", SCOPE))
        if args.production:
            store.signals()
        else:
            store.metadata()  # Includes scope/format verification.
        ring_open = time.perf_counter() - started
        selection_started = time.perf_counter()
        if args.production:
            rows = store
            selected = list(store.nearby(SYSTEM, ORIGIN, args.radius))
        else:
            rows = list(store.nearby(SYSTEM, ORIGIN, args.radius, snapshot_arrays=args.compact))
            selected = rows
    selection_seconds = time.perf_counter() - selection_started
    region = digest(selected)
    del selected
    gc.collect()
    ring_memory = memory()
    markets = load_catalog_snapshot(fixture / NAMES[1], {}).get("markets", [])
    powerplay = load_catalog_snapshot(fixture / NAMES[2], {})
    observations = load_catalog_snapshot(fixture / NAMES[3], [])
    if isinstance(observations, dict):
        observations = observations.get("observations", [])
    facade = NavigationMixin()
    facade._state = {"system": SYSTEM, "currentPosition": ORIGIN}
    facade._network_threads_lock = True
    facade._mining_rows = lambda: rows
    facade._mining_rows_cache_key = ("frozen-ring-store-input",)
    facade._valid_star_position = CockpitController._valid_star_position
    facade._mining_market_rows_for_query = lambda _query: markets
    facade._mining_powerplay_catalog = powerplay
    facade._mining_powerplay_observations = observations
    facade._mining_powerplay_index_cache = PowerplayIndexCache()
    facade._mining_powerplay_index_scope = "frozen-ring-store-input"
    facade._mining_powerplay_index_cache.index_for(
        facade._mining_powerplay_index_scope, catalog_rows(powerplay), observations)
    facade._mining_geometry_cache = MiningGeometryCache()
    data = {"mode": args.worker, "radius": args.radius, "clock": Clock.now(timezone.utc).isoformat(),
            "representation": "production-snapshot" if args.worker == "json" or args.compact else "ordinary-json",
            "initialMemory": initial_memory, "ringMemory": ring_memory,
            "ringOpenSeconds": ring_open, "selectionSeconds": selection_seconds,
            "ringAccessSeconds": ring_open + selection_seconds,
            "loadedRingRows": region["count"] if args.production and args.worker=="sqlite" else len(rows),
            "storedRingRows": len(rows), "region": region, "filters": {}, "routes": {}}
    with patch("ed_companion.navigation.mining_finder.datetime", Clock), \
            patch("ed_companion.navigation.mining_planner.datetime", Clock), \
            patch("ed_companion.phase14.controller_navigation.time.time", return_value=1791547200):
        for label, commodity, evidence, reserve, method, rings_only in (
            ("laser-all", "Platinum", "ALL EVIDENCE", "ALL RESERVES", "LASER", False),
            ("laser-pristine-rings", "Platinum", "ALL EVIDENCE", "PRISTINE", "LASER", True),
            ("laser-major", "Platinum", "ALL EVIDENCE", "MAJOR", "LASER", True),
            ("laser-confirmed", "Platinum", "HOTSPOT_CONFIRMED", "PRISTINE + MAJOR", "LASER", True),
            ("laser-recheck", "Platinum", "RECHECK_RECOMMENDED", "ALL RESERVES", "LASER", True),
            ("core-void-opals", "Void Opals", "ALL EVIDENCE", "ALL RESERVES", "CORE", True),
            ("all-commodities", "ALL COMMODITIES", "ALL EVIDENCE", "ALL RESERVES", "LASER", True),
        ):
            facade._mining_find_cache_key = None
            call_started = time.perf_counter()
            found = facade._mining_find_page(commodity, args.radius, evidence, reserve,
                                             method, SYSTEM, rings_only)
            duration = time.perf_counter() - call_started
            data["filters"][label] = {**digest(found), "seconds": duration}
            del found
        for label, mode, goal in (("reinforce", "POWERPLAY MERITS", "REINFORCE"),
                                  ("acquire", "POWERPLAY MERITS", "ACQUIRE"),
                                  ("profit", "HIGHEST PROFIT", "REINFORCE")):
            facade._mining_find_cache_key = None
            def plan():
                return facade._compute_mining_plan_routes(
                    SYSTEM, "Platinum", args.radius, "ALL RESERVES", "ANY RING",
                    True, "LASER", mode, 5000, 500000, 1, 100, False, True,
                    False, False, "L", "Aisling Duval", goal, "ANY", "ANY")
            call_started = time.perf_counter()
            routes = plan()
            cold_seconds = time.perf_counter() - call_started
            expected = digest(routes)
            durations = []
            for _ in range(3):
                facade._mining_find_cache_key = None
                call_started = time.perf_counter()
                repeated = plan()
                durations.append(time.perf_counter() - call_started)
                if digest(repeated) != expected:
                    raise AssertionError("Repeated routes changed at fixed clock")
            data["routes"][label] = {**expected, "firstSeconds": cold_seconds,
                                      "warmSeconds": durations, "warmMedian": statistics.median(durations)}
            del routes, repeated
        # Changing the clock must affect age/merit evaluation equally in both
        # stores, rather than freezing a result from a previous search.
        class LaterClock(Clock):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 10, 11, 12, tzinfo=timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        with patch("ed_companion.navigation.mining_finder.datetime", LaterClock), \
                patch("ed_companion.navigation.mining_planner.datetime", LaterClock), \
                patch("ed_companion.phase14.controller_navigation.time.time", return_value=1791720000):
            facade._mining_find_cache_key = None
            data["laterRecheck"] = digest(facade._mining_find_page(
                "Platinum", args.radius, "RECHECK_RECOMMENDED", "ALL RESERVES", "LASER", SYSTEM, True))
            facade._mining_find_cache_key = None
            data["laterAcquire"] = digest(facade._compute_mining_plan_routes(
                SYSTEM, "Platinum", args.radius, "ALL RESERVES", "ANY RING",
                True, "LASER", "POWERPLAY MERITS", 5000, 500000, 1, 100, False, True,
                False, False, "L", "Aisling Duval", "ACQUIRE", "ANY", "ANY"))
    gc.collect()
    data["finalMemory"] = memory()
    return data


def worker(args):
    if args.worker == "build":
        started = time.perf_counter()
        if args.production:
            prepared=args.prepared or args.output
            view=RingCatalogStore(args.output / "rings.sqlite3", SCOPE.profile).adopt(prepared / "fixture" / NAMES[0])
            result={"count":len(view),"bytes":view.store.path.stat().st_size,
                    "format":view.head["format"],"production":True}
        else:
            result = build_store(args.output / "fixture" / NAMES[0], args.output / "rings.sqlite3", SCOPE)
        result.update(seconds=time.perf_counter()-started, memory=memory())
    elif args.worker == "integrity":
        prepared = args.prepared or args.output
        store = (RingCatalogStore(args.output / "rings.sqlite3", SCOPE.profile).view()
                 if args.production else PrototypeRingStore(prepared / "rings.sqlite3", SCOPE))
        metadata = {}
        sentinel = object()
        checksum = hashlib.sha256()
        count = 0
        for original, stored in zip_longest(iter_catalog(prepared / "fixture" / NAMES[0], metadata),
                                           store.raw_records() if args.production else store.iter_all(), fillvalue=sentinel):
            if original is sentinel or stored is sentinel or encode(original) != encode(stored):
                raise AssertionError("Full offline payload/order mismatch")
            checksum.update(encode(original).encode())
            count += 1
        if metadata != (store.head["root"] if args.production else store.metadata()["root"]):
            raise AssertionError("Root metadata mismatch")
        with (store.store.reader(store) if args.production else store._reader()) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise AssertionError("SQLite integrity check failed")
            if connection.execute("SELECT rtreecheck('spatial')").fetchone()[0] != "ok":
                raise AssertionError("Spatial index integrity check failed")
        result = {"count": count, "sha256": checksum.hexdigest(), "rootMetadataEqual": True,
                  "sqliteIntegrity": "ok", "spatialIntegrity": "ok"}
    else:
        result = query(args)
    args.result.write_text(json.dumps(result, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--prepared", type=Path, help="Read-only reuse of a prior frozen .test-tmp fixture/store")
    parser.add_argument("--compact", action="store_true", help="Use the production JSON representation for SQLite rows")
    parser.add_argument("--production", action="store_true", help="Build and exercise the integrated durable view using a frozen fixture")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--worker", choices=("build", "integrity", "json", "sqlite"))
    parser.add_argument("--radius", type=int, choices=(250, 500))
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if not args.output.is_relative_to(ROOT / ".test-tmp"):
        raise ValueError("Only isolated .test-tmp outputs are supported")
    if args.prepared is not None:
        args.prepared = args.prepared.resolve()
        if not args.prepared.is_relative_to(ROOT / ".test-tmp") or args.source is not None:
            raise ValueError("Reuse requires an isolated prepared input without --source")
    if args.worker:
        if args.result is None or not args.result.resolve().is_relative_to(args.output):
            raise ValueError("Worker result must stay in isolated output")
        worker(args)
        return
    if (args.source is None and args.prepared is None) or args.output.exists() or args.trials < 1:
        raise ValueError("A source and NEW isolated output plus positive trials are required")
    args.output.mkdir(parents=True)
    if args.prepared:
        fixture = args.prepared / "fixture"
        inventory = json.loads((args.prepared / "inventory.json").read_text(encoding="utf-8"))
        if {item["file"] for item in inventory} != set(NAMES):
            raise ValueError("Unexpected prepared fixture inventory")
        for item in inventory:
            if file_digest(fixture / item["file"]) != item["sha256"]:
                raise ValueError("Prepared input hash mismatch")
        database_before = file_digest(args.prepared / "rings.sqlite3")
    else:
        fixture = args.output / "fixture"
        fixture.mkdir()
        inventory = []
        for name in NAMES:
            original, target = args.source / name, fixture / name
            before = file_digest(original)
            shutil.copy2(original, target)
            if before != file_digest(target) or before != file_digest(original):
                raise ValueError("Public source changed while creating frozen copy")
            inventory.append({"file": name, "bytes": target.stat().st_size, "sha256": before})
    (args.output / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    environment = os.environ.copy()
    isolated = args.output / "isolated"
    isolated.mkdir()
    environment.update(LOCALAPPDATA=str(isolated), TEMP=str(isolated), TMP=str(isolated),
                       QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
    def run(mode, name, radius=None):
        result = args.output / (name + ".json")
        command = [sys.executable, "-B", str(Path(__file__).resolve()), "--output", str(args.output),
                   "--worker", mode, "--result", str(result)]
        if radius is not None:
            command.extend(["--radius", str(radius)])
        if args.prepared:
            command.extend(["--prepared", str(args.prepared)])
        if args.compact:
            command.append("--compact")
        if args.production:
            command.append("--production")
        with (args.output / (name + ".log")).open("w", encoding="utf-8") as log:
            subprocess.run(command, cwd=ROOT, env=environment, stdout=log,
                           stderr=subprocess.STDOUT, timeout=300, check=True)
        value = json.loads(result.read_text(encoding="utf-8"))
        print(name, "PASS", flush=True)
        return value
    build = (json.loads((args.prepared / "build.json").read_text(encoding="utf-8"))
             if args.prepared and not args.production else run("build", "build"))
    data = {"inventory": inventory, "build": build, "buildReused": bool(args.prepared),
            "sourceCode": {name: file_digest(ROOT/name) for name in (
                "tools/mining_ring_store_prototype.py", "tools/benchmark_mining_ring_store.py",
                "ed_companion/navigation/mining_ring_store.py",
                "ed_companion/navigation/catalog_json.py", "ed_companion/phase14/controller_navigation.py")},
            "integrity": run("integrity", "integrity"), "queries": {}}
    for radius in (250, 500):
        values = {"json": [], "sqlite": []}
        # Alternating serial fresh processes limits order and memory bias.
        for trial in range(args.trials):
            for mode in (("json", "sqlite") if trial % 2 == 0 else ("sqlite", "json")):
                values[mode].append(run(mode, f"{mode}-{radius}-{trial}", radius))
        first = values["json"][0]
        def signatures(result):
            return {"region": result["region"],
                    "filters": {key: {k: v for k, v in value.items() if k != "seconds"}
                                for key, value in result["filters"].items()},
                    "routes": {key: {k: value[k] for k in ("count", "sha256")}
                               for key, value in result["routes"].items()},
                    "laterRecheck": result["laterRecheck"], "laterAcquire": result["laterAcquire"]}
        for runs in values.values():
            for result in runs:
                if signatures(result) != signatures(first):
                    raise AssertionError(f"JSON/SQLite results differ at {radius} LY")
        data["queries"][str(radius)] = {"equal": True, "runs": values}
    data["inputsUnchanged"] = all(file_digest(fixture/item["file"]) == item["sha256"]
                                  and (args.source is None or file_digest(args.source/item["file"]) == item["sha256"])
                                  for item in inventory)
    data["databaseUnchanged"] = (file_digest(args.prepared / "rings.sqlite3") == database_before
                                  if args.prepared else True)
    if not data["inputsUnchanged"] or not data["databaseUnchanged"]:
        raise AssertionError("Public input hashes changed")
    (args.output / "result.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("FULL OFFLINE JSON/SQLITE COMPARISON PASS", flush=True)


if __name__ == "__main__":
    main()
