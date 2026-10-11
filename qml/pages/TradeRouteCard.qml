import "../components/UiMetrics.js" as UiMetrics
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

CardSurface {
    id: card
    required property var appWindow
    required property var routeData
    required property int rank
    required selected
    tone: routeData.accessWarning || routeData.prohibitedWarning ? appWindow.error : appWindow.accent
    property bool detailsExpanded: false
    readonly property bool wide: width >= 620
    signal selectRoute()
    signal copySystem(string system)
    objectName: "tradeRouteCard" + rank
    implicitHeight: body.implicitHeight + 28
    height: implicitHeight
    radius: UiMetrics.cardRadius
    color: appWindow.panelRaised
    border.width: selected ? 2 : 1
    border.color: routeData.accessWarning || routeData.prohibitedWarning ? appWindow.error
        : selected ? appWindow.orange : appWindow.borderTone

    function cr(value) { return Number(value).toLocaleString(Qt.locale(), "f", 0) + " CR" }
    function ly(value) { return Number(value).toLocaleString(Qt.locale(), "f", 1) + " LY" }
    function tonnes(value) { return Number(value).toLocaleString(Qt.locale(), "f", 0) + " T" }

    component Action: CockpitAction {
        appWindow: card.appWindow
        accentColor: primary ? appWindow.orange : appWindow.accent
        implicitHeight: 36; font.pixelSize: 12
    }
    component Metric: ColumnLayout {
        id: metric
        property string caption: ""
        property string value: ""
        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 3
        Label {
            Layout.fillWidth: true; text: metric.caption; wrapMode: Text.WordWrap
            color: card.appWindow.textSecondary; font.pixelSize: 11
        }
        Label {
            Layout.fillWidth: true; text: metric.value; wrapMode: Text.WordWrap
            color: card.appWindow.textPrimary; font.pixelSize: 14; font.bold: true
        }
    }
    component Endpoint: RowLayout {
        id: endpoint
        required property var station
        required property string letter
        required property color tone
        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 9
        Rectangle {
            Layout.preferredWidth: 28; Layout.preferredHeight: 28; Layout.alignment: Qt.AlignTop
            radius: 7; color: card.appWindow.inputBackground; border.color: endpoint.tone
            Label { anchors.centerIn: parent; text: endpoint.letter; color: endpoint.tone; font.bold: true; font.pixelSize: 15 }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 2
            Label {
                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: card.appWindow.textPrimary
                text: String(endpoint.station.system); font.pixelSize: 16; font.bold: true
            }
            Label {
                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: card.appWindow.textSecondary
                text: String(endpoint.station.station); font.pixelSize: 12
            }
            Label {
                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: card.appWindow.textSecondary
                visible: card.detailsExpanded; font.pixelSize: 11
                text: String(endpoint.station.landingPadSize || "—") + " PAD · "
                    + (endpoint.station.distanceToArrivalLs === null || endpoint.station.distanceToArrivalLs === undefined
                        ? "—" : Number(endpoint.station.distanceToArrivalLs).toLocaleString(Qt.locale(), "f", 0)) + " LS"
                    + " · " + String(endpoint.station.accessReason || "")
            }
        }
    }
    component Freight: CardSurface {
        id: freight
        required property var leg
        required property bool returning
        tone: returning ? card.appWindow.orange : card.appWindow.accent
        Layout.fillWidth: true; Layout.minimumWidth: 0
        implicitHeight: freightBody.implicitHeight + 22
        color: card.appWindow.inputBackground
        ColumnLayout {
            id: freightBody
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 11
            spacing: card.selected ? 7 : 4
            RowLayout {
                Layout.fillWidth: true; spacing: 6
                Pictogram { name: "goods"; tint: freight.tone; Layout.preferredWidth: 18; Layout.preferredHeight: 18 }
                Label {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap
                    color: freight.tone; font.pixelSize: 11; font.bold: true
                    text: (freight.returning ? "B → A · " : "A → B · ")
                        + card.appWindow.t(freight.returning ? "trade.inbound" : "trade.outbound", freight.returning ? "RETURN CARGO" : "OUTBOUND CARGO")
                }
                Label { text: card.tonnes(freight.leg.tonnes); color: card.appWindow.textPrimary; font.pixelSize: 13; font.bold: true }
            }
            RowLayout {
                Layout.fillWidth: true
                Label {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap
                    text: String(freight.leg.commodityName); color: card.appWindow.textPrimary
                    font.pixelSize: card.selected ? 19 : 14; font.bold: true
                }
                Label {
                    visible: !card.selected; text: String("+") + card.cr(freight.leg.profitCr)
                    color: card.appWindow.green; font.pixelSize: 13; font.bold: true
                }
            }
            GridLayout {
                visible: card.selected; Layout.fillWidth: true; columns: 2; columnSpacing: 12
                Metric {
                    caption: card.appWindow.t("commodities.buy_short", "BUY") + (freight.returning ? " · B" : " · A")
                    value: card.cr(freight.leg.buyPrice) + "/T"
                }
                Metric {
                    caption: card.appWindow.t("commodities.sell_short", "SELL") + (freight.returning ? " · A" : " · B")
                    value: card.cr(freight.leg.sellPrice) + "/T"
                }
            }
            Rectangle { visible: card.selected; Layout.fillWidth: true; implicitHeight: 1; color: card.appWindow.borderTone }
            Label {
                visible: card.selected; Layout.fillWidth: true; wrapMode: Text.WordWrap
                text: String("+") + card.cr(freight.leg.profitCr); color: card.appWindow.green; font.pixelSize: 16; font.bold: true
            }
            GridLayout {
                visible: card.detailsExpanded; Layout.fillWidth: true; columns: 2; columnSpacing: 12; rowSpacing: 8
                Metric { Layout.columnSpan: 2; caption: card.appWindow.t("trade.cost", "Purchase cost"); value: card.cr(freight.leg.purchaseCr) }
                Metric { caption: card.appWindow.t("commodities.stock", "STOCK"); value: card.tonnes(freight.leg.stock) }
                Metric { caption: card.appWindow.t("commodities.demand", "DEMAND"); value: card.tonnes(freight.leg.demand) }
            }
        }
    }

    ColumnLayout {
        id: body
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 14
        spacing: 12
        GridLayout {
            Layout.fillWidth: true; columns: card.width >= 500 ? 2 : 1; columnSpacing: 12; rowSpacing: 5
            ColumnLayout {
                Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 4
                Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; color: card.rank === 1 ? card.appWindow.orange : card.appWindow.textSecondary
                    font.pixelSize: 11; font.bold: true
                    text: String("#") + card.rank + " · " + (card.rank === 1 ? card.appWindow.t("trade.top_result", "TOP RESULT")
                        : card.appWindow.t("trade.title", "TRADE ROUTES"))
                }
                Label { text: String("A → B → A"); color: card.appWindow.textPrimary; font.pixelSize: 16; font.bold: true }
            }
            ColumnLayout {
                Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 1
                Label {
                    Layout.fillWidth: true; horizontalAlignment: card.width >= 500 ? Text.AlignRight : Text.AlignLeft
                    text: String("+") + card.cr(card.routeData.profitCr); color: card.appWindow.green
                    font.pixelSize: card.selected ? 27 : 22; font.bold: true
                    fontSizeMode: Text.Fit; minimumPixelSize: 16
                }
                Label {
                    Layout.fillWidth: true; horizontalAlignment: card.width >= 500 ? Text.AlignRight : Text.AlignLeft
                    text: card.appWindow.t("trade.estimated_profit", "Estimated profit"); wrapMode: Text.WordWrap
                    color: card.appWindow.textSecondary; font.pixelSize: 11
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: card.appWindow.borderTone }
        GridLayout {
            Layout.fillWidth: true; columns: card.wide ? 2 : 1; columnSpacing: 14; rowSpacing: 9
            Endpoint { station: card.routeData.stationA; letter: "A"; tone: card.appWindow.accent }
            Endpoint { station: card.routeData.stationB; letter: "B"; tone: card.appWindow.orange }
        }
        GridLayout {
            Layout.fillWidth: true; columns: card.wide ? 2 : 1; columnSpacing: 12; rowSpacing: 8
            Freight { leg: card.routeData.outbound; returning: false }
            Freight { leg: card.routeData.inbound; returning: true }
        }
        GridLayout {
            Layout.fillWidth: true; columns: card.width >= 720 ? 4 : 2; columnSpacing: 12; rowSpacing: 9
            Metric { caption: card.appWindow.t("trade.approach", "To A"); value: card.ly(card.routeData.approachLy) }
            Metric { caption: card.appWindow.t("trade.round_distance", "Round trip"); value: card.ly(card.routeData.roundTripLy) }
            Metric { caption: card.appWindow.t("trade.oldest", "Oldest price"); value: Number(card.routeData.oldestAgeHours).toLocaleString(Qt.locale(), "f", 1) + " h" }
            Metric { caption: card.appWindow.t("trade.unit_profit", "Combined margin / T"); value: card.cr(card.routeData.unitProfitCr) }
        }
        Label {
            Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 12; color: card.appWindow.orange
            visible: card.routeData.carrierWarning || card.routeData.accessWarning || card.routeData.prohibitedWarning
            text: [card.routeData.carrierWarning ? card.appWindow.t("commodities.carrier", "Carrier: docking restrictions unknown") : "",
                card.routeData.accessWarning ? card.appWindow.t("trade.access_warning", "Check permit requirements") : "",
                card.routeData.prohibitedWarning ? card.appWindow.t("commodities.prohibited", "Reported prohibited commodity") : ""].filter(function(value) { return !!value }).join(" · ")
        }
        Flow {
            Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 8
            Action { pictogram: "copy"; text: card.appWindow.t("trade.copy_a", "COPY SYSTEM A"); onClicked: card.copySystem(String(card.routeData.stationA.system)) }
            Action { pictogram: "copy"; text: card.appWindow.t("trade.copy_b", "COPY SYSTEM B"); onClicked: card.copySystem(String(card.routeData.stationB.system)) }
            Action {
                objectName: "tradeRouteDetails" + card.rank
                text: card.appWindow.t(card.detailsExpanded ? "trade.hide_details" : "trade.show_details", card.detailsExpanded ? "HIDE DETAILS" : "DETAILS")
                onClicked: card.detailsExpanded = !card.detailsExpanded
            }
            Action {
                objectName: "tradeRouteSelect" + card.rank
                text: card.selected ? card.appWindow.t("trade.selected", "SELECTED ROUTE") : card.appWindow.t("trade.select", "USE THIS ROUTE")
                onClicked: card.selectRoute()
            }
        }
    }
}
