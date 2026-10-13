import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "UiMetrics.js" as UiMetrics

CardSurface {
    id: notice
    required property var appWindow
    required property var controller
    signal showUpdates()
    readonly property var info: controller.updateInfo
    readonly property var window: appWindow
    visible: (info.status === "available" || info.status === "ready") && !info.dismissed
    implicitHeight: content.implicitHeight + 20
    tone: window.accent
    ColumnLayout {
        id: content
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.margins: 10
        Label {
            Layout.fillWidth: true
            visible: !window.compactSidebar
            text: window.tf("updates.notice", "ED-Frame %1 is available", [info.version])
            wrapMode: Text.WordWrap
            color: window.textPrimary; font.pixelSize: UiMetrics.caption; font.bold: true
        }
        Flow {
            Layout.fillWidth: true
            spacing: 6
            CockpitAction {
                appWindow: window
                objectName: "qa-update-notice-open"
                width: Math.min(implicitWidth, parent.width)
                text: window.compactSidebar ? "" : window.t("updates.open", "VIEW UPDATE")
                pictogram: window.compactSidebar ? "refresh" : ""
                helpText: window.tf("updates.notice", "ED-Frame %1 is available", [info.version])
                Accessible.name: window.t("updates.open", "VIEW UPDATE")
                onClicked: notice.showUpdates()
            }
            CockpitAction {
                appWindow: window
                objectName: "qa-update-notice-later"
                visible: !window.compactSidebar
                width: Math.min(implicitWidth, parent.width)
                text: window.t("updates.later", "LATER")
                Accessible.name: text
                onClicked: controller.dismissUpdate()
            }
        }
    }
}
