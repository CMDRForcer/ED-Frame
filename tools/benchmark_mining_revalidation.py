"""Synthetic complete/changed/unchanged revalidation, no HTTP or real profile.

--baseline loads the pre-package source into disposable Python namespaces;
neither the checkout nor installed profile is modified. SQL/server timing is
measured separately. This fixture is repetitive, not a disk-size forecast.
"""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ed_companion.navigation import mining_finder, mining_snapshot


class Response:
    status_code = 200
    def __init__(self, payload):
        self.payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self.payload


def baseline(path):
    source = subprocess.run(["git", "show", "HEAD:" + path], cwd=ROOT, check=True,
                            capture_output=True, text=True, encoding="utf-8").stdout
    namespace = {"__name__": "benchmark_baseline", "__package__": "ed_companion.navigation"}
    exec(compile(source, "<baseline-source>", "exec"), namespace)
    return namespace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    fetch = mining_finder.fetch_edframe_mining_candidates
    store_class = mining_snapshot.MiningSnapshotStore
    if args.baseline:
        fetch = baseline("ed_companion/navigation/mining_finder.py")["fetch_edframe_mining_candidates"]
        store_class = baseline("ed_companion/navigation/mining_snapshot.py")["MiningSnapshotStore"]
    class CountedStore(store_class):
        loads = 0
        def load(self, *args, **kwargs):
            self.loads += 1
            return super().load(*args, **kwargs)
    rev, static = "s1-" + "a" * 64, "c" * 64
    rows = [dict(system="Synthetic " + str(i // 10), ring="Ring " + str(i),
                 x=0., y=0., z=0., ringType="Metallic", reserveLevel="Pristine",
                 observedAt="2026-09-01T00:00:00Z", receivedAt="2026-09-01T00:00:00Z",
                 evidence="CATALOG_CANDIDATE", source="Synthetic benchmark",
                 hotspots=[], yieldStats=[], prospectorSampleCount=0) for i in range(24447)]
    active, calls = {"revision": rev}, []
    def get(_url, **kwargs):
        params = kwargs["params"]
        calls.append(dict(params))
        base = dict(snapshotProtocol=1, revision=active["revision"], snapshotStatic=static,
                    communityReferences=[])
        if params.get("known_revision") == active["revision"]:
            return Response({**base, "notModified": True, "snapshotComplete": True,
                             "results": [], "hasMore": False})
        offset, size = params["offset"], params.get("regional_page_size", 1000)
        more = offset + size < len(rows)
        return Response({**base, "notModified": False, "snapshotComplete": not more,
                         "results": rows[offset:offset+size], "hasMore": more,
                         "nextOffset": offset + size if more else None})
    def run(store, **kwargs):
        return fetch("Synthetic", get, commodity="platinum", origin=[0., 0., 0.],
                     max_distance=250, snapshot_store=store, **kwargs)
    with TemporaryDirectory() as directory:
        store = CountedStore(Path(directory, "snapshots.sqlite3"))
        coverage = {}
        full = run(store, diagnostics=coverage)
        initial_calls = len(calls)
        store.save(coverage["_snapshot"])
        result = {"baseline": args.baseline, "rings": len(full), "initialRequests": initial_calls,
                  "inputSha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}
        for kind in ("unchanged", "changed"):
            if kind == "changed":
                active["revision"] = "s1-" + "b" * 64
                rows[0] = {**rows[0], "hotspots": [{"commodity": "platinum", "count": 2}]}
            timings, counts, loads = [], [], []
            for _ in range(5):
                calls.clear()
                store.loads = 0
                started = time.monotonic()
                found = run(store)
                timings.append(time.monotonic() - started)
                counts.append(len(calls))
                loads.append(store.loads)
                assert len(found) == len(full)
                if kind == "unchanged":
                    assert found == full
                else:
                    assert found[0]["hotspots"] == rows[0]["hotspots"]
                    assert found[0]["observedAt"] == full[0]["observedAt"]
            result[kind] = dict(medianSeconds=round(statistics.median(timings), 6),
                                requests=counts, oldPayloadLoads=loads,
                                seconds=[round(value, 6) for value in timings])
        result["equalRowsAndAges"] = True
        print(json.dumps(result))


if __name__ == "__main__":
    main()
