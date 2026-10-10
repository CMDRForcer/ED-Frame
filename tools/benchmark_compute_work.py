"""Compare the same synthetic CPU jobs on threads and the adaptive spawn pool."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QCoreApplication, QTimer
from ed_companion.compute_work import ComputeWork
from ed_companion.cpu_tasks import journal_projection, commander_projection, powerplay_merge
from ed_companion.work_resources import WorkResources


def digest(result):
    return hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("threads", "processes", "small-pc"), required=True)
    args = parser.parse_args()
    events = [{"event": "LoadGame", "Credits": 1000, "timestamp": "2026-10-10T00:00:00Z"},
              {"event": "Location", "StarSystem": "Fixture", "StarPos": [0, 0, 0], "SystemAddress": 1}]
    events.extend({"event": "Scan", "timestamp": "2026-10-10T00:01:00Z", "StarSystem": "Fixture",
                   "SystemAddress": 1, "BodyID": index % 2000, "BodyName": f"Fixture {index % 2000}",
                   "PlanetClass": "Rocky body", "MassEM": 1, "DistanceFromArrivalLS": 1000}
                  for index in range(60000))
    overview = {"credits": {"known": True, "value": 1000, "timestamp": "2026-10-10T00:00:00Z"}}
    observations = [{"system": f"System {index}", "power": "Aisling Duval", "systemAddress": index + 1,
                     "observedAt": "2026-10-09T00:00:00Z"} for index in range(100000)]
    additions = [{**observations[index], "observedAt": "2026-10-10T00:00:00Z"} for index in range(100)]
    jobs = [("journal-projection", journal_projection, (events,), 3),
            ("powerplay-merge", powerplay_merge, (observations, additions, 110000), 0),
            ("commander", commander_projection, (overview, events, []), 1)]
    app = QCoreApplication([])
    heartbeat = QTimer()
    heartbeat.setInterval(10)
    beats = []
    heartbeat.timeout.connect(lambda: beats.append(time.perf_counter()))
    machine = (WorkResources(cores=2, reader=lambda: (4096, 2500), cpu_reader=lambda: None)
               if args.mode == "small-pc" else WorkResources())
    service = ComputeWork(machine)
    phases = []
    try:
        for phase in ("cold", "warm"):
            beats.clear()
            started = time.perf_counter()
            results, values, errors = {}, {}, []
            def run(name, function, payload, priority):
                stamp, cpu = time.perf_counter(), time.thread_time()
                try:
                    # Commander is measured in its existing fast background thread.
                    result = (function(*payload) if args.mode == "threads" or name == "commander" else service.compute(name,
                        function, *payload, memory_mb=512, priority=priority, fallback=lambda: function(*payload)))
                    results[name] = {"seconds": round(time.perf_counter() - stamp, 3),
                        "callerCpuSeconds": round(time.thread_time() - cpu, 3)}
                    values[name] = result
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
            threads = [threading.Thread(target=run, args=job) for job in jobs]
            heartbeat.start()
            beats.append(time.perf_counter())
            for thread in threads:
                thread.start()
            deadline = time.perf_counter() + 120
            while any(thread.is_alive() for thread in threads) and time.perf_counter() < deadline:
                app.processEvents()
                time.sleep(.001)
            app.processEvents()
            beats.append(time.perf_counter())
            heartbeat.stop()
            for thread in threads:
                thread.join(1)
                if thread.is_alive():
                    errors.append("job deadline exceeded")
            gaps = [(b - a) * 1000 for a, b in zip(beats, beats[1:])]
            elapsed = time.perf_counter() - started
            for name, value in values.items():
                results[name]["sha256"] = digest(value)
            phases.append({"phase": phase, "seconds": round(elapsed, 3),
                "maxUiGapMs": round(max(gaps, default=0), 3), "ticks": len(beats),
                "jobs": results, "errors": errors, "service": service.snapshot()})
    finally:
        service.close()
        app.quit()
    report = {"mode": args.mode, "events": len(events), "observations": len(observations), "phases": phases}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"mode": args.mode, "phases": [{k: p[k] for k in ("phase", "seconds", "maxUiGapMs", "errors")} for p in phases]}))
    return 1 if any(phase["errors"] for phase in phases) else 0


if __name__ == "__main__":
    raise SystemExit(main())
