"""Opt-in, isolated QML mining baseline with GET-only public networking.

Never launch against a real profile. --prepare copies only the named public
catalogs and a read-only SQLite snapshot into a new .test-tmp directory.
The source tree, not the installed Windows executable, is measured. Offscreen
software rendering measures event-loop/QML work, not D3D/input-to-paint latency.
"""
from __future__ import annotations

import argparse
from collections import Counter
import ctypes
import gc
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FID = "F0000000"
PROFILE = "profile-" + hashlib.sha256(FID.encode()).hexdigest()[:16]
PUBLIC_FILES = (
    "mining_finder_catalog.json", "mining_powerplay_catalog.json",
    "mining_powerplay_observations.json", "mining_market_cache.json",
    "mining_market_catalog.backup.sqlite3.gz", "hge_live_sightings.json",
    "material_trader_catalog_user.json", "tech_broker_catalog_user.json",
)


def memory():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in (
                "peak", "working", "quota_peak_paged", "quota_paged",
                "quota_peak_nonpaged", "quota_nonpaged", "pagefile", "peak_pagefile",
            )
        ]
    value = Counters()
    value.cb = ctypes.sizeof(value)
    if not ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.c_void_p(-1), ctypes.byref(value), value.cb,
    ):
        raise ctypes.WinError()
    return {"rssMiB": round(value.working / 2**20, 1),
            "peakRssMiB": round(value.peak / 2**20, 1),
            "privateCommitMiB": round(value.pagefile / 2**20, 1)}


def prepare(destination, source):
    if not (source / "mining_market_catalog.sqlite3").is_file():
        raise RuntimeError("Source public market database is missing")
    if destination.exists():
        raise RuntimeError("Preparation requires a new isolated directory")
    profile = destination / "local" / "ED-Frame" / PROFILE
    profile.mkdir(parents=True)
    inventory = []
    for name in PUBLIC_FILES:
        path = source / name
        if path.is_file():
            stat = path.stat()
            inventory.append({"file": name, "bytes": stat.st_size,
                              "mtimeNs": stat.st_mtime_ns})
            shutil.copy2(path, profile / name)
    name = "mining_market_catalog.sqlite3"
    path = source / name
    stat = path.stat()
    inventory.append({"file": name, "bytes": stat.st_size, "mtimeNs": stat.st_mtime_ns})
    # A WAL-consistent read snapshot, not an immutable/raw file copy.
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as src:
        src.execute("PRAGMA query_only=ON")
        with sqlite3.connect(profile / name) as dst:
            src.backup(dst)
    (destination / "source-inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    config = {"onboarding_complete": True, "background_mode": False,
              "journal_auto": False, "last_page": 12, "renderer_mode": "software",
              "edframe_catalog_enabled": True, "edframe_yield_sharing_enabled": True,
              "edframe_signal_sharing_enabled": True,
              "edframe_station_price_sharing_enabled": True,
              "interface_language": "en"}
    (profile / "phase14_graphics.json").write_text(json.dumps(config), encoding="utf-8")
    (profile / "eddn_config.json").write_text(json.dumps({
        "consent": False, "upload_enabled": False, "listener_enabled": False,
        "hge_classifier_version": 2,
    }), encoding="utf-8")
    journal = destination / "journal"
    journal.mkdir()
    events = [
        {"event": "Fileheader", "timestamp": "2026-10-08T00:00:00Z", "part": 1},
        {"event": "LoadGame", "timestamp": "2026-10-08T00:00:01Z", "FID": FID,
         "Commander": "Performance Fixture", "Ship": "Adder", "ShipID": 1,
         "Credits": 1000000, "Horizons": True, "Odyssey": True},
        {"event": "Powerplay", "timestamp": "2026-10-08T00:00:02Z",
         "Power": "Aisling Duval", "Rank": 1, "Merits": 0},
        {"event": "Location", "timestamp": "2026-10-08T00:00:03Z",
         "StarSystem": "Shanteneri", "StarPos": [110.9375, -113.0625, 41.21875],
         "Docked": False},
    ]
    (journal / "Journal.2026-10-08T000000.01.log").write_text(
        "\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8",
    )
    print("PREPARED", json.dumps({"catalogFiles": len(inventory),
                                 "sourceBytes": sum(row["bytes"] for row in inventory)}), flush=True)


def run(args):
    destination = args.output
    if not (destination / "source-inventory.json").is_file():
        raise RuntimeError("Run --prepare first; no real profile may be launched")
    for path in (destination / "local" / "ED-Frame" / PROFILE, destination / "journal"):
        if not path.resolve().is_relative_to(destination):
            raise RuntimeError("Isolated profile/journal may not resolve outside the test directory")
    if args.journal_auto:
        config_path = destination / "local" / "ED-Frame" / PROFILE / "phase14_graphics.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["journal_auto"] = True
        config_path.write_text(json.dumps(config), encoding="utf-8")
    os.environ.update({
        "LOCALAPPDATA": str(destination / "local"),
        "ED_FRAME_JOURNAL_DIR": str(destination / "journal"),
        "ED_FRAME_PROFILE_FID": FID,
        "ED_FRAME_SINGLE_INSTANCE_NAME": "ED-Frame-baseline-" + destination.name,
        "PHASE14_SMOKE_TEST": "1", "PHASE14_SMOKE_ASYNC_PAGES": "1",
        "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
        "PHASE14_PREVIEW_WIDTH": "1600", "PHASE14_PREVIEW_HEIGHT": "1000",
    })
    import requests
    import faulthandler
    faulthandler.dump_traceback_later(90, repeat=True)
    import phase14_main as app_main
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtQml import QQmlEngine, QQmlExpression
    from PySide6 import __version__ as pyside_version
    from ed_companion import APP_VERSION
    from ed_companion.phase14.controller import CockpitController
    from ed_companion.phase14 import controller_navigation as navigation
    from ed_companion.navigation import mining_planner

    source = {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "changes": subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True),
              "hashes": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
                  "ed_companion/phase14/controller_navigation.py", "ed_companion/phase14/controller.py",
                  "ed_companion/navigation/mining_refresh.py", "ed_companion/navigation/mining_region_cache.py",
                  "ed_companion/navigation/mining_planner.py",
                  "ed_companion/navigation/catalog_json.py", "ed_companion/navigation/mining_batch.py",
                  "ed_companion/navigation/mining_finder.py",
                  "ed_companion/phase14/controller_journal_health.py",
                  "ed_companion/phase14/controller_surface_nav.py",
                  "ed_companion/phase14/controller_commander.py",
                  "ed_companion/phase14/controller_eddn.py",
                  "ed_companion/worker_budget.py", "Main.qml",
                  "qml/pages/MiningFinderPage.qml")}}
    started = time.perf_counter()
    trace, beats, tabs, searches, planner_timings, index_timings = [], [], [], [], [], []
    verification_events, busy_events = [], []
    method_timings, gc_timings = [], []
    stall_stacks = []
    last_heartbeat = [None]
    watchdog_stop = threading.Event()
    phase = ["startup"]
    timer_refs = []
    allowed = {"vps-20b25c36.vps.ovh.net", "api.ardent-insight.com",
               "api.eddata.dev", "www.edsm.net", "spansh.co.uk"}
    request = requests.Session.request

    def guarded_request(session, method, url, *pos, **kw):
        host = urlparse(url).hostname
        if method.upper() != "GET" or host not in allowed:
            raise RuntimeError("Baseline blocks uploads and unrelated hosts")
        stamp = time.perf_counter()
        entry = {"at": round(stamp - started, 3), "phase": phase[0],
                 "host": host, "path": urlparse(url).path,
                 "params": kw.get("params"), "thread": threading.current_thread().name}
        try:
            response = request(session, method, url, *pos, **kw)
            entry["status"] = response.status_code
            entry["bytes"] = len(response.content)
            return response
        except Exception as exc:
            entry["error"] = type(exc).__name__
            raise
        finally:
            entry["seconds"] = round(time.perf_counter() - stamp, 3)
            trace.append(entry)
    requests.Session.request = guarded_request

    # Keep search/merge/verification/planner unchanged. Suppress the listed
    # scheduled jobs and sharing paths. Normal startup State Finds sync remains
    # enabled and is included separately in the HTTP trace and baseline report.
    for name in ("_maybe_auto_refresh_spansh", "_maybe_auto_refresh_mining_markets",
                 "refreshEdFrameCatalogStatus", "_maybe_share_state_signals",
                 "_maybe_share_mining_yields", "_ensure_eddn_listener"):
        setattr(CockpitController, name, lambda self, *a, **k: None)
    app_main.register_windows_url_protocol = lambda **kwargs: False
    original_controller = app_main.CockpitController

    def controller_factory():
        previous = [time.perf_counter()]
        heartbeat = QTimer()
        heartbeat.setTimerType(Qt.TimerType.PreciseTimer)
        def tick():
            now = time.perf_counter()
            beats.append({"at": round(now - started, 4), "phase": phase[0],
                          "gapMs": round((now - previous[0]) * 1000, 3), **memory()})
            previous[0] = now
            last_heartbeat[0] = now
        heartbeat.timeout.connect(tick)
        heartbeat.start(10)
        timer_refs.append(heartbeat)
        return original_controller()
    app_main.CockpitController = controller_factory

    original_refresh = navigation.fetch_mining_refresh
    domains = []
    def timed_refresh(*a, **k):
        stamp = time.perf_counter()
        result = original_refresh(*a, **k)
        domains.append({"phase": phase[0], "seconds": round(time.perf_counter() - stamp, 3),
                        "fetchTimings": result.get("fetchTimings"),
                        "siteRows": len(result.get("serverCandidates", [])),
                        "powerplayRows": len(result.get("serverPowerplay", [])),
                        "marketRows": len(result.get("markets", [])),
                        "siteCoverage": result.get("siteCoverage"),
                        "powerplayCoverage": result.get("powerplayCoverage"),
                        "success": result.get("success"),
                        "siteError": result.get("siteError"),
                        "powerplayError": result.get("powerplayError"),
                        "error": result.get("error")})
        return result
    navigation.fetch_mining_refresh = timed_refresh
    original_plan = navigation.NavigationMixin._compute_mining_plan_routes
    def timed_plan(self, *a, **k):
        stamp = time.perf_counter()
        try:
            return original_plan(self, *a, **k)
        finally:
            planner_timings.append({"phase": phase[0],
                                   "seconds": round(time.perf_counter() - stamp, 4)})
    navigation.NavigationMixin._compute_mining_plan_routes = timed_plan
    original_index = mining_planner._powerplay_index
    def timed_index(*a, **k):
        stamp = time.perf_counter()
        try:
            return original_index(*a, **k)
        finally:
            index_timings.append({"phase": phase[0],
                                 "seconds": round(time.perf_counter() - stamp, 4)})
    mining_planner._powerplay_index = timed_index

    if args.profile_ui:
        # Diagnostic wrappers only: keep production scheduling/Qt connections
        # intact. Record long Python calls and generation-2 stop-the-world GC.
        def timed_method(name, original):
            def measured(self, *a, **k):
                stamp = time.perf_counter()
                current_phase = phase[0]
                try:
                    return original(self, *a, **k)
                finally:
                    duration = time.perf_counter() - stamp
                    if duration >= .005 and len(method_timings) < 5000:
                        method_timings.append({"method": name, "phase": current_phase,
                            "at": round(stamp - started, 4), "seconds": round(duration, 6),
                            "thread": threading.current_thread().name})
            return measured

        for name in ("_finish_mining_market_sync", "_publish_mining_powerplay",
                     "_dispatch_mining_observation_batch", "_finish_mining_observation_batch",
                     "_add_mining_system_names", "_finish_mining_rows_build",
                     "_queue_mining_rows_build", "_build_mining_rows",
                     "_finish_mining_plan", "_finish_mining_verification",
                     "_save_mining_json", "_mining_cache_summary", "_mining_ui_revision"):
            setattr(CockpitController, name, timed_method(name, getattr(CockpitController, name)))

        gc_active = {}
        def gc_trace(event, info):
            if info["generation"] != 2:
                return
            thread_id = threading.get_ident()
            if event == "start":
                frames = []
                frame = sys._getframe(1)
                while frame is not None and len(frames) < 12:
                    frames.append({"file": Path(frame.f_code.co_filename).name,
                                   "function": frame.f_code.co_name, "line": frame.f_lineno})
                    frame = frame.f_back
                gc_active[thread_id] = (time.perf_counter(), phase[0], frames)
            elif event == "stop" and thread_id in gc_active:
                stamp, current_phase, frames = gc_active.pop(thread_id)
                gc_timings.append({"phase": current_phase, "at": round(stamp - started, 4),
                    "seconds": round(time.perf_counter() - stamp, 6), "frames": frames,
                    "thread": threading.current_thread().name,
                    "collected": info["collected"], "uncollectable": info["uncollectable"]})
        gc.callbacks.append(gc_trace)
        def watch_stalls():
            while not watchdog_stop.wait(.05):
                stamp = time.perf_counter()
                previous = last_heartbeat[0]
                if previous is None or stamp - previous < .15 or len(stall_stacks) >= 200:
                    continue
                threads = {thread.ident: thread.name for thread in threading.enumerate()}
                stacks = {}
                for ident, frame in sys._current_frames().items():
                    if ident == threading.get_ident():
                        continue
                    frames = []
                    while frame is not None and len(frames) < 14:
                        frames.append({"file": Path(frame.f_code.co_filename).name,
                                       "function": frame.f_code.co_name, "line": frame.f_lineno})
                        frame = frame.f_back
                    stacks[threads.get(ident, str(ident))] = frames
                stall_stacks.append({"at": round(stamp - started, 4), "phase": phase[0],
                                     "gapMs": round((stamp - previous) * 1000, 3), "threads": stacks})
        threading.Thread(target=watch_stalls, name="ui-stall-watchdog", daemon=True).start()

    class Runner(app_main.SmokeTestRunner):
        def start(self):
            self.stage = "ready"
            self.stage_at = time.perf_counter()
            self.poller = QTimer(self)
            self.poller.timeout.connect(self.check)
            self.poller.start(25)
            self.page = None
            self.active = None
            self.search_number = 0
            self.tab_index = 0
            self.tab_pending = None
            self.last_status = time.perf_counter()
            self.verification_signals = 0
            self.last_busy = None
            self.idle_since = None
            self.controller.miningVerificationChanged.connect(self.verification_signal)
            self.tab_plan = [(0, "qa-page-operations"), (2, "qa-page-materials"),
                             (3, "qa-page-engineering"), (10, "qa-page-cmdr"),
                             (12, "qa-page-mining-finder")]

        def verification_signal(self):
            self.verification_signals += 1
            c = self.controller
            request = getattr(c, "_active_mining_verification_request", None) or {}
            event = {"at": round(time.perf_counter() - started, 3), "phase": phase[0],
                     "busy": bool(c.miningVerificationBusy), "completed": int(c.miningVerificationCompleted),
                     "total": int(c.miningVerificationTotal), "status": str(c.miningVerificationStatus),
                     "failures": int(getattr(c, "_mining_verification_failures", 0)),
                     "requestId": request.get("id"), "ringTargets": len(request.get("targets", [])),
                     "powerplayTargets": len(request.get("powerplayLookupTargets", [])),
                     "marketTargets": len(request.get("marketTargets", []))}
            verification_events.append(event)
            if self.active is not None:
                event["searchSeconds"] = round(time.perf_counter() - self.active["began"], 3)
                self.active["lastActivity"] = time.perf_counter()
                if event["busy"] and not any(
                    snapshot["requestId"] == event["requestId"]
                    for snapshot in self.active["verificationSnapshots"]
                ):
                    self.active["verificationSnapshots"].append({**event, "routes": self.route_snapshot()})
                else:
                    self.active["verificationCompletedSeconds"] = event["searchSeconds"]
            print("VERIFICATION", json.dumps(event), flush=True)

        def evaluate(self, expression):
            value = QQmlExpression(QQmlEngine.contextForObject(self.page),
                                  self.page, expression)
            result, _undefined = value.evaluate()
            if value.hasError():
                raise RuntimeError(value.error().toString())
            return result

        def route_snapshot(self):
            return json.loads(self.evaluate("JSON.stringify(resultRows.map(function(r) { return {"
                "key: routeKey(r), system: r.system, ring: r.ring, sellSystem: r.sellSystem,"
                "verificationStatus: r.verificationStatus, powerplayStatus: r.powerplayStatus,"
                "marketStatus: r.marketStatus, marketMatchesFilters: r.marketMatchesFilters,"
                "meritKnown: r.meritKnown, meritStatus: r.meritStatus, sellPrice: r.sellPrice"
                "}; }))"))

        def row_change(self, reused=False):
            if self.active is None:
                return
            routes = self.route_snapshot()
            keys = [row["key"] for row in routes]
            summary = {"count": len(routes), "top": keys[0] if keys else "",
                       "statuses": dict(Counter(row.get("verificationStatus", "") for row in routes)),
                       "powerplayStatuses": dict(Counter(row.get("powerplayStatus", "") for row in routes)),
                       "orderHash": hashlib.sha256(json.dumps(keys).encode()).hexdigest(),
                       "contentHash": hashlib.sha256(json.dumps(routes, sort_keys=True).encode()).hexdigest()}
            summary["atSeconds"] = round(time.perf_counter() - self.active["began"], 3)
            summary.update(memory())
            if reused:
                self.active["reusedAtStart"] = summary
            else:
                self.active["changes"].append(summary)
                self.active["lastChange"] = time.perf_counter()
                self.active["lastActivity"] = time.perf_counter()
            if summary["count"] and self.active.get("firstResultSeconds") is None:
                self.active["firstResultSeconds"] = summary["atSeconds"]
            print("REUSED" if reused else "ROWS", phase[0], json.dumps(summary), flush=True)

        def busy_snapshot(self):
            c = self.controller
            return {"sync": bool(c.miningMarketSyncBusy), "plan": bool(c.miningPlanBusy),
                    "verification": bool(c.miningVerificationBusy),
                    "merge": bool(getattr(c, "_active_mining_observation_batch", None)),
                    "projection": bool(getattr(c, "_mining_rows_build_in_flight", False)),
                    "pendingRings": bool(getattr(c, "_pending_mining_candidates", [])),
                    "pendingPowerplay": bool(getattr(c, "_pending_mining_powerplay_observations", [])),
                    "pendingVerification": bool(getattr(c, "_pending_mining_verification", None))}

        def begin_search(self):
            self.stage = "search"
            self.stage_at = time.perf_counter()
            phase[0] = "first-search" if self.search_number == 0 else "warm-search"
            self.active = {"name": phase[0], "began": self.stage_at,
                           "changes": [], "lastChange": self.stage_at,
                           "lastActivity": self.stage_at, "verificationSnapshots": [],
                           "memoryAtStart": memory(), "firstResultSeconds": None,
                           "verificationSignalsAtStart": self.verification_signals}
            # Keep the benchmark query explicit, independently of QML's
            # current-Journal binding and state notifications.
            self.evaluate("startSystem = 'Shanteneri'")
            self.evaluate("executeSearch()")
            # A warm unchanged result is deliberately reused, not re-emitted.
            if self.search_number:
                self.row_change(reused=True)
            print("SEARCH", phase[0], flush=True)

        def check(self):
            try:
                self.advance()
            except Exception as exc:
                self.finish(str(exc))

        def advance(self):
            now = time.perf_counter()
            c = self.controller
            busy = self.busy_snapshot()
            if busy != self.last_busy:
                busy_events.append({"at": round(now - started, 3), "phase": phase[0], **busy})
                self.last_busy = busy
                if self.active is not None:
                    self.active["lastActivity"] = now
            if now - self.last_status > 15:
                self.last_status = now
                print("STATUS", json.dumps({"elapsed": round(now - started, 3),
                    "stage": self.stage, "sync": bool(c.miningMarketSyncBusy),
                    "plan": bool(c.miningPlanBusy), "verification": bool(c.miningVerificationBusy),
                    "revision": int(self.page.property("searchRevision")) if self.page else None,
                    "verifiedRevision": int(self.page.property("verifiedSearchRevision")) if self.page else None,
                    "rows": int(self.evaluate("resultRows.length")) if self.page else None,
                    "marketStatus": c.miningMarketSyncStatus}), flush=True)
            if now - started > args.deadline:
                self.finish("Global benchmark deadline reached")
                return
            if self.stage == "ready":
                if not (getattr(c, "_journal_state_ready", False)
                        and getattr(c, "_mining_catalog_revision", 0) > 0
                        and getattr(c, "_mining_market_store", None) is not None):
                    return
                self.window.setProperty("currentPage", 12)
                self.page = self._find("qa-page-mining-finder")
                if self.page is None:
                    return
                self.page.setProperty("startSystem", "Shanteneri")
                self.page.setProperty("powerOverride", "Aisling Duval")
                self.page.setProperty("nearbyLy", args.radius)
                self.page.setProperty("resultLimit", args.results)
                self.page.setProperty("optimization", "POWERPLAY MERITS")
                self.page.resultRowsChanged.connect(self.row_change)
                self.ready_at = round(now - started, 3)
                self.dataset = {"rings": len(c._mining_catalog.get("candidates", [])),
                                "markets": c._mining_market_store.count(),
                                "powerplay": len(c._mining_powerplay_catalog.get("systems", [])),
                                "memoryAtReady": memory()}
                print("READY", self.ready_at, json.dumps(self.dataset), flush=True)
                if args.tabs_only:
                    self.begin_tabs(now)
                else:
                    self.begin_search()
                return
            if self.stage == "search":
                idle = not any(busy.values())
                revision = int(self.page.property("searchRevision"))
                attempted = int(self.page.property("verifiedSearchRevision")) == revision
                actual_call = self.verification_signals > self.active["verificationSignalsAtStart"]
                count = int(self.evaluate("resultRows.length"))
                if idle and attempted and actual_call and count and now - self.active["lastActivity"] > 3:
                    self.active.update({"settledSeconds": round(now - self.active["began"], 3),
                                        "rows": count, "verificationStatus": c.miningVerificationStatus,
                                        "verificationCompleted": c.miningVerificationCompleted,
                                        "verificationTotal": c.miningVerificationTotal,
                                        "verificationSignals": self.verification_signals - self.active["verificationSignalsAtStart"],
                                        "memoryAtEnd": memory(), "finalRoutes": self.route_snapshot()})
                    self.active["lastListChangeSeconds"] = round(self.active["lastChange"] - self.active["began"], 3)
                    self.active["lastActivitySeconds"] = round(self.active["lastActivity"] - self.active["began"], 3)
                    snapshots = self.active["verificationSnapshots"]
                    self.active["finalRoutesNotInLastVerificationSnapshot"] = (len(
                        {row["key"] for row in self.active["finalRoutes"]}
                        - {row["key"] for row in snapshots[-1]["routes"]}) if snapshots else None)
                    self.active.pop("began")
                    self.active.pop("lastChange")
                    self.active.pop("lastActivity")
                    searches.append(self.active)
                    self.active = None
                    print("SETTLED", json.dumps({
                        key: value for key, value in searches[-1].items()
                        if key not in ("changes", "finalRoutes", "verificationSnapshots", "reusedAtStart")
                    }), flush=True)
                    self.search_number += 1
                    if self.search_number < 2:
                        self.begin_search()
                    elif args.tabs:
                        self.begin_tabs(now)
                    else:
                        self.finish()
                return
            if self.stage == "tabs":
                if any(busy.values()):
                    self.idle_since = None
                elif self.idle_since is None:
                    self.idle_since = now
                if self.tab_pending is None:
                    if (self.tab_index >= len(self.tab_plan) and self.tab_index % len(self.tab_plan) == 0
                            and self.idle_since is not None and now - self.idle_since >= 3):
                        self.finish()
                        return
                    if now < self.next_tab_at:
                        return
                    page, name = self.tab_plan[self.tab_index % len(self.tab_plan)]
                    self.tab_pending = {"page": page, "object": name,
                                        "began": now, "busyAtRequest": bool(c.miningMarketSyncBusy),
                                        "activityAtRequest": busy,
                                        "at": round(now - started, 3)}
                    self.window.setProperty("currentPage", page)
                target = self._find(self.tab_pending["object"])
                if target is not None and target.property("visible"):
                    # Include synchronous setProperty/find work in this poll.
                    # Reusing `now` from before navigation would report zero
                    # whenever the Loader finishes within the same poll.
                    ready_at = time.perf_counter()
                    row = dict(self.tab_pending)
                    row["readyMs"] = round((ready_at - row.pop("began")) * 1000, 3)
                    row["activityAtReady"] = self.busy_snapshot()
                    tabs.append(row)
                    self.tab_index += 1
                    self.tab_pending = None
                    self.next_tab_at = ready_at + 0.75
                    print("TAB", json.dumps(row), flush=True)

        def begin_tabs(self, now):
            self.stage = "tabs"
            phase[0] = "tabs-during-sync"
            self.page = None  # Real asynchronous Loaders destroy the old page.
            self.controller._mining_region_cache = None
            self.next_tab_at = now
            self.idle_since = None
            self.controller.refreshMiningMarkets("Shanteneri", "Platinum", args.radius, 5000, 1, "LARGE")

        def finish(self, error=None):
            faulthandler.cancel_dump_traceback_later()
            watchdog_stop.set()
            if args.profile_ui:
                gc.callbacks.remove(gc_trace)
            self.poller.stop()
            summary = {}
            for name in dict.fromkeys(beat["phase"] for beat in beats):
                points = [beat for beat in beats if beat["phase"] == name]
                gaps = sorted(beat["gapMs"] for beat in points)
                summary[name] = {"samples": len(gaps), "maxGapMs": max(gaps),
                                 "p95GapMs": gaps[int((len(gaps) - 1) * .95)],
                                 "gapsOver100Ms": sum(gap > 100 for gap in gaps),
                                 "gapsOver500Ms": sum(gap > 500 for gap in gaps),
                                 "maxSampleRssMiB": max(p["rssMiB"] for p in points)}
            if self.flush_pending_qt_diagnostics:
                self.flush_pending_qt_diagnostics()
            report = {"version": APP_VERSION, "resultsRequested": args.results,
                      "label": args.label, "source": source,
                      "journalAuto": args.journal_auto,
                      "python": sys.version, "pyside": pyside_version,
                      "radiusLy": args.radius, "mode": "source/offscreen/software/GET-only",
                      "readySeconds": getattr(self, "ready_at", None),
                      "dataset": getattr(self, "dataset", None), "searches": searches,
                      "tabs": tabs, "heartbeat": summary, "domains": domains,
                      "plannerTimings": planner_timings, "powerplayIndexTimings": index_timings,
                      "verificationEvents": verification_events, "busyEvents": busy_events,
                      "methodTimings": method_timings, "gcTimings": gc_timings,
                      "stallStacks": stall_stacks,
                      "heartbeatGaps": [beat for beat in beats if beat["gapMs"] > 100],
                      "http": trace, "memoryAtFinish": memory(), "error": error,
                      "qmlMessages": self.qml_messages,
                      "elapsedSeconds": round(time.perf_counter() - started, 3)}
            (destination / "result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print("BASELINE_DONE", json.dumps({"error": error, "seconds": report["elapsedSeconds"],
                                              "memory": report["memoryAtFinish"]}), flush=True)
            self.app.exit(1 if error else 0)
    app_main.SmokeTestRunner = Runner
    return app_main.run()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prepare", type=Path, metavar="SOURCE_PUBLIC_PROFILE")
    parser.add_argument("--results", type=int, choices=(30, 100), default=30)
    parser.add_argument("--radius", type=int, default=250)
    parser.add_argument("--deadline", type=int, default=300)
    parser.add_argument("--tabs", action="store_true")
    parser.add_argument("--tabs-only", action="store_true")
    parser.add_argument("--journal-auto", action="store_true")
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--profile-ui", action="store_true")
    args = parser.parse_args()
    args.output = args.output.resolve()
    if not args.output.is_relative_to(ROOT / ".test-tmp") or args.output == ROOT / ".test-tmp":
        parser.error("--output must be a distinct new directory inside repository .test-tmp")
    if args.prepare:
        prepare(args.output, args.prepare.resolve())
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
