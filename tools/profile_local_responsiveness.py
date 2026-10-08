"""Read-only local footprint audit; never construct a writable app store."""
import argparse
from collections import Counter
import ctypes
import json
from pathlib import Path
import sqlite3
import sys
import time
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ed_companion.navigation.catalog_json import load_catalog_json


def rss_mib():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in (
                "peak", "working", "quota_peak_paged", "quota_paged",
                "quota_peak_nonpaged", "quota_nonpaged", "pagefile", "peak_pagefile",
            )
        ]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.c_void_p(-1), ctypes.byref(counters), counters.cb
    )
    return round(counters.working / 1024**2, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--views", action="store_true")
    parser.add_argument("--lean", action="store_true")
    args = parser.parse_args()
    for name in (() if args.json_only else ("mining_market_catalog.sqlite3", "data_history.sqlite3")):
        path = args.profile / name
        started = time.perf_counter()
        # Normal WAL snapshot reads, never ignore uncheckpointed transactions.
        uri = path.as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as db:
            db.execute("PRAGMA query_only=ON")
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            print(name, {
                "MiB": round(path.stat().st_size / 1024**2, 1),
                "freeMiB": round(db.execute("PRAGMA freelist_count").fetchone()[0] * page_size / 1024**2, 1),
            }, flush=True)
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            for (table,) in tables:
                safe = table.replace('"', '""')
                count = db.execute(f'SELECT COUNT(*) FROM "{safe}"').fetchone()[0]
                print("table", table, "rows", count, flush=True)
            if name == "data_history.sqlite3":
                try:
                    print("history categories", db.execute(
                        "SELECT category,COUNT(*),ROUND(SUM(LENGTH(payload))/1048576.0,1) FROM history GROUP BY category"
                    ).fetchall(), flush=True)
                except sqlite3.DatabaseError as exc:
                    print("history scan error", str(exc), flush=True)
        print("sqlite elapsed", round(time.perf_counter() - started, 3), flush=True)
    if args.json or args.json_only:
        for name in ("mining_finder_catalog.json", "mining_powerplay_catalog.json"):
            started = time.perf_counter()
            before = rss_mib()
            stop = threading.Event()
            pauses = []
            def heartbeat():
                previous = time.perf_counter()
                while not stop.wait(0.005):
                    tick = time.perf_counter()
                    pauses.append(tick - previous)
                    previous = tick
            worker = threading.Thread(target=heartbeat)
            worker.start()
            path = args.profile / name
            value = load_catalog_json(path, {}) if args.stream else json.loads(path.read_bytes())
            stop.set()
            worker.join()
            rows = value.get("candidates", value.get("systems", []))
            print(name, {"rows": len(rows), "loadSeconds": round(time.perf_counter()-started, 3),
                         "rssMiB": rss_mib(), "rssIncreaseMiB": round(rss_mib()-before,1),
                         "maxHeartbeatGapSeconds": round(max(pauses, default=0), 3),
                         "keys": Counter(key for row in rows for key in row).most_common()}, flush=True)
            lists = Counter()
            for row in rows:
                for key, field in row.items():
                    if isinstance(field, list):
                        lists[key] += len(field)
            print("nested list totals", lists, flush=True)
            print("largest record bytes", max(len(json.dumps(row)) for row in rows), flush=True)
            if args.views and name == "mining_finder_catalog.json":
                from ed_companion.phase14.controller import CockpitController
                c = CockpitController.__new__(CockpitController)
                before = rss_mib()
                started = time.perf_counter()
                projected = c._build_mining_rows(
                    {"system": "", "currentPosition": [0, 0, 0]}, value,
                    decorate=not args.lean,
                )
                print("projected view", {"lean": args.lean, "rows": len(projected),
                    "seconds": round(time.perf_counter() - started, 3),
                    "rssIncreaseMiB": round(rss_mib() - before, 1), "rssMiB": rss_mib()}, flush=True)
                del projected, c
            del value, rows


if __name__ == "__main__":
    main()
