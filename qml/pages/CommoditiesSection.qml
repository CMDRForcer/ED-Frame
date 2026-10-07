import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ColumnLayout {
    id: finder
    objectName: "commodityFinder"
    required property var appWindow
    spacing: 10
    component CommodityButton: Button {
        id: control
        implicitHeight: 42
        property bool primary: false
        contentItem: Label {
            text: control.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            font.pixelSize: 13; font.bold: true
            color: control.primary ? finder.appWindow.backgroundPrimary : finder.appWindow.textPrimary
        }
        background: Rectangle {
            radius: 7; color: control.primary ? finder.appWindow.orange : finder.appWindow.panelRaised
            border.color: control.hovered ? finder.appWindow.accentSecondary : finder.appWindow.borderTone
            opacity: control.enabled ? 1 : 0.5
        }
    }
    readonly property var catalog: cockpit.commodityCatalog || []
    readonly property var categories: {
        var keys = []
        catalog.forEach(function(row) {
            if (row.category) keys.push(row.category)
            if (row.tradeCategory) keys.push(row.tradeCategory)
        })
        return ["ALL"].concat(Array.from(new Set(keys)).sort())
    }
    readonly property var filteredChoices: catalog.filter(function(r) {
        var query = search.text.trim().toLowerCase()
        return (category.currentValue === "ALL" || r.category === category.currentValue
                || r.tradeCategory === category.currentValue)
            && (!query || r.name.toLowerCase().indexOf(query) >= 0 || r.id.indexOf(query) >= 0)
    })
    readonly property var choices: category.currentValue === "Rare Goods" && filteredChoices.length
        ? [{id:"ALL_RARE_GOODS", name:appWindow.t("common.all", "ALL")}].concat(filteredChoices)
        : filteredChoices
    onVisibleChanged: if (visible) cockpit.loadCommodityCatalog()
    Component.onCompleted: if (visible) cockpit.loadCommodityCatalog()
    GridLayout {
        Layout.fillWidth: true
        columns: finder.width >= 1000 ? 4 : 2
        columnSpacing: 10; rowSpacing: 10
        CockpitComboBox {
            id: category; appWindow: finder.appWindow; Layout.fillWidth: true
            Layout.preferredWidth: 200; Layout.minimumWidth: 0
            font.pixelSize: 13
            objectName: "commodityCategory"
            model: finder.categories.map(function(key) {
                return {key:key, label:key === "Rare Goods" ? appWindow.t("commodities.rare", "RARE GOODS") : key}
            })
            textRole: "label"; valueRole: "key"
            Accessible.name: appWindow.t("commodities.category", "Commodity category")
        }
        CockpitComboBox {
            id: commodity; appWindow: finder.appWindow; Layout.fillWidth: true
            Layout.preferredWidth: 260; Layout.minimumWidth: 0
            font.pixelSize: 13
            model: finder.choices; textRole: "name"; valueRole: "id"
            Accessible.name: appWindow.t("commodities.choose", "Choose commodity")
        }
        TextField {
            id: search; Layout.fillWidth: true
            objectName: "commoditySearch"
            Layout.preferredWidth: 440; Layout.minimumWidth: 0
            implicitHeight: 42; font.pixelSize: 14
            placeholderText: appWindow.t("commodities.search", "Filter names or symbols…")
            color: appWindow.textPrimary
            placeholderTextColor: appWindow.textSecondary
            background: Rectangle { radius: 6; color: appWindow.inputBackground; border.color: appWindow.borderTone }
        }
        CommodityButton {
            Layout.fillWidth: true
            Layout.preferredWidth: 220; Layout.maximumWidth: 260; Layout.minimumWidth: 0
            text: appWindow.t("commodities.refresh", "REFRESH CATALOG")
            enabled: !cockpit.commodityBusy
            onClicked: cockpit.refreshCommodityCatalog()
        }
    }
    GridLayout {
        Layout.fillWidth: true
        columns: finder.width >= 1000 ? 6 : 3
        columnSpacing: 10; rowSpacing: 10
        CockpitComboBox {
            id: direction; appWindow: finder.appWindow; Layout.fillWidth: true
            Layout.preferredWidth: 240; Layout.alignment: Qt.AlignBottom; font.pixelSize: 13
            model: [{key:"BUY",name:appWindow.t("commodities.buy", "BUY · station stock")},
                    {key:"SELL",name:appWindow.t("commodities.sell", "SELL · station demand")}]
            textRole: "name"; valueRole: "key"
        }
        CockpitComboBox {
            id: radius; appWindow: finder.appWindow; Layout.fillWidth: true
            Layout.preferredWidth: 140; Layout.alignment: Qt.AlignBottom; font.pixelSize: 13
            model: ["25 LY", "50 LY", "100 LY", "250 LY", "500 LY"]; currentIndex: 2
        }
        CockpitComboBox {
            id: pad; appWindow: finder.appWindow; Layout.fillWidth: true
            Layout.preferredWidth: 140; Layout.alignment: Qt.AlignBottom; font.pixelSize: 13
            model: [appWindow.t("nav.services.pad_any", "ANY PAD"), "S", "M", "L"]
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.preferredWidth: 160; Layout.alignment: Qt.AlignBottom
            spacing: 4
            Label {
                text: appWindow.t("commodities.quantity", "Minimum tonnes")
                color: appWindow.textSecondary; font.pixelSize: 12
            }
            SpinBox {
                id: quantity; Layout.fillWidth: true; implicitHeight: 42
                from: 1; to: 1000000; value: 1; editable: true
                font.pixelSize: 13
                Accessible.name: appWindow.t("commodities.quantity", "Minimum tonnes")
                palette.base: appWindow.inputBackground
                palette.text: appWindow.textPrimary
                palette.button: appWindow.panelRaised
                palette.buttonText: appWindow.textPrimary
            }
        }
        CockpitComboBox {
            id: age; appWindow: finder.appWindow; Layout.fillWidth: true
            Layout.preferredWidth: 140; Layout.alignment: Qt.AlignBottom; font.pixelSize: 13
            model: ["1 h", "6 h", "24 h", "72 h", "168 h"]; currentIndex: 2
            Accessible.name: appWindow.t("commodities.age", "Maximum quote age")
        }
        CommodityButton {
            Layout.fillWidth: true
            Layout.preferredWidth: 220; Layout.alignment: Qt.AlignBottom
            primary: true
            text: appWindow.t("commodities.find", "FIND OFFERS")
            enabled: !cockpit.commodityBusy && !!commodity.currentValue
            onClicked: cockpit.searchCommodities(String(commodity.currentValue), String(direction.currentValue),
                [25,50,100,250,500][radius.currentIndex], quantity.value, [1,6,24,72,168][age.currentIndex],
                ["ANY","S","M","L"][pad.currentIndex], carriers.checked)
        }
    }
    CheckBox {
        id: carriers; checked: true
        text: appWindow.t("nav.services.exclude_carriers", "Exclude Fleet Carriers")
        palette.windowText: appWindow.textPrimary
    }
    Text {
        id: statusText
        Layout.fillWidth: true; Layout.minimumHeight: statusMeasure.implicitHeight; Layout.preferredHeight: statusMeasure.implicitHeight
        wrapMode: Text.WordWrap; font.pixelSize: 13
        text: cockpit.commodityStatus || ""; color: appWindow.accentSecondary
    }
    Text {
        id: hintText
        Layout.fillWidth: true; Layout.minimumHeight: hintMeasure.implicitHeight; Layout.preferredHeight: hintMeasure.implicitHeight
        wrapMode: Text.WordWrap; font.pixelSize: 12
        text: appWindow.t("commodities.hint", "Minimum tonnes · maximum quote age. BUY: cheapest first; SELL: highest price first. Observations are not guarantees; legality and docking restrictions can change.")
        objectName: "commodityHint"
        color: appWindow.textSecondary
    }
    // Measure wrapping at the final available width, independent of the
    // layout's first (unconstrained) text measurement and resize cache.
    Text { id: statusMeasure; visible: false; width: finder.width; text: statusText.text; font: statusText.font; wrapMode: Text.WordWrap }
    Text { id: hintMeasure; visible: false; width: finder.width; text: hintText.text; font: hintText.font; wrapMode: Text.WordWrap }
    ListView {
        id: offers; Layout.fillWidth: true; Layout.fillHeight: true
        clip: true; spacing: 8; model: cockpit.commodityRows || []
        ScrollBar.vertical: CockpitScrollBar {}
        delegate: Rectangle {
            required property var modelData
            width: offers.width; height: details.implicitHeight + 28; radius: 8
            color: appWindow.panelRaised
            border.color: modelData.accessTone === "LOCKED" ? appWindow.error : appWindow.borderTone
            ColumnLayout {
                id: details; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 14
                Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; font.bold: true; font.pixelSize: 16
                    text: String(modelData.station || "—") + " · " + String(modelData.system || "—")
                        + " · " + String(modelData.commodityName || modelData.commodity || "")
                    color: appWindow.textPrimary
                }
                Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; color: appWindow.orange
                    text: String(modelData.direction || "") + " · " + Number(modelData.price).toLocaleString(Qt.locale(), "f", 0)
                        + " CR · " + Number(modelData.quantity).toLocaleString(Qt.locale(), "f", 0)
                        + " T · " + (modelData.direction === "BUY" ? appWindow.t("commodities.stock", "STOCK") : appWindow.t("commodities.demand", "DEMAND"))
                }
                Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; color: appWindow.textSecondary
                    text: Number(modelData.distanceLy).toFixed(1) + " LY · "
                        + (modelData.distanceToArrivalLs === null || modelData.distanceToArrivalLs === undefined ? "—" : Number(modelData.distanceToArrivalLs).toLocaleString(Qt.locale(), "f", 0))
                        + " LS · PAD " + String(modelData.landingPadSize || "—") + " · "
                        + (modelData.ageHours === null || modelData.ageHours === undefined ? "—" : Number(modelData.ageHours).toFixed(1) + " h")
                        + " · " + String(modelData.source || "—")
                }
                Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap
                    text: String(modelData.accessReason || modelData.accessStatus || "—")
                        + (modelData.fleetCarrier ? " · " + appWindow.t("commodities.carrier", "Carrier: docking restrictions unknown") : "")
                        + (modelData.knownProhibited ? " · " + appWindow.t("commodities.prohibited", "Reported prohibited commodity") : "")
                    color: modelData.accessTone === "LOCKED" || modelData.knownProhibited ? appWindow.error : appWindow.textSecondary
                }
                CommodityButton {
                    text: appWindow.t("nav.services.copy", "COPY SYSTEM")
                    onClicked: cockpit.copySystem(String(modelData.system || ""))
                }
            }
        }
    }
}
