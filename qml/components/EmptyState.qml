import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "UiMetrics.js" as UiMetrics

ColumnLayout {
    id: emptyState
    property string symbol: "◇"
    property string title: ""
    property string detail: ""
    property color tone: hostWindow ? hostWindow.accent : "#3bdcff"
    property bool prominent: false
    readonly property var hostWindow: ApplicationWindow.window
    spacing: prominent ? 14 : 8

    Rectangle {
        Layout.alignment: Qt.AlignHCenter
        implicitWidth: emptyState.prominent ? 86 : 46
        implicitHeight: emptyState.prominent ? 86 : 46
        Layout.minimumWidth: implicitWidth
        Layout.minimumHeight: implicitHeight
        radius: emptyState.prominent ? 26 : 15
        color: Qt.rgba(emptyState.tone.r, emptyState.tone.g, emptyState.tone.b, 0.10)
        border.width: 1
        border.color: Qt.rgba(emptyState.tone.r, emptyState.tone.g, emptyState.tone.b, 0.42)
        Label {
            anchors.centerIn: parent
            text: emptyState.symbol
            color: emptyState.tone
            font.pixelSize: emptyState.prominent ? 38 : 21
            font.bold: true
        }
    }
    Label {
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignHCenter
        text: emptyState.title
        color: emptyState.tone
        font.pixelSize: emptyState.prominent ? 21 : 13
        font.bold: true
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
    }
    Label {
        visible: emptyState.detail.length > 0
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignHCenter
        Layout.maximumWidth: emptyState.prominent ? 720 : 420
        text: emptyState.detail
        color: emptyState.hostWindow ? emptyState.hostWindow.muted : "#8fa4ba"
        font.pixelSize: emptyState.prominent ? 14 : UiMetrics.caption
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
    }
}
