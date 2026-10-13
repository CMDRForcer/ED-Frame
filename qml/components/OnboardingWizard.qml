import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "UiMetrics.js" as UiMetrics
import "OnboardingTour.js" as Tour

CockpitDialog {
    id: wizard
    required property var controller
    required property var navigationItems
    readonly property var window: appWindow
    readonly property var tourPages: Tour.pages(navigationItems)
    readonly property int pageCount: 4 + tourPages.length
    property int stepIndex: 0
    readonly property bool lastPage: stepIndex === pageCount - 1
    readonly property var tourPage: stepIndex >= 4 ? tourPages[stepIndex - 4] : null
    readonly property string pageTitle: stepIndex === 0
        ? window.t("onboarding.welcome.title", "Welcome, Commander")
        : stepIndex === 1 ? window.t("onboarding.journal.title", "Your Journal")
        : stepIndex === 2 ? window.t("onboarding.connections.title", "Your connections")
        : stepIndex === 3 ? window.t("onboarding.appearance.title", "Your cockpit, your style")
        : window.t("onboarding.tour." + tourPage.id, tourPage.id)
    signal openArea(int page)

    parent: Overlay.overlay
    transformOrigin: Popup.TopLeft
    x: (parent.width - width * scale) / 2
    y: (parent.height - height * scale) / 2
    width: Math.min(760, Math.max(240, parent.width / scale - 24))
    height: Math.min(680, parent.height / scale - 24)
    scale: controller.uiScale
    padding: 16
    closePolicy: Popup.NoAutoClose
    standardButtons: Dialog.NoButton
    title: window.t("dialog.onboarding.title", "Welcome, Commander")

    function finish() {
        controller.completeOnboarding()
        close()
    }
    function finishAndOpen(page) {
        finish()
        openArea(page)
    }
    function advance() {
        if (lastPage) finish()
        else stepIndex++
    }
    function setCommunityEnabled(enabled) {
        controller.setEdFrameCatalogEnabled(enabled)
        controller.setEdFrameYieldSharingEnabled(enabled)
        controller.setEdFrameSignalSharingEnabled(enabled)
        controller.setEdFrameStationPriceSharingEnabled(enabled)
    }
    onOpened: {
        stepIndex = 0
        nextButton.forceActiveFocus()
    }
    onStepIndexChanged: {
        if (scrollView.contentItem) scrollView.contentItem.contentY = 0
    }
    Shortcut {
        sequence: "Escape"
        enabled: wizard.visible && !journalFolderDialog.visible
        onActivated: wizard.finish()
    }

    component BodyText: Label {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        wrapMode: Text.WordWrap
        color: wizard.window.textSecondary
        font.pixelSize: UiMetrics.body
    }
    component WizardButton: Button {
        id: control
        padding: 10
        implicitHeight: Math.max(UiMetrics.controlHeight, contentItem.implicitHeight + 20)
        Accessible.name: text
        activeFocusOnTab: true
        contentItem: Label {
            text: control.text
            color: control.enabled ? wizard.window.textPrimary : wizard.window.textDisabled
            font.pixelSize: UiMetrics.body
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.WordWrap
        }
        background: Rectangle {
            radius: UiMetrics.controlRadius
            color: control.down ? wizard.window.active
                 : control.hovered ? wizard.window.hover : wizard.window.panelRaised
            border.width: control.activeFocus ? 2 : 1
            border.color: control.activeFocus ? wizard.window.accentSecondary : wizard.window.borderTone
        }
    }
    component ConnectionSwitch: Switch {
        id: control
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        Accessible.name: text
        activeFocusOnTab: true
        contentItem: Label {
            text: control.text
            leftPadding: control.indicator.width + control.spacing
            color: control.enabled ? wizard.window.textPrimary : wizard.window.textMuted
            font.pixelSize: UiMetrics.body
            wrapMode: Text.WordWrap
            verticalAlignment: Text.AlignVCenter
        }
    }

    header: Item {
        implicitHeight: headerLayout.implicitHeight + 24
        ColumnLayout {
            id: headerLayout
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 16
            spacing: 10
            RowLayout {
                Layout.fillWidth: true
                Pictogram { name: "operations"; tint: wizard.window.accentSecondary; width: 26; height: 26 }
                Label {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: wizard.pageTitle
                    wrapMode: Text.WordWrap
                    color: wizard.window.textPrimary
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Repeater {
                    model: wizard.pageCount
                    Rectangle {
                        required property int index
                        Layout.fillWidth: true
                        height: 4
                        radius: 2
                        color: index <= wizard.stepIndex ? wizard.window.accentSecondary : wizard.window.divider
                    }
                }
                Label {
                    text: wizard.window.t("onboarding.progress", "%1 of %2")
                        .replace("%1", wizard.stepIndex + 1).replace("%2", wizard.pageCount)
                    color: wizard.window.textMuted
                    font.pixelSize: UiMetrics.caption
                }
            }
        }
    }

    contentItem: ScrollView {
        id: scrollView
        objectName: "qa-onboarding-scroll"
        clip: true
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: ScrollBar.AsNeeded
        ScrollBar.vertical.active: true
        ColumnLayout {
            width: scrollView.availableWidth
            spacing: UiMetrics.sectionGap
            Loader {
                id: pageLoader
                objectName: "qa-onboarding-page"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                sourceComponent: wizard.stepIndex === 0 ? welcomePage
                    : wizard.stepIndex === 1 ? journalPage
                    : wizard.stepIndex === 2 ? connectionsPage
                    : wizard.stepIndex === 3 ? appearancePage : tourContent
            }
        }
    }

    footer: Item {
        implicitHeight: footerFlow.implicitHeight + 24
        Flow {
            id: footerFlow
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 12
            spacing: 8
            WizardButton {
                objectName: "qa-onboarding-skip"
                text: wizard.window.t("onboarding.skip", "Skip")
                width: Math.min(implicitWidth, footerFlow.width)
                onClicked: wizard.finish()
            }
            WizardButton {
                objectName: "qa-onboarding-back"
                text: wizard.window.t("onboarding.back", "Back")
                width: Math.min(implicitWidth, footerFlow.width)
                enabled: wizard.stepIndex > 0
                onClicked: wizard.stepIndex--
            }
            WizardButton {
                id: nextButton
                objectName: "qa-onboarding-next"
                text: wizard.lastPage ? wizard.window.t("onboarding.finish", "Let's go")
                    : wizard.window.t("onboarding.next", "Next")
                width: Math.min(implicitWidth, footerFlow.width)
                onClicked: wizard.advance()
            }
        }
    }

    Component {
        id: welcomePage
        CardSurface {
            implicitHeight: welcomeLayout.implicitHeight + 32
            ColumnLayout {
                id: welcomeLayout
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 16
                spacing: 16
                Pictogram { name: "cmdr"; tint: wizard.window.accentSecondary; width: 48; height: 48 }
                BodyText {
                    text: wizard.window.t("onboarding.welcome.heading", "Your Journal. One cockpit.")
                    color: wizard.window.textPrimary
                    font.pixelSize: 24
                    font.weight: Font.DemiBold
                }
                BodyText {
                    text: wizard.window.t("onboarding.welcome.body", "ED-Frame turns your Elite Dangerous Journal into useful next steps: plan upgrades, find resources and markets, and follow your Commander’s progress.")
                }
                BodyText {
                    text: wizard.window.t("onboarding.welcome.help", "Set up your cockpit, then take a short tour. You can skip at any time and return in Settings.")
                }
            }
        }
    }
    Component {
        id: journalPage
        ColumnLayout {
            spacing: UiMetrics.sectionGap
            BodyText { text: wizard.window.t("onboarding.journal.body", "Your Journal supplies your inventory, ship, missions and location. ED-Frame follows new events as you play.") }
            CardSurface {
                Layout.fillWidth: true
                implicitHeight: journalLayout.implicitHeight + 32
                ColumnLayout {
                    id: journalLayout
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 16
                    spacing: 12
                    Pictogram { name: "logbook"; tint: wizard.window.accentSecondary }
                    BodyText {
                        objectName: "qa-onboarding-journal-status"
                        text: wizard.controller.journalHealth.status === "CHECKING"
                            ? wizard.window.t("onboarding.journal.checking", "Checking Journal folder…")
                            : !wizard.controller.journalHealth.directoryExists
                              ? wizard.window.t("onboarding.journal.missing", "Journal folder not found")
                              : wizard.controller.journalHealth.fileCount > 0
                                ? wizard.window.t("onboarding.journal.found", "Journal found")
                                : wizard.window.t("onboarding.journal.empty", "Folder found; no Journal files yet")
                        color: wizard.controller.journalHealth.directoryExists ? wizard.window.success : wizard.window.warning
                        font.weight: Font.DemiBold
                    }
                    BodyText {
                        text: wizard.controller.journalPath || wizard.window.t("onboarding.journal.no_path", "No folder detected")
                        wrapMode: Text.WrapAnywhere
                    }
                    WizardButton {
                        objectName: "qa-onboarding-journal-change"
                        Layout.fillWidth: true
                        text: wizard.window.t("onboarding.journal.change", "Change Journal folder")
                        onClicked: journalFolderDialog.open()
                    }
                    ConnectionSwitch {
                        objectName: "qa-onboarding-journal-auto"
                        text: wizard.window.t("onboarding.journal.auto", "Follow Journal updates automatically")
                        checked: wizard.controller.journalAuto
                        onToggled: wizard.controller.setJournalAuto(checked)
                    }
                }
            }
        }
    }
    FolderDialog {
        id: journalFolderDialog
        title: wizard.window.t("onboarding.journal.change", "Change Journal folder")
        onAccepted: wizard.controller.setJournalFolder(selectedFolder)
    }
    Component {
        id: connectionsPage
        ColumnLayout {
            spacing: UiMetrics.sectionGap
            BodyText { text: wizard.window.t("onboarding.connections.body", "New installations enable the ED-Frame catalog and EDDN by default. The switches below show your actual saved settings.") }
            ConnectionSwitch {
                objectName: "qa-onboarding-catalog"
                text: wizard.window.t("onboarding.connections.catalog", "ED-Frame catalog & community sharing")
                checked: wizard.controller.edFrameCatalogEnabled && wizard.controller.edFrameYieldSharingEnabled
                    && wizard.controller.edFrameSignalSharingEnabled && wizard.controller.edFrameStationPriceSharingEnabled
                onToggled: wizard.setCommunityEnabled(checked)
            }
            BodyText { text: wizard.window.t("onboarding.connections.catalog_help", "Fetch public market, station and mining data, and contribute supported anonymous observations. Your Commander state comes from your local Journal.") }
            ConnectionSwitch {
                objectName: "qa-onboarding-eddn"
                text: wizard.window.t("onboarding.connections.eddn", "EDDN reception & public data sharing")
                checked: wizard.controller.eddnConsent && wizard.controller.eddnUploadEnabled && wizard.controller.eddnListenerEnabled
                onToggled: wizard.controller.saveEddnConfig(checked, checked, checked)
            }
            BodyText { text: wizard.window.t("onboarding.connections.eddn_help", "Receive public observations and share supported new Journal observations with EDDN. Disabling connections keeps retained local data.") }
            BodyText {
                objectName: "qa-onboarding-eddn-partial"
                visible: wizard.controller.eddnConsent
                    && wizard.controller.eddnUploadEnabled !== wizard.controller.eddnListenerEnabled
                color: wizard.window.warning
                text: wizard.window.t("onboarding.connections.eddn_partial", "Some EDDN functions are enabled. This switch changes reception and sharing together; individual controls are available in Connections.")
            }
            CardSurface {
                Layout.fillWidth: true
                implicitHeight: accountsLayout.implicitHeight + 32
                ColumnLayout {
                    id: accountsLayout
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 16
                    spacing: 12
                    BodyText { text: wizard.window.t("onboarding.connections.accounts", "INARA needs your API key and permission; Frontier CAPI needs account authorization. Configure these separately in Settings → Connections.") }
                    WizardButton {
                        objectName: "qa-onboarding-connections-open"
                        Layout.fillWidth: true
                        text: wizard.window.t("onboarding.connections.configure", "Finish & configure connections")
                        onClicked: wizard.finishAndOpen(6)
                    }
                }
            }
            BodyText {
                objectName: "qa-onboarding-usage-info"
                text: wizard.window.t("onboarding.connections.usage", "Active installation counting")
                color: wizard.window.accentSecondary
                font.weight: Font.DemiBold
            }
            BodyText { text: wizard.window.t("usage.privacy", "Release builds automatically send a random installation ID + app version, at most once per UTC day with the catalog enabled. The ID is recognizable across days. Stored for 90 days; no IP addresses in the database, no Commander data or Journals.") }
        }
    }
    Component {
        id: appearancePage
        ColumnLayout {
            spacing: UiMetrics.sectionGap
            BodyText { text: wizard.window.t("onboarding.appearance.body", "Language and theme apply immediately and stay saved, even if you skip the tour.") }
            BodyText { text: wizard.window.t("onboarding.appearance.language", "Language"); color: wizard.window.accentSecondary }
            ComboBox {
                objectName: "qa-onboarding-language"
                Layout.fillWidth: true
                model: wizard.controller.interfaceLanguages
                textRole: "label"
                valueRole: "id"
                currentIndex: model.findIndex(entry => entry.id === wizard.controller.interfaceLanguage)
                Accessible.name: wizard.window.t("onboarding.appearance.language", "Language")
                onActivated: wizard.controller.setInterfaceLanguage(currentValue)
            }
            BodyText { text: wizard.window.t("onboarding.appearance.theme", "Theme"); color: wizard.window.accentSecondary }
            Repeater {
                model: Object.keys(wizard.window.themeSets)
                delegate: WizardButton {
                    required property string modelData
                    objectName: "qa-onboarding-theme-" + modelData
                    Layout.fillWidth: true
                    text: wizard.window.t("onboarding.theme." + modelData, modelData)
                    highlighted: wizard.controller.theme === modelData
                    contentItem: Label {
                        text: parent.text
                        color: wizard.window.themeSets[modelData].textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        wrapMode: Text.WordWrap
                        font.pixelSize: UiMetrics.body
                    }
                    background: CardSurface {
                        color: wizard.window.themeSets[modelData].card
                        border.width: wizard.controller.theme === modelData ? 2 : 1
                        border.color: wizard.controller.theme === modelData ? wizard.window.accentSecondary : wizard.window.borderTone
                    }
                    onClicked: wizard.controller.setTheme(modelData)
                }
            }
        }
    }
    Component {
        id: tourContent
        ColumnLayout {
            spacing: UiMetrics.sectionGap
            BodyText { text: wizard.window.t("onboarding.tour.body", "A quick look at your cockpit. Open a section to finish the tour and jump straight in.") }
            Repeater {
                id: tourEntries
                model: wizard.tourPage ? wizard.tourPage.entries : []
                delegate: CardSurface {
                    required property var modelData
                    objectName: "qa-onboarding-area-" + modelData.id
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    implicitHeight: areaLayout.implicitHeight + 32
                    ColumnLayout {
                        id: areaLayout
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 16
                        spacing: 10
                        RowLayout {
                            Layout.fillWidth: true
                            Pictogram { name: modelData.id; tint: wizard.window.accentSecondary; width: 26; height: 26 }
                            BodyText { text: modelData.label; color: wizard.window.textPrimary; font.weight: Font.DemiBold }
                        }
                        BodyText { text: wizard.window.t(Tour.descriptionKey(modelData.id), wizard.window.t("onboarding.area.other", "Explore this section of your cockpit.")) }
                        WizardButton {
                            objectName: "qa-onboarding-open-" + modelData.id
                            Layout.fillWidth: true
                            text: wizard.window.t("onboarding.open", "Open")
                            Accessible.name: wizard.window.t("onboarding.open_area", "Open %1").replace("%1", modelData.label)
                            onClicked: wizard.finishAndOpen(modelData.page)
                        }
                    }
                }
            }
            BodyText {
                visible: wizard.tourPage && wizard.tourPage.id === "setup"
                text: wizard.window.t("onboarding.tour.setup_help", "Press Ctrl+K to search across the cockpit. Reopen this tour any time with %1 in Settings.")
                    .replace("%1", wizard.window.t("settings.onboarding", "OPEN ONBOARDING"))
            }
        }
    }
}
