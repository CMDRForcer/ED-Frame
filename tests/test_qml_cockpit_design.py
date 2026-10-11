"""Render the shared design on real lazy pages and without system icon fonts."""
import json
import os
import unittest

from tests.test_qml_smoke_load import _run_smoke
from tests.test_qml_ui_quality import SCRIPT as BASE

SCRIPT = BASE[:BASE.index('original_init = main.SmokeTestRunner.__init__')] + r'''
from PySide6.QtQuick import QQuickItem

def configure(runner, language, width, height, theme='navy'):
    setup(runner, language, width, height)
    runner.controller.setTheme(theme)
    runner.window.setProperty('navTradeRoutesOpen', False)
    runner.window.setProperty('navStationServicesOpen', False)
    runner.window.setProperty('connectionPreviewMode', 0)
    return True

def rendered(runner, name):
    icons = [o for o in runner.window.findChildren(QQuickItem)
        if o.inherits('QQuickImage') and o.isVisible()
        and str(o.property('source').toString()).startswith('data:image/svg+xml;utf8,')]
    # ListView delegates belong to an incubation context, so inspect their
    # actual visual children in QML instead of using QObject ownership.
    assert len(icons) >= 4, ('Missing workspace/action pictograms', len(icons))
    for icon in icons:
        assert evaluate(icon, 'status === Image.Ready'), ('SVG not ready', icon.objectName())
        assert icon.width() > 0 and icon.height() > 0
    ready = evaluate(runner._find('qa-navigation-drag-list'), """(function() {
        var icons = 0;
        function visit(item) {
            if (!item) return;
            if (String(item.objectName).indexOf('nav-icon-') === 0) {
                if (item.children[0].status !== Image.Ready) throw new Error('Navigation SVG not ready');
                icons++;
            }
            for (var child = 0; child < item.children.length; child++) visit(item.children[child]);
        }
        for (var i = 0; i < count; i++) visit(itemAtIndex(i));
        return icons;
    })()""")
    assert ready >= 8, ('Missing navigation pictograms', ready)
    output = os.environ.get('ED_FRAME_DESIGN_CAPTURES', '')
    if output:
        folder = Path(output)
        folder.mkdir(parents=True, exist_ok=True)
        assert runner.window.grabWindow().save(str(folder/(name+'.png')))
    return True

def goods_data(runner):
    runner.controller._commodity_catalog = [dict(id='gold',name='Gold',category='Metals'),
        dict(id='lithiumhydroxide',name='Lithium Hydroxide',category='Minerals')]
    runner.controller._commodity_last_search = dict(system='Sol',radius=None,quantity=1,ageHours=24,pad='ANY',sortBy='PRICE',count=3)
    runner.controller._commodity_generation = runner.controller._profile_generation
    runner.controller._commodity_request = None
    populated_offers(runner)
    caption = str(runner._find('commoditySearchFilters').property('text'))
    assert 'undefined' not in caption, caption
    assert runner.controller.translate('commodities.unlimited','UNLIMITED') in caption, caption
    assert not runner._find('commodityExpandRadius').isVisible()
    return True

def server_data(runner):
    runner.controller._edframe_catalog_stats = dict(
        systems=251321,stations=41977,markets=6300827,sites=1150095,
        freshMarkets1h=114863,freshMarkets24h=1508939,freshMarketPercent24h=23.95,
        olderMarkets24h=4791888,siteHotspotPercent=10,yieldSamples=51,measuredSites=2,
        measuredCommodities=13,moduleOffers=9155136,outfittingStations=18981,
        pricedModuleOffers=925515,catalogModules=961,shipOffers=342395,
        shipyardStations=15286,pricedShipOffers=5,catalogShips=48,commodities=412,
        stateBgsSnapshots=49444,stateSightings=125,collector24hMessages=1762552,
        collector24hUsedPercent=66.8,collector24hErrors=0,collector24hProjectedRows=8000000,
        collector24hUsedMessages=1173385,collector24hIgnoredMessages=589167,
        marketDetailPercent=99.8,stationTypePercent=99.1,stationLandingPadPercent=96.3,
        stationServicesPercent=98.8,marketCoordinatePercent=99.6,siteCoordinatePercent=98.4)
    runner.controller._edframe_catalog_online = True
    runner.controller.connectionChanged.emit()
    runner.window.setProperty('connectionPreviewMode', 3)
    return True

original_init = main.SmokeTestRunner.__init__
def init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    self.steps = [('startup', lambda: self.controller._journal_state_ready)]
    for language, width, height in [('en',1920,1080), ('de',1120,700)]:
        prefix = language + '-'
        self.steps.append((prefix+'setup', lambda l=language,w=width,h=height: configure(self,l,w,h)))
        for label, page, object_name in self.PAGE_STEPS:
            self.steps.extend([
                (prefix+label, lambda p=page,n=object_name:self._page(p,n)),
                (prefix+label+'-render', lambda n=prefix+label:rendered(self,n))])
        self.steps.extend([
            (prefix+'mining-open', lambda:self._page(12,'qa-page-mining-finder')),
            (prefix+'mining-fixture', lambda:populated_mining(self)),
            (prefix+'mining-result-render', lambda n=prefix+'mining-result':rendered(self,n)),
            (prefix+'goods-open', lambda:open_commodities(self)),
            (prefix+'goods-fixture', lambda:goods_data(self)),
            (prefix+'goods-render', lambda n=prefix+'goods':rendered(self,n)),
            (prefix+'server-open', lambda:self._page(6,'qa-page-connections')),
            (prefix+'server-fixture', lambda:server_data(self)),
            (prefix+'server-render', lambda n=prefix+'server':rendered(self,n))])
    for theme in ('arctic_alloy','neon_vector','orbital_dawn','crimson_dark','crimson_light'):
        self.steps.extend([
            (theme+'-setup', lambda t=theme:configure(self,'de',1120,700,t)),
            (theme+'-goods-open', lambda:open_commodities(self)),
            (theme+'-goods-fixture', lambda:goods_data(self)),
            (theme+'-render', lambda t=theme:rendered(self,t))])
main.SmokeTestRunner.__init__ = init
raise SystemExit(main.run())
'''


class CockpitDesignTests(unittest.TestCase):
    def test_pages_and_theme_variants_render_with_local_svg_pictograms(self):
        completed, report = _run_smoke({
            'PHASE14_SMOKE_ASYNC_PAGES': '1', 'QT_QUICK_BACKEND': 'software',
            'ED_FRAME_DESIGN_CAPTURES': os.environ.get('ED_FRAME_DESIGN_CAPTURES',''),
        }, script=SCRIPT, timeout=180)
        self.assertIsNotNone(report, completed.stdout+completed.stderr)
        self.assertEqual(report['status'], 'PASS', json.dumps(report, ensure_ascii=False))
        self.assertEqual(completed.returncode, 0, completed.stderr)
