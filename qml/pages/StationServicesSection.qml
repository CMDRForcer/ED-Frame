import "../components/UiMetrics.js" as UiMetrics
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ColumnLayout {
    id: finder
    required property var appWindow
    property bool filtersReady: false
    property string filterLanguage: ""
    readonly property var filterDraft: ({service: String(service.currentValue || ""),
        radius: radius.currentIndex, pad: pad.currentIndex, excludeCarriers: excludeCarriers.checked})
    onFilterDraftChanged: if (filtersReady && filterLanguage === String(cockpit.interfaceLanguage)
                             && typeof appWindow.stationServiceFinderState !== "undefined")
        appWindow.stationServiceFinderState = filterDraft
    Connections {
        target: cockpit
        function onUiChanged() { Qt.callLater(finder.restoreFilters) }
    }
    function restoreFilters() {
        filtersReady = false
        var saved = appWindow.stationServiceFinderState || ({})
        if (Object.keys(saved).length) {
            service.currentIndex = Math.max(0, service.indexOfValue(saved.service))
            radius.currentIndex = saved.radius; pad.currentIndex = saved.pad
            excludeCarriers.checked = saved.excludeCarriers
        }
        filterLanguage = String(cockpit.interfaceLanguage)
        filtersReady = true
    }
    Component.onCompleted: restoreFilters()
    spacing: 12
    component ServiceButton: CockpitAction {
        appWindow: finder.appWindow
        accentColor: primary ? appWindow.orange : appWindow.accent
    }
    GridLayout {
        Layout.fillWidth: true
        columns: finder.width >= 900 ? 4 : 2
        columnSpacing: 12; rowSpacing: 8
        CockpitComboBox {
            id: service; objectName: "stationServiceChoice"; Layout.fillWidth: true
            appWindow: finder.appWindow
            font.pixelSize: 13
            model: (cockpit.stationServiceChoices || []).map(function(row) {
                return {key: row.key, label: appWindow.t("nav.services.option." + row.key, row.label)}
            })
            textRole: "label"; valueRole: "key"
            Accessible.name: appWindow.t("nav.services.service", "Station service")
        }
        CockpitComboBox {
            id: radius; objectName: "stationServiceRadius"; Layout.fillWidth: true
            appWindow: finder.appWindow
            font.pixelSize: 13
            model: ["25 LY", "50 LY", "100 LY", "250 LY", "500 LY"]
            currentIndex: 2
            Accessible.name: appWindow.t("nav.services.radius", "Search radius")
        }
        CockpitComboBox {
            id: pad; objectName: "stationServicePad"; Layout.fillWidth: true
            appWindow: finder.appWindow
            font.pixelSize: 13
            model: [appWindow.t("nav.services.pad_any", "ANY PAD"), "S", "M", "L"]
            Accessible.name: appWindow.t("nav.services.pad", "Required landing pad")
        }
        ServiceButton {
            Layout.fillWidth: true
            primary: true
            text: cockpit.stationServiceBusy
                  ? appWindow.t("status.searching", "SEARCHING…")
                  : appWindow.t("nav.services.find", "FIND STATIONS")
            enabled: !cockpit.stationServiceBusy && !!service.currentValue
            onClicked: cockpit.searchStationServices(
                String(service.currentValue), [25, 50, 100, 250, 500][radius.currentIndex],
                ["ANY", "S", "M", "L"][pad.currentIndex], excludeCarriers.checked)
        }
    }
    CheckBox {
        id: excludeCarriers; objectName: "stationServiceExcludeCarriers"
        checked: true
        text: appWindow.t("nav.services.exclude_carriers", "Exclude Fleet Carriers")
        font.pixelSize: 13
        palette.windowText: finder.appWindow.textPrimary
        palette.text: finder.appWindow.textPrimary
    }
    Label {
        id: serviceStatus
        Layout.fillWidth: true; wrapMode: Text.WordWrap
        Layout.minimumHeight: statusMeasure.implicitHeight
        Layout.preferredHeight: statusMeasure.implicitHeight
        text: cockpit.stationServiceStatus || ""
        color: appWindow.accentSecondary; font.pixelSize: 13
    }
    Label {
        id: serviceHint
        Layout.fillWidth: true; wrapMode: Text.WordWrap
        Layout.minimumHeight: hintMeasure.implicitHeight
        Layout.preferredHeight: hintMeasure.implicitHeight
        objectName: "stationServiceHint"
        text: appWindow.t("nav.services.hint",
                         "Nearest systems first, then arrival distance. Metadata age is shown; service availability and access can change. Trader/broker subtypes are not known.")
        color: appWindow.textSecondary; font.pixelSize: 12
    }
    Text { id: statusMeasure; visible: false; width: finder.width; text: serviceStatus.text; font: serviceStatus.font; wrapMode: Text.WordWrap }
    Text { id: hintMeasure; visible: false; width: finder.width; text: serviceHint.text; font: serviceHint.font; wrapMode: Text.WordWrap }
    ListView {
        id: stations
        objectName: "stationServiceResultList"
        Layout.fillWidth: true; Layout.fillHeight: true
        clip: true; spacing: 8
        model: cockpit.stationServiceRows || []
        ScrollBar.vertical: CockpitScrollBar {}
        delegate: CardSurface {
            required property var modelData
            width: stations.width
            height: rowLayout.implicitHeight + 28
            radius: UiMetrics.cardRadius; color: appWindow.panelRaised
            border.color: modelData.accessTone === "LOCKED" ? appWindow.error : appWindow.borderTone
            RowLayout {
                id: rowLayout
                anchors.left: parent.left; anchors.right: parent.right
                anchors.top: parent.top; anchors.margins: 14; spacing: 14
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    Label {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                        text: String(modelData.station || "") + " · " + String(modelData.system || "")
                        color: appWindow.textPrimary; font.pixelSize: 16; font.bold: true
                    }
                    Label {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                        text: Number(modelData.distanceLy || 0).toLocaleString(Qt.locale(), "f", 1) + " LY · "
                              + (modelData.distanceToArrivalLs === null || modelData.distanceToArrivalLs === undefined
                                 ? "—" : Number(modelData.distanceToArrivalLs).toLocaleString(Qt.locale(), "f", 0))
                              + " LS · " + String(modelData.stationType || "—") + " · " + appWindow.t("nav.services.pad_short", "PAD") + " "
                              + String(modelData.landingPadSize || "—")
                        color: appWindow.accentSecondary; font.pixelSize: 13
                    }
                    Label {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                        text: String(modelData.accessStatus || "") + " · " + String(modelData.accessReason || "")
                        color: modelData.accessTone === "LOCKED" ? appWindow.error
                               : modelData.accessTone === "UNKNOWN" ? appWindow.orange : appWindow.green
                        font.pixelSize: 12
                    }
                    Label {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                        text: appWindow.t("nav.services.observed", "Station metadata age: ")
                              + (modelData.ageHours === null || modelData.ageHours === undefined
                                 ? appWindow.t("status.unknown", "UNKNOWN") : Number(modelData.ageHours).toLocaleString(Qt.locale(), "f", 1) + " h")
                              + " · " + String(modelData.source || "ED-Frame")
                              + (modelData.carrierWarning ? " · " + appWindow.t("nav.services.carrier_warning", "Carrier docking access must be checked") : "")
                        color: modelData.ageHours === null || modelData.ageHours > 24
                               ? appWindow.orange : appWindow.textSecondary
                        font.pixelSize: 12
                    }
                }
                ServiceButton {
                    text: appWindow.t("nav.services.copy", "COPY SYSTEM")
                    onClicked: cockpit.copySystem(String(modelData.system || ""))
                }
            }
        }
        Label {
            anchors.centerIn: parent
            width: Math.max(0, parent.width - 24)
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            visible: stations.count === 0 && !cockpit.stationServiceBusy
            text: appWindow.t("nav.services.empty", "No results · choose a service and search")
            color: appWindow.muted; font.pixelSize: 14
        }
    }
}
