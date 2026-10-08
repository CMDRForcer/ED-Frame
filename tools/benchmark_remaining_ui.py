"""Synthetic CMDR workload and actual Qt heartbeat during blocked archive I/O.

No user profiles, files, server requests or installed app settings are changed.
"""
import json
from pathlib import Path
import sys
import threading
import time
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QCoreApplication, QTimer
from ed_companion.phase14.commander_projection import prepare_commander_projection
from ed_companion.phase14.controller import CockpitController
from ed_companion.phase14.dashboard_views import build_commander_cards, build_finance_history, filter_finance_history


def main():
    events = [{"event": "Scan", "timestamp": "2026-10-08T08:00:00Z"}] * 120000
    events = [*events, {"event": "LoadGame", "timestamp": "2026-10-08T08:00:00Z", "Credits": 1000}]
    overview = {"credits": {"known": True, "value": 2000, "timestamp": "2026-10-08T09:00:00Z"}}
    started = time.perf_counter()
    prepared = prepare_commander_projection(overview, events, [])
    preparation_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    for period in ("all", "session", "1h", "6h", "24h", "7d", "30d"):
        build_commander_cards(overview, events)
        filter_finance_history(build_finance_history(events, current_credits=overview["credits"]), period, events)
    previous_ms = (time.perf_counter() - started) * 1000
    c = CockpitController.__new__(CockpitController)
    c._network_threads_lock = threading.Lock()
    c.profile_context = Mock(key="benchmark")
    c._profile_generation = 1
    c._state_revision = 1
    c._commander_credit_snapshots = []
    c._journal_state_ready = True
    c._state = {"commanderOverview": overview}
    c._commander_projection = {"key": c._commander_projection_key(), **prepared}
    started = time.perf_counter()
    for _ in range(1000):
        c._commander_cards()
        for period in prepared["histories"]:
            c._commander_finance_period = period
            c._commander_finance_history()
            c._commander_finance_summary()
    cached_ms = (time.perf_counter() - started) * 1000 / 1000

    app = QCoreApplication.instance() or QCoreApplication([])
    release = threading.Event()
    entered = threading.Event()
    workers = []
    c._hge_sightings = []
    c.hge_cache_file = Path("unused-hge.json")
    c._pending_bgs_snapshots = []
    c._pending_hge_observations = []
    c._history_archive = Mock()
    c.hgeObservationBatchFinished = Mock()
    c.journalLocationReady = Mock()
    c.journalHealthReady = Mock()
    c.commanderProjectionReady = Mock()
    c._journal_auto = True
    c._renderer_active = "software"
    c.timer = Mock()
    c.timer.isActive.return_value = True
    c._commander_projection = {}
    def wait(*args):
        entered.set()
        if not release.wait(3):
            raise RuntimeError("Test did not release worker")
        return []
    c._history_archive.archive.side_effect = wait
    def start(target, _name):
        worker = threading.Thread(target=target)
        workers.append(worker)
        worker.start()
        return True
    c._start_network_worker = start
    ticks = []
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: ticks.append(time.perf_counter()))
    heartbeat.start(10)
    try:
        with patch("ed_companion.phase14.controller_commander.profiled_journal_events", side_effect=wait), patch(
                "ed_companion.phase14.controller_journal_health.resolve_profile_context",
                side_effect=lambda: wait() or c.profile_context), patch(
                "ed_companion.phase14.controller_journal_health.journal_change_signature", return_value=("fixture", ())), patch(
                "ed_companion.phase14.controller_journal_health.journal_dir", return_value=Path("unused-journal")), patch(
                "ed_companion.phase14.controller_journal_health.latest_profile_location", return_value={}), patch(
                "ed_companion.phase14.controller_journal_health.journal_paths_for_profile", return_value=[]):
            c._read_journal_health = lambda *_args: wait() or {"status": "READY", "parserOk": True}
            started = time.perf_counter()
            c._dispatch_hge_observation_batch([], [{"system": "Benchmark"}])
            c._commander_cards()
            c._live_profile_location()
            c._journal_health()
            dispatch_ms = (time.perf_counter() - started) * 1000
            assert entered.wait(1)
            deadline = time.perf_counter() + .25
            while time.perf_counter() < deadline:
                app.processEvents()
                time.sleep(.001)
            tick_count = len(ticks)
            assert tick_count >= 10, f"Qt heartbeat blocked: {tick_count} ticks"
            gaps = [(later - earlier) * 1000 for earlier, later in zip(ticks, ticks[1:])]
            release.set()
            for worker in workers:
                worker.join(3)
                assert not worker.is_alive()
    finally:
        release.set()
        heartbeat.stop()
        for worker in workers:
            worker.join(3)
    print(json.dumps({"synthetic_journal_events": len(events),
        "previous_seven_period_rebuilds_ms": round(previous_ms, 3),
        "new_all_period_preparation_worker_ms": round(preparation_ms, 3),
        "cached_all_period_getters_ms": round(cached_ms, 3),
        "four_worker_dispatch_ms": round(dispatch_ms, 3),
        "qt_ticks_during_250ms_blocked_io": tick_count,
        "qt_max_heartbeat_gap_ms": round(max(gaps, default=0), 3)}, indent=2))


if __name__ == "__main__":
    main()
