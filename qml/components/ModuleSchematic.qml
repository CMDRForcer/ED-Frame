import QtQuick

Item {
    id: root
    property color lineColor: "#46d9ff"
    property color accentColor: "#ffb347"
    property color surfaceColor: "#18222e"

    Canvas {
        id: schematicCanvas
        anchors.fill: parent
        antialiasing: true
        onPaint: {
            var c = getContext("2d")
            c.clearRect(0, 0, width, height)
            c.globalAlpha = 1.0
            c.fillStyle = root.surfaceColor
            c.fillRect(0, 0, width, height)
            c.strokeStyle = Qt.rgba(0.27, 0.85, 1.0, 0.14)
            c.lineWidth = 1
            var step = Math.max(18, Math.floor(width / 12))
            for (var x = 0; x <= width; x += step) {
                c.beginPath(); c.moveTo(x, 0); c.lineTo(x, height); c.stroke()
            }
            for (var y = 0; y <= height; y += step) {
                c.beginPath(); c.moveTo(0, y); c.lineTo(width, y); c.stroke()
            }

            var cx = width * 0.47
            var cy = height * 0.50
            c.strokeStyle = root.lineColor
            c.fillStyle = "#202f3d"
            c.lineWidth = 2
            c.beginPath()
            c.moveTo(width * 0.18, cy - height * 0.17)
            c.lineTo(width * 0.62, cy - height * 0.17)
            c.lineTo(width * 0.72, cy - height * 0.08)
            c.lineTo(width * 0.72, cy + height * 0.15)
            c.lineTo(width * 0.22, cy + height * 0.15)
            c.lineTo(width * 0.14, cy + height * 0.06)
            c.closePath(); c.fill(); c.stroke()

            c.strokeRect(width * 0.23, cy - height * 0.11,
                         width * 0.23, height * 0.20)
            c.beginPath(); c.arc(width * 0.34, cy - height * 0.01,
                                 height * 0.065, 0, Math.PI * 2); c.stroke()
            c.beginPath(); c.arc(width * 0.34, cy - height * 0.01,
                                 height * 0.025, 0, Math.PI * 2); c.stroke()

            c.fillStyle = root.accentColor
            c.fillRect(width * 0.50, cy - height * 0.09,
                       width * 0.15, height * 0.025)
            c.fillRect(width * 0.50, cy - height * 0.03,
                       width * 0.12, height * 0.018)
            c.fillRect(width * 0.50, cy + height * 0.025,
                       width * 0.09, height * 0.018)

            c.strokeStyle = root.lineColor
            c.strokeRect(width * 0.72, cy - height * 0.055,
                         width * 0.14, height * 0.12)
            c.beginPath()
            c.moveTo(width * 0.86, cy - height * 0.025)
            c.lineTo(width * 0.94, cy - height * 0.025)
            c.lineTo(width * 0.94, cy + height * 0.035)
            c.lineTo(width * 0.86, cy + height * 0.035)
            c.stroke()

            c.globalAlpha = 0.65
            c.beginPath(); c.moveTo(width * 0.12, cy + height * 0.22)
            c.lineTo(width * 0.88, cy + height * 0.22); c.stroke()
            c.beginPath(); c.moveTo(width * 0.18, cy + height * 0.18)
            c.lineTo(width * 0.18, cy + height * 0.26); c.stroke()
            c.beginPath(); c.moveTo(width * 0.82, cy + height * 0.18)
            c.lineTo(width * 0.82, cy + height * 0.26); c.stroke()
        }
        Connections {
            target: root
            function onLineColorChanged() { schematicCanvas.requestPaint() }
            function onAccentColorChanged() { schematicCanvas.requestPaint() }
            function onSurfaceColorChanged() { schematicCanvas.requestPaint() }
        }
    }
}
