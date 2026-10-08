"""Public GET-only retrieval comparison; no app startup, persistence or uploads."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import threading
import time
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from ed_companion.navigation.mining_refresh import fetch_mining_refresh
from ed_companion.navigation.mining_region_cache import MiningRegionCache


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--radius", type=int, default=50)
    args = parser.parse_args()
    query = {"startSystem": "shanteneri", "commodity": "platinum", "nearbyLy": args.radius,
             "minDemand": 5000, "maxMarketAgeHours": 1, "landingPad": "LARGE"}
    origin = {"system": "Shanteneri", "coordinates": [110.9375, -113.0625, 41.21875]}
    trace = []
    lock = threading.Lock()

    class ReadOnlySession(requests.Session):
        def request(self, method, url, **kwargs):
            if method.upper() != "GET":
                raise RuntimeError("Probe allows only public GETs")
            started = time.perf_counter()
            try:
                return super().request(method, url, **kwargs)
            finally:
                with lock:
                    trace.append({"path": urlsplit(url).netloc + urlsplit(url).path,
                                  "seconds": round(time.perf_counter() - started, 3)})

    cache = MiningRegionCache()
    measurements = []
    values = []
    for label in ("initial", "repeat"):
        trace.clear()
        started = time.perf_counter()
        result = fetch_mining_refresh(query, origin=origin, region_cache=cache,
                                      session_factory=ReadOnlySession)
        values.append(result)
        measurements.append({
            "phase": label, "seconds": round(time.perf_counter() - started, 3),
            "httpCalls": len(trace), "callsByEndpoint": dict(Counter(row["path"] for row in trace)),
            "domainTimings": result["fetchTimings"],
            "rings": len(result.get("serverCandidates", [])),
            "powerplay": len(result.get("serverPowerplay", [])),
            "markets": len(result.get("markets", [])),
            "siteCoverage": result.get("siteCoverage"),
            "powerplayCoverage": result.get("powerplayCoverage"),
            "errors": {key: result[key] for key in ("error", "siteError", "powerplayError") if key in result},
        })
        print(json.dumps(measurements[-1]), flush=True)
    identical = {key: (values[0][key] == values[1][key]
                      if all(key in result for result in values) else None)
                 for key in ("serverCandidates", "serverPowerplay")}
    print(json.dumps({
        "radiusLy": args.radius,
        "identicalRings": identical["serverCandidates"],
        "identicalPowerplay": identical["serverPowerplay"],
        "cacheBytes": cache.stored_bytes, "cacheEntries": cache.entry_count,
        "scope": "Retrieval only; not whole-app time, RAM, planning or verification",
    }), flush=True)
    return 0 if all(result.get("success") for result in values) and all(identical.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
