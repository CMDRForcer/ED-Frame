import QtQuick
import QtQuick.Controls

ScrollBar {
    id: themedScrollBar
    property real trackThickness: 8
    property real thumbThickness: 5
    readonly property var hostWindow: ApplicationWindow.window
    implicitWidth: orientation === Qt.Vertical ? trackThickness : 100
    implicitHeight: orientation === Qt.Horizontal ? trackThickness : 100
    contentItem: Rectangle {
        implicitWidth: themedScrollBar.thumbThickness
        implicitHeight: themedScrollBar.thumbThickness
        radius: themedScrollBar.thumbThickness / 2
        color: themedScrollBar.hovered || themedScrollBar.pressed
               ? (themedScrollBar.hostWindow ? themedScrollBar.hostWindow.accent : "#3bdcff")
               : (themedScrollBar.hostWindow ? themedScrollBar.hostWindow.textDisabled : "#587086")
        opacity: themedScrollBar.active ? 0.92 : 0.42
        Behavior on opacity { NumberAnimation { duration: 140 } }
    }
    background: Rectangle {
        color: themedScrollBar.hostWindow ? themedScrollBar.hostWindow.inputBackground : "#0d1b2b"
        radius: 4
        opacity: themedScrollBar.active ? 0.46 : 0.16
        Behavior on opacity { NumberAnimation { duration: 140 } }
    }
}
