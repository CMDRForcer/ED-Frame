"""Isolated offscreen commodity view QA with explicitly simulated rows."""
import sys
from pathlib import Path
from PySide6.QtQuick import QQuickWindow
from PySide6.QtCore import QObject, Property, Slot, QTimer, QUrl, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication, QFontDatabase, QFont
from PySide6.QtQml import QQmlApplicationEngine

root = Path(__file__).resolve().parents[1]
errors = []
def message(kind, context, text):
    if "Error" in text or "Unable" in text or "binding loop" in text.lower() or "recursive rearrange" in text.lower():
        errors.append(text)
    print(text, file=sys.stderr)
qInstallMessageHandler(message)
app = QGuiApplication(sys.argv)
QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
app.setFont(QFont("Segoe UI", 10))
class Fake(QObject):
    @Property("QVariantList", constant=True)
    def commodityCatalog(self):
        return [{"id":"gold","name":"Gold","category":"Metals"},
                {"id":"water","name":"Water","category":"Chemicals"},
                {"id":"fujintea","name":"Fujin Tea","category":"Rare Goods","tradeCategory":"Foods","rare":True}]
    @Property("QVariantList", constant=True)
    def commodityRows(self):
        return [dict(station="Buchli City",system="Mildeptu",direction="SELL",price=66957,
                     quantity=17997,distanceLy=35.8,distanceToArrivalLs=684,
                     landingPadSize="L",ageHours=0.2,source="eddn",
                     accessTone="CONFIRMED",accessReason="No known permit requirement"),
                dict(station="Permit station",system="Sol",direction="BUY",price=4434,
                     quantity=179,distanceLy=0,distanceToArrivalLs=None,
                     landingPadSize="L",ageHours=1,source="eddn",fleetCarrier=True,
                     accessTone="LOCKED",accessReason="Sol permit missing",knownProhibited=True)]
    @Property(bool, constant=True)
    def commodityBusy(self): return False
    @Property(str, constant=True)
    def commodityStatus(self): return "SIMULATED PREVIEW · 2 offers · around Sol"
    @Slot()
    def loadCommodityCatalog(self): pass
    @Slot()
    def refreshCommodityCatalog(self): pass
    @Slot(str)
    def copySystem(self, value): pass
    @Slot(str,str,int,int,int,str,bool)
    def searchCommodities(self, *args): pass
fake=Fake(); engine=QQmlApplicationEngine()
engine.rootContext().setContextProperty("cockpit",fake)
engine.loadData('''
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "qml/pages"
ApplicationWindow {
 id: win; width: 1280; height: 800; visible: true; color: "#1e2634"
 property color panelRaised: "#28344a"
 property color cardRaised: "#28344a"
 property color borderTone: "#3c4c65"
 property color textPrimary: "#eff5ff"
 property color textSecondary: "#a5b8cc"
 property color textDisabled: "#64788e"
 property color accentSecondary: "#54d7ed"
 property color accent: "#54d7ed"
 property color active: "#344861"
 property color hover: "#304059"
 property color inputBackground: "#222b3b"
 property color orange: "#ffd276"
 property color error: "#ff6684"
 function t(key, fallback) { return fallback }
 ColumnLayout {
  anchors.fill: parent; anchors.margins: 24
  Label { text: "COMMODITIES · ED-FRAME"; font.pixelSize: 22; color: win.accent }
  CommoditiesSection { Layout.fillWidth: true; Layout.fillHeight: true; appWindow: win }
 }
}
'''.encode("utf-8"), QUrl.fromLocalFile(str(root / "commodity-preview.qml")))
if not engine.rootObjects(): sys.exit(1)
window=engine.rootObjects()[0]
def narrow():
    try:
        hint = window.findChild(QObject, "commodityHint")
        print("hint geometry", hint.property("y"), hint.property("height"), hint.property("contentHeight"))
        if hint.property("height") < hint.property("contentHeight"):
            errors.append("Hint text clipped at narrow width")
        if not window.grabWindow().save(str(root / "reports/commodities-narrow.png")):
            errors.append("Unable to save narrow preview")
    finally: app.exit(1 if errors else 0)
def wide():
    finder = window.findChild(QObject, "commodityFinder")
    category = window.findChild(QObject, "commodityCategory")
    search = window.findChild(QObject, "commoditySearch")
    if window.width() >= 1000 and search.property("x") <= category.property("x"):
        errors.append("Search field must be right of category")
    keys = finder.property("categories").toVariant()
    for key in ("Rare Goods", "Foods"):
        category.setProperty("currentIndex", keys.index(key))
        selected = finder.property("choices").toVariant()
        if key == "Rare Goods":
            if selected[0]["id"] != "ALL_RARE_GOODS":
                errors.append("Rare goods ALL choice missing")
            selected = selected[1:]
        if len(selected) != 1 or selected[0]["id"] != "fujintea":
            errors.append("Rare goods not selectable through " + key)
    category.setProperty("currentIndex", 0)
    if not window.grabWindow().save(str(root / "reports/commodities-preview.png")):
        errors.append("Unable to save preview")
    window.resize(650,850); QTimer.singleShot(300,narrow)
QTimer.singleShot(600,wide)
code = app.exec()
engine.rootContext().setContextProperty("cockpit", fake)
del engine
sys.exit(code)
