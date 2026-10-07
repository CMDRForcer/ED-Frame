import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ColumnLayout {
    id: finder
    required property var appWindow
    spacing: 12
    component ServiceButton: Button {
        id: control
        property bool primary: false
        implicitHeight: 42
        leftPadding: 14; rightPadding: 14
        font.pixelSize: 13; font.bold: true
        contentItem: Label {
            text: control.text; font: control.font
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            color: control.primary ? finder.appWindow.backgroundPrimary : finder.appWindow.textPrimary
        }
        background: Rectangle {
            radius: 7
            color: control.primary ? finder.appWindow.orange : finder.appWindow.panelRaised
            border.color: control.hovered ? finder.appWindow.accentSecondary : finder.appWindow.borderTone
            opacity: control.enabled ? 1 : 0.5
        }
    }
    GridLayout {
        Layout.fillWidth: true
        columns: finder.width >= 900 ? 4 : 2
        columnSpacing: 12; rowSpacing: 8
        CockpitComboBox {
            id: service; Layout.fillWidth: true
            appWindow: finder.appWindow
            font.pixelSize: 13
            model: (cockpit.stationServiceChoices || []).map(function(row) {
                return {key: row.key, label: appWindow.t("nav.services.option." + row.key, row.label)}
            })
            textRole: "label"; valueRole: "key"
            Accessible.name: appWindow.t("nav.services.service", "Station service")
        }
        CockpitComboBox {
            id: radius; Layout.fillWidth: true
            appWindow: finder.appWindow
            font.pixelSize: 13
            model: ["25 LY", "50 LY", "100 LY", "250 LY", "500 LY"]
            currentIndex: 2
            Accessible.name: appWindow.t("nav.services.radius", "Search radius")
        }
        CockpitComboBox {
            id: pad; Layout.fillWidth: true
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
        id: excludeCarriers
        checked: true
        text: appWindow.t("nav.services.exclude_carriers", "Exclude Fleet Carriers")
        font.pixelSize: 13
        palette.windowText: finder.appWindow.textPrimary
        palette.text: finder.appWindow.textPrimary
    }
    Label {
        Layout.fillWidth: true; wrapMode: Text.WordWrap
        Layout.minimumHeight: implicitHeight
        text: cockpit.stationServiceStatus || ""
        color: appWindow.accentSecondary; font.pixelSize: 13
    }
    Label {
        Layout.fillWidth: true; wrapMode: Text.WordWrap
        Layout.minimumHeight: implicitHeight
        objectName: "stationServiceHint"
        text: appWindow.t("nav.services.hint",
                         "Nearest systems first, then arrival distance. Metadata age is shown; service availability and access can change. Trader/broker subtypes are not known.")
        color: appWindow.textSecondary; font.pixelSize: 12
    }
    ListView {
        id: stations
        objectName: "stationServiceResultList"
        Layout.fillWidth: true; Layout.fillHeight: true
        clip: true; spacing: 8
        model: cockpit.stationServiceRows || []
        ScrollBar.vertical: CockpitScrollBar {}
        delegate: Rectangle {
            required property var modelData
            width: stations.width
            height: rowLayout.implicitHeight + 28
            radius: 8; color: appWindow.panelRaised
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
                        text: Number(modelData.distanceLy || 0).toFixed(1) + " LY · "
                              + (modelData.distanceToArrivalLs === null || modelData.distanceToArrivalLs === undefined
                                 ? "—" : Number(modelData.distanceToArrivalLs).toLocaleString(Qt.locale(), "f", 0))
                              + " LS · " + String(modelData.stationType || "—") + " · PAD "
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
                                 ? appWindow.t("status.unknown", "UNKNOWN") : modelData.ageHours + " h")
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
            visible: stations.count === 0 && !cockpit.stationServiceBusy
            text: appWindow.t("nav.services.empty", "No results · choose a service and search")
            color: appWindow.muted; font.pixelSize: 14
        }
    }
}
