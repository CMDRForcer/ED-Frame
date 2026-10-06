import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: finder
    required property var appWindow
    required property real sidebarWidth

    property string mode: "MODULES"
    property string selectedSymbol: ""
    property var selectedItem: ({})
    property string originSystem: String(cockpit.system || "") === "Unknown"
                                  ? "" : String(cockpit.system || "")
    property int rangeLy: 100
    property string padFilter: "ANY"
    property string accessFilter: "SAFE + UNKNOWN"
    readonly property var suggestions: cockpit.shipyardFinderSuggestions || []
    readonly property var ships: cockpit.shipyardShipCatalog || []
    readonly property var results: cockpit.shipyardFinderResults || []
    readonly property var stats: cockpit.edFrameCatalogStats || ({})
    readonly property var overview: cockpit.commanderOverview || ({})
    readonly property color cyan: appWindow.cyan
    readonly property color orange: appWindow.orange
    readonly property color green: appWindow.green
    readonly property color textPrimary: appWindow.textPrimary
    readonly property color textSecondary: appWindow.textSecondary
    readonly property color muted: appWindow.muted
    readonly property color panelRaised: appWindow.panelRaised
    readonly property color borderTone: appWindow.borderTone
    readonly property color inputBackground: appWindow.inputBackground

    objectName: "qa-page-shipyard"
    anchors.fill: parent
    anchors.leftMargin: sidebarWidth + (appWindow.compactSidebar ? 18 : 26)
    anchors.rightMargin: appWindow.compactSidebar ? 18 : 26
    anchors.topMargin: appWindow.compactSidebar ? 18 : 26
    anchors.bottomMargin: appWindow.compactSidebar ? 18 : 26

    function stationCount() {
        return Number(mode === "MODULES"
                      ? Math.max(Number(stats.outfittingStations || 0),
                                 Number(stats.localOutfittingStations || 0))
                      : Math.max(Number(stats.shipyardStations || 0),
                                 Number(stats.localShipyardStations || 0)))
    }
    function formatNumber(value) {
        return Number(value || 0).toLocaleString(Qt.locale(), "f", 0)
    }
    function priceLabel(row) {
        if (!row || row.priceKnown !== true)
            return appWindow.t("shipyard.price_unknown", "PRICE UNKNOWN")
        return formatNumber(row.price) + " CR"
    }
    function distanceLabel(row) {
        if (!row || row.distanceKnown !== true)
            return appWindow.t("shipyard.distance_unknown", "DISTANCE UNKNOWN")
        return Number(row.distanceLy || 0).toLocaleString(Qt.locale(), "f", 1) + " LY"
    }
    function arrivalLabel(row) {
        if (!row || row.distanceToArrivalLs === null || row.distanceToArrivalLs === undefined)
            return appWindow.t("shipyard.arrival_unknown", "ARRIVAL UNKNOWN")
        return formatNumber(row.distanceToArrivalLs) + " LS"
    }
    function accessColor(row) {
        var tone = String((row || {}).accessTone || "UNKNOWN")
        if (tone === "CONFIRMED" || tone === "OPEN") return green
        if (tone === "LOCKED") return appWindow.red || "#ff586f"
        return orange
    }
    function schematicSource(row) {
        var path = String((row || {}).schematicSource || "")
        return path ? Qt.resolvedUrl("../../" + path) : ""
    }
    function chooseItem(row) {
        selectedItem = row || ({})
        selectedSymbol = String((row || {}).symbol || "")
        searchField.text = String((row || {}).displayName || selectedSymbol)
        suggestionPopup.close()
    }
    function resetMode(nextMode) {
        mode = nextMode
        selectedSymbol = ""
        selectedItem = ({})
        searchField.text = ""
        cockpit.clearShipyardFinder()
        cockpit.requestShipyardSuggestions(nextMode, "")
    }
    function runSearch() {
        cockpit.searchShipyardOffers(
            mode, selectedSymbol, originSystem, rangeLy,
            padFilter, accessFilter, selectedItem)
    }

    Component.onCompleted: cockpit.requestShipyardSuggestions(mode, "")

    component FinderButton: Button {
        id: control
        property bool selected: false
        property color tone: finder.orange
        onClicked: {}
        implicitHeight: 38
        font.pixelSize: 11
        font.bold: true
        contentItem: Label {
            text: control.text
            color: control.selected ? appWindow.backgroundPrimary : textSecondary
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            font: control.font
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: 7
            color: control.selected ? control.tone
                  : control.hovered ? appWindow.hover : inputBackground
            border.width: control.selected ? 0 : 1
            border.color: control.hovered ? control.tone : borderTone
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        WorkspaceHeader {
            appWindow: finder.appWindow
            eyebrow: appWindow.t("shipyard.eyebrow", "GALAXY INTELLIGENCE")
            title: appWindow.t("shipyard.title", "SHIPYARD & OUTFITTING")
            subtitle: appWindow.t(
                "shipyard.subtitle",
                "Find modules and ships · observed prices · permit-aware routes")
            statusText: cockpit.edFrameCatalogOnline
                        ? appWindow.t("shipyard.server_online", "SERVER ONLINE")
                        : appWindow.t("shipyard.local_active", "LOCAL CATALOG ACTIVE")
            statusTone: cockpit.edFrameCatalogOnline ? green : orange
            StatusBadge {
                compact: true
                statusText: appWindow.tf(
                    "shipyard.offer_stations", "%1 OFFER STATIONS",
                    [finder.formatNumber(finder.stationCount())])
                tone: cyan
            }
            StatusBadge {
                compact: true
                statusText: appWindow.tf(
                    "shipyard.permits_confirmed", "PERMITS · %1 JOURNAL",
                    [Number((finder.overview.permits || []).length)])
                tone: Number((finder.overview.permits || []).length) > 0 ? green : orange
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            FinderButton {
                objectName: "qa-shipyard-modules-tab"
                Layout.preferredWidth: 132
                text: appWindow.t("shipyard.modules", "MODULES")
                selected: finder.mode === "MODULES"
                tone: cyan
                onClicked: finder.resetMode("MODULES")
            }
            FinderButton {
                objectName: "qa-shipyard-ships-tab"
                Layout.preferredWidth: 132
                text: appWindow.t("shipyard.ships", "SHIPS")
                selected: finder.mode === "SHIPS"
                tone: cyan
                onClicked: finder.resetMode("SHIPS")
            }
            Item { Layout.fillWidth: true }
            Label {
                text: cockpit.shipyardFinderStatus || ""
                color: cockpit.shipyardFinderBusy ? cyan : muted
                font.pixelSize: 10
                font.bold: true
                elide: Text.ElideLeft
                Layout.maximumWidth: Math.max(220, finder.width * 0.43)
            }
        }

        ShadowCard {
            Layout.fillWidth: true
            Layout.preferredHeight: appWindow.narrowWorkspace ? 236 : 126
            accent: orange
            GridLayout {
                anchors.fill: parent
                anchors.margins: 14
                columns: appWindow.narrowWorkspace ? 2 : 6
                columnSpacing: 10
                rowSpacing: 8

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.columnSpan: appWindow.narrowWorkspace ? 2 : 2
                    spacing: 4
                    Label {
                        text: finder.mode === "MODULES"
                              ? appWindow.t("shipyard.find_module", "FIND MODULE")
                              : appWindow.t("shipyard.find_ship", "FIND SHIP")
                        color: cyan; font.pixelSize: 9; font.bold: true
                    }
                    TextField {
                        id: searchField
                        objectName: "qa-shipyard-query"
                        Layout.fillWidth: true
                        placeholderText: finder.mode === "MODULES"
                            ? appWindow.t("shipyard.module_hint", "Fragment Cannon, Frame Shift Drive…")
                            : appWindow.t("shipyard.ship_hint", "Python, Cobra Mk III…")
                        color: textPrimary; placeholderTextColor: muted
                        font.pixelSize: 12; selectByMouse: true
                        background: Rectangle {
                            radius: 7; color: inputBackground
                            border.width: searchField.activeFocus ? 2 : 1
                            border.color: searchField.activeFocus ? cyan : borderTone
                        }
                        onTextEdited: {
                            finder.selectedSymbol = ""
                            finder.selectedItem = ({})
                            suggestionTimer.restart()
                        }
                        Keys.onDownPressed: suggestionPopup.open()
                        Timer {
                            id: suggestionTimer
                            interval: 160; repeat: false
                            onTriggered: {
                                cockpit.requestShipyardSuggestions(finder.mode, searchField.text)
                                suggestionPopup.open()
                            }
                        }
                        Popup {
                            id: suggestionPopup
                            y: searchField.height + 4
                            width: searchField.width
                            height: Math.min(330, suggestionList.contentHeight + 12)
                            padding: 6; modal: false
                            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
                            background: Rectangle {
                                radius: 8; color: appWindow.cardRaised
                                border.width: 1; border.color: cyan
                            }
                            contentItem: ListView {
                                id: suggestionList
                                clip: true; model: finder.suggestions
                                delegate: ItemDelegate {
                                    required property var modelData
                                    width: suggestionList.width; height: 58
                                    onClicked: finder.chooseItem(modelData)
                                    contentItem: RowLayout {
                                        spacing: 9
                                        ShipSchematic {
                                            visible: finder.mode === "SHIPS"
                                            Layout.preferredWidth: visible ? 62 : 0
                                            Layout.fillHeight: true
                                            source: finder.schematicSource(modelData)
                                            tone: cyan; accent: orange; compact: true
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true; spacing: 2
                                            Label {
                                                Layout.fillWidth: true
                                                text: String(modelData.displayName || modelData.symbol || "")
                                                color: textPrimary; font.pixelSize: 11; font.bold: true
                                                elide: Text.ElideRight
                                            }
                                            Label {
                                                text: finder.mode === "MODULES"
                                                    ? [modelData.sizeRating || appWindow.t("common.unknown", "UNKNOWN"),
                                                       modelData.mount || ""].filter(Boolean).join(" · ")
                                                    : [modelData.manufacturer || "", modelData.size || ""].filter(Boolean).join(" · ")
                                                color: muted; font.pixelSize: 9
                                            }
                                        }
                                    }
                                    background: Rectangle {
                                        radius: 5; color: hovered ? appWindow.hover : "transparent"
                                    }
                                }
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    Label { text: appWindow.t("shipyard.start_system", "START SYSTEM"); color: muted; font.pixelSize: 9; font.bold: true }
                    TextField {
                        id: originField
                        Layout.fillWidth: true; text: finder.originSystem
                        color: textPrimary; font.pixelSize: 11; selectByMouse: true
                        placeholderText: appWindow.t("shipyard.current_system", "Current system")
                        placeholderTextColor: muted
                        onTextEdited: finder.originSystem = text
                        background: Rectangle {
                            radius: 7; color: inputBackground
                            border.width: originField.activeFocus ? 2 : 1
                            border.color: originField.activeFocus ? cyan : borderTone
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    Label { text: appWindow.t("shipyard.range_pad", "RANGE / PAD"); color: muted; font.pixelSize: 9; font.bold: true }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 6
                        CockpitComboBox {
                            Layout.fillWidth: true
                            model: ["25 LY", "50 LY", "100 LY", "250 LY", "500 LY"]
                            currentIndex: 2
                            onActivated: finder.rangeLy = [25, 50, 100, 250, 500][currentIndex]
                        }
                        CockpitComboBox {
                            Layout.fillWidth: true
                            model: ["ANY", "LARGE", "MEDIUM", "SMALL"]
                            onActivated: finder.padFilter = String(currentText)
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    Label { text: appWindow.t("shipyard.access_filter", "ACCESS"); color: muted; font.pixelSize: 9; font.bold: true }
                    CockpitComboBox {
                        Layout.fillWidth: true
                        model: ["SAFE + UNKNOWN", "CONFIRMED ONLY"]
                        onActivated: finder.accessFilter = String(currentText)
                    }
                }
                FinderButton {
                    objectName: "qa-shipyard-search"
                    Layout.fillWidth: true; Layout.alignment: Qt.AlignBottom
                    text: cockpit.shipyardFinderBusy
                        ? appWindow.t("shipyard.searching", "SEARCHING…")
                        : appWindow.t("shipyard.find_offers", "FIND OFFERS")
                    selected: true; enabled: !cockpit.shipyardFinderBusy
                    onClicked: finder.runSearch()
                }
            }
        }

        ShadowCard {
            Layout.fillWidth: true
            Layout.preferredHeight: 206
            accent: cyan
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 7
                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: finder.mode === "SHIPS"
                            ? appWindow.tf("shipyard.ship_catalog", "SHIP CATALOG · %1 HULLS", [finder.ships.length])
                            : appWindow.t("shipyard.module_catalog", "MODULE CATALOG · SELECT A RESULT")
                        color: cyan; font.pixelSize: 9; font.bold: true
                    }
                    Item { Layout.fillWidth: true }
                    Label {
                        text: appWindow.t("shipyard.catalog_help", "CLICK A TILE TO SELECT")
                        color: muted; font.pixelSize: 8; font.bold: true
                    }
                }
                ListView {
                    id: visualCatalog
                    Layout.fillWidth: true; Layout.fillHeight: true
                    orientation: ListView.Horizontal; spacing: 8; clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    model: finder.mode === "SHIPS" ? finder.ships : finder.suggestions
                    ScrollBar.horizontal: CockpitScrollBar {}
                    delegate: Rectangle {
                        required property var modelData
                        width: finder.mode === "SHIPS" ? 232 : 210
                        height: visualCatalog.height - 9
                        radius: 10
                        color: "transparent"
                        MouseArea { anchors.fill: parent; onClicked: finder.chooseItem(modelData) }
                        ColumnLayout {
                            anchors.fill: parent; spacing: 5
                            ShipSchematic {
                                visible: finder.mode === "SHIPS"
                                Layout.fillWidth: true; Layout.fillHeight: true
                                source: finder.schematicSource(modelData)
                                tone: cyan; accent: orange
                                selected: String(modelData.symbol || "") === finder.selectedSymbol
                            }
                            ModuleSchematic {
                                visible: finder.mode === "MODULES"
                                Layout.fillWidth: true; Layout.fillHeight: true
                                lineColor: cyan; accentColor: orange
                                surfaceColor: inputBackground
                            }
                            Label {
                                Layout.fillWidth: true
                                text: String(modelData.displayName || modelData.symbol || "")
                                color: String(modelData.symbol || "") === finder.selectedSymbol ? orange : textPrimary
                                font.pixelSize: 10; font.bold: true
                                horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                            }
                            Label {
                                Layout.fillWidth: true
                                text: finder.mode === "SHIPS"
                                    ? String(modelData.manufacturer || modelData.size || "")
                                    : [modelData.sizeRating || "", modelData.mount || ""].filter(Boolean).join(" · ")
                                color: muted; font.pixelSize: 8
                                horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                            }
                            Label {
                                Layout.fillWidth: true
                                visible: finder.mode === "SHIPS"
                                text: Number(modelData.referencePrice || 0) > 0
                                    ? finder.formatNumber(modelData.referencePrice) + " CR"
                                    : appWindow.t("shipyard.price_unknown", "PRICE UNKNOWN")
                                color: Number(modelData.referencePrice || 0) > 0 ? orange : muted
                                font.pixelSize: 9; font.bold: true
                                horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                            }
                        }
                    }
                }
            }
        }

        ScrollView {
            id: resultScroll
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true; contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical: CockpitScrollBar {}

            ColumnLayout {
                width: resultScroll.availableWidth
                spacing: 12

                GridLayout {
                    Layout.fillWidth: true
                    columns: appWindow.narrowWorkspace ? 1 : 2
                    columnSpacing: 12; rowSpacing: 12

                    ShadowCard {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 0.82
                        Layout.preferredHeight: 420
                        accent: cyan
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 15; spacing: 8
                            Label {
                                text: finder.mode === "SHIPS"
                                    ? appWindow.t("shipyard.selected_ship", "SELECTED SHIP")
                                    : appWindow.t("shipyard.selected_module", "SELECTED MODULE")
                                color: cyan; font.pixelSize: 9; font.bold: true
                            }
                            Rectangle {
                                Layout.fillWidth: true; Layout.preferredHeight: 215
                                radius: 8; color: inputBackground
                                border.width: 1; border.color: borderTone; clip: true
                                ShipSchematic {
                                    visible: finder.mode === "SHIPS"
                                    anchors.fill: parent
                                    source: finder.schematicSource(finder.selectedItem)
                                    tone: cyan; accent: orange; selected: true
                                }
                                ModuleSchematic {
                                    visible: finder.mode === "MODULES"
                                    anchors.fill: parent
                                    lineColor: cyan; accentColor: orange
                                    surfaceColor: inputBackground
                                }
                                Label {
                                    anchors.centerIn: parent
                                    visible: !finder.selectedSymbol
                                    text: appWindow.t("shipyard.choose_catalog_item", "CHOOSE AN ITEM FROM THE CATALOG")
                                    color: muted; font.pixelSize: 10; font.bold: true
                                }
                            }
                            Label {
                                Layout.fillWidth: true
                                text: String(finder.selectedItem.displayName || appWindow.t("shipyard.no_selection", "NO ITEM SELECTED"))
                                color: textPrimary; font.pixelSize: 19; font.bold: true
                                wrapMode: Text.Wrap
                            }
                            GridLayout {
                                Layout.fillWidth: true; columns: 2; columnSpacing: 7; rowSpacing: 7
                                Repeater {
                                    model: finder.mode === "SHIPS" ? [
                                        appWindow.t("shipyard.manufacturer", "MANUFACTURER") + "\n" + String(finder.selectedItem.manufacturer || "—"),
                                        appWindow.t("shipyard.hull_size", "HULL SIZE") + "\n" + String(finder.selectedItem.size || "—"),
                                        appWindow.t("shipyard.reference_price", "REFERENCE PRICE") + "\n" +
                                            (Number(finder.selectedItem.referencePrice || 0) > 0
                                             ? finder.formatNumber(finder.selectedItem.referencePrice) + " CR"
                                             : appWindow.t("shipyard.price_unknown", "PRICE UNKNOWN")),
                                        appWindow.t("shipyard.price_level", "PRICE LEVEL") + "\n" +
                                            (Number(finder.selectedItem.referencePrice || 0) > 0 ? "REFERENCE" : "UNKNOWN"),
                                        appWindow.t("shipyard.speed", "SPEED") + "\n" + String(finder.selectedItem.maximumSpeed || "—") + " M/S",
                                        appWindow.t("shipyard.boost", "BOOST") + "\n" + String(finder.selectedItem.boost || "—") + " M/S"
                                    ] : [
                                        appWindow.t("shipyard.class_rating", "CLASS / RATING") + "\n" + String(finder.selectedItem.sizeRating || "—"),
                                        appWindow.t("shipyard.mount", "MOUNT") + "\n" + String(finder.selectedItem.mount || "—"),
                                        appWindow.t("shipyard.availability", "AVAILABILITY") + "\n" + String(finder.results.length ? "OBSERVED" : "—"),
                                        appWindow.t("shipyard.best_price", "BEST PRICE") + "\n" + String(finder.results.length ? finder.priceLabel(finder.results[0]) : "—")
                                    ]
                                    delegate: Rectangle {
                                        required property string modelData
                                        Layout.fillWidth: true; Layout.preferredHeight: 43
                                        radius: 6; color: appWindow.cardRaised
                                        Label {
                                            anchors.fill: parent; anchors.margins: 6
                                            text: modelData; color: textSecondary
                                            font.pixelSize: 8; font.bold: true
                                            verticalAlignment: Text.AlignVCenter
                                        }
                                    }
                                }
                            }
                        }
                    }

                    ShadowCard {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1.55
                        Layout.preferredHeight: 420
                        accent: finder.results.length ? green : orange
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 14; spacing: 8
                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    text: appWindow.t("shipyard.best_stations", "BEST VERIFIED STATIONS")
                                    color: orange; font.pixelSize: 9; font.bold: true
                                }
                                Item { Layout.fillWidth: true }
                                Label {
                                    text: appWindow.tf("shipyard.results_count", "%1 RESULTS", [finder.results.length])
                                    color: finder.results.length ? green : muted
                                    font.pixelSize: 9; font.bold: true
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true; Layout.preferredHeight: 25
                                radius: 5; color: inputBackground
                                RowLayout {
                                    anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                                    Label { Layout.fillWidth: true; text: appWindow.t("shipyard.station_system", "STATION / SYSTEM"); color: muted; font.pixelSize: 8; font.bold: true }
                                    Label { Layout.preferredWidth: 90; text: appWindow.t("shipyard.distance", "DISTANCE"); color: muted; font.pixelSize: 8; font.bold: true }
                                    Label { Layout.preferredWidth: 124; text: appWindow.t("shipyard.access", "ACCESS"); color: muted; font.pixelSize: 8; font.bold: true }
                                    Label { Layout.preferredWidth: 105; text: appWindow.t("shipyard.price", "PRICE"); color: muted; font.pixelSize: 8; font.bold: true }
                                    Item { Layout.preferredWidth: 76 }
                                }
                            }
                            ListView {
                                id: resultList
                                Layout.fillWidth: true; Layout.fillHeight: true
                                clip: true; spacing: 6
                                model: finder.results.slice(0, 80)
                                ScrollBar.vertical: CockpitScrollBar {}
                                delegate: Rectangle {
                                    required property var modelData
                                    width: resultList.width; height: 68; radius: 8
                                    color: panelRaised
                                    border.width: index === 0 ? 2 : 1
                                    border.color: index === 0 ? orange : borderTone
                                    RowLayout {
                                        anchors.fill: parent; anchors.margins: 10; spacing: 10
                                        ColumnLayout {
                                            Layout.fillWidth: true; spacing: 2
                                            Label {
                                                Layout.fillWidth: true
                                                text: String(modelData.station || "")
                                                color: textPrimary; font.pixelSize: 10; font.bold: true
                                                elide: Text.ElideRight
                                            }
                                            Label {
                                                Layout.fillWidth: true
                                                text: String(modelData.system || "") + " · "
                                                    + String(modelData.stationType || "UNKNOWN") + " · PAD "
                                                    + String(modelData.landingPadSize || "UNKNOWN")
                                                color: muted; font.pixelSize: 8; elide: Text.ElideRight
                                            }
                                            Label {
                                                Layout.fillWidth: true
                                                text: String(modelData.accessReason || modelData.reason || "")
                                                color: finder.accessColor(modelData); font.pixelSize: 8
                                                elide: Text.ElideRight
                                            }
                                        }
                                        ColumnLayout {
                                            Layout.preferredWidth: 90; spacing: 2
                                            Label { text: finder.distanceLabel(modelData); color: textSecondary; font.pixelSize: 9; font.bold: true }
                                            Label { text: finder.arrivalLabel(modelData); color: muted; font.pixelSize: 8 }
                                        }
                                        Label {
                                            Layout.preferredWidth: 124
                                            text: String(modelData.accessStatus || "UNKNOWN")
                                            color: finder.accessColor(modelData); font.pixelSize: 8; font.bold: true
                                            wrapMode: Text.Wrap
                                        }
                                        ColumnLayout {
                                            Layout.preferredWidth: 105; spacing: 2
                                            Label { text: finder.priceLabel(modelData); color: modelData.priceStatus === "OBSERVED" ? green : orange; font.pixelSize: 9; font.bold: true }
                                            Label { text: String(modelData.priceStatus || "UNKNOWN"); color: muted; font.pixelSize: 8 }
                                        }
                                        FinderButton {
                                            Layout.preferredWidth: 76
                                            text: appWindow.t("common.copy", "COPY")
                                            onClicked: cockpit.copySystem(String(modelData.system || ""))
                                        }
                                    }
                                }
                            }
                            Label {
                                visible: finder.results.length === 0
                                Layout.fillWidth: true; Layout.fillHeight: true
                                text: finder.selectedSymbol
                                    ? String(cockpit.shipyardFinderStatus || "")
                                    : appWindow.t("shipyard.select_then_search", "Select a visual catalog item, then find offers.")
                                color: muted; font.pixelSize: 11
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true; spacing: 10
                    Repeater {
                        model: [
                            {title: appWindow.t("shipyard.source_server", "ED-FRAME SERVER"), detail: cockpit.edFrameCatalogOnline ? appWindow.t("shipyard.source_live", "ONLINE · LIVE CATALOG") : appWindow.t("shipyard.source_offline", "OFFLINE · LOCAL FALLBACK"), tone: cockpit.edFrameCatalogOnline ? finder.green : finder.orange},
                            {title: appWindow.t("shipyard.source_journal", "JOURNAL ACCESS"), detail: appWindow.tf("shipyard.journal_access_detail", "%1 PERMITS · %2 VISITED SYSTEMS", [String((finder.overview.permits || []).length), String((finder.overview.visitedSystems || []).length)]), tone: finder.cyan},
                            {title: appWindow.t("shipyard.source_price", "STATION PRICE"), detail: appWindow.t("shipyard.price_levels", "OBSERVED · ESTIMATED · UNKNOWN · REFERENCE SEPARATE"), tone: finder.orange}
                        ]
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true; Layout.preferredHeight: 54
                            radius: 8; color: panelRaised
                            border.width: 1; border.color: borderTone
                            Column {
                                anchors.fill: parent; anchors.margins: 9; spacing: 3
                                Label { text: String(modelData.title); color: modelData.tone; font.pixelSize: 8; font.bold: true }
                                Label { width: parent.width; text: String(modelData.detail); color: textSecondary; font.pixelSize: 8; elide: Text.ElideRight }
                            }
                        }
                    }
                }
                Item { Layout.preferredHeight: 6 }
            }
        }
    }
}
