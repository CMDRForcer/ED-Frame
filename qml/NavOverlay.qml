import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Window {
    id: navOverlay
    objectName: "nav-overlay-window"
    width: 360
    height: 250
    minimumWidth: 300
    minimumHeight: 200
    visible: navOverlaySettings.visible
    color: "transparent"
    opacity: navOverlaySettings.opacity
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
           | (navOverlaySettings.clickThrough ? Qt.WindowTransparentForInput : 0)
    title: t("nav.overlay_title", "ED-Frame Nav Overlay")

    readonly property var nav: cockpit.surfaceNav || ({})
    readonly property var guide: nav.guidance || ({})
    readonly property var targets: nav.targets || []
    readonly property var target: targets.find(function(row) {
        return row.id === navOverlay.nav.activeId
    }) || ({})

    function t(key, fallback) {
        return cockpit.translate(key, fallback)
    }
    function tf(key, fallback, values) {
        var result = t(key, fallback)
        for (var index = 0; index < values.length; index++)
            result = result.replace("%" + (index + 1), values[index])
        return result
    }
    function distance(value) {
        return value >= 1000 ? (value / 1000).toFixed(2) + " km"
                             : Math.round(value) + " m"
    }
    function guidanceText() {
        if (!target.id)
            return t("nav.no_target", "NO ACTIVE TARGET")
        if (guide.wrongBody)
            return t("nav.wrong_body", "Target is on another body or in another system.")
        if (!nav.position || !nav.position.body)
            return t("nav.wait_position", "Waiting for surface coordinates from Elite Dangerous.")
        if (guide.turnDeg === undefined)
            return t("nav.wait_heading", "Waiting for ship or suit heading.")
        if (guide.arrived)
            return t("nav.arrived", "TARGET REACHED")
        if (guide.turnDeg > 5)
            return tf("nav.turn_right", "TURN RIGHT %1°", [Math.round(guide.turnDeg)])
        if (guide.turnDeg < -5)
            return tf("nav.turn_left", "TURN LEFT %1°", [Math.round(-guide.turnDeg)])
        return t("nav.go_straight", "GO STRAIGHT")
    }

    Rectangle {
        anchors.fill: parent
        radius: 12
        color: "#f2071119"
        border.color: "#39c9ef"
        border.width: 1

        MouseArea {
            anchors.fill: parent
            enabled: !navOverlaySettings.locked && !navOverlaySettings.clickThrough
            onPressed: navOverlay.startSystemMove()
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 10 * navOverlaySettings.scale
            spacing: 5 * navOverlaySettings.scale

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 34 * navOverlaySettings.scale
                radius: 7
                color: "#17394a"
                border.color: "#39c9ef"
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    Label {
                        text: t("nav.surface", "SURFACE NAV")
                        color: "#7de7ff"
                        font.pixelSize: 13 * navOverlaySettings.scale
                        font.bold: true
                    }
                    Item { Layout.fillWidth: true }
                    Label {
                        text: navOverlaySettings.locked
                              ? t("overlay.locked", "LOCKED") : t("overlay.move", "MOVE")
                        color: "#a9bdd0"
                        font.pixelSize: 9 * navOverlaySettings.scale
                        font.bold: true
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10 * navOverlaySettings.scale
                Item {
                    Layout.preferredWidth: 102 * navOverlaySettings.scale
                    Layout.preferredHeight: 102 * navOverlaySettings.scale
                    Canvas {
                        id: compass
                        anchors.fill: parent
                        onWidthChanged: requestPaint()
                        onHeightChanged: requestPaint()
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            var x = width / 2, y = height / 2
                            var radius = Math.min(width, height) * 0.43
                            ctx.strokeStyle = "#557386"
                            ctx.lineWidth = 2
                            ctx.beginPath()
                            ctx.arc(x, y, radius, 0, Math.PI * 2)
                            ctx.stroke()
                            ctx.strokeStyle = "#a9bdd0"
                            ctx.beginPath()
                            ctx.moveTo(x, y - radius + 2)
                            ctx.lineTo(x, y - radius + 12)
                            ctx.stroke()
                            if (navOverlay.guide.turnDeg === undefined
                                    || navOverlay.guide.wrongBody)
                                return
                            ctx.save()
                            ctx.translate(x, y)
                            ctx.rotate(Number(navOverlay.guide.turnDeg) * Math.PI / 180)
                            ctx.fillStyle = navOverlay.guide.arrived ? "#42d888" : "#39c9ef"
                            ctx.beginPath()
                            ctx.moveTo(0, -radius + 12)
                            ctx.lineTo(13, 18)
                            ctx.lineTo(0, 7)
                            ctx.lineTo(-13, 18)
                            ctx.closePath()
                            ctx.fill()
                            ctx.restore()
                        }
                    }
                    Connections {
                        target: cockpit
                        function onSurfaceNavChanged() { compass.requestPaint() }
                    }
                    Label {
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom
                        text: t("nav.forward", "FORWARD")
                        color: "#a9bdd0"
                        font.pixelSize: 8 * navOverlaySettings.scale
                        font.bold: true
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5 * navOverlaySettings.scale
                    Label {
                        objectName: "overlay-nav-target"
                        Layout.fillWidth: true
                        text: navOverlay.target.name || t("nav.no_target", "NO ACTIVE TARGET")
                        color: "#ffffff"
                        font.pixelSize: 14 * navOverlaySettings.scale
                        font.bold: true
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.fillWidth: true
                        text: navOverlay.guidanceText()
                        color: navOverlay.guide.arrived ? "#42d888" : "#7de7ff"
                        font.pixelSize: 12 * navOverlaySettings.scale
                        font.bold: true
                        wrapMode: Text.WordWrap
                    }
                    Label {
                        objectName: "overlay-nav-distance"
                        text: navOverlay.guide.distanceM === undefined
                              ? t("nav.distance_unknown", "Distance unavailable")
                              : navOverlay.distance(navOverlay.guide.distanceM)
                        color: "#ffffff"
                        font.pixelSize: 19 * navOverlaySettings.scale
                        font.bold: true
                    }
                    Label {
                        visible: navOverlay.guide.bearingDeg !== undefined
                        text: tf("nav.bearing", "Bearing %1° · Heading %2°",
                                 [Math.round(navOverlay.guide.bearingDeg || 0),
                                  navOverlay.guide.headingDeg === undefined
                                  ? "—" : Math.round(navOverlay.guide.headingDeg)])
                        color: "#a9bdd0"
                        font.pixelSize: 9 * navOverlaySettings.scale
                    }
                }
            }

            Label {
                Layout.fillWidth: true
                text: navOverlay.target.id
                      ? navOverlay.target.system + " · " + navOverlay.target.body
                      : t("nav.choose_target", "Save or select a coordinate to start guidance.")
                color: "#a9bdd0"
                font.pixelSize: 9 * navOverlaySettings.scale
                elide: Text.ElideRight
            }
            Label {
                Layout.fillWidth: true
                visible: !navOverlaySettings.clickThrough
                text: t("overlay.fullscreen_warning", "Exclusive fullscreen may cover overlays; use Borderless Windowed.")
                color: "#687b8f"
                font.pixelSize: 8 * navOverlaySettings.scale
                elide: Text.ElideRight
            }
            RowLayout {
                visible: !navOverlaySettings.locked && !navOverlaySettings.clickThrough
                spacing: 4
                Label {
                    text: t("nav.overlay_opacity", "OPACITY")
                    color: "#a9bdd0"
                    font.pixelSize: 9 * navOverlaySettings.scale
                }
                Button {
                    text: t("nav.overlay_decrease", "−")
                    ToolTip.visible: hovered
                    ToolTip.text: t("overlay.opacity_down", "− OPACITY")
                    onClicked: navOverlaySettings.opacity -= 0.05
                }
                Button {
                    text: t("nav.overlay_increase", "+")
                    ToolTip.visible: hovered
                    ToolTip.text: t("overlay.opacity_up", "+ OPACITY")
                    onClicked: navOverlaySettings.opacity += 0.05
                }
                Label {
                    text: t("nav.overlay_scale", "SCALE")
                    color: "#a9bdd0"
                    font.pixelSize: 9 * navOverlaySettings.scale
                }
                Button {
                    text: t("nav.overlay_decrease", "−")
                    ToolTip.visible: hovered
                    ToolTip.text: t("overlay.scale_down", "− SCALE")
                    onClicked: navOverlaySettings.scale -= 0.05
                }
                Button {
                    text: t("nav.overlay_increase", "+")
                    ToolTip.visible: hovered
                    ToolTip.text: t("overlay.scale_up", "+ SCALE")
                    onClicked: navOverlaySettings.scale += 0.05
                }
            }
        }

        Canvas {
            width: 18
            height: 18
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: 3
            visible: !navOverlaySettings.locked && !navOverlaySettings.clickThrough
            onPaint: {
                var ctx = getContext("2d")
                ctx.strokeStyle = "#7de7ff"
                ctx.lineWidth = 1.5
                for (var offset = 0; offset < 3; offset++) {
                    ctx.beginPath()
                    ctx.moveTo(width - 15 + offset * 5, height - 3)
                    ctx.lineTo(width - 3, height - 15 + offset * 5)
                    ctx.stroke()
                }
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.SizeFDiagCursor
                onPressed: navOverlay.startSystemResize(Qt.RightEdge | Qt.BottomEdge)
            }
        }
    }
}
