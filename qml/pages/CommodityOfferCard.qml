import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../components/UiMetrics.js" as UiMetrics

CardSurface {
    id: offer
    required property var appWindow
    required property var offerData
    required property int rank
    property bool preferredPrice: false
    readonly property bool locked: offerData.accessTone === "LOCKED" || !!offerData.knownProhibited
    signal copySystem(string system)
    objectName: "commodityOfferCard" + rank
    tone: locked ? appWindow.error : preferredPrice ? appWindow.green : appWindow.accent
    color: appWindow.panelRaised
    border.color: locked || preferredPrice ? Qt.rgba(tone.r, tone.g, tone.b, 0.6) : appWindow.borderTone
    implicitHeight: content.implicitHeight + UiMetrics.cardInset * 2
    height: implicitHeight

    ColumnLayout {
        id: content
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.margins: UiMetrics.cardInset
        spacing: 8
        RowLayout {
            Layout.fillWidth: true; spacing: 12
            Pictogram {
                name: offer.offerData.fleetCarrier ? "shipyard" : "station"
                tint: offer.tone
                Layout.preferredWidth: 24; Layout.preferredHeight: 24
            }
            ColumnLayout {
                Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 3
                Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap
                    text: String(offer.offerData.station || "—")
                    color: offer.appWindow.textPrimary; font.pixelSize: 16; font.bold: true
                }
                Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap
                    text: String(offer.offerData.system || "—") + " · "
                        + String(offer.offerData.commodityName || offer.offerData.commodity || "")
                    color: offer.appWindow.textSecondary; font.pixelSize: UiMetrics.body
                }
            }
            ColumnLayout {
                Layout.maximumWidth: offer.width * 0.35; spacing: 2
                Label {
                    Layout.fillWidth: true; horizontalAlignment: Text.AlignRight
                    text: offer.appWindow.t(offer.offerData.direction === "BUY" ? "commodities.buy_short" : "commodities.sell_short",
                        offer.offerData.direction === "BUY" ? "BUY" : "SELL")
                    color: offer.appWindow.textSecondary; font.pixelSize: UiMetrics.caption
                }
                Label {
                    Layout.fillWidth: true; horizontalAlignment: Text.AlignRight
                    text: Number(offer.offerData.price).toLocaleString(Qt.locale(), "f", 0) + " CR/T"
                    color: offer.preferredPrice && !offer.locked ? offer.appWindow.green : offer.appWindow.textPrimary
                    font.pixelSize: 21; font.bold: true; fontSizeMode: Text.Fit; minimumPixelSize: 14
                }
                Label {
                    Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; wrapMode: Text.WordWrap
                    text: Number(offer.offerData.quantity).toLocaleString(Qt.locale(), "f", 0) + " T · "
                        + offer.appWindow.t(offer.offerData.direction === "BUY" ? "commodities.stock" : "commodities.demand",
                            offer.offerData.direction === "BUY" ? "STOCK" : "DEMAND")
                    color: offer.appWindow.textSecondary; font.pixelSize: UiMetrics.caption
                }
            }
        }
        Label {
            Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: UiMetrics.caption
            text: Number(offer.offerData.distanceLy).toLocaleString(Qt.locale(), "f", 1) + " LY · "
                + (offer.offerData.distanceToArrivalLs === null || offer.offerData.distanceToArrivalLs === undefined ? "—"
                    : Number(offer.offerData.distanceToArrivalLs).toLocaleString(Qt.locale(), "f", 0))
                + " LS · " + offer.appWindow.t("nav.services.pad_short", "PAD") + " " + String(offer.offerData.landingPadSize || "—")
                + " · " + (offer.offerData.ageHours === null || offer.offerData.ageHours === undefined ? "—"
                    : Number(offer.offerData.ageHours).toLocaleString(Qt.locale(), "f", 1) + " h")
                + " · " + String(offer.offerData.source || "—")
            color: offer.appWindow.textSecondary
        }
        Label {
            Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: UiMetrics.caption
            text: String(offer.offerData.accessReason || offer.offerData.accessStatus || "—")
                + (offer.offerData.fleetCarrier ? " · " + offer.appWindow.t("commodities.carrier", "Carrier: docking restrictions unknown") : "")
                + (offer.offerData.knownProhibited ? " · " + offer.appWindow.t("commodities.prohibited", "Reported prohibited commodity") : "")
            color: offer.locked ? offer.appWindow.error : offer.offerData.fleetCarrier ? offer.appWindow.orange : offer.appWindow.textSecondary
        }
        CockpitAction {
            appWindow: offer.appWindow; pictogram: "copy"; implicitHeight: 34; font.pixelSize: 12
            text: appWindow.t("nav.services.copy", "COPY SYSTEM")
            onClicked: offer.copySystem(String(offer.offerData.system || ""))
        }
    }
}
