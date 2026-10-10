"""Exercise bounded continuation and source details in the real Mining page."""
import os
import unittest

from tests.test_qml_smoke_load import _run_smoke


SCRIPT = r'''
import json, os, time
from datetime import datetime, timezone
from unittest.mock import Mock
from pathlib import Path
os.environ['QT_QPA_FONTDIR'] = 'C:/Windows/Fonts'
fixture = Path(os.environ['LOCALAPPDATA']) / 'journal-fixture'
fixture.mkdir()
events = [
    {'event':'Fileheader','timestamp':'2026-10-10T00:00:00Z'},
    {'event':'LoadGame','timestamp':'2026-10-10T00:00:01Z', 'FID':'F0000000',
     'Commander':'QML Fixture','Ship':'Adder','Credits':1000,'Horizons':True,'Odyssey':True},
    {'event':'Location','timestamp':'2026-10-10T00:00:02Z','StarSystem':'Preview',
     'StarPos':[1,2,3],'SystemAddress':42,'Docked':False},
]
(fixture/'Journal.2026-10-10T000000.01.log').write_text('\n'.join(json.dumps(event) for event in events)+'\n')
os.environ['ED_FRAME_JOURNAL_DIR'] = str(fixture)
import requests, urllib.request
requests.sessions.Session.request = Mock(side_effect=RuntimeError('Offline QML fixture'))
urllib.request.urlopen = Mock(side_effect=RuntimeError('Offline QML fixture'))
import phase14_main as main
from PySide6.QtCore import QTimer, QObject
from PySide6.QtQml import QQmlEngine, QQmlExpression
from ed_companion.navigation.mining_planner import plan_mining_routes

original_init = main.SmokeTestRunner.__init__

def evaluate(runner, text):
    page = runner._find('qa-page-mining-finder')
    if page is None:
        return None
    expression = QQmlExpression(QQmlEngine.contextForObject(page), page, text)
    result, _undefined = expression.evaluate()
    if expression.hasError():
        raise RuntimeError(expression.error().toString())
    return result

def prepare(runner):
    if not runner._page(12, 'qa-page-mining-finder'):
        return False
    for name in ('qa-dialog-onboarding', 'qa-dialog-about'):
        dialog = runner._find(name)
        if dialog is not None:
            dialog.setProperty('visible', False)
    c = runner.controller
    now = datetime.now(timezone.utc).isoformat()
    rows = plan_mining_routes([{'system': 'HIP 92103', 'systemAddress': 1384900446587,
        'coordinates': [1,2,3], 'ring': 'HIP 92103 3 A Ring', 'ringTypeName': 'Metallic',
        'distanceLy': 40.7, 'reserveLevel': 'PristineResources',
        'targetMatch': 'HOTSPOT', 'observedAt': now, 'evidence': 'LIVE_REPORTED'}],
        'Platinum', 'POWERPLAY MERITS', power='Aisling Duval')
    assert len(rows) == 1
    rows[0].update(sellSystem='HIP 3254', sellCoordinates=[4,5,6])
    c.miningPlanRoutes = Mock(return_value=rows)
    c._start_network_worker = Mock(return_value=True)
    c._mining_powerplay_source_pending = ['HIP 92103']
    c._mining_powerplay_lookup_states = {
        'hip 92103': {'system': 'HIP 92103', 'state': 'STALE', 'observedAt': '2026-10-02T23:23:01Z'},
        'hip 3254': {'system': 'HIP 3254', 'state': 'CURRENT', 'observedAt': now},
    }
    c._mining_verification_busy = False
    c._mining_market_sync_busy = False
    c._mining_plan_busy = False
    c._edframe_catalog_enabled = True
    runner._find('qa-page-mining-finder').setProperty('resultRows', rows)
    runner.timer = runner._find('qa-page-mining-finder').findChild(QObject, 'qa-mining-powerplay-continuation')
    assert runner.timer is not None
    runner.timer.setProperty('interval', 100)
    evaluate(runner, "appliedPower = 'Aisling Duval'; appliedStartSystem = 'Preview'; "
                     "searchRevision = 1; verifiedSearchRevision = 1; searchGoalExpanded = false;")
    c.miningVerificationChanged.emit()
    return True

def continued(runner):
    c = runner.controller
    request = getattr(c, '_active_mining_verification_request', None)
    if not request or not c._start_network_worker.called:
        return False
    assert len(request['powerplayLookupTargets']) == 2, request
    assert request['powerplayLookupTargets'][0]['systemAddress'] == 1384900446587, request
    assert not runner.timer.property('running'), 'busy work must pause timer'
    details = evaluate(runner, 'powerplaySourceDetails(bestRoute)')
    expected = datetime.fromisoformat('2026-10-02T23:23:01+00:00').astimezone().strftime('%d.%m.%Y %H:%M')
    assert 'HIP 92103' in details and expected in details and 'HIP 3254' in details, details
    assert evaluate(runner, 'powerplaySourceTooOld(bestRoute)'), details
    assert not any(row.get('system') == 'HIP 92103' for row in getattr(c, '_mining_powerplay_observations', [])), 'diagnostics became facts'
    runner.window.setProperty('currentPage', 0)
    return True

def hidden(runner):
    c = runner.controller
    c._mining_verification_busy = False
    c.miningVerificationChanged.emit()
    import shiboken6
    assert not shiboken6.isValid(runner.timer) or not runner.timer.property('running'), 'hidden page must pause timer'
    runner.window.setProperty('currentPage', 12)
    return True

def complete(runner):
    c = runner.controller
    page = runner._find('qa-page-mining-finder')
    if page is None or not page.property('visible'):
        return False
    c._mining_powerplay_source_pending = []
    c.miningVerificationChanged.emit()
    timer = page.findChild(QObject, 'qa-mining-powerplay-continuation')
    assert timer is not None and not timer.property('running'), 'empty queue must stop timer'
    calls = [call for call in c._start_network_worker.call_args_list
             if call.args[1] == 'mining-route-verification']
    if not hasattr(runner, 'capture_at'):
        runner.completed_call_count = len(calls)
        c._active_mining_verification_request = None
        c._mining_verification_busy = False
        c.miningVerificationChanged.emit()
        page.setProperty('resultRows', c.miningPlanRoutes.return_value)
        evaluate(runner, 'searchRevision = 1; verifiedSearchRevision = 1; searchGoalExpanded = false;')
        runner.capture_at = time.monotonic() + .15
        return False
    if time.monotonic() < runner.capture_at:
        return False
    assert len(calls) == runner.completed_call_count, 'empty queue kept polling'
    screenshot = os.environ.get('POWERPLAY_QA_SCREENSHOT')
    if screenshot and not runner.window.grabWindow().save(screenshot):
        raise RuntimeError('Screenshot failed')
    return True

def init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    self.steps = [('powerplay-source-fixture', lambda: prepare(self)),
                  ('powerplay-batch-continuation', lambda: continued(self)),
                  ('powerplay-hidden-pauses', lambda: hidden(self)),
                  ('powerplay-queue-stops', lambda: complete(self))]
main.SmokeTestRunner.__init__ = init
raise SystemExit(main.run())
'''


class MiningPowerplayContinuationQmlTests(unittest.TestCase):
    def test_real_page_continues_and_stops_without_background_polling(self):
        extra = {'PHASE14_SMOKE_ASYNC_PAGES': '0'}
        if os.environ.get('POWERPLAY_QA_SCREENSHOT'):
            extra['POWERPLAY_QA_SCREENSHOT'] = os.environ['POWERPLAY_QA_SCREENSHOT']
        completed, report = _run_smoke(extra, script=SCRIPT)
        self.assertIsNotNone(report, completed.stdout + completed.stderr)
        self.assertEqual(report['status'], 'PASS', completed.stdout + completed.stderr)
        self.assertEqual(completed.returncode, 0)


if __name__ == '__main__':
    unittest.main()
