import QtQuick

// A compact diagonal DNA double helix, kept as a Canvas so it inherits the
// exact selected/unselected tint of the Fluent sidebar glyphs around it.
Canvas {
    id: dnaIcon
    property color color: "#3bdcff"
    property real strokeWidth: 1.7
    width: 24
    height: 20
    antialiasing: true
    onColorChanged: requestPaint()
    onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        ctx.strokeStyle = dnaIcon.color
        ctx.lineWidth = dnaIcon.strokeWidth
        ctx.lineCap = "round"
        var w = width
        var h = height
        var length = 18
        var amplitude = 3.0
        var samples = 36

        function strandX(t, phase) {
            return amplitude * Math.sin(t * Math.PI * 2.5 + phase)
        }

        ctx.translate(w / 2, h / 2)
        // Starting from a vertical helix, this places the strand on the same
        // lively bottom-left to top-right axis as the surrounding line icons.
        ctx.rotate(-55 * Math.PI / 180)

        // Draw the base-pair rungs first so the continuous outer strands stay
        // crisp at this very small navigation size.
        ctx.globalAlpha = 0.68
        for (var r = 1; r <= 5; r++) {
            var rungT = r / 6
            var rungY = (rungT - 0.5) * length
            var xA = strandX(rungT, 0)
            var xB = strandX(rungT, Math.PI)
            ctx.beginPath()
            ctx.moveTo(xA, rungY)
            ctx.lineTo(xB, rungY)
            ctx.stroke()
        }

        // Two intertwined strands.
        ctx.globalAlpha = 1.0
        var phases = [0, Math.PI]
        phases.forEach(function(phase) {
            ctx.beginPath()
            for (var i = 0; i <= samples; i++) {
                var t = i / samples
                var x = strandX(t, phase)
                var y = (t - 0.5) * length
                if (i === 0) ctx.moveTo(x, y)
                else ctx.lineTo(x, y)
            }
            ctx.stroke()
        })
    }
}
