import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "UiMetrics.js" as UiMetrics

Button {
    id: control
    property var appWindow: ApplicationWindow.window
    property color accentColor: appWindow ? appWindow.accent : "#4ad7ed"
    property bool selected: highlighted || (checkable && checked)
    property bool primary: false
    property string pictogram: ""
    property string helpText: ""
    property real horizontalContentPadding: 12
    readonly property color ink: !enabled ? (appWindow ? appWindow.textDisabled : "#587086")
        : primary ? (appWindow ? appWindow.backgroundPrimary : "#081620")
        : selected ? accentColor : (appWindow ? appWindow.textPrimary : "#f4f8ff")
    implicitHeight: UiMetrics.controlHeight
    implicitWidth: Math.max(42, caption.implicitWidth + horizontalContentPadding * 2
        + (pictogram.length ? 26 : 0))
    leftPadding: text.length ? horizontalContentPadding : 6
    rightPadding: text.length ? horizontalContentPadding : 6
    font.family: appWindow ? appWindow.font.family : "Segoe UI"
    font.pixelSize: UiMetrics.body
    font.weight: Font.DemiBold
    focusPolicy: Qt.StrongFocus
    hoverEnabled: true
    Accessible.name: text
    Accessible.description: helpText
    ToolTip.visible: hovered && (helpText.length > 0 || caption.truncated)
    ToolTip.text: helpText.length > 0 ? helpText : text

    contentItem: RowLayout {
        spacing: control.text.length ? 7 : 0
        Pictogram {
            visible: control.pictogram.length > 0
            name: control.pictogram; tint: control.ink
            Layout.preferredWidth: 18; Layout.preferredHeight: 18
            Layout.alignment: Qt.AlignHCenter
        }
        Label {
            id: caption
            visible: control.text.length > 0
            Layout.fillWidth: true; Layout.minimumWidth: 0
            text: control.text; font: control.font; color: control.ink
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }
    background: Rectangle {
        radius: UiMetrics.controlRadius
        color: control.primary ? control.accentColor
            : control.selected ? Qt.rgba(control.accentColor.r, control.accentColor.g, control.accentColor.b, 0.15)
            : control.hovered ? (control.appWindow ? control.appWindow.hover : "#1c3650")
            : (control.appWindow ? control.appWindow.inputBackground : "#0d202e")
        opacity: control.enabled ? 1 : 0.55
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus || control.hovered || control.selected
            ? control.accentColor : (control.appWindow ? control.appWindow.borderTone : "#2b4a5e")
    }
}
