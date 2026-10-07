import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: overview
    readonly property var window: ApplicationWindow.window
    property var stats: ({})
    property string lastSuccess: ""
    property string marketSync: ""
    property string offerSync: ""
    property string stateSync: ""
    property color surface: "#202c3a"
    property color foreground: "#e1ebf4"
    property color secondary: "#a5b7ca"
    property color accent: "#50d5ef"
    property color warning: "#ffd178"
    spacing: 14

    function value(key) {
        const n = stats[key]
        return n === undefined || n === null || !isFinite(Number(n)) ? -1 : Number(n)
    }
    function number(key) {
        const n = value(key)
        return n < 0 ? "—" : n.toLocaleString(Qt.locale(), "f", 0)
    }
    function percent(key) {
        const n = value(key)
        return n < 0 ? "—" : n.toLocaleString(Qt.locale(), "f", 1) + "%"
    }
    function date(text) {
        const d = new Date(text)
        return !text || isNaN(d.getTime()) ? "—" : Qt.formatDateTime(d, "dd.MM.yyyy HH:mm:ss") + window.t("connections.catalog_overview_0", " (local)")
    }
    readonly property var cards: [
        {title: window.t("connections.catalog_overview_1", "SYSTEMS & STATIONS"), value: number("stations"),
         detail: window.t("connections.catalog_overview_2", "stations · ") + number("systems") + window.t("connections.catalog_overview_3", " systems"), hint: window.t("connections.catalog_overview_4", "Public geography and station metadata")},
        {title: window.t("connections.catalog_overview_5", "COMMODITY MARKETS"), value: number("markets"),
         detail: number("freshMarkets1h") + window.t("connections.catalog_overview_6", " updated ≤ 1 h · ") + number("freshMarkets24h") + window.t("connections.catalog_overview_7", " ≤ 24 h"),
         hint: window.t("connections.catalog_overview_8", "Commodity rows, not stations · ") + number("commodities") + window.t("connections.catalog_overview_9", " commodities")},
        {title: window.t("connections.catalog_overview_10", "MINING EVIDENCE"), value: number("sites"),
         detail: percent("siteHotspotPercent") + window.t("connections.catalog_overview_11", " with hotspot evidence · ") + number("yieldSamples") + window.t("connections.catalog_overview_12", " yield samples"),
         hint: window.t("connections.catalog_overview_13", "Measured: ") + number("measuredSites") + window.t("connections.catalog_overview_14", " sites / ") + number("measuredCommodities") + window.t("connections.catalog_overview_9", " commodities")},
        {title: window.t("connections.catalog_overview_42", "OUTFITTING"), value: number("moduleOffers"),
         detail: window.t("connections.catalog_overview_15", "offers at ") + number("outfittingStations") + window.t("connections.catalog_overview_16", " stations · ") + number("pricedModuleOffers") + window.t("connections.catalog_overview_17", " priced"),
         hint: number("catalogModules") + window.t("connections.catalog_overview_18", " module definitions · availability ≠ exact price")},
        {title: window.t("connections.catalog_overview_43", "SHIPYARDS"), value: number("shipOffers"),
         detail: window.t("connections.catalog_overview_15", "offers at ") + number("shipyardStations") + window.t("connections.catalog_overview_16", " stations · ") + number("pricedShipOffers") + window.t("connections.catalog_overview_17", " priced"),
         hint: number("catalogShips") + window.t("connections.catalog_overview_19", " hulls · reference prices are separate from observations")},
        {title: window.t("signals.bgs", "BGS CANDIDATES"), value: number("stateBgsSnapshots"),
         detail: window.t("signals.bgs_detail", "Current system snapshots · last 24 h"),
         hint: window.t("connections.catalog_overview_23", "BGS predicts candidates; it does not confirm an active HGE")},
        {title: window.t("signals.sightings", "FSS SIGHTINGS"), value: number("stateSightings"),
         detail: window.t("signals.sightings_detail", "Supported signal sightings · last 24 h · latest per system/type/faction"),
         hint: window.t("signals.sightings_hint", "Seen, but lifetime unknown. Not all sightings are HGEs.")},
        {title: window.t("signals.active", "REPORTED ACTIVE SIGNALS"), value: number("stateSignals"),
         detail: window.t("signals.active_detail", "Journal reports with an unexpired reported lifetime"),
         hint: window.t("signals.active_hint", "Not a guarantee of the same signal instance for every Commander.")}
    ]
    GridLayout {
        Layout.fillWidth: true
        columns: overview.width >= 1000 ? 3 : overview.width >= 580 ? 2 : 1
        rowSpacing: 10; columnSpacing: 10
        Repeater {
            model: overview.cards
            Rectangle {
                required property var modelData
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.preferredHeight: tileColumn.implicitHeight + 28
                radius: 8; color: overview.surface
                border.color: Qt.rgba(overview.accent.r, overview.accent.g, overview.accent.b, 0.20)
                ColumnLayout {
                    id: tileColumn
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.top: parent.top; anchors.margins: 14
                    spacing: 6
                    Label { text: modelData.title; color: overview.accent; font.pixelSize: 12; font.bold: true }
                    Label { text: modelData.value; color: overview.foreground; font.pixelSize: 26; font.bold: true }
                    Label { text: modelData.detail; color: overview.foreground; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Label { text: modelData.hint; color: overview.secondary; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                }
            }
        }
    }
    Label {
        Layout.fillWidth: true; wrapMode: Text.WordWrap
        text: window.t("connections.catalog_overview_24", "EDDN INTAKE · ") + overview.number("collector24hMessages") + window.t("connections.catalog_overview_25", " messages / last 24 h · ")
              + overview.percent("collector24hUsedPercent") + window.t("connections.catalog_overview_26", " used · ")
              + overview.number("collector24hErrors") + window.t("connections.catalog_overview_27", " errors / last 24 h")
        color: overview.foreground; font.pixelSize: 13
    }
    Label {
        Layout.fillWidth: true; wrapMode: Text.WordWrap
        text: window.t("connections.catalog_overview_28", "Last successful server check: ") + overview.date(overview.lastSuccess)
        color: overview.secondary; font.pixelSize: 12
    }
    ToolButton {
        id: details
        objectName: "catalogServerDetails"
        Layout.fillWidth: true
        checkable: true; checked: false
        text: (checked ? "- " : "+ ") + window.t("connections.catalog_overview_31", "DATA QUALITY & LOCAL SYNCHRONIZATION")
        font.pixelSize: 13; font.bold: true
        palette.buttonText: overview.accent
        padding: 12
        background: Rectangle {
            radius: 6
            color: Qt.rgba(overview.accent.r, overview.accent.g, overview.accent.b, details.hovered ? 0.14 : 0.06)
            border.color: Qt.rgba(overview.accent.r, overview.accent.g, overview.accent.b, 0.25)
        }
        contentItem: Label {
            text: details.text; font: details.font; color: overview.accent
            wrapMode: Text.WordWrap
        }
    }
    ColumnLayout {
        visible: details.checked
        Layout.fillWidth: true; spacing: 12
        GridLayout {
            Layout.fillWidth: true
            columns: overview.width >= 580 ? 2 : 1
            columnSpacing: 20; rowSpacing: 10
            Repeater {
                model: [
                    {label: window.t("connections.catalog_overview_32", "Complete commodity fields"), key: "marketDetailPercent"},
                    {label: window.t("connections.catalog_overview_33", "Station type known"), key: "stationTypePercent"},
                    {label: window.t("connections.catalog_overview_34", "Landing pad known"), key: "stationLandingPadPercent"},
                    {label: window.t("connections.catalog_overview_35", "Station services known"), key: "stationServicesPercent"}
                ]
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Label { text: modelData.label + window.t("connections.catalog_overview_36", " · ") + overview.percent(modelData.key); color: overview.foreground; font.pixelSize: 13 }
                    ProgressBar {
                        id: qualityBar
                        Layout.fillWidth: true; from: 0; to: 100
                        value: Math.max(0, overview.value(modelData.key))
                        background: Rectangle {
                            implicitHeight: 6; radius: 3; color: overview.surface
                        }
                        contentItem: Item {
                            implicitHeight: 6
                            Rectangle {
                                width: parent.width * qualityBar.visualPosition
                                height: parent.height; radius: 3; color: overview.accent
                            }
                        }
                    }
                }
            }
        }
        Label {
            Layout.fillWidth: true; wrapMode: Text.WordWrap
            text: window.t("connections.catalog_overview_37", "Coverage describes stored records, not the entire galaxy. Known fields do not guarantee fresh data.")
            color: overview.warning; font.pixelSize: 12
        }
        Repeater {
            model: [
                {name: window.t("connections.catalog_overview_38", "LOCAL MARKET CACHE"), status: overview.marketSync},
                {name: window.t("connections.catalog_overview_39", "LOCAL STATION OFFERS"), status: overview.offerSync},
                {name: window.t("connections.catalog_overview_40", "LOCAL STATE FINDS"), status: overview.stateSync}
            ]
            ColumnLayout {
                required property var modelData
                Layout.fillWidth: true; spacing: 3
                Label { text: modelData.name; color: overview.accent; font.pixelSize: 12; font.bold: true }
                Label { text: modelData.status || window.t("connections.catalog_overview_41", "Not checked"); color: overview.foreground; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            }
        }
    }
}
