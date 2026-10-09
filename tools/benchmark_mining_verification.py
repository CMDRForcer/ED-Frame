"""Controlled, zero-network before/after check of the real verification path.

Use identical synthetic public HTTP responses and per-request latency. Run the
baseline method from a local release ref and the current method against the same
real market/Powerplay projectors. No app profile, persistence or live API is used.
"""

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import Mock, patch
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ed_companion.phase14.controller import CockpitController
from ed_companion.phase14 import controller_navigation as navigation


def baseline_method(ref):
    source = subprocess.check_output([
        "git", "show", f"{ref}:ed_companion/phase14/controller_navigation.py",
    ], cwd=ROOT, text=True, encoding="utf-8")
    tree = ast.parse(source)
    mixin = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                 and node.name == "NavigationMixin")
    method = next(node for node in mixin.body if isinstance(node, ast.FunctionDef)
                  and node.name == "verifyMiningRoutes")
    method.decorator_list = []
    namespace = dict(vars(navigation))
    exec(compile(ast.Module(body=[method], type_ignores=[]), f"{ref}:verifyMiningRoutes", "exec"), namespace)
    return namespace["verifyMiningRoutes"]


def measure(method, *, delay, stamp):
    c = CockpitController.__new__(CockpitController)
    c.profile_context = Mock(key="benchmark")
    c._profile_generation = 1
    c.mining_catalog_file = Path("synthetic-catalog.json")
    c._known_mining_origin = Mock(return_value={"coordinates": [10, 20, 30]})
    c._start_network_worker = Mock(return_value=True)
    c._persist_verified_mining_markets = Mock()
    for signal in ("miningChanged", "miningVerificationChanged", "miningVerificationProgress",
                   "miningVerificationFinished"):
        setattr(c, signal, Mock())
    routes = [{"system": f"Mine {index}", "coordinates": [index, 2, 3],
               "sellSystem": "Sale", "sellCoordinates": [10, 20, 30],
               "optimization": "POWERPLAY MERITS", "powerplayStatus": "POWERPLAY_DATA_MISSING",
               "sameSystemSaleRequired": True, "marketMatchesFilters": False,
               "selectedCommodity": "platinum", "selectedPower": "Aisling Duval"}
              for index in range(6)]
    active, maximum = 0, 0
    calls = []
    lock = threading.Lock()

    def get(url, **kwargs):
        nonlocal active, maximum
        parsed = urlsplit(url)
        params = kwargs.get("params") or {}
        with lock:
            active += 1
            maximum = max(maximum, active)
            calls.append({"host": parsed.hostname, "path": parsed.path, "params": params})
        try:
            time.sleep(delay)  # Synthetic latency, not a live timing assertion.
            if parsed.path.endswith("/systems/suggest"):
                index = int(params["q"].split()[-1])
                payload = {"results": [{"name": params["q"], "x": index, "y": 2, "z": 3}]}
            elif parsed.path.endswith("/mining/powerplay"):
                payload = {"results": [], "hasMore": False, "selection": "systems"}
            elif parsed.path.endswith("/markets/search"):
                payload = {"results": []}
            else:
                system = unquote(parsed.path.split("/system/name/")[1].split("/commodity/")[0])
                if "ardent" in str(parsed.hostname) and system == "Mine 2":
                    raise RuntimeError("synthetic primary outage; exercise fallback")
                index = int(system.split()[-1])
                payload = [{"commodityName": "platinum", "systemName": system,
                            "stationName": "Public Port", "marketId": 1000 + index,
                            "sellPrice": 200000 + index, "demand": 10000,
                            "maxLandingPadSize": "L", "updatedAt": stamp,
                            "systemX": index, "systemY": 2, "systemZ": 3}]
            return Mock(json=Mock(return_value=payload))
        finally:
            with lock:
                active -= 1

    sessions = []

    class SyntheticSession:
        def __init__(self):
            self.get = Mock(side_effect=get)
            self.close = Mock()

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            self.close()
            return False

    def factory():
        session = SyntheticSession()
        sessions.append(session)
        return session

    with patch("requests.get", side_effect=get), patch("requests.Session", side_effect=factory):
        method(c, routes, "Origin", "Platinum", 1, 5000, "LARGE")
        began = time.perf_counter()
        c._start_network_worker.call_args.args[0]()
        seconds = time.perf_counter() - began
    result = c.miningVerificationFinished.emit.call_args.args[0]
    comparable = {key: result[key] for key in (
        "candidates", "succeeded", "failed", "markets", "marketSucceeded", "marketFailed",
        "marketOutcomes", "powerplayLookup", "total", "completed",
    )}
    progress = [call.args[0] for call in c.miningVerificationProgress.emit.call_args_list]
    assert progress[-1]["completed"] == result["total"]
    assert all(session.close.call_count == 1 for session in sessions)
    digest = hashlib.sha256(json.dumps(comparable, sort_keys=True).encode()).hexdigest()
    return {"seconds": round(seconds, 4), "requests": len(calls), "maxConcurrentRequests": maximum,
            "coordinateRequests": sum(call["path"].endswith("/systems/suggest") for call in calls),
            "completed": progress[-1]["completed"], "total": result["total"], "digest": digest,
            "calls": calls, "providerCounts": dict(Counter(call["host"] for call in calls))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="1.5.41")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--delay", type=float, default=0.05)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / ".test-tmp") or output.exists() or not 0 < args.delay <= 1:
        parser.error("Use a new output file inside .test-tmp and a delay in (0, 1]")
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    before = measure(baseline_method(args.baseline), delay=args.delay, stamp=stamp)
    after = measure(navigation.NavigationMixin.verifyMiningRoutes, delay=args.delay, stamp=stamp)
    # Only the six redundant coordinate lookups may disappear. Every actual
    # market/Powerplay query, including the outage fallback, must stay identical.
    def evidence_calls(run):
        return sorted(json.dumps(call, sort_keys=True) for call in run["calls"]
                      if not call["path"].endswith("/systems/suggest"))
    assert before["digest"] == after["digest"]
    assert evidence_calls(before) == evidence_calls(after)
    assert before["requests"] - after["requests"] == 6
    assert after["maxConcurrentRequests"] <= 2
    report = {"mode": "synthetic HTTP/no network/no profile", "baseline": args.baseline,
              "perRequestLatencySeconds": args.delay, "identicalResults": True,
              "identicalEvidenceQueries": True, "before": before, "after": after}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in ("before", "after")}))
    for name in ("before", "after"):
        print(name, json.dumps({key: value for key, value in report[name].items() if key != "calls"}))


if __name__ == "__main__":
    main()
