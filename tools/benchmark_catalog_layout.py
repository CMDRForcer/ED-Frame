"""Read-only public-catalog load/merge comparison in separate processes.

Run once per mode against the same frozen public JSON copy. The plain mode
disables only dictionary-layout sharing, not string sharing or domain logic.
No HTTP, real profile mutation, journal or personal data is required.
"""
from __future__ import annotations

import argparse
import ctypes
import gc
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ed_companion.navigation.catalog_json import (
    CatalogDictFactory, iter_catalog_json, load_catalog_json,
)
from ed_companion.navigation.mining_batch import prepare_mining_batch
from ed_companion.navigation.mining_finder import mining_candidate_positions
from ed_companion.navigation import mining_finder


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


def digest(value):
    hasher = hashlib.sha256()
    for chunk in iter_catalog_json(value):
        hasher.update(chunk.encode("utf-8"))
    return hasher.hexdigest()


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 10, 8, 12, tzinfo=timezone.utc)
        return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)


def run(args):
    started = time.perf_counter()
    catalog = load_catalog_json(args.catalog, {}, snapshot_arrays=args.mode == "snapshot")
    rows = catalog["candidates"]
    result = {"mode": args.mode, "python": sys.version,
              "loadSeconds": round(time.perf_counter() - started, 4),
              "rows": len(rows), "memoryAfterLoad": memory(),
              "rowDictMiB": round(sum(sys.getsizeof(row) for row in rows) / 2**20, 3)}
    result["loadedDigest"] = digest(catalog)
    collections = []
    for _ in range(4):
        stamp = time.perf_counter()
        gc.collect(2)
        collections.append(round(time.perf_counter() - stamp, 6))
    result["fullGcSeconds"] = collections
    result["gcTrackedRows"] = sum(gc.is_tracked(row) for row in rows)
    started = time.perf_counter()
    positions = mining_candidate_positions(rows)
    result["indexSeconds"] = round(time.perf_counter() - started, 4)
    # Re-fetch a deterministic, spaced subset, keeping the exact source facts.
    step = max(1, len(rows) // args.batch)
    incoming = rows[::step][:args.batch]
    original_digest = digest(incoming)
    started = time.perf_counter()
    with patch.object(mining_finder, "datetime", FixedClock):
        merged = prepare_mining_batch(
            rows, incoming, positions=positions,
            archive_path=args.output.with_suffix(".sqlite3"),
            transient_fields={"ageSeconds", "confirmationStatus",
                              "freshnessLimitSeconds", "recheckRecommended", "stale"},
            snapshot_arrays=args.mode == "snapshot",
        )
    result.update(mergeSeconds=round(time.perf_counter() - started, 4),
                  mergedRows=len(merged["candidates"]), batchRows=len(incoming),
                  archiveError=merged["archiveError"], memoryAfterMerge=memory(),
                  mergedRowDictMiB=round(sum(sys.getsizeof(row) for row in merged["candidates"]) / 2**20, 3))
    result["mergedDigest"] = digest(merged["candidates"])
    result["incomingUnchanged"] = digest(incoming) == original_digest
    result["sourceBytes"] = args.catalog.stat().st_size
    hasher = hashlib.sha256()
    with args.catalog.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    result["sourceSha256"] = hasher.hexdigest()
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("plain", "shared", "snapshot"), required=True)
    parser.add_argument("--batch", type=int, default=24455)
    args = parser.parse_args()
    if args.batch <= 0:
        parser.error("--batch must be positive")
    if args.output.exists() or args.output.with_suffix(".sqlite3").exists():
        parser.error("Use fresh output and archive paths")
    if args.mode == "plain":
        with patch.object(CatalogDictFactory, "new_dict", lambda _self, _keys: {}):
            run(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
