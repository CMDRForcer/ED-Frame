"""Offline, fixed-clock replay of public catalogs; never writes to inputs.

Use the same copied fixture for before/after runs. Output must be a new
.test-tmp directory. Measures CPU/domain work, not GUI/network latency.
"""
import argparse
import cProfile
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import pstats
import statistics
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ed_companion.history_archive import HistoryArchive
from ed_companion.navigation.catalog_json import load_catalog_json, catalog_view_value
from ed_companion.navigation.mining_batch import prepare_mining_batch
from ed_companion.navigation.mining_finder import mining_candidate_positions
from ed_companion.navigation.mining_planner import PowerplayIndexCache
from ed_companion.navigation.mining_powerplay import catalog_rows
from ed_companion.phase14.controller import CockpitController
from ed_companion.phase14.controller_navigation import NavigationMixin


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 10, 9, 12, tzinfo=timezone.utc)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


def digest(rows):
    result = hashlib.sha256()
    for row in rows:
        result.update(json.dumps(row, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":")).encode())
    return result.hexdigest()


def profiled(call):
    profiler = cProfile.Profile()
    result = profiler.runcall(call)
    output = io.StringIO()
    pstats.Stats(profiler, stream=output).sort_stats("cumulative").print_stats(30)
    return result, output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=3)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / ".test-tmp") or args.output.exists():
        raise RuntimeError("New .test-tmp output directory required")
    args.output.mkdir(parents=True)
    names = ("mining_finder_catalog.json", "mining_market_cache.json",
             "mining_powerplay_catalog.json", "mining_powerplay_observations.json")
    hashes = {}
    for name in names:
        with (args.fixture / name).open("rb") as source:
            hashes[name] = hashlib.file_digest(source, "sha256").hexdigest()
    sources = [load_catalog_json(args.fixture / name, {}, snapshot_arrays=True) for name in names]
    existing = sources[0]["candidates"]
    markets = sources[1].get("markets", [])
    incoming = [catalog_view_value(row) for row in existing[:24456]]
    positions = mining_candidate_positions(existing)
    data = {"inputs": hashes, "rings": len(existing), "markets": len(markets),
            "clock": Clock.now(timezone.utc).isoformat(), "merge": {}, "search": {}}
    with patch("ed_companion.navigation.mining_finder.datetime", Clock), \
            patch("ed_companion.navigation.mining_planner.datetime", Clock), \
            patch("ed_companion.phase14.controller_navigation.time.time", return_value=1791547200):
        times = []
        for trial in range(args.trials):
            archive = HistoryArchive(args.output / f"merge-{trial}.sqlite3")
            started = time.perf_counter()
            merged = prepare_mining_batch(existing, incoming, positions=positions,
                                         archive=archive, snapshot_arrays=True)
            times.append(time.perf_counter() - started)
        merge_hash = digest(merged["candidates"])
        counts = archive.counts()
        history_hashes = {category: digest(archive.records(category)) for category in counts}
        archive = HistoryArchive(args.output / "merge-profile.sqlite3")
        merged, profile = profiled(lambda: prepare_mining_batch(
            existing, incoming, positions=positions, archive=archive, snapshot_arrays=True))
        assert digest(merged["candidates"]) == merge_hash
        data["merge"] = {"seconds": times, "median": statistics.median(times),
                         "hash": merge_hash, "counts": counts,
                         "historyHashes": history_hashes, "profile": profile}
        print("MERGE", json.dumps({k: v for k, v in data["merge"].items() if k != "profile"}), flush=True)
        facade = NavigationMixin()
        facade._state = {"system": "Shanteneri", "currentPosition": [110.9375, -113.0625, 41.21875]}
        facade._network_threads_lock = True
        facade._mining_rows = lambda: existing
        facade._mining_rows_cache_key = ("fixed-public-fixture",)
        facade._valid_star_position = CockpitController._valid_star_position
        facade._mining_market_rows_for_query = lambda _query: markets
        facade._mining_powerplay_catalog = sources[2]
        facade._mining_powerplay_observations = sources[3]
        if isinstance(sources[3], dict):
            facade._mining_powerplay_observations = sources[3].get("observations", [])
        facade._mining_powerplay_index_cache = PowerplayIndexCache()
        facade._mining_powerplay_index_scope = "fixed-public-fixture"
        facade._mining_powerplay_index_cache.index_for(
            facade._mining_powerplay_index_scope, catalog_rows(sources[2]),
            facade._mining_powerplay_observations)
        # Opt in only if the implementation exposes this immutable-source cache.
        try:
            from ed_companion.navigation.mining_geometry import MiningGeometryCache
        except ImportError:
            pass
        else:
            facade._mining_geometry_cache = MiningGeometryCache()
        for label, commodity, mode, goal, radius in (
            ("reinforce", "Platinum", "POWERPLAY MERITS", "REINFORCE", 250),
            ("acquire", "Platinum", "POWERPLAY MERITS", "ACQUIRE", 250),
            ("profit", "Platinum", "HIGHEST PROFIT", "REINFORCE", 250),
            ("large-region", "Platinum", "POWERPLAY MERITS", "ACQUIRE", 500),
        ):
            def run():
                facade._mining_find_cache_key = None
                return facade._compute_mining_plan_routes(
                    "Shanteneri", commodity, radius, "ALL RESERVES", "ANY RING",
                    True, "LASER", mode, 5000, 500000, 1, 100, False, True,
                    False, False, "L", "Aisling Duval", goal, "ANY", "ANY")
            started = time.perf_counter()
            routes = run()
            cold = time.perf_counter() - started
            expected = digest(routes)
            times = []
            for _ in range(args.trials):
                started = time.perf_counter()
                routes = run()
                times.append(time.perf_counter() - started)
                assert digest(routes) == expected
            routes, profile = profiled(run)
            assert digest(routes) == expected
            data["search"][label] = {"coldSeconds": cold, "seconds": times,
                                      "median": statistics.median(times), "hash": expected,
                                      "routes": len(routes), "profile": profile}
            print(label, json.dumps({k: v for k, v in data["search"][label].items() if k != "profile"}), flush=True)
    (args.output / "result.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
