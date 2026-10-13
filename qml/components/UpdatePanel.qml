import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "UiMetrics.js" as UiMetrics

CardSurface {
    id: panel
    required property var appWindow
    required property var controller
    readonly property var info: controller.updateInfo
    readonly property var window: appWindow
    implicitHeight: body.implicitHeight + 28
    tone: window.accent
    ColumnLayout {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 14
        spacing: 10
        Label {
            Layout.fillWidth: true
            text: window.t("updates.title", "APP UPDATES")
            color: window.accent; font.bold: true; font.pixelSize: UiMetrics.body + 2
            wrapMode: Text.WordWrap
        }
        Label {
            objectName: "qa-update-status"
            Layout.fillWidth: true
            text: info.status === "error"
                ? window.t("updates.error." + info.error, "Update could not be completed. Try again or open the release page.")
                : info.status === "available" || info.status === "ready"
                  ? window.tf("updates.status." + info.status, "Version %1 is available", [info.version])
                  : window.t("updates.status." + info.status, "Check for a newer release")
            color: info.status === "error" ? window.orange : window.textPrimary
            wrapMode: Text.WordWrap; font.pixelSize: UiMetrics.body
        }
        Label {
            Layout.fillWidth: true
            text: window.t("updates.data_safe", "Profiles, plans, credentials and local data stay outside the app folder. Before installing, the helper saves a complete local backup; the previous app is retained.")
            color: window.textSecondary; wrapMode: Text.WordWrap
            font.pixelSize: UiMetrics.caption
        }
        CheckBox {
            objectName: "qa-update-auto-check"
            Layout.fillWidth: true
            text: window.t("updates.auto_check", "Check automatically once per day")
            Accessible.name: text
            checked: info.enabled
            enabled: !info.busy
            onToggled: controller.setUpdateChecksEnabled(checked)
            contentItem: Label {
                text: parent.text; color: window.textPrimary
                leftPadding: 32; wrapMode: Text.WordWrap
                font.pixelSize: UiMetrics.body; verticalAlignment: Text.AlignVCenter
            }
        }
        CheckBox {
            objectName: "qa-update-auto-download"
            Layout.fillWidth: true
            text: window.t("updates.auto_download", "Download updates automatically; restart when I choose")
            Accessible.name: text
            checked: info.autoDownload
            enabled: !info.busy && info.canInstall
            onToggled: controller.setAutomaticUpdateDownload(checked)
            contentItem: Label {
                text: parent.text; color: window.textPrimary
                leftPadding: 32; wrapMode: Text.WordWrap
                font.pixelSize: UiMetrics.body; verticalAlignment: Text.AlignVCenter
            }
        }
        Label {
            Layout.fillWidth: true
            visible: !info.canInstall
            text: window.t("updates.source", "Source checkouts do not update themselves. Automatic checks are disabled for development and smoke builds. You can check releases manually.")
            color: window.muted; wrapMode: Text.WordWrap; font.pixelSize: UiMetrics.caption
        }
        ProgressBar {
            objectName: "qa-update-progress"
            Layout.fillWidth: true
            visible: info.status === "downloading" || info.status === "preparing"
            value: info.progress
            indeterminate: info.status === "preparing"
            Accessible.name: window.t("updates.progress", "Update download and verification progress")
        }
        Flow {
            Layout.fillWidth: true
            spacing: 8
            CockpitAction {
                appWindow: window
                visible: !!info.version && !info.dismissed
                text: window.t("updates.later", "LATER")
                Accessible.name: text
                onClicked: controller.dismissUpdate()
            }
            CockpitAction {
                appWindow: window
                objectName: "qa-update-backups"
                visible: info.backupAvailable
                text: window.t("updates.backups", "OPEN PROFILE BACKUPS")
                Accessible.name: text
                onClicked: controller.openUpdateBackups()
            }
            CockpitAction {
                appWindow: window
                objectName: "qa-update-check"
                text: window.t("updates.check", "CHECK NOW")
                Accessible.name: text
                enabled: !info.busy && info.status !== "ready" && info.status !== "restarting"
                onClicked: controller.checkForUpdates()
            }
            CockpitAction {
                appWindow: window
                objectName: "qa-update-download"
                visible: !!info.version && info.status !== "ready" && info.status !== "preparing" && info.status !== "restarting"
                text: window.t("updates.download", "DOWNLOAD UPDATE")
                Accessible.name: text
                enabled: !info.busy
                onClicked: controller.downloadUpdate()
            }
            CockpitAction {
                appWindow: window
                objectName: "qa-update-cancel"
                visible: info.status === "downloading"
                text: window.t("updates.cancel", "CANCEL DOWNLOAD")
                Accessible.name: text
                onClicked: controller.cancelUpdateDownload()
            }
            CockpitAction {
                appWindow: window
                objectName: "qa-update-install"
                visible: info.status === "ready"
                text: window.t("updates.install", "UPDATE AND RESTART")
                Accessible.name: text
                selected: true
                enabled: info.canInstall
                onClicked: confirmDialog.open()
            }
            CockpitAction {
                appWindow: window
                objectName: "qa-update-release"
                text: window.t("updates.release", "RELEASE NOTES")
                Accessible.name: text
                onClicked: controller.openUpdateRelease()
            }
        }
        Label {
            Layout.fillWidth: true
            visible: !!info.notes
            text: info.notes
            textFormat: Text.PlainText
            wrapMode: Text.Wrap; color: window.textSecondary
            font.pixelSize: UiMetrics.caption
        }
    }
    CockpitDialog {
        id: confirmDialog
        objectName: "qa-update-confirm"
        appWindow: panel.appWindow
        parent: Overlay.overlay
        scale: controller.uiScale
        transformOrigin: Popup.TopLeft
        x: (parent.width - width * scale) / 2
        y: (parent.height - height * scale) / 2
        width: Math.min(560, parent.width / scale - 24)
        title: window.t("updates.confirm.title", "Install update?")
        standardButtons: Dialog.NoButton
        contentItem: Label {
            text: window.t("updates.confirm.body", "ED-Frame will save its settings and close, including the tray process. The helper backs up all local profiles before replacing the app files and starting the new version. Keep enough free disk space for these backups.")
            color: window.textPrimary; wrapMode: Text.WordWrap
            font.pixelSize: UiMetrics.body
        }
        footer: Flow {
            padding: 12; spacing: 8
            CockpitAction {
                appWindow: window
                objectName: "qa-update-confirm-install"
                text: window.t("updates.install", "UPDATE AND RESTART")
                Accessible.name: text
                selected: true
                onClicked: { confirmDialog.close(); controller.installUpdate() }
            }
            CockpitAction {
                appWindow: window
                text: window.t("updates.later", "LATER")
                Accessible.name: text
                onClicked: confirmDialog.close()
            }
        }
    }
}
