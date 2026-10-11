import QtQuick
import QtQuick.Controls
import "IconPaths.js" as IconPaths

Item {
    id: icon
    property string name: "info"
    property color tint: hostWindow ? hostWindow.accent : "#4ad7ed"
    readonly property var hostWindow: ApplicationWindow.window
    implicitWidth: 22
    implicitHeight: 22
    Accessible.ignored: true
    Image {
        anchors.fill: parent
        source: IconPaths.svg(icon.name, icon.tint)
        sourceSize.width: Math.max(1, Math.ceil(width * 2))
        sourceSize.height: Math.max(1, Math.ceil(height * 2))
        fillMode: Image.PreserveAspectFit
        smooth: true
    }
}
