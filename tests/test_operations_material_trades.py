"""The complete build's actionable trades must remain visible beside NBA focus."""
import json
import os
import unittest

from tests.test_qml_smoke_load import _run_smoke
from tests.test_qml_ui_quality import SCRIPT as BASE


SCRIPT = BASE[:BASE.index('original_init = main.SmokeTestRunner.__init__')] + r'''
def fixture(runner):
    c = runner.controller
    c._operation_action = lambda: dict(kind='COLLECT', moduleName='Thrusters',
        blueprintName='Dirty Drive Tuning', experimentalName='Drag Drives', targetGrade=5,
        engineerName='Professor Palin', engineerOptions=[], experimentalEffects=[], executable=False)
    c._state.update(ship='Anaconda Mk II',activeShip='Anaconda Mk II',fleetKnown=True,
        completion=.53, completionReliable=True, covered=53, required=100,
        materials=[dict(key='iron',name='Iron',missing=18)],
        trades=[dict(id='raw',category='RAW',targetKey='iron',giveName='Cadmium',giveAmount=2,
                receiveName='Iron',receiveAmount=18,usefulAmount=12,surplusAmount=6,remaining=0,
                system='Raw System',station='Raw Trader',status='open',traderWarning=''),
            dict(id='manufactured',category='MANUFACTURED',targetKey='chemicalprocessors',
                giveName='Chemical Manipulators',giveAmount=1,receiveName='Chemical Processors',
                receiveAmount=9,usefulAmount=9,surplusAmount=0,remaining=4,
                system='Manufactured System',station='Manufactured Trader',status='open',traderWarning=''),
            dict(id='encoded',category='ENCODED',targetKey='untypicalshieldscans',
                giveName='Peculiar Shield Frequency Data',giveAmount=3,receiveName='Untypical Shield Scans',
                receiveAmount=9,usefulAmount=9,surplusAmount=0,remaining=0,
                system='Encoded System',station='Encoded Trader',status='open',traderWarning='')],
        traderRoute=[dict(sequence=1,category='Encoded',system='Encoded System',station='Encoded Trader'),
            dict(sequence=2,category='Raw',system='Raw System',station='Raw Trader'),
            dict(sequence=3,category='Manufactured',system='Manufactured System',station='Manufactured Trader')])
    c.stateChanged.emit(); c.materialsChanged.emit(); c.operationsChanged.emit()
    runner.window.setProperty('currentPage',0)
    return True

def show_build(runner):
    card=runner._find('qa-card-material-trades')
    scroll=runner._find('qa-page-operations')
    top=card.mapToItem(scroll,QPointF(0,0)).y()
    evaluate(scroll, 'contentItem.contentY = Math.max(0, Math.min(contentHeight - availableHeight, contentItem.contentY + %s))' % top)
    return True

def visible_build(runner):
    card=runner._find('qa-card-material-trades')
    view=runner._find('qa-full-build-trades')
    assert card and view, 'Material trade card/list missing'
    assert card.width() >= 300, ('Trade card collapsed',card.width(),card.height())
    assert view.height() >= 180, ('Trade list collapsed',view.width(),view.height())
    assert view.property('count') == 3, ('Full build should show every category',view.property('count'))
    assert runner.window.property('materialTradeFilter') == 'ALL'
    def visual_items(item):
        yield item
        for child in item.childItems():
            yield from visual_items(child)
    labels={item.objectName():item for item in visual_items(view.property('contentItem'))
            if item.objectName().startswith(('trade-give-','trade-receive-'))}
    for name,amount,material in [('trade-give-encoded','3','Peculiar Shield Frequency Data'),
                                ('trade-receive-encoded','9','Untypical Shield Scans')]:
        label=labels[name]
        assert amount in label.property('text') and material in label.property('text')
        assert label.width() >= 120, (name,label.width())
        assert label.height() >= label.property('contentHeight'), (name,'Clipped trade text')
    output=os.environ.get('ED_FRAME_TRADES_CAPTURE_DIR','')
    if output:
        folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
        assert runner.window.grabWindow().save(str(folder/('operations-full-build-trades-%s.png' % runner.window.width())))
    return True

def filter_raw(runner):
    runner.window.setProperty('materialTradeFilter','RAW')
    return True

def raw_visible(runner):
    view=runner._find('qa-full-build-trades')
    assert view.property('count') == 1
    rows=evaluate(runner.window,'JSON.stringify(visibleMaterialTrades(cockpit.trades))')
    row=json.loads(rows)[0]
    assert row['giveAmount'] == 2 and row['receiveAmount'] == 18, row
    assert row['surplusAmount'] == 6 and row['remaining'] == 0, row
    runner.window.setProperty('materialTradeFilter','ALL')
    runner.controller._state['trades']=runner.controller._state['trades'][1:]
    runner.controller.materialsChanged.emit()
    return True

def after_trade(runner):
    assert runner._find('qa-full-build-trades').property('count') == 2
    return True

original_init=main.SmokeTestRunner.__init__
def init(self,*args,**kwargs):
    original_init(self,*args,**kwargs)
    self.steps=[('startup',lambda:self.controller._journal_state_ready),
        ('wide',lambda:setup(self,'en',1920,1080)),
        ('fixture',lambda:fixture(self)),('show-build',lambda:show_build(self)),
        ('complete-build-list',lambda:visible_build(self)),
        ('filter-raw',lambda:filter_raw(self)),('raw-trade-amounts',lambda:raw_visible(self)),
        ('after-confirmed-trade',lambda:after_trade(self)),
        ('narrow',lambda:setup(self,'de',1120,700)),
        ('restore-fixture',lambda:fixture(self)),('show-narrow-build',lambda:show_build(self)),
        ('narrow-build-list',lambda:visible_build(self))]
main.SmokeTestRunner.__init__=init
raise SystemExit(main.run())
'''


class OperationsMaterialTradesTests(unittest.TestCase):
    def test_complete_build_trades_render_and_update_beside_experimental_focus(self):
        completed, report = _run_smoke({
            'ED_FRAME_TRADES_CAPTURE_DIR': os.environ.get('ED_FRAME_TRADES_CAPTURE_DIR', ''),
        }, script=SCRIPT, timeout=90)
        self.assertIsNotNone(report, completed.stdout + completed.stderr)
        self.assertEqual(report['status'], 'PASS', json.dumps(report, ensure_ascii=False))
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == '__main__':
    unittest.main()
