"""Keep unsubmitted finder drafts across real lazy QML page destruction."""
import json
import unittest
import uuid

from tests.test_qml_smoke_load import _run_smoke
from tests.test_qml_ui_quality import SCRIPT as BASE

SCRIPT = BASE[:BASE.index("original_init = main.SmokeTestRunner.__init__")] + r'''
REQUESTS = {"commodity-search", "trade-routes", "station-services"}

def checked(function, runner):
    try:
        return function(runner)
    except AssertionError:
        import traceback
        raise AssertionError(traceback.format_exc()) from None

def edit(runner):
    controller = runner.controller
    controller._commodity_catalog = [
        dict(id="gold", name="Gold", category="Metals"),
        dict(id="water", name="Water", category="Chemicals")]
    controller.commoditiesChanged.emit()
    original = controller._start_network_worker
    controller._start_network_worker = Mock(side_effect=lambda worker, label:
        True if label in REQUESTS else original(worker, label))
    runner.window.setProperty("navCommoditiesOpen", True)
    runner._find("commodityCategory").setProperty("currentIndex", 2)
    # Use keys, rather than relying on the translated category order.
    finder = runner._find("commodityFinder")
    index = finder.property("categories").toVariant().index("Metals")
    runner._find("commodityCategory").setProperty("currentIndex", index)
    runner._find("commoditySearch").setProperty("text", "gol")
    runner._find("commodityOrigin").setProperty("text", "Cubeo")
    runner._find("commodityDirection").setProperty("currentIndex", 1)
    runner._find("commodityRadius").setProperty("currentIndex", 7)
    runner._find("commodityPad").setProperty("currentIndex", 3)
    runner._find("commodityQuantity").setProperty("value", 64)
    runner._find("commodityAge").setProperty("currentIndex", 3)
    runner._find("commoditySort").setProperty("currentIndex", 2)
    runner._find("commodityExcludeCarriers").setProperty("checked", True)
    runner._find("stationServiceChoice").setProperty("currentIndex", 3)
    runner._find("stationServiceRadius").setProperty("currentIndex", 4)
    runner._find("stationServicePad").setProperty("currentIndex", 2)
    runner._find("stationServiceExcludeCarriers").setProperty("checked", False)
    runner.window.setProperty("navCommoditiesOpen", False)
    runner.window.setProperty("navTradeRoutesOpen", True)
    runner._find("tradeRouteOrigin").setProperty("text", "Achenar")
    runner._find("tradeRouteCommodity").setProperty("currentIndex", 1)
    runner._find("tradeRouteCargo").setProperty("value", 127)
    runner._find("tradeRouteBudget").setProperty("text", "5000000000")
    runner._find("tradeRouteRadius").setProperty("currentIndex", 3)
    runner._find("tradeRouteLegDistance").setProperty("currentIndex", 1)
    runner._find("tradeRouteAge").setProperty("currentIndex", 3)
    runner._find("tradeRoutePad").setProperty("currentIndex", 3)
    runner._find("tradeRouteSort").setProperty("currentIndex", 2)
    runner._find("tradeRouteExcludeCarriers").setProperty("checked", True)
    return True

def verify(runner):
    assert runner._find("commodityOrigin").property("text") == "Cubeo"
    assert runner._find("commoditySearch").property("text") == "gol"
    assert evaluate(runner._find("commodityChoice"), "currentValue") == "gold"
    assert evaluate(runner._find("commodityCategory"), "currentValue") == "Metals"
    for name, expected in [("commodityDirection",1),("commodityRadius",7),
            ("commodityPad",3),("commodityAge",3),("commoditySort",2)]:
        assert runner._find(name).property("currentIndex") == expected, name
    assert runner._find("commodityQuantity").property("value") == 64
    assert runner._find("commodityExcludeCarriers").property("checked") is True, 'carrier selection'
    assert evaluate(runner._find("stationServiceChoice"), "currentValue") == "facilitator"
    assert runner._find("stationServiceRadius").property("currentIndex") == 4
    assert runner._find("stationServicePad").property("currentIndex") == 2
    assert runner._find("stationServiceExcludeCarriers").property("checked") is False, 'carrier selection'
    assert runner._find("tradeRouteOrigin").property("text") == "Achenar"
    assert evaluate(runner._find("tradeRouteCommodity"), "currentValue") == "gold"
    assert runner._find("tradeRouteCargo").property("value") == 127
    assert runner._find("tradeRouteBudget").property("text") == "5000000000"
    for name, expected in [("tradeRouteRadius",3),("tradeRouteLegDistance",1),
            ("tradeRouteAge",3),("tradeRoutePad",3),("tradeRouteSort",2)]:
        assert runner._find(name).property("currentIndex") == expected, name
    assert runner._find("tradeRouteExcludeCarriers").property("checked") is True, 'carrier selection'
    assert not any(call.args[1] in REQUESTS for call in
        runner.controller._start_network_worker.call_args_list), "Restoration launched a search"
    return True

def request(runner):
    controller = runner.controller
    controller._edframe_catalog_enabled = True
    runner._find("tradeRouteFind").clicked.emit()
    query = controller._trade_request
    assert query["origin_system"] == "Achenar" and query["commodity"] == "gold"
    assert (query["capacity"],query["budget"],query["radius"],query["leg_distance"],
        query["age_hours"],query["pad"],query["exclude_carriers"],query["sort_by"]) == (
        127,5000000000,250,50,72,"L",True,"DISTANCE")
    controller._finish_trade_routes(dict(query, success=False, error="offline fixture"))
    return True

original_init = main.SmokeTestRunner.__init__
def init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    self.steps = [
        ("startup",lambda:self.controller._journal_state_ready),
        ("setup",lambda:setup(self,"en",1120,700)),
        ("nav",lambda:self._page(15,"qa-page-nav")),
        ("edit",lambda:edit(self)),
        ("unload",lambda:self._page(0,"qa-page-operations")),
        ("restore",lambda:self._page(15,"qa-page-nav")),
        ("verify",lambda:checked(verify,self)),
        ("translate",lambda:setup(self,"de",1120,700)),
        ("unload-de",lambda:self._page(0,"qa-page-operations")),
        ("restore-de",lambda:self._page(15,"qa-page-nav")),
        ("verify-de",lambda:checked(verify,self)),
        ("request",lambda:checked(request,self))]
main.SmokeTestRunner.__init__ = init
raise SystemExit(main.run())
'''

class NavigationFinderStateTests(unittest.TestCase):
    def test_unsubmitted_filters_survive_page_unload_and_language_change(self):
        completed, report = _run_smoke({
            "PHASE14_SMOKE_ASYNC_PAGES": "1",
            "QT_QUICK_BACKEND": "software",
            "ED_FRAME_SINGLE_INSTANCE_NAME": "ED-Frame-finder-drafts-"+uuid.uuid4().hex,
        }, script=SCRIPT, timeout=90)
        self.assertIsNotNone(report, completed.stdout+completed.stderr)
        self.assertEqual(report["status"], "PASS", json.dumps(report, ensure_ascii=False))
        self.assertEqual(completed.returncode, 0, completed.stderr)
