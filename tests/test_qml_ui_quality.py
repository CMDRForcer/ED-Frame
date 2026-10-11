"""Exercise narrow layouts, empty views and translated search controls in Qt."""
import json
import unittest

from tests.test_qml_smoke_load import _run_smoke


SCRIPT = r'''
import json
import os
from pathlib import Path
import shutil
from datetime import datetime, timezone
from unittest.mock import Mock
import requests
import urllib.request
os.environ['PHASE14_PREVIEW_SKIP_ONBOARDING'] = '1'

def offline(*args, **kwargs):
    raise RuntimeError('UI regression tests must remain offline')
requests.Session.request = offline
urllib.request.urlopen = offline
local = Path(os.environ['LOCALAPPDATA']) / 'ED-Frame'
local.mkdir(parents=True, exist_ok=True)
journal = local / 'journal-fixture'
journal.mkdir()
shutil.copyfile('tests/fixtures/smoke_journal.ndjson', journal / 'Journal.2026-08-23T170000.01.log')
os.environ['ED_FRAME_JOURNAL_DIR'] = str(journal)
(local / 'phase14_graphics.json').write_text(json.dumps({
    'renderer_mode': 'software', 'onboarding_complete': True,
    'journal_auto': False, 'background_mode': False, 'ui_scale': 1.15,
    'edframe_catalog_enabled': False,
}), encoding='utf-8')
(local / 'eddn_config.json').write_text(json.dumps({
    'consent': False, 'upload_enabled': False, 'listener_enabled': False,
}), encoding='utf-8')
import phase14_main as main
from PySide6.QtCore import QPointF, QLocale
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlEngine, QQmlExpression

class TestApplication(main.QApplication):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        font_dir = Path(os.environ.get('WINDIR', '')) / 'Fonts'
        for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisym.ttf', 'SegUIVar.ttf', 'consola.ttf'):
            if (font_dir / name).is_file():
                QFontDatabase.addApplicationFont(str(font_dir / name))
main.QApplication = TestApplication

def evaluate(obj, source):
    expr = QQmlExpression(QQmlEngine.contextForObject(obj), obj, source)
    value, _undefined = expr.evaluate()
    assert not expr.hasError(), expr.error().toString()
    return value

def setup(runner, language, width, height):
    QLocale.setDefault(QLocale(language))
    runner.controller.setInterfaceLanguage(language)
    runner.window.resize(width, height)
    runner.window.setProperty('navCommoditiesOpen', False)
    return True

def diagnostic_layout(runner):
    scroll = runner._find('qa-diagnostics-scroll')
    assert scroll.height() > 100
    journal = runner._find('qa-journal-pipeline')
    log = runner._find('qa-diagnostic-log')
    assert journal.height() > 350 and log.height() >= 320
    grid = journal.parentItem()
    assert min(journal.width(), log.width()) > grid.width() / 3
    assert runner._find('qa-interface-activity').height() >= 250
    labels = [str(o.property('text') or '') for o in runner._find('qa-page-diagnostics').findChildren(main.QObject)]
    assert not any('%1' in text for text in labels)
    evaluate(scroll, 'contentItem.contentY = Math.max(0, contentHeight - availableHeight)')
    return True

def diagnostic_bottom(runner):
    scroll = runner._find('qa-diagnostics-scroll')
    activity = runner._find('qa-interface-activity')
    top = activity.mapToItem(scroll, QPointF(0, 0)).y()
    assert top >= -1 and top + activity.height() <= scroll.height() + 1
    return True

def mining_caption(runner):
    button = runner._find('qa-mining-refresh')
    caption = button.property('contentItem')
    assert caption.property('contentWidth') <= caption.width() + 1
    return True

def populated_mining(runner):
    from ed_companion.navigation.mining_planner import plan_mining_routes
    now = datetime.now(timezone.utc)
    date = now.isoformat()
    candidates = [dict(system='HIP 32145', ring='HIP 32145 4 A Ring', distanceLy=62.3,
        coordinates=[62.3,0,0], targetMatch='HOTSPOT', targetMatchName='HOTSPOT',
        ringTypeName='Metallic', reserveLevel='PristineResources', reserveName='Pristine',
        confirmationStatus='RECENTLY CONFIRMED', evidence='LIVE_REPORTED', observedAt=date)]
    markets = [dict(system='HIP 32145', station='Conklin Landing', commodity='platinum',
        sellPrice=285200, demand=18000, landingPadSize='L', stationType='Orbis',
        distanceLs=9, source='UI regression fixture', observedAt=date)]
    powers = [dict(system='HIP 32145', power='Aisling Duval', controllingPower='Aisling Duval',
        powerState='Stronghold', observedAt=date)]
    rows = plan_mining_routes(candidates, 'Platinum', 'POWERPLAY MERITS',
        min_demand=5000, max_demand=500000, max_market_age_hours=1, landing_pad='LARGE',
        power='Aisling Duval', power_goal='REINFORCE', markets=markets, powerplay_systems=powers, now=now)
    assert len(rows) == 1
    controller = runner.controller
    controller.miningPlanRoutes = Mock(return_value=rows)
    controller.refreshMiningMarkets = Mock()
    controller._start_network_worker = Mock(return_value=True)
    page = runner._find('qa-page-mining-finder')
    page.setProperty('resultRows', rows)
    evaluate(page, "powerOverride='Aisling Duval'; appliedPower='Aisling Duval'; searchRevision=1; verifiedSearchRevision=1; searchGoalExpanded=false")
    controller.miningVerificationChanged.emit()
    return True

def mining_details(runner):
    refresh = runner._find('qa-mining-refresh')
    assert refresh.x() + refresh.width() <= refresh.parentItem().width() + 1, ('refresh outside status bar', refresh.x(), refresh.width(), refresh.parentItem().width())
    for name in ('qa-mining-copy-mine', 'qa-mining-copy-sell'):
        button = runner._find(name)
        caption = button.property('contentItem')
        assert caption.property('contentWidth') <= caption.width() + 1
    scroll = runner._find('qa-mining-route-reasons-scroll')
    source = runner._find('qa-mining-powerplay-source')
    assert source.property('text') and source.height() >= source.property('contentHeight')
    evaluate(scroll, 'contentItem.contentY = Math.max(0, contentHeight - availableHeight)')
    return True

def mining_source_reachable(runner):
    scroll = runner._find('qa-mining-route-reasons-scroll')
    source = runner._find('qa-mining-powerplay-source')
    top = source.mapToItem(scroll, QPointF(0, 0)).y()
    assert top >= -1 and top + source.height() <= scroll.height() + 1
    return True

def open_commodities(runner):
    if not runner._page(15, 'qa-page-nav'):
        return False
    runner.window.setProperty('navCommoditiesOpen', True)
    return runner._find('commodityFinder') is not None

def catalog_and_filters(runner):
    controller = runner.controller
    controller._launch_commodity_request = Mock()
    controller._commodity_request = None
    controller._commodity_catalog = [
        {'id':'gold', 'name':'Gold', 'category':'Metals'},
        {'id':'lithiumhydroxide', 'name':'Lithium Hydroxide', 'category':'Minerals'},
        {'id':'fujintea', 'name':'Fujin Tea', 'category':'Rare Goods', 'tradeCategory':'Foods', 'rare':True},
    ]
    controller._commodity_rows = []
    controller._commodity_generation = controller._profile_generation
    controller.commoditiesChanged.emit()
    finder = runner._find('commodityFinder')
    category = runner._find('commodityCategory')
    keys = finder.property('categories').toVariant()
    category.setProperty('currentIndex', keys.index('Rare Goods'))
    assert evaluate(category, 'currentValue') == 'Rare Goods', 'Rare Goods category key changed'
    assert finder.property('choices').toVariant()[0]['id'] == 'ALL_RARE_GOODS', 'Rare Goods aggregate choice missing'
    category.setProperty('currentIndex', keys.index('Metals'))
    assert evaluate(category, 'currentValue') == 'Metals', 'Metals category key changed'
    runner._find('commodityDirection').setProperty('currentIndex', 1)
    runner._find('commodityRadius').setProperty('currentIndex', 3)
    runner._find('commodityPad').setProperty('currentIndex', 3)
    runner._find('commodityAge').setProperty('currentIndex', 3)
    runner._find('commodityQuantity').setProperty('value', 750)
    assert runner._find('commodityFind').property('enabled'), 'Search button disabled in idle fixture'
    runner._find('commodityFind').clicked.emit()
    kind, params = controller._launch_commodity_request.call_args.args
    assert kind == 'offers', ('request kind', kind)
    assert (params['commodity'], params['direction'], params['radius'], params['quantity'],
            params['age_hours'], params['pad'], params['exclude_carriers']) == ('gold','SELL',250,750,72,'L',False), params
    carriers = runner._find('commodityExcludeCarriers')
    assert not carriers.property('checked'), 'Carrier offers excluded by default'
    carriers.setProperty('checked', True)
    runner._find('commodityFind').clicked.emit()
    assert controller._launch_commodity_request.call_args.args[1]['exclude_carriers'] is True
    runner._find('commodityDirection').setProperty('currentIndex', 0)
    assert runner._find('commodityCarrierHint').isVisible(), 'Excluded-carrier purchase hint missing'
    carriers.setProperty('checked', False)
    assert not runner._find('commodityCarrierHint').isVisible()
    category.setProperty('currentIndex', keys.index('Minerals'))
    runner._find('commodityFind').clicked.emit()
    params = controller._launch_commodity_request.call_args.args[1]
    assert (params['commodity'], params['direction'], params['exclude_carriers']) == ('lithiumhydroxide','BUY',False), params
    radius = runner._find('commodityRadius')
    radius.setProperty('currentIndex', 7)
    assert runner._find('commodityUnlimitedHint').isVisible(), 'Unlimited search explanation missing'
    runner._find('commodityFind').clicked.emit()
    params = controller._launch_commodity_request.call_args.args[1]
    assert params['radius'] == 0 and params['region']['radiusLy'] is None, params
    radius.setProperty('currentIndex', 6)
    runner._find('commodityFind').clicked.emit()
    params = controller._launch_commodity_request.call_args.args[1]
    assert params['radius'] == 2000 and params['region']['radiusLy'] == 2000, params
    assert not runner._find('commodityUnlimitedHint').isVisible()
    assert runner._find('commodityEmptyState').isVisible(), ('empty state hidden', controller.commodityBusy, controller.commodityRows)
    origin = runner._find('commodityOrigin')
    sorting = runner._find('commoditySort')
    before = controller._launch_commodity_request.call_count
    origin.setProperty('text', 'Cubeo')
    sorting.setProperty('currentIndex', 1)
    assert controller._launch_commodity_request.call_count == before, 'Typing or sorting triggered a server request'
    runner._find('commodityFind').clicked.emit()
    params = controller._launch_commodity_request.call_args.args[1]
    assert (params['origin_system'], params['origin_mode'], params['sort_by']) == ('Cubeo','MANUAL','DISTANCE'), params
    assert params['region'] is None, 'Manual system should resolve in worker'
    runner._find('commodityUseJournal').clicked.emit()
    assert origin.property('text') == ''
    assert controller._launch_commodity_request.call_count == before + 1, 'Current-system button triggered a request'
    carriers.setProperty('checked', True)
    runner._find('commodityFind').clicked.emit()
    params = controller._launch_commodity_request.call_args.args[1]
    controller._commodity_request = dict(id='empty-fixture', kind='offers', params=params,
        generation=controller._profile_generation, system=controller._state.get('system',''))
    controller._finish_commodities(dict(id='empty-fixture', generation=controller._profile_generation,
        success=True, payload=dict(results=[], hasMore=False)))
    assert runner._find('commoditySearchFilters').isVisible()
    assert runner._find('commodityIncludeCarriers').isVisible()
    assert runner._find('commodityReduceQuantity').isVisible()
    before = controller._launch_commodity_request.call_count
    runner._find('commodityIncludeCarriers').clicked.emit()
    assert controller._launch_commodity_request.call_count == before + 1
    assert controller._launch_commodity_request.call_args.args[1]['exclude_carriers'] is False
    assert controller.commodityLastSearch['excludeCarriers'] is True, 'Displayed filters changed before completing a search'
    runner._find('commoditySearch').setProperty('text', 'no-such-commodity')
    return True

def no_matching_commodity(runner):
    assert not runner._find('commodityFind').property('enabled')
    assert not runner._find('commodityFinder').property('choices').toVariant()
    before = runner.controller._launch_commodity_request.call_count
    runner._find('commodityIncludeCarriers').clicked.emit()
    assert runner.controller._launch_commodity_request.call_count == before
    runner._find('commoditySearch').setProperty('text', '')
    return True

def populated_offers(runner):
    controller = runner.controller
    controller._commodity_last_search = {**controller._commodity_last_search, 'count':3}
    controller._commodity_rows = [{
        'commodity':'gold', 'station':'A long station name with several words for wrapping',
        'system':'A distant system with a deliberately long name', 'direction':'SELL',
        'price':66957, 'quantity':17997, 'distanceLy':35.8,
        'distanceToArrivalLs':684, 'landingPadSize':'L', 'ageHours':0.2,
        'source':'UI regression fixture',
    }]
    for symbol in ['lithiumhydroxide', 'modularterminals']:
        controller._commodity_rows.append({
            **controller._commodity_rows[0], 'commodity':symbol,
            'station':'TEST-01 · Fleet Carrier', 'fleetCarrier':True,
            'direction':'BUY',
        })
    controller.commoditiesChanged.emit()
    assert len(controller.commodityRows) == 3, 'Carrier commodity rows lost during display projection'
    assert controller.commodityRows[1]['commodityName'] == 'Lithium Hydroxide'
    assert controller.commodityRows[1]['carrierWarning'] is True
    return True

def check_offer_layout(runner):
    offers = runner._find('commodityOffers')
    viewport = runner._find('commodityFilterViewport')
    button = runner._find('commodityFind')
    assert button.isVisible()
    parent = button.parentItem()
    while parent is not None:
        assert parent is not viewport, 'Search button scrolls away with the filters'
        parent = parent.parentItem()
    button_bottom = button.mapToItem(runner.window.contentItem(), QPointF(0,button.height())).y()
    assert button_bottom < runner.window.height(), 'Search button is outside the usable window'
    assert offers.height() > 45 and offers.property('count') == 3
    assert not runner._find('commodityEmptyState').isVisible()
    row = offers.property('currentItem')
    assert row is not None and row.width() <= offers.width() + 1
    labels = [o for o in row.findChildren(main.QObject) if o.inherits('QQuickText')]
    assert any('CR/T' in str(o.property('text')) for o in labels)
    for label in labels:
        assert label.property('contentHeight') <= label.height() + 1
        assert label.property('contentWidth') <= label.width() + 1
    return True

original_init = main.SmokeTestRunner.__init__
def init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    self.steps = [('startup', lambda: self.controller._journal_state_ready)]
    for language, width, height in [('en',1920,1080), ('de',1120,700), ('fr',1366,768)]:
        prefix = language + '-'
        self.steps.extend([
            (prefix+'setup', lambda l=language,w=width,h=height: setup(self,l,w,h)),
            (prefix+'diagnostics', lambda: self._page(7,'qa-page-diagnostics')),
            (prefix+'diagnostic-layout', lambda: diagnostic_layout(self)),
            (prefix+'diagnostic-bottom', lambda: diagnostic_bottom(self)),
            (prefix+'mining', lambda: self._page(12,'qa-page-mining-finder')),
            (prefix+'mining-caption', lambda: mining_caption(self)),
            (prefix+'mining-fixture', lambda: populated_mining(self)),
            (prefix+'mining-details', lambda: mining_details(self)),
            (prefix+'mining-source', lambda: mining_source_reachable(self)),
            (prefix+'commodities', lambda: open_commodities(self)),
            (prefix+'filters', lambda: catalog_and_filters(self)),
            (prefix+'no-match', lambda: no_matching_commodity(self)),
            (prefix+'offer-fixture', lambda: populated_offers(self)),
            (prefix+'offer-layout', lambda: check_offer_layout(self)),
        ])
main.SmokeTestRunner.__init__ = init
raise SystemExit(main.run())
'''


class QmlUiQualityTests(unittest.TestCase):
    def test_small_windows_scroll_and_preserve_search_filter_values(self):
        completed, report = _run_smoke(
            {"PHASE14_SMOKE_ASYNC_PAGES": "1"}, script=SCRIPT,
        )
        self.assertIsNotNone(report, completed.stdout + completed.stderr)
        self.assertEqual(report["status"], "PASS", json.dumps(report, ensure_ascii=False))
        self.assertEqual(completed.returncode, 0, completed.stderr)
