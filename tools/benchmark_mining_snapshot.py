"""Synthetic complete/unchanged transfer and persistent snapshot benchmark.

No external network or real Commander profile. HTTP/SQL time is deliberately
excluded; the production SQL probe is documented separately.
"""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ed_companion.navigation.mining_finder import fetch_edframe_mining_candidates
from ed_companion.navigation.mining_snapshot import MiningSnapshotStore


class Response:
    status_code = 200
    def __init__(self, payload):
        self.payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self.payload


def main():
    revision, static = "s1-" + "a" * 64, "b" * 64
    count = 24447
    rows = [dict(system="Synthetic " + str(i // 10), ring="Ring " + str(i),
                 x=0., y=0., z=0., ringType="Metallic", reserveLevel="Pristine",
                 observedAt="2026-09-01T00:00:00Z", receivedAt="2026-09-01T00:00:00Z",
                 source="Synthetic benchmark", evidence="CATALOG_CANDIDATE",
                 hotspots=[], yieldStats=[], prospectorSampleCount=0) for i in range(count)]
    calls = []
    def get(_url, **kwargs):
        calls.append(dict(kwargs["params"]))
        base = dict(snapshotProtocol=1, revision=revision, snapshotStatic=static,
                    communityReferences=[])
        if "known_revision" in kwargs["params"]:
            return Response({**base, "notModified": True, "snapshotComplete": True,
                             "results": [], "hasMore": False})
        offset = kwargs["params"]["offset"]
        more = offset + 1000 < count
        return Response({**base, "notModified": False, "snapshotComplete": not more,
                         "results": rows[offset:offset + 1000], "hasMore": more,
                         "nextOffset": offset + 1000 if more else None})
    with TemporaryDirectory() as directory:
        path = Path(directory, "sites.sqlite3")
        store = MiningSnapshotStore(path)
        coverage = {}
        started = time.monotonic()
        full = fetch_edframe_mining_candidates("Synthetic", get, commodity="platinum",
                 origin=[0., 0., 0.], max_distance=250, snapshot_store=store, diagnostics=coverage)
        projection = time.monotonic() - started
        first_calls = len(calls)
        started = time.monotonic()
        store.save(coverage["_snapshot"])
        save = time.monotonic() - started
        started = time.monotonic()
        cached = fetch_edframe_mining_candidates("Synthetic", get, commodity="platinum",
                 origin=[0., 0., 0.], max_distance=250, snapshot_store=MiningSnapshotStore(path))
        reuse = time.monotonic() - started
        assert full == cached
        print(json.dumps(dict(rings=count, fullRequests=first_calls,
                              unchangedRequests=len(calls) - first_calls,
                              projectionSeconds=round(projection, 6),
                              saveSeconds=round(save, 6), reloadSeconds=round(reuse, 6),
                              databaseBytes=path.stat().st_size, equalRows=True)))


if __name__ == "__main__":
    main()
