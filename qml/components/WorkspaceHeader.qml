import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "UiMetrics.js" as UiMetrics

Item {
    id: header
    required property var appWindow
    property string eyebrow: "COMMANDER WORKSPACE"
    property string title: ""
    property string subtitle: ""
    property string statusText: ""
    property color statusTone: appWindow.accentSecondary
    property string qaName: ""
    default property alias actions: actionRow.data

    objectName: qaName
    Layout.fillWidth: true
    implicitHeight: Math.max(76, titleColumn.height + 16,
                             actionRow.y + actionRow.height + 16)
    Layout.preferredHeight: implicitHeight

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        width: 3
        height: 52
        radius: 2
        color: appWindow.accent
    }

    ColumnLayout {
        id: titleColumn
        anchors.left: parent.left
        anchors.leftMargin: 16
        anchors.top: parent.top
        anchors.right: appWindow.narrowWorkspace ? parent.right : actionRow.left
        anchors.rightMargin: appWindow.narrowWorkspace ? 0 : 22
        spacing: 2

        Label {
            visible: header.eyebrow.length > 0
            text: header.eyebrow
            color: appWindow.accentSecondary
            font.pixelSize: UiMetrics.caption
            font.weight: Font.DemiBold
            font.letterSpacing: 1.0
        }
        Label {
            Layout.fillWidth: true
            text: header.title
            color: appWindow.textPrimary
            font.pixelSize: appWindow.narrowWorkspace ? 21 : 25
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }
        Label {
            Layout.fillWidth: true
            text: header.subtitle
            color: appWindow.muted
            font.pixelSize: UiMetrics.body
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }
    }

    RowLayout {
        id: actionRow
        anchors.right: parent.right
        anchors.top: appWindow.narrowWorkspace ? titleColumn.bottom : parent.top
        anchors.topMargin: appWindow.narrowWorkspace ? 10 : 8
        spacing: 8
        StatusBadge {
            visible: header.statusText.length > 0
            statusText: header.statusText
            tone: header.statusTone
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: appWindow.divider
    }
}
