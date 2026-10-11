import json, os, unittest, uuid, subprocess
from tests.test_qml_smoke_load import _run_smoke
from tests.test_qml_ui_quality import SCRIPT as BASE
SCRIPT = BASE[:BASE.index('original_init = main.SmokeTestRunner.__init__')] + r'''
from tests.test_trade_routes import fixture
from unittest.mock import patch
import faulthandler
faulthandler.dump_traceback_later(60)

def open_routes(runner):
    if not runner._page(15,'qa-page-nav'):
        return False
    controller=runner.controller
    controller._commodity_catalog=[dict(id='gold',name='Gold',category='Metals'),dict(id='water',name='Water',category='Chemicals')]
    controller.commoditiesChanged.emit()
    runner._find('tradeRoutesTab').clicked.emit()
    return runner._find('tradeRoutesFinder') is not None

def inputs(runner):
    controller=runner.controller
    controller._edframe_catalog_enabled=True
    controller._trade_request=None
    if not hasattr(controller,'_trade_qa_original_submit'):
        controller._trade_qa_original_submit=controller._start_network_worker
    def submit(worker,label):
        return True if label=='trade-routes' else controller._trade_qa_original_submit(worker,label)
    controller._start_network_worker=Mock(side_effect=submit)
    before=controller._start_network_worker.call_count
    if not runner._find('tradeRouteFilterViewport').isVisible():
        runner._find('tradeRouteToggleFilters').clicked.emit()
    runner._find('tradeRouteCommodity').setProperty('currentIndex',0)
    runner._find('tradeRouteOrigin').setProperty('text','Cubeo')
    runner._find('tradeRouteCargo').setProperty('value',123)
    runner._find('tradeRouteBudget').setProperty('text','5000000000')
    runner._find('tradeRouteRadius').setProperty('currentIndex',2)
    runner._find('tradeRouteLegDistance').setProperty('currentIndex',1)
    runner._find('tradeRouteAge').setProperty('currentIndex',3)
    runner._find('tradeRoutePad').setProperty('currentIndex',3)
    runner._find('tradeRouteSort').setProperty('currentIndex',2)
    assert controller._start_network_worker.call_count==before, 'Editing filters triggered a request'
    runner._find('tradeRouteFind').clicked.emit()
    query=controller._trade_request
    assert query['origin_system']=='Cubeo' and query['origin_mode']=='MANUAL'
    assert (query['capacity'],query['budget'],query['radius'],query['leg_distance'],query['age_hours'],query['pad'],query['sort_by'])==(123,5000000000,100,50,72,'L','DISTANCE'),query
    assert controller._start_network_worker.call_count==before+1
    assert runner._find('tradeRouteFind').property('enabled') is False
    f,s,q=fixture(capacity=123,budget=5000000000,sort_by='DISTANCE')
    f.update(radiusLy=100,maxLegLy=50,maxAgeHours=72)
    from ed_companion.navigation.trade_route_model import rank_loops
    payload=dict(rank_loops(s,q,f),filters=f,coverage=dict(stations=2,availableStations=500,starts=2,availableStarts=100,sampled=True),generatedAt=datetime.now(timezone.utc).isoformat())
    with patch('ed_companion.phase14.controller_trade_routes.fetch_edframe_system_coordinates') as resolve, patch('ed_companion.phase14.controller_trade_routes.fetch_trade_routes') as fetch:
        resolve.return_value=dict(system='Cubeo',coordinates=[0,0,0]);fetch.return_value=payload
        controller._start_network_worker.call_args.args[0]()
    return True

def route_layout(runner):
    controller=runner.controller
    results=runner._find('tradeRouteResults')
    assert results.property('count')==2, ('result count',results.property('count'),controller.tradeRouteStatus)
    assert results.height()>80, ('result height',results.height())
    assert not runner._find('tradeRouteFilterViewport').isVisible(), 'Completed search did not release space for routes'
    assert not runner._find('tradeRouteEmptyState').isVisible()
    assert controller.selectedTradeRouteId
    first=results.property('currentItem')
    assert first is not None
    labels=[o for o in first.findChildren(main.QObject) if o.inherits('QQuickText') and o.isVisible()]
    assert any('A → B → A' in str(o.property('text')) for o in labels)
    assert any('B → A' in str(o.property('text')) for o in labels)
    for label in labels:
        assert label.property('contentHeight')<=label.height()+1, str(label.property('text'))
        assert label.property('contentWidth')<=label.width()+1, str(label.property('text'))
    assert runner._find('tradeRouteCoverage').isVisible()
    button=runner._find('tradeRouteFind')
    assert button.mapToItem(runner.window.contentItem(),QPointF(0,button.height())).y()<runner.window.height()
    assert runner._find('tradeRouteRefresh').property('enabled')
    controller._trade_origin_cache={}
    runner._find('tradeRouteRefresh').clicked.emit()
    assert controller._trade_request['refresh'] is True
    assert controller._trade_request['budget']==5000000000
    # Keep the preview idle, with no background network request.
    controller._trade_request=None
    controller.tradeRoutesChanged.emit()
    return True

def route_value(runner,rank,property_name):
    return evaluate(runner._find('tradeRouteResults'),'itemAtIndex('+str(rank-1)+').'+property_name)

def click_route_action(runner,rank,name):
    # Invoke the actual QML button without exporting virtual delegates to Python.
    expression="""(function() {
        function find(item,name) {
            if (item.objectName===name) return item;
            for (var i=0;i<item.children.length;i++) {
                var found=find(item.children[i],name);
                if (found) return found;
            }
            return null;
        }
        var button=find(itemAtIndex(%d),%s);
        if (!button) return false;
        button.clicked(); return true;
    })()""" % (rank-1,json.dumps(name+str(rank)))
    assert evaluate(runner._find('tradeRouteResults'),expression),name

def expand_details(runner):
    click_route_action(runner,1,'tradeRouteDetails')
    return True

def expanded_layout(runner):
    card=runner._find('tradeRouteResults').property('currentItem')
    assert route_value(runner,1,'detailsExpanded') is True
    labels=[o for o in card.findChildren(main.QObject) if o.inherits('QQuickText') and o.isVisible()]
    for label in labels:
        assert label.property('contentHeight')<=label.height()+1, str(label.property('text'))
        assert label.property('contentWidth')<=label.width()+1, str(label.property('text'))
    assert any(str(label.property('text'))==runner.controller.translate('trade.cost','Purchase cost') for label in labels)
    click_route_action(runner,1,'tradeRouteDetails')
    click_route_action(runner,2,'tradeRouteSelect')
    return True

def alternative_layout(runner):
    assert route_value(runner,2,'selected') is True
    assert route_value(runner,1,'selected') is False
    assert route_value(runner,1,'detailsExpanded') is False
    click_route_action(runner,1,'tradeRouteSelect')
    return True

def seed_from_commodity(runner):
    runner.window.setProperty('navTradeRoutesOpen',False)
    runner.window.setProperty('navCommoditiesOpen',True)
    runner._find('commodityOrigin').setProperty('text','Cubeo')
    category=runner._find('commodityCategory')
    finder=runner._find('commodityFinder')
    category.setProperty('currentIndex',finder.property('categories').toVariant().index('Metals'))
    runner._find('commodityTradeRoute').clicked.emit()
    assert runner.window.property('navTradeRoutesOpen') is True
    assert runner._find('tradeRouteOrigin').property('text')=='Cubeo'
    assert evaluate(runner._find('tradeRouteCommodity'),'currentValue')=='gold'
    runner._find('tradeRouteOrigin').setProperty('text','Sol')
    runner.window.setProperty('navTradeRoutesOpen',False)
    runner.window.setProperty('navCommoditiesOpen',True)
    runner._find('tradeRoutesTab').clicked.emit()
    assert runner._find('tradeRouteOrigin').property('text')=='Sol', 'Tab switch discarded edited origin'
    return True

original_init=main.SmokeTestRunner.__init__
def init(self,*args,**kwargs):
    original_init(self,*args,**kwargs)
    self.steps=[('startup',lambda:self.controller._journal_state_ready)]
    for language,width,height in [('en',1920,1080),('de',1120,700),('fr',1366,768),('es',1120,700)]:
        self.steps.extend([
            (language+'-setup',lambda l=language,w=width,h=height:setup(self,l,w,h)),
            (language+'-open',lambda:open_routes(self)),
            (language+'-inputs',lambda:inputs(self)),
            (language+'-layout',lambda:route_layout(self)),
            (language+'-details',lambda:expand_details(self)),
            (language+'-expanded-layout',lambda:expanded_layout(self)),
            (language+'-alternative',lambda:alternative_layout(self)),
            (language+'-commodity-seed',lambda:seed_from_commodity(self))])
main.SmokeTestRunner.__init__=init
original_poll=main.SmokeTestRunner._poll
def poll(self):
    before=self.step_index
    original_poll(self)
    if self.step_index != before:
        print('TRADE_QA_STEP='+json.dumps(self.results[-1]),flush=True)
main.SmokeTestRunner._poll=poll
raise SystemExit(main.run())
'''

class TradeRouteQmlTests(unittest.TestCase):
    def test_round_trip_page_inputs_results_and_commodity_link(self):
        try:
            completed,report=_run_smoke({'PHASE14_SMOKE_ASYNC_PAGES':'1',
                'QT_QUICK_BACKEND':'software',
                'ED_FRAME_SINGLE_INSTANCE_NAME':'ED-Frame-trade-qa-'+uuid.uuid4().hex},script=SCRIPT,timeout=90)
        except subprocess.TimeoutExpired as exc:
            self.fail('Native route test timed out: '+str(exc.output)[-3500:]+str(exc.stderr)[-3500:])
        self.assertIsNotNone(report,completed.stdout+completed.stderr)
        self.assertEqual(report['status'],'PASS',json.dumps(report,ensure_ascii=False))
        self.assertEqual(completed.returncode,0,completed.stderr)
