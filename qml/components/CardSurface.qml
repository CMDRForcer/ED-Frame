import QtQuick
import QtQuick.Controls
import "UiMetrics.js" as UiMetrics

Rectangle {
    id: surface
    readonly property var hostWindow: ApplicationWindow.window
    property color tone: "transparent"
    property bool selected: false
    property real tintStrength: selected ? 0.13 : 0.065
    color: hostWindow ? hostWindow.panelRaised : "#1a3244"
    radius: UiMetrics.cardRadius
    border.width: selected ? 2 : 1
    border.color: selected && tone.a > 0 ? tone
                  : hostWindow ? hostWindow.borderTone : "#2b4a5e"

    function blend(base, accent, amount) {
        var weight = Math.max(0, Math.min(1, amount)) * accent.a
        return Qt.rgba(base.r * (1 - weight) + accent.r * weight,
                       base.g * (1 - weight) + accent.g * weight,
                       base.b * (1 - weight) + accent.b * weight, base.a)
    }
    // A static fill also works with Qt's software renderer. No blur, shadow
    // shader or render timer is used for the card hierarchy.
    gradient: Gradient {
        orientation: Gradient.Horizontal
        GradientStop { position: 0; color: surface.blend(surface.color, surface.tone, surface.tintStrength) }
        GradientStop { position: 1; color: surface.color }
    }
}
