"""Render the real catalog component with labelled example data, never HTTP."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
if os.name == 'nt':
    os.environ.setdefault('QT_QPA_FONTDIR', 'C:/Windows/Fonts')
from PySide6.QtCore import QTimer, QUrl, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication, QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
QQuickStyle.setStyle('Basic')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--language', choices=('en', 'de'), default='en')
    parser.add_argument('--unknown', action='store_true')
    parser.add_argument('--width', type=int, default=1600)
    args = parser.parse_args()
    translations = json.loads((ROOT / 'ed_data/i18n' / (args.language+'.json')).read_text(encoding='utf-8'))
    stats = {} if args.unknown else {
        'systems':251321,'stations':41977,'markets':6300827,'sites':1150095,
        'freshMarkets1h':114863,'freshMarkets24h':1508939,'freshMarketPercent24h':23.95,
        'olderMarkets24h':4791888,'siteHotspotPercent':10,'yieldSamples':51,
        'measuredSites':2,'measuredCommodities':13,'moduleOffers':9155136,
        'outfittingStations':18981,'pricedModuleOffers':925515,'catalogModules':961,
        'shipOffers':342395,'shipyardStations':15286,'pricedShipOffers':5,'catalogShips':48,
        'commodities':412,'stateBgsSnapshots':49444,'stateSightings':125,
        'collector24hMessages':1762552,'collector24hUsedPercent':66.8,'collector24hErrors':0,
        'collector24hProjectedRows':8000000,'collector24hUsedMessages':1173385,
        'collector24hIgnoredMessages':589167,'generatedAt':'2026-10-10T06:38:17Z',
        'marketDetailPercent':99.8,'stationTypePercent':99.1,'stationLandingPadPercent':96.3,
        'stationServicesPercent':98.8,'marketCoordinatePercent':99.6,'siteCoordinatePercent':98.4,
        'localMarkets':150000,'localOfferStations':5000,
    }
    activity = {'active':1,'queued':2,'catalogRequests60s':3,'nextCatalogSync':'2026-10-10T06:48:17Z',
                'cpuWorkerLimit':2,'computeActive':1,'computeQueued':0}
    component_url = QUrl.fromLocalFile(str(ROOT / 'qml/components')).toString()
    qml = '''import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "%s" as Panels
ApplicationWindow {
  visible: true; width: %d; height: 1250; color: "#28354b"
  property var translations: %s
  function t(key, fallback) { return translations[key] || fallback; }
  ScrollView {
    id: scroller
    anchors.fill: parent
    ColumnLayout {
      width: scroller.availableWidth; spacing: 12
      Label { text: "LOCAL UI PREVIEW · EXAMPLE SNAPSHOT"; color: "#ffd178"; padding: 12 }
      Panels.CatalogServerOverview {
        objectName: "overview"; Layout.fillWidth: true
        stats: (%s); activity: (%s); lastSuccess: "2026-10-10T06:38:17Z"
        marketSync: "Up to date · retained local market observations"
        offerSync: "Up to date · retained station inventories"
        stateSync: "Up to date · regional public observations"
      }
    }
  }
}''' % (component_url, args.width, json.dumps(translations), json.dumps(stats), json.dumps(activity))
    messages = []
    qInstallMessageHandler(lambda mode, context, message: messages.append(message))
    app = QGuiApplication([])
    app.setFont(QFont('Segoe UI'))
    engine = QQmlApplicationEngine()
    engine.loadData(qml.encode('utf-8'))
    if not engine.rootObjects():
        raise RuntimeError(messages)
    window = engine.rootObjects()[0]
    from PySide6.QtCore import QObject
    details = window.findChild(QObject, 'catalogServerDetails')
    details.setProperty('checked', True)
    def capture():
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if not window.grabWindow().save(str(args.output)):
                raise RuntimeError('Screenshot failed')
            print(json.dumps({'image':str(args.output.resolve()), 'messages':messages}))
        finally:
            app.quit()
    QTimer.singleShot(600, capture)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
