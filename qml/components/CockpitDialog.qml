import QtQuick
import QtQuick.Controls
import "UiMetrics.js" as UiMetrics

Dialog {
    property var appWindow: ApplicationWindow.window
    id: dialogControl
    modal: true
    dim: true
    padding: 20
    topPadding: 18
    leftPadding: 20
    rightPadding: 20
    bottomPadding: 18
    palette.window: dialogControl.appWindow.panel
    palette.windowText: dialogControl.appWindow.textPrimary
    palette.base: dialogControl.appWindow.inputBackground
    palette.text: dialogControl.appWindow.textPrimary
    palette.button: dialogControl.appWindow.panelRaised
    palette.buttonText: dialogControl.appWindow.textPrimary
    palette.highlight: dialogControl.appWindow.accent
    palette.highlightedText: dialogControl.appWindow.backgroundPrimary

    Overlay.modal: Rectangle { color: dialogControl.appWindow.overlay }
    background: Rectangle {
        radius: 14
        color: dialogControl.appWindow.panel
        border.width: 1
        border.color: dialogControl.appWindow.borderTone
        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 3
            radius: 2
            color: dialogControl.appWindow.accent
        }
    }
    header: CardSurface {
        implicitHeight: 58
        color: dialogControl.appWindow.panelRaised
        radius: UiMetrics.cardRadius
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: dialogControl.appWindow.divider
        }
        Label {
            anchors.left: parent.left
            anchors.leftMargin: 20
            anchors.right: parent.right
            anchors.rightMargin: 20
            anchors.verticalCenter: parent.verticalCenter
            elide: Text.ElideRight
            text: dialogControl.title
            color: dialogControl.appWindow.textPrimary
            font.pixelSize: 17
            font.weight: Font.DemiBold
        }
    }
    footer: DialogButtonBox {
        visible: dialogControl.standardButtons !== Dialog.NoButton
        standardButtons: dialogControl.standardButtons
        padding: 12
        spacing: 8
        palette.button: dialogControl.appWindow.inputBackground
        palette.buttonText: dialogControl.appWindow.textSecondary
        palette.highlight: dialogControl.appWindow.accent
        background: Rectangle {
            color: dialogControl.appWindow.panelRaised
            radius: 14
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 1
                color: dialogControl.appWindow.divider
            }
        }
        onAccepted: dialogControl.accept()
        onRejected: dialogControl.reject()
    }
}
