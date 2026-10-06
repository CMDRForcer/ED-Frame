import QtQuick

Item {
    id: root
    property url source: ""
    property color tone: "#46d9ff"
    property color accent: "#ffb347"
    property bool selected: false
    property bool compact: false

    Rectangle {
        anchors.fill: parent
        radius: root.compact ? 6 : 9
        gradient: Gradient {
            GradientStop { position: 0.0; color: root.selected ? "#27374b" : "#1a2634" }
            GradientStop { position: 0.64; color: root.selected ? "#202d3c" : "#17222f" }
            GradientStop { position: 1.0; color: "#131d28" }
        }
    }

    Rectangle {
        width: Math.min(parent.width, parent.height) * 0.72
        height: width
        radius: width / 2
        anchors.centerIn: parent
        color: "transparent"
        border.width: 1
        border.color: Qt.rgba(0.27, 0.85, 1.0, root.selected ? 0.22 : 0.10)
    }

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.compact ? 5 : 9
        width: parent.width * 0.62
        height: 2
        radius: 1
        color: root.selected ? root.accent : root.tone
        opacity: root.selected ? 0.9 : 0.34
    }

    Image {
        id: shipImage
        anchors.fill: parent
        anchors.margins: root.compact ? 4 : 12
        source: root.source
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
        cache: true
        asynchronous: true
        sourceSize.width: root.compact ? 640 : 1200
        sourceSize.height: root.compact ? 430 : 800
        opacity: status === Image.Ready ? (root.selected ? 1.0 : 0.82) : 0.0

        Behavior on opacity { NumberAnimation { duration: 130 } }
    }

    Rectangle {
        visible: root.selected
        anchors.fill: parent
        radius: root.compact ? 6 : 9
        color: "transparent"
        border.width: 2
        border.color: root.accent
    }
}
