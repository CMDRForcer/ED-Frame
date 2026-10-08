"""Exercise real QML publication/model behavior, without user data or networking."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock


class MiningResultsStabilityTests(unittest.TestCase):
    def test_real_page_keeps_results_and_viewport_during_background_refresh(self):
        with tempfile.TemporaryDirectory(prefix="ed-frame-mining-ui-") as scratch:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--qml"],
                env={**os.environ, "QT_QPA_PLATFORM": "offscreen",
                     "QT_QUICK_CONTROLS_STYLE": "Basic", "LOCALAPPDATA": scratch},
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


def run_qml():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QObject, QUrl, qInstallMessageHandler
    from PySide6.QtGui import QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtTest import QSignalSpy
    from ed_companion.phase14.controller import CockpitController

    app = QGuiApplication([])
    if os.name == "nt":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("segoeui.ttf", "seguisb.ttf", "consola.ttf"):
            if (fonts / name).is_file():
                QFontDatabase.addApplicationFont(str(fonts / name))
    errors = []
    def qt_message(kind, context, message):
        # Windows offscreen lacks Qt's optional bundled-font directory; load
        # system fonts above. Do not suppress any QML/runtime warnings.
        if not message.startswith("QFontDatabase: Cannot find font directory"):
            errors.append(message)
    qInstallMessageHandler(qt_message)
    engine = QQmlEngine()
    # Exercise the real Python slot, not just a permissive JavaScript stub.
    # Capture worker dispatch without running HTTP, persistence or startup.
    verifier = CockpitController.__new__(CockpitController)
    QObject.__init__(verifier)
    verifier.profile_context = SimpleNamespace(key="qml-stability-fixture")
    verifier._profile_generation = 1
    verifier.mining_catalog_file = Path("unused-mining-fixture.json")
    verifier._known_mining_origin = Mock(return_value={"coordinates": [1, 2, 3]})
    verifier._start_network_worker = Mock(return_value=True)
    engine.rootContext().setContextProperty("productionVerifier", verifier)
    component = QQmlComponent(engine)
    base = Path(__file__).resolve().parents[1] / "qml/pages"
    component.setData(b'''
import QtQuick
Item {
    id: root
    width: 1900; height: 1200
    property int currentPage: 12
    property bool compactSidebar: false
    property bool narrowWorkspace: false
    property font font: Qt.font({family: "Segoe UI"})
    property color cyan: "#3bdcff"
    property color green: "#40ef99"
    property color orange: "#ffbb55"
    property color textPrimary: "#eeeeee"
    property color textSecondary: "#aabbcc"
    property color textDisabled: "#667788"
    property color muted: "#778899"
    property color panelRaised: "#253042"
    property color backgroundSecondary: "#202630"
    property color inputBackground: "#152030"
    property color borderTone: "#334455"
    property color divider: "#334455"
    property color warningBackground: "#453020"
    property color successBackground: "#204530"
    property color active: "#304560"
    property color hover: "#253550"
    property color cardRaised: "#253042"
    property color accent: cyan
    property color accentSecondary: cyan
    property int resultChanges: 0
    property int verifyCalls: 0
    property int planCalls: 0
    property var planArgs: []
    function t(key, fallback) { return fallback }
    function tf(key, fallback, args) {
        for (let i=0; i<args.length; ++i) fallback = fallback.replace("%"+(i+1), args[i])
        return fallback
    }
    QtObject {
        id: cockpit
        signal miningChanged()
        property string system: "Shanteneri"
        property int miningRevision: 1
        property bool miningPlanBusy: false
        property bool miningMarketSyncBusy: false
        property bool miningSyncBusy: false
        property bool miningVerificationBusy: false
        property int miningVerificationCompleted: 0
        property int miningVerificationTotal: 0
        property string miningVerificationStatus: "Ready"
        property string miningMarketSyncStatus: "Ready"
        property string miningCurrentAction: "Ready"
        property var powerplayOverview: ({power: "Aisling Duval"})
        property var miningCacheSummary: ({total: 30})
        property bool edFrameCatalogEnabled: true
        property bool edFrameCatalogBusy: false
        property bool edFrameCatalogSyncBusy: false
        property bool edFrameCatalogOnline: true
        property string edFrameCatalogStatus: "Ready"
        property string edFrameCatalogSyncStatus: "Ready"
        property string edFrameCatalogLastSuccess: ""
        property var edFrameCatalogStats: ({markets: 30})
        property var rows: []
        property bool newQueryReady: false
        function miningPlanRoutes() {
            root.planCalls += 1
            root.planArgs = Array.prototype.slice.call(arguments)
            return arguments[0] === "Shanteneri" || newQueryReady
                    ? JSON.parse(JSON.stringify(rows)) : []
        }
        function miningMarketDiagnostics() { return {cacheMatches: true, originKnown: true, eligible: 30, total: 30, summary: "30 markets"} }
        function miningLoadoutReadiness() { return {ready: true} }
        function miningCommodityFiltersForMethod() { return ["Platinum"] }
        function miningRingFiltersForCommodity() { return ["ANY RING"] }
        function miningSystemSuggestions() { return [] }
        function refreshMiningMarkets() { miningMarketSyncBusy = true }
        function refreshMiningFinder() {}
        function copySystem() {}
        function verifyMiningRoutes(routes, start, commodity, maxAge, demand, pad) {
            productionVerifier.verifyMiningRoutes(routes, start, commodity, maxAge, demand, pad)
            root.verifyCalls += 1
        }
    }
    MiningFinderPage {
        id: page
        appWindow: root
        sidebarWidth: 0
        onResultRowsChanged: root.resultChanges += 1
    }
    function makeRows() {
        let rows = []
        for (let i=0; i<30; ++i) rows.push({
            system: "Mine"+i, ring: "Mine"+i+" A Ring", systemAddress: i+1,
            ringTypeName: "Metallic", reserveName: "Pristine", bodyId: 1,
            station: "Station", sellSystem: "Sale", selectedCommodity: "platinum",
            selectedCommodityName: "Platinum", marketKnown: true, targetMatch: true,
            targetMatchName: "HOTSPOT CONFIRMED", distanceLy: 10+i, mineToSellLy: 5,
            sellPrice: 300000, demand: 10000, marketAgeSeconds: 600,
            profitStars: "*****", meritStars: "-", dataStars: "***",
            marketQualityStatus: "CURRENT", meritStatus: "NOT ELIGIBLE",
            freshnessStatus: "RECENT", verificationGroupLabel: "POWERPLAY VERIFIED",
            communityOverlapReports: [{commodity: "platinum", reportedResTypes: ["HAZARDOUS"], reportedOverlap: "Haz @80%"}]
        })
        return rows
    }
    function start() {
        cockpit.rows = makeRows()
        page.startSystem = "Shanteneri"
        page.optimization = "PLATINUM + RES"
        page.overlapResLevel = "HAZARDOUS"
        page.executeSearch()
    }
    function refresh(busy) {
        cockpit.miningPlanBusy = busy
        cockpit.miningMarketSyncBusy = busy
        cockpit.miningRevision += 1
        cockpit.miningChanged()
    }
    function finishSearch() { cockpit.miningMarketSyncBusy = false; cockpit.miningChanged() }
    function updatePrice() {
        let rows = JSON.parse(JSON.stringify(cockpit.rows))
        rows[12].sellPrice = 321000
        cockpit.rows = rows
        refresh(false)
    }
    function reorder() {
        let rows = JSON.parse(JSON.stringify(cockpit.rows))
        rows.unshift(rows.pop())
        cockpit.rows = rows
        refresh(false)
    }
    function removeSelected() {
        cockpit.rows = cockpit.rows.filter(function(row) { return row.system !== "Mine7" })
        refresh(false)
    }
    function newSearch() { page.startSystem = "Other"; page.executeSearch() }
    function zeroMatches() { cockpit.rows = []; refresh(false) }
    function burst() { for (let i=0; i<20; ++i) refresh(false) }
    function merits() { page.optimization = "POWERPLAY MERITS"; page.executeSearch() }
    function changeGroup() {
        let rows = JSON.parse(JSON.stringify(cockpit.rows))
        rows[12].verificationGroupLabel = "POWERPLAY DATA MISSING"
        cockpit.rows = rows
        refresh(false)
    }
    function select() { page.selectRoute(page.resultRows[7]) }
    function selectedSystem() { return String(page.bestRoute.system || "") }
    function scroll() {
        const list = findList(page)
        list.positionViewAtIndex(11, ListView.Beginning)
        list.contentY += 13
    }
    function findList(item) {
        if (item.objectName === "qa-mining-routes") return item
        for (let i=0; i<item.children.length; ++i) {
            let found = findList(item.children[i])
            if (found) return found
        }
        return null
    }
    function anchorOffset() {
        const list = findList(page)
        list.forceLayout()
        for (let i=0; i<list.count; ++i) {
            let item = list.itemAtIndex(i)
            if (item && item.modelData.system === "Mine12") return list.contentY-item.y
        }
        return -9999
    }
    function anchorItem() {
        const list = findList(page)
        for (let i=0; i<list.count; ++i) {
            let item = list.itemAtIndex(i)
            if (item && item.modelData.system === "Mine12") return item
        }
        return null
    }
}
''', QUrl.fromLocalFile(str(base / "test.qml")))
    obj = component.create()
    assert obj is not None, component.errors()

    def settle():
        for _ in range(12):
            app.processEvents()

    def visible(name):
        return obj.findChild(QObject, name).property("visible")

    settle()
    assert visible("qa-mining-empty")
    obj.start()
    settle()
    assert obj.property("verifyCalls") == 0, "verification started before the regional search finished"
    verifier._start_network_worker.assert_not_called()
    obj.finishSearch()
    settle()
    assert obj.property("verifyCalls") == 1, "completed search was not verified"
    verifier._start_network_worker.assert_called_once()
    assert verifier._mining_verification_busy, "real controller did not start verification"
    request = verifier._active_mining_verification_request
    assert request["commodity"] == "platinum" and request["minDemand"] == 5000
    assert request["maxMarketAgeHours"] == 1 and request["landingPad"] == "LARGE"
    assert len(request["targets"]) == 30, "copied QML routes did not reach Python"
    route_model = obj.findChild(QObject, "qa-stable-mining-route-model")
    model_resets = QSignalSpy(route_model.modelReset)
    assert obj.property("planArgs").toVariant()[7] == "PLATINUM + RES: HAZARDOUS"
    assert visible("qa-mining-results") and not visible("qa-mining-empty")
    obj.select()
    settle()
    obj.scroll()
    settle()
    assert abs(obj.anchorOffset() - 13) < 1, obj.anchorOffset()
    anchor = obj.anchorItem()
    changes = obj.property("resultChanges")
    verifies = obj.property("verifyCalls")
    for busy in (True, False, True, False):
        obj.refresh(busy)
        settle()
        assert visible("qa-mining-results") and not visible("qa-mining-empty")
        assert obj.property("resultChanges") == changes
        assert obj.selectedSystem() == "Mine7"
        assert abs(obj.anchorOffset() - 13) < 1, obj.anchorOffset()
        assert obj.anchorItem() == anchor, "unchanged delegate was recreated"
    assert obj.property("verifyCalls") == verifies, "verification loop restarted"
    calls = obj.property("planCalls")
    obj.burst()
    settle()
    assert obj.property("planCalls") == calls + 1, "notifications were not coalesced"
    obj.updatePrice()
    settle()
    assert obj.property("resultChanges") == changes + 1
    assert obj.selectedSystem() == "Mine7"
    assert abs(obj.anchorOffset() - 13) < 1, obj.anchorOffset()
    assert obj.anchorItem() == anchor, "updated delegate was recreated"
    assert anchor.property("modelData")["sellPrice"] == 321000
    obj.reorder()
    settle()
    assert obj.selectedSystem() == "Mine7"
    assert abs(obj.anchorOffset() - 13) < 1, obj.anchorOffset()
    assert model_resets.count() == 0, "route model was reset instead of updated in place"
    obj.removeSelected()
    settle()
    assert obj.selectedSystem() != "Mine7"
    assert visible("qa-mining-results") and not visible("qa-mining-empty")
    obj.newSearch()
    settle()
    assert visible("qa-mining-empty") and not visible("qa-mining-results")
    assert obj.property("verifyCalls") == verifies, "old-query routes were verified for new query"
    obj.start()
    settle()
    obj.finishSearch()
    settle()
    obj.merits()
    settle()
    obj.finishSearch()
    settle()
    obj.select()
    settle()
    obj.scroll()
    settle()
    assert abs(obj.anchorOffset() - 13) < 1, obj.anchorOffset()
    obj.changeGroup()
    settle()
    assert abs(obj.anchorOffset() - 13) < 1, obj.anchorOffset()
    assert visible("qa-mining-results") and not visible("qa-mining-empty")
    # A completed, genuinely empty same-query result must not stay stale.
    obj.start()
    settle()
    obj.finishSearch()
    settle()
    obj.zeroMatches()
    settle()
    assert visible("qa-mining-empty") and not visible("qa-mining-results")
    assert not errors, errors
    del obj, component, engine


if __name__ == "__main__":
    if "--qml" in sys.argv:
        run_qml()
    else:
        unittest.main()
