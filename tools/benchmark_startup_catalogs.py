"""Isolated native startup/RAM comparison using frozen public JSON copies.

No real profile, history, uploads or HTTP; the synthetic market store is empty.
Measures source/offscreen/software rendering, not the installed executable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.benchmark_mining_baseline import FID, PROFILE, memory

PUBLIC_FILES = (
    "mining_finder_catalog.json", "mining_powerplay_catalog.json",
    "mining_powerplay_observations.json", "hge_live_sightings.json",
)


def file_digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def prepare(destination, source):
    if destination.exists():
        raise RuntimeError("Use a fresh isolated fixture directory")
    profile = destination / "local" / "ED-Frame" / PROFILE
    profile.mkdir(parents=True)
    inventory = []
    for name in PUBLIC_FILES:
        original = source / name
        if not original.is_file():
            continue
        target = profile / name
        shutil.copy2(original, target)
        inventory.append({"file": name, "bytes": target.stat().st_size,
                          "sha256": file_digest(target)})
    (destination / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    (profile / "phase14_graphics.json").write_text(json.dumps({
        "onboarding_complete": True, "background_mode": False,
        "journal_auto": False, "last_page": 0, "renderer_mode": "software",
        "edframe_catalog_enabled": False, "interface_language": "en",
    }), encoding="utf-8")
    (profile / "eddn_config.json").write_text(json.dumps({
        "consent": False, "upload_enabled": False, "listener_enabled": False,
        "hge_classifier_version": 2,
    }), encoding="utf-8")
    journal = destination / "journal"
    journal.mkdir()
    events = [
        {"event": "Fileheader", "timestamp": "2026-10-09T00:00:00Z", "part": 1},
        {"event": "LoadGame", "timestamp": "2026-10-09T00:00:01Z", "FID": FID,
         "Commander": "Startup Fixture", "Ship": "Adder", "ShipID": 1,
         "Credits": 1000000, "Horizons": True, "Odyssey": True},
        {"event": "Location", "timestamp": "2026-10-09T00:00:02Z",
         "StarSystem": "Shanteneri", "StarPos": [110.9375, -113.0625, 41.21875],
         "Docked": False},
    ]
    (journal / "Journal.2026-10-09T000000.01.log").write_text(
        "\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")


def run(args):
    destination = args.output
    profile = destination / "local" / "ED-Frame" / PROFILE
    if not (destination / "inventory.json").is_file() or not profile.resolve().is_relative_to(destination):
        raise RuntimeError("Prepare an isolated fixture first")
    # Each run starts on Operations; a previous run closes on Mining and the
    # controller correctly persists that navigation choice in the test profile.
    config_path = profile / "phase14_graphics.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["last_page"] = 0
    config_path.write_text(json.dumps(config), encoding="utf-8")
    inventory = json.loads((destination / "inventory.json").read_text())
    for item in inventory:
        if file_digest(profile / item["file"]) != item["sha256"]:
            raise RuntimeError("Public fixture changed; restore the exact frozen input before comparing")
    os.environ.update({
        "LOCALAPPDATA": str(destination / "local"), "TEMP": str(destination), "TMP": str(destination),
        "ED_FRAME_JOURNAL_DIR": str(destination / "journal"), "ED_FRAME_PROFILE_FID": FID,
        "ED_FRAME_SINGLE_INSTANCE_NAME": "ED-Frame-startup-" + destination.name,
        "PHASE14_SMOKE_TEST": "1", "PHASE14_SMOKE_ASYNC_PAGES": "1",
        "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
        "PHASE14_PREVIEW_WIDTH": "1600", "PHASE14_PREVIEW_HEIGHT": "1000",
    })
    import requests
    import phase14_main as app_main
    from PySide6.QtCore import QTimer, Qt
    from ed_companion.phase14.controller import CockpitController
    from ed_companion import APP_VERSION

    def reject_http(*_args, **_kwargs):
        raise RuntimeError("Offline startup benchmark forbids all networking")
    requests.Session.request = reject_http
    app_main.register_windows_url_protocol = lambda **kwargs: False
    for name in ("_ensure_eddn_listener", "refreshEdFrameCatalogStatus", "syncEdFrameCatalog",
                 "_maybe_auto_refresh_spansh", "_maybe_auto_refresh_mining_markets",
                 "_maybe_share_state_signals", "_maybe_share_mining_yields",
                 "_schedule_mining_market_backup"):
        setattr(CockpitController, name, lambda self, *a, **k: None)
    started = time.perf_counter()
    beats = []
    timers = []
    phase = ["startup"]
    load_requests = []
    original = app_main.CockpitController
    ensure = CockpitController._ensure_mining_catalog_loaded
    def traced_ensure(self, **kwargs):
        if (not getattr(self, "_mining_catalog_loaded", True)
                and getattr(self, "_mining_catalog_load_future", None) is None):
            load_requests.append({"phase": phase[0], "at": round(time.perf_counter() - started, 4),
                                  "stack": traceback.format_stack(limit=8)})
        return ensure(self, **kwargs)
    CockpitController._ensure_mining_catalog_loaded = traced_ensure
    source = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
        "ed_companion/phase14/controller.py", "ed_companion/phase14/controller_navigation.py",
        "ed_companion/navigation/mining_batch.py", "ed_companion/navigation/catalog_json.py",
        "ed_companion/navigation/mining_ring_store.py",
    )}

    def factory():
        stamp = [time.perf_counter()]
        timer = QTimer()
        timer.setTimerType(Qt.TimerType.PreciseTimer)
        def tick():
            now = time.perf_counter()
            beats.append({"phase": phase[0], "gapMs": round((now - stamp[0]) * 1000, 3)})
            stamp[0] = now
        timer.timeout.connect(tick)
        timer.start(10)
        timers.append(timer)
        return original()
    app_main.CockpitController = factory

    class Runner(app_main.SmokeTestRunner):
        def start(self):
            self.stage = "operations"
            self.first_ui = round(time.perf_counter() - started, 4)
            self.operations_ready = None
            self.loaded_at = None
            self.opened_at = None
            self.samples = {}
            self.poller = QTimer(self)
            self.poller.timeout.connect(self.check)
            self.poller.start(25)

        def check(self):
            now = time.perf_counter()
            c = self.controller
            if now - started > 90:
                self.finish("Timed out")
                return
            if self.stage == "operations":
                if self.operations_ready is None and getattr(c, "_journal_state_ready", False):
                    self.operations_ready = round(now - started, 4)
                    self.samples["operationsReady"] = memory()
                if now - started < 12:
                    return
                self.samples["operationsIdle"] = memory()
                self.idle_rings = len(c._mining_catalog.get("candidates", []))
                self.idle_positions = len(getattr(c, "_mining_catalog_positions", {}))
                self.stage = "mining"
                phase[0] = "mining"
                self.opened_at = now
                self.window.setProperty("currentPage", 12)
                return
            if self.stage == "mining":
                rows = c._mining_catalog.get("candidates", [])
                if not rows or getattr(c, "_mining_rows_build_in_flight", False):
                    return
                if self._find("qa-page-mining-finder") is None:
                    return
                if self.loaded_at is None:
                    self.loaded_at = now
                if now - self.loaded_at >= 2:
                    self.samples["miningIdle"] = memory()
                    if args.exercise_mining:
                        if args.local_delta:
                            state = dict(c._state)
                            local = dict(state.get("localMiningEvidence") or {})
                            local["candidates"] = [*local.get("candidates", []), {
                                "system": "Ring Delta Fixture", "ring": "Ring Delta Fixture 1 A Ring",
                                "coordinates": [111.9375, -113.0625, 41.21875],
                                "ringType": "Metallic", "reserveLevel": "Pristine",
                                "sourceEvidence": "LOCAL_CONFIRMED", "observedAt": "2026-10-09T12:00:00Z",
                                "learnedAt": "2026-10-09T12:00:00Z",
                                "hotspots": [{"commodity": "platinum", "count": 1}],
                            }]
                            state["localMiningEvidence"] = local
                            c._state = state
                            c._mining_rows_cache_key = None
                        self.stage = "plan"
                        self.plan_started = now
                        self.plan_args = ("Shanteneri", "Platinum", args.mining_radius, "ALL RESERVES", "ANY RING",
                            True, "LASER", "POWERPLAY MERITS", 5000, 500000, 1, 100, False, True,
                            False, False, "L", "Aisling Duval", "ACQUIRE", "ANY", "ANY")
                        c.miningPlanRoutes(*self.plan_args)
                        return
                    self.finish()
            if self.stage == "plan":
                c.miningPlanRoutes(*self.plan_args)
                if (getattr(c, "_active_mining_plan", None) is None
                        and getattr(c, "_mining_plan_cache_key", None) == c._mining_plan_key(self.plan_args)):
                    self.plan_seconds = now - self.plan_started
                    rows = c._mining_rows_cache
                    if not hasattr(rows, "nearby") or not rows._region:
                        self.finish("Planner did not exercise the regional ring view")
                        return
                    self.regional_count = len(rows._region)
                    self.samples["afterRegionalPlan"] = memory()
                    self.finish()

        def finish(self, error=None):
            self.poller.stop()
            c = self.controller
            summaries = {}
            for name in ("startup", "mining"):
                gaps = sorted(row["gapMs"] for row in beats if row["phase"] == name)
                if gaps:
                    summaries[name] = {"maxGapMs": max(gaps),
                        "p95GapMs": gaps[int((len(gaps) - 1) * .95)],
                        "gapsOver100Ms": sum(gap > 100 for gap in gaps)}
            result = {"label": args.label, "version": APP_VERSION,
                "mode": "native/source/offscreen/software/offline/empty-market-store",
                "source": source, "inventory": json.loads((destination / "inventory.json").read_text()),
                "firstUiSeconds": self.first_ui, "operationsReadySeconds": self.operations_ready,
                "idleRings": getattr(self, "idle_rings", None),
                "idlePositions": getattr(self, "idle_positions", None),
                "miningOpenedToLoadedSeconds": round(self.loaded_at - self.opened_at, 4) if self.loaded_at else None,
                "finalRings": len(c._mining_catalog.get("candidates", [])),
                "finalPositions": len(getattr(c, "_mining_catalog_positions", {})),
                "powerplayRows": len(c._mining_powerplay_catalog.get("systems", [])),
                "powerplayObservations": len(c._mining_powerplay_observations),
                "memory": self.samples, "heartbeat": summaries, "loadRequests": load_requests, "error": error,
                "elapsedSeconds": round(time.perf_counter() - started, 4)}
            if args.exercise_mining:
                result.update(planSeconds=getattr(self,"plan_seconds",None),
                              regionalRows=getattr(self,"regional_count",None),
                              miningRadius=args.mining_radius,localDelta=args.local_delta)
            (destination / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result, indent=2), flush=True)
            self.app.exit(1 if error else 0)
    app_main.SmokeTestRunner = Runner
    return app_main.run()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare", type=Path)
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--exercise-mining", action="store_true")
    parser.add_argument("--local-delta", action="store_true", help="Add one synthetic local ring only to isolated in-memory state")
    parser.add_argument("--mining-radius", type=int, choices=(250,500), default=250)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.output == ROOT / ".test-tmp" or not args.output.is_relative_to(ROOT / ".test-tmp"):
        parser.error("Output must be a distinct directory inside repository .test-tmp")
    if args.prepare:
        prepare(args.output, args.prepare.resolve())
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
