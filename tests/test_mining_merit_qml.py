"""Native QML handoff and dated last-known route presentation."""
import os
import unittest

from tests.test_mining_powerplay_continuation_qml import SCRIPT as BASE_SCRIPT
from tests.test_qml_smoke_load import _run_smoke

SCRIPT = BASE_SCRIPT[:BASE_SCRIPT.index('def init(self, *args, **kwargs):')] + r'''
from datetime import timedelta
from ed_companion.navigation.mining_planner import plan_mining_routes

def show_history(runner):
    c = runner.controller
    dialog=runner._find('qa-dialog-onboarding')
    if dialog is not None:
        dialog.setProperty('visible',False)
    runner.window.setProperty('currentPage',12)
    runner.window.setProperty('width',1366)
    page = runner._find('qa-page-mining-finder')
    if page is None or not page.property('visible'):
        return False
    now = datetime.now(timezone.utc)
    old = (now-timedelta(days=8)).isoformat()
    rows = plan_mining_routes([{'system':'HIP 92103','ring':'HIP 92103 3 A Ring',
        'systemAddress':1384900446587,'coordinates':[1,2,3],'ringType':'Metallic',
        'evidence':'CATALOG_CANDIDATE','observedAt':now.isoformat()}],
        'Platinum','POWERPLAY MERITS', power='Aisling Duval',power_goal='REINFORCE',
        powerplay_systems=[{'system':'HIP 92103','power':'Aisling Duval',
            'controllingPower':'Aisling Duval','powerState':'Exploited','observedAt':old}],
        markets=[{'system':'HIP 92103','station':'Example Port','commodity':'platinum',
            'sellPrice':58486,'demand':5945,'observedAt':now.isoformat()}],now=now)
    assert rows[0]['verificationStatus']=='PROVISIONAL', rows
    c.miningPlanRoutes=Mock(return_value=rows)
    c._start_network_worker=Mock(return_value=True)
    c._mining_powerplay_lookup_states={}
    c._mining_market_verification_states={}
    c._mining_powerplay_source_pending=[]
    c._edframe_catalog_enabled=True
    c._mining_market_busy=False
    c._mining_verification_busy=False
    c._mining_plan_busy=False
    c.refreshMiningMarkets=Mock()
    page.setProperty('resultRows', rows)
    evaluate(runner, "powerOverride='Aisling Duval'; startSystem='HIP 3254'; "
        "appliedPower='Aisling Duval'; appliedPowerGoal='REINFORCE'; "
        "searchRevision=1; verifiedSearchRevision=1; searchGoalExpanded=false;")
    label=evaluate(runner, 'verificationShortLabel(bestRoute)')
    assert 'LAST KNOWN' in label, label
    details=evaluate(runner, 'powerplaySourceDetails(bestRoute)')
    assert 'Aisling Duval' in details and 'Exploited' in details, details
    expected=datetime.fromisoformat(old).astimezone().strftime('%d.%m.%Y %H:%M')
    assert expected in details, details
    assert not evaluate(runner,'bestRoute.meritVerified')
    evaluate(runner,'executeSearch()')
    args=c.refreshMiningMarkets.call_args.args
    assert len(args)==10 and args[6:] == ('Aisling Duval','REINFORCE','ANY','LASER'), args
    evaluate(runner,'verifiedSearchRevision=searchRevision')
    c._mining_market_verification_states={'mine\x1fplatinum':{'state':'QUEUED'}}
    c.miningVerificationChanged.emit()
    runner.history_ready=time.monotonic()+.15
    return True

def finish_history(runner):
    if time.monotonic()<runner.history_ready:
        return False
    c=runner.controller
    c._active_mining_verification_request=None
    c._mining_verification_busy=False
    c.miningVerificationChanged.emit()
    timer=runner._find('qa-page-mining-finder').findChild(QObject,'qa-mining-powerplay-continuation')
    state=evaluate(runner, 'JSON.stringify([appWindow.currentPage,searchRevision,resultRows.length,'
        'cockpit.edFrameCatalogEnabled,cockpit.miningPowerplayPendingSourceCount,'
        'cockpit.miningMarketPendingSourceCount,cockpit.miningVerificationBusy,'
        'cockpit.miningPlanBusy,cockpit.miningMarketSyncBusy])')
    assert timer.property('running'), 'queued market checks did not continue: '+str(state)
    runner.controller._mining_market_verification_states={}
    runner.controller.miningVerificationChanged.emit()
    card=runner._find('qa-mining-best-route')
    assert card is not None
    layout=card.childItems()[0]
    for row in layout.childItems():
        if not row.isVisible():
            continue
        for child in row.childItems():
            if child.isVisible():
                assert child.x()+child.width() <= row.width()+1, (
                    'route content overflows the card', child, child.x(), child.width(), row.width())
    screenshot=os.environ.get('MERIT_QA_SCREENSHOT')
    if screenshot:
        assert runner.window.grabWindow().save(screenshot)
    return True

def init(self,*args,**kwargs):
    original_init(self,*args,**kwargs)
    self.steps=[('merit-history-ui',lambda: show_history(self)),
                ('merit-history-final',lambda: finish_history(self))]
main.SmokeTestRunner.__init__=init
raise SystemExit(main.run())
'''


class MeritQmlTests(unittest.TestCase):
    def test_native_page_sends_power_context_and_displays_unconfirmed_history(self):
        extra = {'PHASE14_SMOKE_ASYNC_PAGES': '0'}
        if os.environ.get('MERIT_QA_SCREENSHOT'):
            extra['MERIT_QA_SCREENSHOT'] = os.environ['MERIT_QA_SCREENSHOT']
        completed, report = _run_smoke(extra, script=SCRIPT)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIsNotNone(report)
        self.assertEqual(report['status'], 'PASS', report)


if __name__ == '__main__':
    unittest.main()
