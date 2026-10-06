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
    property string accessFilter: "ALL · SHOW LOCKED"
    property string moduleGroup: "HARDPOINTS"
    property string moduleDepartment: "LASERS"
    property string moduleFamilyKey: ""
    property string moduleClassFilter: "ANY"
    property string moduleRatingFilter: "ANY"
    property string moduleMountFilter: "ANY"
    property bool fitCurrentShip: true
    readonly property var suggestions: cockpit.shipyardFinderSuggestions || []
    readonly property var ships: cockpit.shipyardShipCatalog || []
    readonly property var modules: cockpit.shipyardModuleCatalog || []
    readonly property var moduleFamilies: cockpit.shipyardModuleFamilies || []
    readonly property var results: cockpit.shipyardFinderResults || []
    readonly property var stats: cockpit.edFrameCatalogStats || ({})
    readonly property var overview: cockpit.commanderOverview || ({})
    readonly property string currentShipName: String(cockpit.shipyardCurrentShip || "")
    readonly property bool currentShipFitKnown: Boolean(cockpit.shipyardCurrentShipFitKnown)
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
    function purchaseColor(row) {
        var tone = String((row || {}).purchaseTone || "OPEN")
        if (tone === "CONFIRMED" || tone === "OPEN") return green
        if (tone === "LOCKED") return appWindow.red || "#ff586f"
        return orange
    }
    function priceColor(row) {
        var status = String((row || {}).priceStatus || "UNKNOWN")
        if (status === "OBSERVED" || status === "PURCHASE CONFIRMED") return green
        if (status === "ESTIMATED" || status === "DISCOUNTED" || status === "STATION RULE") return orange
        if (status === "REFERENCE") return cyan
        return muted
    }
    function schematicSource(row) {
        var path = String((row || {}).schematicSource || "")
        return path ? Qt.resolvedUrl("../../" + path) : ""
    }
    function chooseItem(row) {
        selectedItem = row || ({})
        selectedSymbol = String((row || {}).symbol || "")
        if (String((row || {}).kind || "") === "MODULES") {
            moduleGroup = String((row || {}).moduleGroup || moduleGroup)
            moduleDepartment = String((row || {}).moduleDepartment || moduleDepartment)
            moduleFamilyKey = String((row || {}).moduleFamilyKey || moduleFamilyKey)
            Qt.callLater(function() { moduleVariantGrid.positionViewAtBeginning() })
        }
        searchField.text = String((row || {}).displayName || selectedSymbol)
        suggestionPopup.close()
    }
    function moduleFamilyRows() {
        var term = searchField ? String(searchField.text || "").trim().toLowerCase() : ""
        return moduleFamilies.filter(function(row) {
            if (String(row.moduleGroup || "") !== moduleGroup) return false
            if (moduleDepartment !== "ALL"
                    && String(row.moduleDepartment || "SUPPORT") !== moduleDepartment) return false
            if (fitCurrentShip
                    && String(row.currentShipFitStatus || "UNKNOWN") === "INCOMPATIBLE") return false
            if (!term) return true
            return String(row.moduleFamily || "").toLowerCase().indexOf(term) >= 0
        })
    }
    function moduleVariantRows() {
        return modules.filter(function(row) {
            if (String(row.moduleGroup || "") !== moduleGroup) return false
            if (String(row.moduleFamilyKey || "") !== moduleFamilyKey) return false
            if (fitCurrentShip
                    && String(row.currentShipFitStatus || "UNKNOWN") === "INCOMPATIBLE") return false
            if (moduleClassFilter !== "ANY"
                    && String(row.moduleClass || "") !== moduleClassFilter) return false
            if (moduleRatingFilter !== "ANY"
                    && String(row.moduleRating || "") !== moduleRatingFilter) return false
            if (moduleMountFilter !== "ANY"
                    && String(row.mount || "") !== moduleMountFilter) return false
            return true
        })
    }
    function moduleDepartments(group) {
        if (group === "HARDPOINTS")
            return ["LASERS", "KINETIC", "EXPLOSIVE", "EXPERIMENTAL", "MINING"]
        if (group === "UTILITY")
            return ["DEFENCE", "SCANNERS", "SUPPORT"]
        if (group === "CORE")
            return ["POWER", "PROPULSION", "NAVIGATION", "SUPPORT"]
        return ["CARGO", "PROTECTION", "LIMPETS", "PASSENGER", "EXPLORATION", "SUPPORT"]
    }
    function defaultModuleDepartment(group) {
        var rows = moduleDepartments(group)
        return rows.length ? String(rows[0]) : "ALL"
    }
    function selectModuleGroup(group) {
        moduleGroup = String(group || "HARDPOINTS")
        moduleDepartment = defaultModuleDepartment(moduleGroup)
        moduleFamilyKey = ""
        moduleClassFilter = "ANY"
        moduleRatingFilter = "ANY"
        moduleMountFilter = "ANY"
        selectedSymbol = ""
        selectedItem = ({})
        searchField.text = ""
        cockpit.clearShipyardFinder()
        Qt.callLater(function() { moduleFamilyGrid.positionViewAtBeginning() })
    }
    function selectModuleDepartment(department) {
        moduleDepartment = String(department || "ALL")
        moduleFamilyKey = ""
        selectedSymbol = ""
        selectedItem = ({})
        searchField.text = ""
        cockpit.clearShipyardFinder()
        Qt.callLater(function() { moduleFamilyGrid.positionViewAtBeginning() })
    }
    function selectModuleFamily(row) {
        moduleFamilyKey = String((row || {}).moduleFamilyKey || "")
        selectedSymbol = ""
        selectedItem = ({})
        searchField.text = String((row || {}).moduleFamily || "")
        cockpit.clearShipyardFinder()
        Qt.callLater(function() { moduleVariantGrid.positionViewAtBeginning() })
    }
    function backToModuleFamilies() {
        moduleFamilyKey = ""
        selectedSymbol = ""
        selectedItem = ({})
        searchField.text = ""
        cockpit.clearShipyardFinder()
    }
    function resetMode(nextMode) {
        mode = nextMode
        selectedSymbol = ""
        selectedItem = ({})
        searchField.text = ""
        if (nextMode === "MODULES") {
            moduleGroup = "HARDPOINTS"
            moduleDepartment = "LASERS"
            moduleFamilyKey = ""
            moduleClassFilter = "ANY"
            moduleRatingFilter = "ANY"
            moduleMountFilter = "ANY"
        }
        cockpit.clearShipyardFinder()
        cockpit.requestShipyardSuggestions(nextMode, "")
        if (nextMode === "SHIPS")
            Qt.callLater(function() { visualCatalog.positionViewAtBeginning() })
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
                            height: Math.min(430, suggestionList.contentHeight + 12)
                            padding: 6; modal: false
                            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
                            background: Rectangle {
                                radius: 8; color: appWindow.cardRaised
                                border.width: 1; border.color: cyan
                            }
                            contentItem: ListView {
                                id: suggestionList
                                clip: true; model: finder.suggestions
                                boundsBehavior: Flickable.StopAtBounds
                                ScrollBar.vertical: CockpitScrollBar {}
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
                                        Rectangle {
                                            visible: finder.mode === "MODULES"
                                            Layout.preferredWidth: visible ? 62 : 0
                                            Layout.fillHeight: true
                                            radius: 5; color: inputBackground
                                            border.width: 1; border.color: cyan
                                            Label {
                                                anchors.centerIn: parent
                                                text: String(modelData.sizeRating || "—")
                                                color: orange; font.pixelSize: 15; font.bold: true
                                            }
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
                        model: ["ALL · SHOW LOCKED", "ACCESSIBLE ONLY"]
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
            Layout.preferredHeight: finder.mode === "MODULES" ? 282 : 206
            accent: cyan
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 7
                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: finder.mode === "SHIPS"
                            ? appWindow.tf("shipyard.ship_catalog", "SHIP CATALOG · %1 HULLS", [finder.ships.length])
                            : finder.moduleFamilyKey === ""
                              ? appWindow.t("shipyard.shop_categories", "OUTFITTING · SHOP CATEGORIES")
                              : appWindow.t("shipyard.shop_variants", "OUTFITTING · SELECT CLASS / RATING / MOUNT")
                        color: cyan; font.pixelSize: 9; font.bold: true
                    }
                    Item { Layout.fillWidth: true }
                    Label {
                        text: appWindow.t("shipyard.catalog_help", "CLICK A TILE TO SELECT")
                        color: muted; font.pixelSize: 8; font.bold: true
                    }
                }
                RowLayout {
                    visible: finder.mode === "MODULES"
                    Layout.fillWidth: true; Layout.fillHeight: true; spacing: 9

                    Rectangle {
                        Layout.preferredWidth: 238; Layout.fillHeight: true
                        radius: 8; color: inputBackground
                        border.width: 1; border.color: borderTone; clip: true
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 8; spacing: 4
                            FinderButton {
                                Layout.fillWidth: true; Layout.preferredHeight: 30
                                text: finder.fitCurrentShip
                                    ? appWindow.tf("shipyard.follow_current", "FOLLOW CURRENT · %1",
                                                   [finder.currentShipName || "SHIP UNKNOWN"])
                                    : appWindow.t("shipyard.show_all_modules", "SHOW ALL MODULES")
                                selected: finder.fitCurrentShip; tone: finder.currentShipFitKnown ? green : orange
                                onClicked: {
                                    finder.fitCurrentShip = !finder.fitCurrentShip
                                    moduleFamilyGrid.positionViewAtBeginning()
                                    moduleVariantGrid.positionViewAtBeginning()
                                }
                                ToolTip.visible: hovered
                                ToolTip.text: finder.currentShipFitKnown
                                    ? appWindow.t("shipyard.follow_current_help", "Automatically follows the active Journal ship and hides modules that cannot fit its physical slots.")
                                    : appWindow.t("shipyard.follow_current_unknown", "Current ship slots are unknown. No modules are hidden.")
                            }
                            Label {
                                Layout.fillWidth: true
                                text: finder.currentShipFitKnown
                                    ? appWindow.t("shipyard.slots_verified", "JOURNAL SLOTS VERIFIED")
                                    : appWindow.t("shipyard.slots_unknown", "SLOTS UNKNOWN · NOTHING HIDDEN")
                                color: finder.currentShipFitKnown ? green : orange
                                font.pixelSize: 7; font.bold: true; elide: Text.ElideRight
                            }
                            GridLayout {
                                Layout.fillWidth: true; columns: 2; columnSpacing: 5; rowSpacing: 5
                                Repeater {
                                    model: [
                                        {key: "HARDPOINTS", label: "HARDPOINTS"},
                                        {key: "UTILITY", label: "UTILITY"},
                                        {key: "CORE", label: "CORE"},
                                        {key: "OPTIONAL", label: "OPTIONAL"}
                                    ]
                                    delegate: FinderButton {
                                        required property var modelData
                                        Layout.fillWidth: true; Layout.preferredHeight: 27
                                        text: String(modelData.label)
                                        selected: finder.moduleGroup === String(modelData.key)
                                        tone: cyan
                                        onClicked: finder.selectModuleGroup(modelData.key)
                                    }
                                }
                            }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: borderTone }
                            Label {
                                text: appWindow.t("shipyard.departments", "DEPARTMENTS")
                                color: cyan; font.pixelSize: 8; font.bold: true
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 2; columnSpacing: 4; rowSpacing: 4
                                Repeater {
                                    model: finder.moduleDepartments(finder.moduleGroup)
                                    delegate: FinderButton {
                                        required property var modelData
                                        Layout.fillWidth: true; Layout.preferredHeight: 25
                                        text: String(modelData)
                                        selected: finder.moduleDepartment === String(modelData)
                                        tone: orange
                                        onClicked: finder.selectModuleDepartment(modelData)
                                    }
                                }
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true; Layout.fillHeight: true; spacing: 7
                        RowLayout {
                            Layout.fillWidth: true; spacing: 7
                            FinderButton {
                                visible: finder.moduleFamilyKey !== ""
                                Layout.preferredWidth: 84
                                text: appWindow.t("common.back", "‹ BACK")
                                tone: orange
                                onClicked: finder.backToModuleFamilies()
                            }
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 1
                                Label {
                                    Layout.fillWidth: true
                                    text: finder.moduleFamilyKey === ""
                                        ? finder.moduleGroup + " › " + finder.moduleDepartment
                                        : finder.moduleGroup + " › " + finder.moduleDepartment
                                          + " › " + String(finder.selectedItem.moduleFamily || searchField.text || "")
                                    color: orange; font.pixelSize: 10; font.bold: true
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: finder.moduleFamilyKey === ""
                                        ? appWindow.tf("shipyard.family_count", "%1 MODULE FAMILIES", [finder.moduleFamilyRows().length])
                                        : appWindow.tf("shipyard.variant_count", "%1 COMPATIBLE VARIANTS", [finder.moduleVariantRows().length])
                                    color: muted; font.pixelSize: 7; font.bold: true
                                }
                            }
                            CockpitComboBox {
                                visible: finder.moduleFamilyKey !== ""
                                Layout.preferredWidth: 105
                                model: ["ANY", "0", "1", "2", "3", "4", "5", "6", "7", "8"]
                                currentIndex: Math.max(0, model.indexOf(finder.moduleClassFilter))
                                onActivated: {
                                    finder.moduleClassFilter = String(currentText)
                                    moduleVariantGrid.positionViewAtBeginning()
                                }
                            }
                            CockpitComboBox {
                                visible: finder.moduleFamilyKey !== ""
                                Layout.preferredWidth: 105
                                model: ["ANY", "A", "B", "C", "D", "E", "F", "G", "H", "I"]
                                currentIndex: Math.max(0, model.indexOf(finder.moduleRatingFilter))
                                onActivated: {
                                    finder.moduleRatingFilter = String(currentText)
                                    moduleVariantGrid.positionViewAtBeginning()
                                }
                            }
                            CockpitComboBox {
                                visible: finder.moduleFamilyKey !== ""
                                Layout.preferredWidth: 132
                                model: ["ANY", "FIXED", "GIMBALLED", "TURRETED"]
                                currentIndex: Math.max(0, model.indexOf(finder.moduleMountFilter))
                                onActivated: {
                                    finder.moduleMountFilter = String(currentText)
                                    moduleVariantGrid.positionViewAtBeginning()
                                }
                            }
                        }
                        GridView {
                            id: moduleFamilyGrid
                            visible: finder.moduleFamilyKey === ""
                            Layout.fillWidth: true; Layout.fillHeight: true
                            clip: true; boundsBehavior: Flickable.StopAtBounds
                            cellWidth: Math.max(205, width / 4)
                            cellHeight: 76
                            model: finder.moduleFamilyRows()
                            ScrollBar.vertical: CockpitScrollBar {}
                            delegate: Rectangle {
                                required property var modelData
                                width: moduleFamilyGrid.cellWidth - 8
                                height: moduleFamilyGrid.cellHeight - 7
                                radius: 8; color: panelRaised
                                border.width: 1; border.color: familyMouse.containsMouse ? orange : borderTone
                                Rectangle {
                                    anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
                                    width: 4; radius: 2; color: cyan
                                }
                                RowLayout {
                                    anchors.fill: parent; anchors.margins: 9; spacing: 9
                                    Rectangle {
                                        Layout.preferredWidth: 42; Layout.fillHeight: true
                                        radius: 5; color: inputBackground
                                        border.width: 1; border.color: cyan
                                        Label {
                                            anchors.centerIn: parent
                                            text: String(modelData.moduleFamily || "?").slice(0, 2)
                                            color: cyan; font.pixelSize: 13; font.bold: true
                                        }
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 2
                                        Label {
                                            Layout.fillWidth: true
                                            text: String(modelData.moduleFamily || "MODULE")
                                            color: textPrimary; font.pixelSize: 10; font.bold: true
                                            elide: Text.ElideRight
                                        }
                                        Label {
                                            Layout.fillWidth: true
                                            text: [modelData.classLabel || "",
                                                   appWindow.tf("shipyard.module_variants", "%1 VARIANTS", [Number(modelData.variantCount || 0)])]
                                                  .filter(Boolean).join(" · ")
                                            color: orange; font.pixelSize: 8; font.bold: true
                                            elide: Text.ElideRight
                                        }
                                        Label {
                                            Layout.fillWidth: true
                                            text: finder.fitCurrentShip && finder.currentShipFitKnown
                                                ? appWindow.tf("shipyard.compatible_variants", "%1 FIT CURRENT SHIP",
                                                               [Number(modelData.compatibleVariantCount || 0)])
                                                : String(modelData.mountLabel || modelData.moduleGroupLabel || "")
                                            color: finder.fitCurrentShip ? green : muted; font.pixelSize: 7
                                            elide: Text.ElideRight
                                        }
                                    }
                                }
                                MouseArea {
                                    id: familyMouse
                                    anchors.fill: parent; hoverEnabled: true
                                    onClicked: finder.selectModuleFamily(modelData)
                                }
                            }
                        }
                        GridView {
                            id: moduleVariantGrid
                            visible: finder.moduleFamilyKey !== ""
                            Layout.fillWidth: true; Layout.fillHeight: true
                            clip: true; boundsBehavior: Flickable.StopAtBounds
                            cellWidth: Math.max(168, width / 6)
                            cellHeight: 82
                            model: finder.moduleVariantRows()
                            ScrollBar.vertical: CockpitScrollBar {}
                            delegate: Rectangle {
                                required property var modelData
                                width: moduleVariantGrid.cellWidth - 8
                                height: moduleVariantGrid.cellHeight - 7
                                radius: 8; color: panelRaised
                                border.width: String(modelData.symbol || "") === finder.selectedSymbol ? 2 : 1
                                border.color: String(modelData.symbol || "") === finder.selectedSymbol
                                              ? orange : variantMouse.containsMouse ? cyan : borderTone
                                ToolTip.visible: variantMouse.containsMouse
                                ToolTip.text: String(modelData.currentShipFitReason || "")
                                RowLayout {
                                    anchors.fill: parent; anchors.margins: 8; spacing: 8
                                    Rectangle {
                                        Layout.preferredWidth: 52; Layout.fillHeight: true
                                        radius: 5; color: inputBackground
                                        border.width: 1; border.color: cyan
                                        Label {
                                            anchors.centerIn: parent
                                            text: String(modelData.sizeRating || "—")
                                            color: orange; font.pixelSize: 17; font.bold: true
                                        }
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 2
                                        Label {
                                            Layout.fillWidth: true
                                            text: String(modelData.displayName || modelData.symbol || "")
                                            color: textPrimary; font.pixelSize: 9; font.bold: true
                                            elide: Text.ElideRight
                                        }
                                        Label {
                                            Layout.fillWidth: true
                                            text: [modelData.mount || "",
                                                   modelData.moduleGroupLabel || ""].filter(Boolean).join(" · ")
                                            color: muted; font.pixelSize: 7
                                            elide: Text.ElideRight
                                        }
                                    }
                                }
                                MouseArea {
                                    id: variantMouse
                                    anchors.fill: parent; hoverEnabled: true
                                    onClicked: finder.chooseItem(modelData)
                                }
                            }
                        }
                    }
                }
                ListView {
                    id: visualCatalog
                    visible: finder.mode === "SHIPS"
                    Layout.fillWidth: true; Layout.fillHeight: true
                    orientation: ListView.Horizontal; spacing: 8; clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    model: finder.ships
                    ScrollBar.horizontal: CockpitScrollBar {}
                    delegate: Rectangle {
                        id: catalogTile
                        required property var modelData
                        readonly property bool rankLocked:
                            String(modelData.purchaseTone || "") === "LOCKED"
                        width: finder.mode === "SHIPS" ? 232 : 188
                        height: visualCatalog.height - 9
                        radius: 10
                        color: panelRaised
                        border.width: catalogTile.rankLocked ? 2 : 1
                        border.color: catalogTile.rankLocked
                                      ? (appWindow.red || "#ff586f")
                                      : String(modelData.symbol || "") === finder.selectedSymbol
                                        ? orange : borderTone
                        ToolTip.visible: catalogMouse.containsMouse
                                             && String(modelData.purchaseReason || "") !== ""
                        ToolTip.text: String(modelData.purchaseReason || "")
                        ToolTip.delay: 350
                        MouseArea {
                            id: catalogMouse
                            anchors.fill: parent; hoverEnabled: true; z: 5
                            onClicked: finder.chooseItem(modelData)
                        }
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 3; spacing: 5
                            ShipSchematic {
                                visible: finder.mode === "SHIPS"
                                Layout.fillWidth: true; Layout.fillHeight: true
                                source: finder.schematicSource(modelData)
                                tone: cyan; accent: orange
                                selected: String(modelData.symbol || "") === finder.selectedSymbol
                            }
                            Rectangle {
                                visible: finder.mode === "MODULES"
                                Layout.fillWidth: true; Layout.fillHeight: true
                                radius: 7; color: inputBackground
                                border.width: 1
                                border.color: String(modelData.symbol || "") === finder.selectedSymbol
                                              ? orange : cyan
                                ColumnLayout {
                                    anchors.fill: parent; anchors.margins: 8; spacing: 2
                                    Item { Layout.fillHeight: true }
                                    Label {
                                        Layout.alignment: Qt.AlignHCenter
                                        text: String(modelData.sizeRating || "—")
                                        color: orange; font.pixelSize: 24
                                        font.bold: true
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: String(modelData.mount || modelData.moduleGroupLabel || "")
                                        color: muted; font.pixelSize: 8; font.bold: true
                                        horizontalAlignment: Text.AlignHCenter
                                        elide: Text.ElideRight
                                    }
                                    Item { Layout.fillHeight: true }
                                }
                            }
                            Label {
                                Layout.fillWidth: true
                                text: String(modelData.displayName || modelData.moduleFamily || modelData.symbol || "")
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
                                    ? "REFERENCE · " + finder.formatNumber(modelData.referencePrice) + " CR"
                                    : appWindow.t("shipyard.price_unknown", "PRICE UNKNOWN")
                                color: Number(modelData.referencePrice || 0) > 0 ? orange : muted
                                font.pixelSize: 9; font.bold: true
                                horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                            }
                            Label {
                                Layout.fillWidth: true
                                visible: finder.mode === "SHIPS"
                                text: String(modelData.purchaseStatus || "OPEN")
                                color: finder.purchaseColor(modelData)
                                font.pixelSize: 8; font.bold: true
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
                        Layout.preferredHeight: finder.mode === "SHIPS" ? 510 : 470
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
                                Layout.fillWidth: true; Layout.preferredHeight: 178
                                radius: 8; color: inputBackground
                                border.width: 1; border.color: borderTone; clip: true
                                ShipSchematic {
                                    visible: finder.mode === "SHIPS"
                                    anchors.fill: parent
                                    source: finder.schematicSource(finder.selectedItem)
                                    tone: cyan; accent: orange; selected: true
                                }
                                ColumnLayout {
                                    visible: finder.mode === "MODULES"
                                    anchors.fill: parent
                                    anchors.margins: 18; spacing: 5
                                    Item { Layout.fillHeight: true }
                                    Label {
                                        Layout.alignment: Qt.AlignHCenter
                                        text: String(finder.selectedItem.sizeRating || "—")
                                        color: orange; font.pixelSize: 42; font.bold: true
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: String(finder.selectedItem.moduleGroupLabel || "SELECT A SHOP CATEGORY")
                                        color: cyan; font.pixelSize: 11; font.bold: true
                                        horizontalAlignment: Text.AlignHCenter
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: [finder.selectedItem.moduleFamily || "",
                                               finder.selectedItem.mount || ""].filter(Boolean).join(" · ")
                                        color: textSecondary; font.pixelSize: 10
                                        horizontalAlignment: Text.AlignHCenter
                                        elide: Text.ElideRight
                                    }
                                    Item { Layout.fillHeight: true }
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
                            Rectangle {
                                visible: finder.mode === "SHIPS" && finder.selectedSymbol !== ""
                                Layout.fillWidth: true; Layout.preferredHeight: 38
                                radius: 6
                                color: String(finder.selectedItem.purchaseTone || "") === "LOCKED"
                                       ? Qt.rgba(1.0, 0.20, 0.30, 0.13)
                                       : Qt.rgba(0.20, 0.85, 0.55, 0.08)
                                border.width: 1
                                border.color: finder.purchaseColor(finder.selectedItem)
                                Label {
                                    anchors.fill: parent; anchors.margins: 7
                                    text: String(finder.selectedItem.purchaseStatus || "OPEN")
                                          + " · " + String(finder.selectedItem.purchaseReason || "")
                                    color: finder.purchaseColor(finder.selectedItem)
                                    font.pixelSize: 8; font.bold: true
                                    wrapMode: Text.Wrap; verticalAlignment: Text.AlignVCenter
                                }
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
                                        appWindow.t("shipyard.schematic_type", "MODULE TYPE") + "\n" + String(finder.selectedItem.schematicKind || "—").replace("_", " "),
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
                        Layout.preferredHeight: finder.mode === "SHIPS" ? 510 : 470
                        accent: finder.results.length ? green : orange
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 14; spacing: 8
                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    text: appWindow.t("shipyard.best_stations", "MATCHED STATIONS · ACCESS EXPLAINED")
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
                                    required property int index
                                    width: resultList.width; height: 84; radius: 8
                                    color: String(modelData.accessTone || "") === "LOCKED"
                                           ? Qt.rgba(1.0, 0.20, 0.30, 0.09) : panelRaised
                                    border.width: index === 0 || String(modelData.accessTone || "") === "LOCKED" ? 2 : 1
                                    border.color: String(modelData.accessTone || "") === "LOCKED"
                                                  ? (appWindow.red || "#ff586f")
                                                  : index === 0 ? orange : borderTone
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
                                                text: String(modelData.recommendationReason || modelData.reason || "")
                                                color: String(modelData.accessTone || "") === "LOCKED"
                                                       ? finder.accessColor(modelData) : textSecondary
                                                font.pixelSize: 8; font.bold: true
                                                elide: Text.ElideRight
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
                                            Label { text: finder.priceLabel(modelData); color: finder.priceColor(modelData); font.pixelSize: 9; font.bold: true }
                                            Label { text: String(modelData.priceStatus || "UNKNOWN"); color: finder.priceColor(modelData); font.pixelSize: 8; font.bold: true }
                                            Label { text: String(modelData.dataAgeLabel || "AGE UNKNOWN"); color: muted; font.pixelSize: 7 }
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
                            {title: appWindow.t("shipyard.source_price", "SHIP PRICE"), detail: appWindow.t("shipyard.price_levels", "FIXED REFERENCE · STATION RULE · PURCHASE CONFIRMED"), tone: finder.orange}
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
