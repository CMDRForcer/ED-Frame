"""Native JavaScript arrays must reach the production Qt verification slots."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class MiningVerificationQmlTests(unittest.TestCase):
    def test_production_slots_accept_copied_arrays_and_preserve_query_context(self):
        with tempfile.TemporaryDirectory(prefix="ed-frame-verification-qml-") as scratch:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--qml"],
                env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "LOCALAPPDATA": scratch},
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PRODUCTION_VERIFICATION_QML_PASS", result.stdout)


def run_qml():
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QObject
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlEngine, QQmlExpression
    from PySide6.QtTest import QSignalSpy
    from ed_companion.phase14.controller import CockpitController

    app = QGuiApplication([])
    engine = QQmlEngine()

    def controller():
        value = CockpitController.__new__(CockpitController)
        QObject.__init__(value)
        value.profile_context = SimpleNamespace(key="qml-verification-fixture")
        value._profile_generation = 1
        value.mining_catalog_file = Path("unused-mining-fixture.json")
        value._known_mining_origin = Mock(return_value={"coordinates": [1, 2, 3]})
        value._start_network_worker = Mock(return_value=True)
        return value

    def invoke(value, routes, *, legacy=False):
        engine.rootContext().setContextProperty("verifier", value)
        # Match the real page: copy routes into a new JS array and snapshot
        # scalar values before dispatching across the QML/Python boundary.
        arguments = "copied, String('Origin')" if legacy else (
            "copied, String('Origin'), String('Platinum'), Number(1), Number(5000), String('LARGE')"
        )
        expression = QQmlExpression(engine.rootContext(), None, """
            (function() {
                let rows = %s;
                let copied = [];
                for (let i=0; i<rows.length; ++i) copied.push(rows[i]);
                verifier.verifyMiningRoutes(%s);
            })()
        """ % (json.dumps(routes), arguments))
        expression.evaluate()
        assert not expression.hasError(), expression.error().toString()

    routes = [{
        "system": f"Mine {index}", "ring": f"Mine {index} A Ring",
        "systemAddress": index + 1, "coordinates": [1, 2, 3],
        "sellSystem": "Shared sale", "sellCoordinates": [4, 5, 6],
        "optimization": "POWERPLAY MERITS", "powerplayStatus": "POWERPLAY_DATA_MISSING",
        "selectedCommodity": "platinum", "sameSystemSaleRequired": True,
        "marketMatchesFilters": False,
    } for index in range(100)]
    routes[0]['systemAddress'] = 1384900446587
    current = controller()
    changed = QSignalSpy(current.miningVerificationChanged)
    invoke(current, routes)
    current._start_network_worker.assert_called_once()
    assert current._start_network_worker.call_args.args[1] == "mining-route-verification"
    request = current._active_mining_verification_request
    assert current._mining_verification_busy and changed.count() == 1
    assert len(request["powerplayLookupTargets"]) == 101, "mine/sale coverage was lost"
    assert request["powerplayLookupTargets"][0]["systemAddress"] == 1384900446587, "QML id64 was lost"
    current._mining_powerplay_source_pending = ['Mine 99']
    current._mining_powerplay_lookup_states = {'mine 0': {'state': 'STALE', 'observedAt': '2020-01-01T00:00:00Z'}}
    state_expression = QQmlExpression(engine.rootContext(), None,
        "verifier.miningPowerplayPendingSourceCount === 1 && "
        "verifier.miningPowerplayLookupStates['mine 0'].state === 'STALE'")
    ready, _undefined = state_expression.evaluate()
    assert not state_expression.hasError(), state_expression.error().toString()
    assert ready, 'Powerplay source state did not reach QML'
    assert len(request["marketTargets"]) == 6, "existing network budget changed"
    assert request["targets"] == [], "Powerplay checks unexpectedly caused ring downloads"
    assert request["commodity"] == "platinum" and request["minDemand"] == 5000
    assert request["maxMarketAgeHours"] == 1 and request["landingPad"] == "LARGE"
    assert "Verifying top routes" in current._mining_verification_status

    queued = [{**routes[-1], "sellPrice": None, "communityOverlapReports": [
        {"commodity": "platinum", "reportedResTypes": ["HAZARDOUS"]},
    ]}]
    invoke(current, queued)
    assert current._pending_mining_verification == {
        "routes": queued, "startSystem": "Origin", "commodity": "platinum",
        "maxMarketAgeHours": 1, "minDemand": 5000, "landingPad": "LARGE",
    }, "queued query or nested array/null values changed across QML"
    current._start_network_worker.assert_called_once()

    legacy = controller()
    invoke(legacy, [{"system": "Legacy", "systemAddress": 42}], legacy=True)
    legacy._start_network_worker.assert_called_once()
    legacy_request = legacy._active_mining_verification_request
    assert len(legacy_request["targets"]) == 1
    assert legacy_request["commodity"] == "" and legacy_request["minDemand"] == 0
    assert legacy_request["maxMarketAgeHours"] == 0 and legacy_request["landingPad"] == "ANY"

    empty = controller()
    invoke(empty, [])
    empty._start_network_worker.assert_not_called()
    assert not getattr(empty, "_mining_verification_busy", False)
    assert empty._mining_verification_total == 0
    assert "No displayed route" in empty._mining_verification_status

    engine.rootContext().setContextProperty("verifier", None)
    del engine
    app.processEvents()
    print("PRODUCTION_VERIFICATION_QML_PASS", flush=True)


if __name__ == "__main__":
    if "--qml" in sys.argv:
        run_qml()
    else:
        unittest.main()
