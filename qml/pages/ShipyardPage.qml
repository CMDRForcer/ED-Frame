import QtQuick
import "../components/UiMetrics.js" as UiMetrics
import "../components/PresentationLabels.js" as PresentationLabels
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
    property string moduleDepartment: "ALL"
    property string moduleFamilyKey: ""
    property string moduleClassFilter: "ANY"
    property string moduleRatingFilter: "ANY"
    property string moduleMountFilter: "ANY"
    property bool fitCurrentShip: true
    property bool showIncompatibleVariants: false
    property string brokerFilter: "ALL BROKERS"
    property var selectedSlot: ({})
    readonly property string selectedModuleFitStatus: {
        var evidence = selectedItem.currentShipSlotFits || ({})
        var fit = evidence[String(selectedSlot.slot || "")]
        return String(fit ? fit.status : selectedItem.currentShipFitStatus || "UNKNOWN")
    }
    readonly property var currentShipSlots: cockpit.shipyardCurrentShipSlots || []
    readonly property var suggestions: cockpit.shipyardFinderSuggestions || []
    readonly property var ships: cockpit.shipyardShipCatalog || []
    readonly property var modules: cockpit.shipyardModuleCatalog || []
    readonly property var moduleFamilies: cockpit.shipyardModuleFamilies || []
    readonly property var results: cockpit.shipyardFinderResults || []
    readonly property var stats: cockpit.edFrameCatalogStats || ({})
    readonly property var overview: cockpit.commanderOverview || ({})
    readonly property string currentShipName: String(cockpit.shipyardCurrentShip || "")
    readonly property bool currentShipFitKnown: Boolean(cockpit.shipyardCurrentShipFitKnown)
    onCurrentShipSlotsChanged: {
        var slotId = String(selectedSlot.slot || "")
        if (slotId) {
            var rows = currentShipSlots.filter(function(row) { return String(row.slot || "") === slotId })
            selectedSlot = rows.length ? rows[0] : ({})
        }
    }
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
        if (tone === "LOCKED") return appWindow.error
        return orange
    }
    function purchaseColor(row) {
        var tone = String((row || {}).purchaseTone || "OPEN")
        if (tone === "CONFIRMED" || tone === "OPEN") return green
        if (tone === "LOCKED") return appWindow.error
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
            if (String(selectedSlot.slot || "") && !slotAllows(row) && !showIncompatibleVariants) selectedSlot = ({})
            moduleGroup = moduleBrowseGroup(row)
            if (moduleGroup === "TECH BROKER" && !matchesModuleGroup(row)) brokerFilter = "ALL BROKERS"
            moduleDepartment = String((row || {}).moduleDepartment || moduleDepartment)
            moduleFamilyKey = String((row || {}).moduleFamilyKey || moduleFamilyKey)
        }
        searchField.text = String((row || {}).displayName || selectedSymbol)
        suggestionPopup.close()
    }
    function isMiningModule(row) {
        var family = String((row || {}).moduleFamily || (row || {}).displayName || "").toUpperCase()
        return ["MINING LASER", "MINING LANCE BEAM LASER", "MINING VOLLEY REPEATER",
                "ABRASION BLASTER", "SEISMIC CHARGE LAUNCHER",
                "SUB-SURFACE DISPLACEMENT MISSILE", "SUB-SURFACE EXTRACTION MISSILE",
                "REFINERY", "PROSPECTOR LIMPET CONTROLLER", "COLLECTOR LIMPET CONTROLLER",
                "MINING MULTI-LIMPET CONTROLLER", "PULSE WAVE ANALYSER", "CARGO RACK"]
                .indexOf(family) >= 0
    }
    function moduleBrowseGroup(row) {
        var route = String((row || {}).acquisitionRoute || "")
        if (route === "TECH_BROKER") return "TECH BROKER"
        if (isMiningModule(row)) return "MINING"
        if (route === "POWERPLAY") return "POWERPLAY"
        return String((row || {}).moduleGroup || "")
    }
    function matchesModuleGroup(row) {
        if (moduleBrowseGroup(row) !== moduleGroup) return false
        if (moduleGroup !== "TECH BROKER" || brokerFilter === "ALL BROKERS") return true
        var guardian = String((row || {}).displayName || (row || {}).moduleFamily || "").toUpperCase().indexOf("GUARDIAN") >= 0
        return brokerFilter === "GUARDIAN" ? guardian : !guardian
    }
    function moduleFamilyRows() {
        var term = moduleFamilyKey ? "" : searchField ? String(searchField.text || "").trim().toLowerCase() : ""
        var matchingFamilies = ({})
        modules.forEach(function(row) {
            if (!matchesModuleGroup(row) || !slotAllows(row)) return
            if (fitCurrentShip && String(row.currentShipFitStatus || "UNKNOWN") === "INCOMPATIBLE") return
            var key = String(row.moduleFamilyKey || "")
            if (!matchingFamilies[key]) matchingFamilies[key] = []
            matchingFamilies[key].push(row)
        })
        return moduleFamilies.filter(function(row) {
            if (!matchingFamilies[String(row.moduleFamilyKey || "")]) return false
            if (!term) return true
            return String(row.moduleFamily || "").toLowerCase().indexOf(term) >= 0
        }).map(function(row) {
            var variants = matchingFamilies[String(row.moduleFamilyKey || "")]
            var classes = variants.map(function(v) { return Number(v.moduleClass) })
                .filter(function(v) { return !isNaN(v) }).sort(function(a, b) { return a - b })
            var copy = Object.assign({}, row)
            copy.variantCount = variants.length
            copy.compatibleVariantCount = variants.filter(function(v) { return v.currentShipFitStatus === "FITS" }).length
            copy.classLabel = classes.length ? "CLASS " + classes[0]
                + (classes[0] !== classes[classes.length - 1] ? "–" + classes[classes.length - 1] : "") : "CLASS UNKNOWN"
            copy.purchaseStatus = variants[0].purchaseStatus || "ACQUISITION UNKNOWN"
            copy.purchaseReason = variants[0].purchaseReason || ""
            copy.purchaseTone = variants[0].purchaseTone || "UNKNOWN"
            return copy
        }).sort(function(a, b) {
            var order = ["ARMOUR", "POWER PLANT", "THRUSTERS", "FRAME SHIFT DRIVE",
                         "FRAME SHIFT DRIVE (SCO)", "LIFE SUPPORT", "POWER DISTRIBUTOR", "SENSORS", "FUEL TANK"]
            if (moduleGroup === "CORE") {
                var ai = order.indexOf(String(a.moduleFamily || ""))
                var bi = order.indexOf(String(b.moduleFamily || ""))
                if (ai < 0) ai = order.length
                if (bi < 0) bi = order.length
                if (ai !== bi) return ai - bi
            }
            return String(a.moduleFamily || "").localeCompare(String(b.moduleFamily || ""))
        })
    }
    function moduleVariantRows() {
        return modules.filter(function(row) {
            if (!matchesModuleGroup(row)) return false
            if (String(row.moduleFamilyKey || "") !== moduleFamilyKey) return false
            if (!showIncompatibleVariants && !slotAllows(row)) return false
            if (!showIncompatibleVariants && fitCurrentShip
                    && String(row.currentShipFitStatus || "UNKNOWN") === "INCOMPATIBLE") return false
            if (moduleClassFilter !== "ANY"
                    && String(row.moduleClass || "") !== moduleClassFilter) return false
            if (moduleRatingFilter !== "ANY"
                    && String(row.moduleRating || "") !== moduleRatingFilter) return false
            if (moduleMountFilter !== "ANY"
                    && String(row.mount || "") !== moduleMountFilter) return false
            return true
        }).sort(function(a, b) {
            var classDifference = Number(a.moduleClass || 0) - Number(b.moduleClass || 0)
            if (classDifference) return classDifference
            var ratingDifference = String(a.moduleRating || "").localeCompare(String(b.moduleRating || ""))
            if (ratingDifference) return ratingDifference
            return String(a.mount || "").localeCompare(String(b.mount || ""))
        })
    }
    function slotRows() {
        var groups = { HARDPOINTS: "HARDPOINTS", UTILITY: "UTILITY MOUNTS",
                       CORE: "CORE INTERNALS", OPTIONAL: "OPTIONAL INTERNALS" }
        return currentShipSlots.filter(function(row) {
            return String(row.group || "") === groups[moduleGroup]
        })
    }
    function slotLabel(row) {
        var names = { Armour: "ARMOUR", PowerPlant: "POWER PLANT", MainEngines: "THRUSTERS",
                      FrameShiftDrive: "FRAME SHIFT DRIVE", LifeSupport: "LIFE SUPPORT",
                      PowerDistributor: "POWER DISTRIBUTOR", Radar: "SENSORS", FuelTank: "FUEL TANK" }
        var id = String(row.slot || "")
        if (names[id]) return names[id]
        if (moduleGroup === "OPTIONAL") {
            var match = /^Slot(\d+)_/.exec(id)
            return "OPTIONAL SLOT " + (match ? Number(match[1]) : id.replace(/([a-z])([A-Z])/g, "$1 $2"))
        }
        if (moduleGroup === "UTILITY") return "UTILITY " + id.replace(/\D/g, "")
        return id.replace(/([a-z])([A-Z])/g, "$1 $2")
    }
    function slotAllows(row) {
        if (!fitCurrentShip || !String(selectedSlot.slot || "")) return true
        var evidence = row.currentShipSlotFits
        if (evidence) {
            var slotFit = evidence[String(selectedSlot.slot || "")]
            return slotFit !== undefined && String(slotFit.status || "UNKNOWN") !== "INCOMPATIBLE"
        }
        if (moduleGroup === "CORE"
                && String(row.moduleCoreSlot || "") !== String(selectedSlot.slot || "")) return false
        var size = Number(row.moduleClass)
        return isNaN(size) || size <= Number(selectedSlot.slotSize || 0)
    }
    function selectSlot(row) {
        selectedSlot = row || ({})
        moduleFamilyKey = ""
        moduleDepartment = "ALL"
        moduleClassFilter = "ANY"
        moduleRatingFilter = "ANY"
        moduleMountFilter = "ANY"
        selectedSymbol = ""
        selectedItem = ({})
        searchField.text = ""
        cockpit.clearShipyardFinder()
        var families = moduleFamilyRows()
        if (moduleGroup === "CORE" && families.length === 1)
            selectModuleFamily(families[0])
    }
    function selectModuleGroup(group) {
        selectedSlot = ({})
        brokerFilter = "ALL BROKERS"
        moduleGroup = String(group || "HARDPOINTS")
        moduleDepartment = "ALL"
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
        selectedSlot = ({})
        mode = nextMode
        selectedSymbol = ""
        selectedItem = ({})
        searchField.text = ""
        if (nextMode === "MODULES") {
            moduleGroup = "HARDPOINTS"
            moduleDepartment = "ALL"
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
        if (mode === "MODULES" && fitCurrentShip && selectedModuleFitStatus === "INCOMPATIBLE") return
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
        implicitHeight: UiMetrics.controlHeight
        font.pixelSize: UiMetrics.body
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
            radius: UiMetrics.controlRadius
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
                font.pixelSize: UiMetrics.caption
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
                        color: cyan; font.pixelSize: UiMetrics.caption; font.bold: true
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
                                                Layout.fillWidth: true
                                                text: finder.mode === "MODULES"
                                                    ? [modelData.sizeRating || appWindow.t("common.unknown", "UNKNOWN"),
                                                       modelData.mount || "", modelData.purchaseStatus || "ACQUISITION UNKNOWN"].filter(Boolean).join(" · ")
                                                    : [modelData.manufacturer || "", modelData.size || ""].filter(Boolean).join(" · ")
                                                color: muted; font.pixelSize: UiMetrics.caption; elide: Text.ElideRight
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
                    Label { text: appWindow.t("shipyard.start_system", "START SYSTEM"); color: muted; font.pixelSize: UiMetrics.caption; font.bold: true }
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
                    Label { text: appWindow.t("shipyard.range_pad", "RANGE / PAD"); color: muted; font.pixelSize: UiMetrics.caption; font.bold: true }
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
                    Label { text: appWindow.t("shipyard.access_filter", "ACCESS"); color: muted; font.pixelSize: UiMetrics.caption; font.bold: true }
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
                        && !(finder.mode === "MODULES" && finder.fitCurrentShip && finder.selectedModuleFitStatus === "INCOMPATIBLE")
                    onClicked: finder.runSearch()
                }
            }
        }

        ShadowCard {
            Layout.fillWidth: true
            Layout.preferredHeight: finder.mode === "MODULES" ? 430 : 206
            accent: cyan
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 7
                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: finder.mode === "SHIPS"
                            ? appWindow.tf("shipyard.ship_catalog", "SHIP CATALOG · %1 HULLS", [finder.ships.length])
                            : finder.moduleFamilyKey === ""
                              ? "OUTFITTING · SELECT A SHIP SLOT"
                              : appWindow.t("shipyard.shop_variants", "OUTFITTING · SELECT CLASS / RATING / MOUNT")
                        color: cyan; font.pixelSize: UiMetrics.caption; font.bold: true
                    }
                    Item { Layout.fillWidth: true }
                    Label {
                        text: appWindow.t("shipyard.catalog_help", "CLICK A TILE TO SELECT")
                        color: muted; font.pixelSize: UiMetrics.caption; font.bold: true
                    }
                }
                Flow {
                    objectName: "qa-outfitting-category-flow"
                    visible: finder.mode === "MODULES"
                    Layout.fillWidth: true
                    Layout.preferredHeight: implicitHeight
                    spacing: 8
                    Label {
                        height: 42
                        verticalAlignment: Text.AlignVCenter
                        text: finder.currentShipName || "SHIP UNKNOWN"
                        color: textPrimary; font.pixelSize: 12; font.bold: true
                    }
                    CheckBox {
                        height: 42
                        text: appWindow.t("shipyard.follow_current", "Follow current ship")
                        checked: finder.fitCurrentShip
                        onToggled: {
                            finder.fitCurrentShip = checked
                            finder.selectedSlot = ({})
                        }
                    }
                    Repeater {
                        model: ["HARDPOINTS", "UTILITY", "CORE", "OPTIONAL", "MINING", "TECH BROKER", "POWERPLAY"]
                        delegate: FinderButton {
                            required property var modelData
                            width: Math.max(126, implicitWidth); height: UiMetrics.controlHeight
                            text: PresentationLabels.label(appWindow, modelData)
                            selected: finder.moduleGroup === String(modelData)
                            tone: cyan
                            onClicked: finder.selectModuleGroup(modelData)
                        }
                    }
                }
                RowLayout {
                    visible: finder.mode === "MODULES" && finder.moduleGroup === "TECH BROKER"
                    Layout.fillWidth: true; spacing: 8
                    Repeater {
                        model: ["ALL BROKERS", "HUMAN", "GUARDIAN"]
                        delegate: FinderButton {
                            required property var modelData
                            text: String(modelData); selected: finder.brokerFilter === String(modelData)
                            tone: orange; Layout.preferredHeight: 28
                            onClicked: {
                                finder.brokerFilter = String(modelData)
                                finder.backToModuleFamilies()
                                cockpit.clearShipyardFinder()
                            }
                        }
                    }
                    Item { Layout.fillWidth: true }
                }
                RowLayout {
                    visible: finder.mode === "MODULES"
                    Layout.fillWidth: true; Layout.fillHeight: true; spacing: 9

                    Rectangle {
                        Layout.preferredWidth: Math.min(390, finder.width * 0.32)
                        Layout.minimumWidth: 180
                        Layout.fillHeight: true
                        color: "transparent"; clip: true
                        ColumnLayout {
                            anchors.fill: parent; spacing: 6
                            Label {
                                text: finder.moduleGroup === "TECH BROKER" ? "TECH BROKER · " + finder.brokerFilter
                                    : finder.moduleGroup === "POWERPLAY" ? "POWERPLAY · UNLOCK REQUIRED"
                                    : finder.moduleGroup === "MINING" ? "MINING EQUIPMENT"
                                    : finder.fitCurrentShip && finder.currentShipFitKnown
                                    ? "SELECT SLOT" : finder.fitCurrentShip
                                      ? "BROWSE CATEGORIES · SLOTS UNKNOWN" : "BROWSE CATEGORIES"
                                color: cyan; font.pixelSize: UiMetrics.caption; font.bold: true
                            }
                            ListView {
                                visible: ["MINING", "TECH BROKER", "POWERPLAY"].indexOf(finder.moduleGroup) >= 0 || !finder.fitCurrentShip || !finder.currentShipFitKnown
                                Layout.fillWidth: true; Layout.fillHeight: true
                                model: finder.moduleFamilyRows()
                                clip: true; spacing: 6
                                ScrollBar.vertical: CockpitScrollBar {}
                                delegate: FinderButton {
                                    required property var modelData
                                    width: ListView.view.width - 12; height: 64
                                    text: String(modelData.moduleFamily || "MODULE")
                                        + "\n" + String(modelData.classLabel || "CLASS UNKNOWN")
                                    selected: finder.moduleFamilyKey === String(modelData.moduleFamilyKey || "")
                                    tone: orange
                                    onClicked: finder.selectModuleFamily(modelData)
                                    ToolTip.visible: hovered
                                    ToolTip.text: PresentationLabels.label(appWindow, modelData.purchaseStatus || "ACQUISITION UNKNOWN")
                                        + " · " + String(modelData.purchaseReason || "")
                                }
                            }
                            ListView {
                                Layout.fillWidth: true; Layout.fillHeight: true
                                visible: ["MINING", "TECH BROKER", "POWERPLAY"].indexOf(finder.moduleGroup) < 0 && finder.fitCurrentShip && finder.currentShipFitKnown
                                model: finder.slotRows()
                                clip: true; spacing: 5
                                ScrollBar.vertical: CockpitScrollBar {}
                                delegate: Button {
                                    id: slotControl
                                    required property var modelData
                                    property bool selected: String(finder.selectedSlot.slot || "") === String(modelData.slot || "")
                                    width: ListView.view.width - 12; height: 102
                                    background: Rectangle {
                                        radius: 5
                                        color: slotControl.selected ? panelRaised : inputBackground
                                        border.width: 1
                                        border.color: slotControl.selected ? orange : borderTone
                                        Rectangle {
                                            visible: slotControl.selected
                                            width: 3; anchors.left: parent.left
                                            anchors.top: parent.top; anchors.bottom: parent.bottom; color: orange
                                        }
                                    }
                                    contentItem: RowLayout {
                                        spacing: 10
                                        ColumnLayout {
                                            Layout.fillWidth: true; Layout.preferredWidth: 1; spacing: 5
                                            Label {
                                                Layout.fillWidth: true
                                                text: finder.slotLabel(slotControl.modelData)
                                                color: slotControl.selected ? orange : textPrimary
                                                font.pixelSize: 12; font.bold: true; wrapMode: Text.WordWrap
                                            }
                                            Label {
                                                Layout.fillWidth: true
                                                text: appWindow.tf("shipyard.slot_class", "CLASS %1", [String(slotControl.modelData.slotBadge || "—")])
                                                color: textSecondary; font.pixelSize: UiMetrics.caption; elide: Text.ElideRight
                                            }
                                        }
                                        Rectangle {
                                            Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.fillHeight: true
                                            color: inputBackground; radius: 3
                                            Label {
                                                anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 5
                                                text: slotControl.modelData.empty ? "EMPTY" : String(slotControl.modelData.sizeRating || "—")
                                                color: textPrimary; font.pixelSize: 14; font.bold: true
                                            }
                                            Label {
                                                anchors.fill: parent; anchors.margins: 8; anchors.topMargin: 25
                                                text: slotControl.modelData.empty ? "Empty slot"
                                                    : String(slotControl.modelData.module || "Unknown module")
                                                color: textSecondary; font.pixelSize: UiMetrics.caption
                                                wrapMode: Text.WordWrap
                                                verticalAlignment: Text.AlignVCenter
                                            }
                                            Label {
                                                anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 5
                                                text: slotControl.modelData.engineered ? "ENG" : ""
                                                color: orange; font.pixelSize: UiMetrics.caption
                                            }
                                        }
                                    }
                                    onClicked: finder.selectSlot(modelData)
                                    ToolTip.visible: hovered
                                    ToolTip.text: String(modelData.module || "Empty slot")
                                        + (modelData.restriction ? " · " + modelData.restriction : "")
                                }
                            }
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
                                        ? finder.moduleGroup + " › " + (finder.selectedSlot.slot ? finder.slotLabel(finder.selectedSlot) : "MODULE TYPES")
                                        : finder.moduleGroup + " › " + String(finder.selectedItem.moduleFamily || searchField.text || "")
                                    color: orange; font.pixelSize: UiMetrics.caption; font.bold: true
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: finder.moduleFamilyKey === ""
                                        ? appWindow.tf("shipyard.family_count", "%1 MODULE FAMILIES", [finder.moduleFamilyRows().length])
                                        : appWindow.tf("shipyard.variant_count", "%1 COMPATIBLE VARIANTS", [finder.moduleVariantRows().length])
                                    color: muted; font.pixelSize: UiMetrics.caption; font.bold: true
                                }
                                Label {
                                    Layout.fillWidth: true
                                    visible: String(finder.selectedSlot.slot || "") !== ""
                                    text: appWindow.t("shipyard.installed_prefix", "INSTALLED: ") + (finder.selectedSlot.empty ? "EMPTY"
                                        : String(finder.selectedSlot.sizeRating || "") + " "
                                          + String(finder.selectedSlot.module || "UNKNOWN"))
                                        + (finder.selectedSlot.engineered ? " · ENGINEERED (CURRENT ONLY)" : "")
                                        + " · CHECK RESULTS IN COMPARISON"
                                        + (finder.selectedSlot.restriction ? " · " + finder.selectedSlot.restriction : "")
                                    color: green; font.pixelSize: UiMetrics.caption; wrapMode: Text.WordWrap
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
                        CheckBox {
                            visible: finder.moduleFamilyKey !== "" && finder.fitCurrentShip
                            text: appWindow.t("shipyard.compare_all", "COMPARE ALL CLASSES · SHOW INCOMPATIBLE")
                            checked: finder.showIncompatibleVariants
                            onToggled: finder.showIncompatibleVariants = checked
                        }
                        GridView {
                            id: moduleFamilyGrid
                            visible: finder.moduleFamilyKey === ""
                                && finder.fitCurrentShip && finder.currentShipFitKnown
                                && String(finder.selectedSlot.slot || "") !== ""
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
                                ToolTip.visible: familyMouse.containsMouse
                                ToolTip.text: String(modelData.purchaseReason || "")
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
                                            color: textPrimary; font.pixelSize: UiMetrics.caption; font.bold: true
                                            elide: Text.ElideRight
                                        }
                                        Label {
                                            Layout.fillWidth: true
                                            text: [modelData.classLabel || "",
                                                   appWindow.tf("shipyard.module_variants", "%1 VARIANTS", [Number(modelData.variantCount || 0)])]
                                                  .filter(Boolean).join(" · ")
                                            color: orange; font.pixelSize: UiMetrics.caption; font.bold: true
                                            elide: Text.ElideRight
                                        }
                                        Label {
                                            Layout.fillWidth: true
                                            text: finder.fitCurrentShip && finder.currentShipFitKnown
                                                ? appWindow.tf("shipyard.compatible_variants", "%1 FIT CURRENT SHIP",
                                                               [Number(modelData.compatibleVariantCount || 0)])
                                                : String(modelData.mountLabel || modelData.moduleGroupLabel || "")
                                            color: finder.fitCurrentShip ? green : muted; font.pixelSize: UiMetrics.caption
                                            elide: Text.ElideRight
                                        }
                                        Label {
                                            Layout.fillWidth: true
                                            text: PresentationLabels.label(appWindow, modelData.purchaseStatus || "ACQUISITION UNKNOWN")
                                            color: finder.purchaseColor(modelData); font.pixelSize: UiMetrics.caption
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
                        Label {
                            Layout.fillWidth: true; Layout.fillHeight: true
                            visible: finder.moduleFamilyKey === ""
                                && (!finder.fitCurrentShip || !finder.currentShipFitKnown
                                    || String(finder.selectedSlot.slot || "") === "")
                            text: appWindow.t("shipyard.compare_hint", "SELECT A MODULE TYPE OR SLOT ON THE LEFT\nThen choose class, rating and mount.\nOr use the module search above.")
                            color: textSecondary; font.pixelSize: 13
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            wrapMode: Text.WordWrap
                        }
                        ListView {
                            id: moduleVariantGrid
                            objectName: "qa-module-comparison-list"
                            visible: finder.moduleFamilyKey !== ""
                            Layout.fillWidth: true; Layout.fillHeight: true
                            clip: true; boundsBehavior: Flickable.StopAtBounds
                            spacing: 6
                            header: RowLayout {
                                width: moduleVariantGrid.width; height: 30; spacing: 8
                                Label { Layout.preferredWidth: 60; text: appWindow.t("shipyard.compare_class", "CLASS"); color: muted; font.pixelSize: UiMetrics.caption }
                                Label { Layout.fillWidth: true; text: appWindow.t("shipyard.compare_module", "MODULE / MOUNT / ACQUISITION"); color: muted; font.pixelSize: UiMetrics.caption }
                                Label { Layout.preferredWidth: 150; text: appWindow.t("shipyard.compare_fit", "INSTALLATION CHECK"); color: muted; font.pixelSize: UiMetrics.caption }
                                Label { Layout.preferredWidth: 120; text: appWindow.t("shipyard.compare_reference", "REFERENCE · NOT STATION"); color: muted; font.pixelSize: UiMetrics.caption; wrapMode: Text.WordWrap }
                            }
                            model: finder.moduleVariantRows()
                            ScrollBar.vertical: CockpitScrollBar {}
                            delegate: Rectangle {
                                objectName: "qa-module-comparison-row"
                                id: variantRow
                                required property var modelData
                                readonly property var slotEvidence: finder.fitCurrentShip && finder.selectedSlot.slot
                                    ? (modelData.currentShipSlotFits || ({}))[String(finder.selectedSlot.slot)] : null
                                width: moduleVariantGrid.width - 12
                                height: 82
                                radius: 8; color: panelRaised
                                border.width: String(modelData.symbol || "") === finder.selectedSymbol ? 2 : 1
                                border.color: String(modelData.symbol || "") === finder.selectedSymbol
                                              ? orange : variantMouse.containsMouse ? cyan : borderTone
                                ToolTip.visible: variantMouse.containsMouse
                                ToolTip.text: String(variantRow.slotEvidence ? variantRow.slotEvidence.reason : modelData.currentShipFitReason || "")
                                    + "\n" + String(variantRow.slotEvidence ? variantRow.slotEvidence.powerWarning : modelData.powerWarning || "Power budget not verified")
                                    + "\n" + String(modelData.purchaseReason || "Acquisition unknown")
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
                                            color: textPrimary; font.pixelSize: 11; font.bold: true
                                            elide: Text.ElideRight
                                        }
                                        Label {
                                            Layout.fillWidth: true
                                            text: [modelData.mount || "",
                                                   modelData.moduleGroupLabel || ""].filter(Boolean).join(" · ")
                                            color: muted; font.pixelSize: UiMetrics.caption
                                            elide: Text.ElideRight
                                        }
                                        Label {
                                            Layout.fillWidth: true
                                            text: PresentationLabels.label(appWindow, modelData.purchaseStatus || "ACQUISITION UNKNOWN")
                                            color: finder.purchaseColor(modelData); font.pixelSize: UiMetrics.caption
                                            elide: Text.ElideRight
                                        }
                                    }
                                    ColumnLayout {
                                        Layout.preferredWidth: 150; spacing: 4
                                        readonly property var fitEvidence: variantRow.slotEvidence
                                        readonly property string fitStatus: !finder.fitCurrentShip ? "NOT CHECKED"
                                            : String(fitEvidence ? fitEvidence.status : modelData.currentShipFitStatus || "UNKNOWN")
                                        Label {
                                            Layout.fillWidth: true
                                            text: parent.fitStatus === "FITS" ? appWindow.t("shipyard.fit_yes", "FITS SLOT") : parent.fitStatus === "INCOMPATIBLE" ? appWindow.t("shipyard.fit_no", "DOES NOT FIT") : appWindow.t("shipyard.fit_unknown", "NOT VERIFIED")
                                            color: parent.fitStatus === "FITS" ? (appWindow.green || "#69e1b5") : parent.fitStatus === "INCOMPATIBLE" ? appWindow.error : orange
                                            font.pixelSize: UiMetrics.caption; font.bold: true; elide: Text.ElideRight
                                        }
                                        Label { Layout.fillWidth: true; text: appWindow.t("shipyard.compare_power", "POWER · SEE DETAILS"); color: muted; font.pixelSize: UiMetrics.caption }
                                    }
                                    Label {
                                        Layout.preferredWidth: 120
                                        text: modelData.referencePrice !== undefined && modelData.referencePrice !== null && Number(modelData.referencePrice) >= 0
                                            ? finder.formatNumber(modelData.referencePrice) + " CR" : "PRICE UNKNOWN"
                                        color: modelData.referencePrice !== undefined && modelData.referencePrice !== null ? orange : muted
                                        font.pixelSize: 11; elide: Text.ElideRight
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
                                      ? appWindow.error
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
                                        color: muted; font.pixelSize: UiMetrics.caption; font.bold: true
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
                                font.pixelSize: UiMetrics.caption; font.bold: true
                                horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                            }
                            Label {
                                Layout.fillWidth: true
                                text: finder.mode === "SHIPS"
                                    ? String(modelData.manufacturer || modelData.size || "")
                                    : [modelData.sizeRating || "", modelData.mount || ""].filter(Boolean).join(" · ")
                                color: muted; font.pixelSize: UiMetrics.caption
                                horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                            }
                            Label {
                                Layout.fillWidth: true
                                visible: finder.mode === "SHIPS"
                                text: Number(modelData.referencePrice || 0) > 0
                                    ? "REFERENCE · " + finder.formatNumber(modelData.referencePrice) + " CR"
                                    : appWindow.t("shipyard.price_unknown", "PRICE UNKNOWN")
                                color: Number(modelData.referencePrice || 0) > 0 ? orange : muted
                                font.pixelSize: UiMetrics.caption; font.bold: true
                                horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                            }
                            Label {
                                Layout.fillWidth: true
                                visible: finder.mode === "SHIPS"
                                text: PresentationLabels.label(appWindow, modelData.purchaseStatus || "OPEN")
                                color: finder.purchaseColor(modelData)
                                font.pixelSize: UiMetrics.caption; font.bold: true
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
                                color: cyan; font.pixelSize: UiMetrics.caption; font.bold: true
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
                                        text: PresentationLabels.label(appWindow, finder.selectedItem.moduleGroupLabel || "SELECT A SHOP CATEGORY")
                                        color: cyan; font.pixelSize: 11; font.bold: true
                                        horizontalAlignment: Text.AlignHCenter
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: [finder.selectedItem.moduleFamily || "",
                                               finder.selectedItem.mount || ""].filter(Boolean).join(" · ")
                                        color: textSecondary; font.pixelSize: UiMetrics.caption
                                        horizontalAlignment: Text.AlignHCenter
                                        elide: Text.ElideRight
                                    }
                                    Item { Layout.fillHeight: true }
                                }
                                Label {
                                    anchors.centerIn: parent
                                    visible: !finder.selectedSymbol
                                    text: appWindow.t("shipyard.choose_catalog_item", "CHOOSE AN ITEM FROM THE CATALOG")
                                    color: muted; font.pixelSize: UiMetrics.caption; font.bold: true
                                }
                            }
                            Label {
                                Layout.fillWidth: true
                                text: String(finder.selectedItem.displayName || appWindow.t("shipyard.no_selection", "NO ITEM SELECTED"))
                                color: textPrimary; font.pixelSize: 19; font.bold: true
                                wrapMode: Text.Wrap
                            }
                            Rectangle {
                                visible: finder.selectedSymbol !== ""
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.max(48, purchaseExplanation.implicitHeight + 16)
                                radius: 6
                                color: String(finder.selectedItem.purchaseTone || "") === "LOCKED"
                                       ? Qt.rgba(1.0, 0.20, 0.30, 0.13)
                                       : String(finder.selectedItem.purchaseTone || "") === "UNKNOWN"
                                         ? Qt.rgba(1.0, 0.65, 0.20, 0.08)
                                         : Qt.rgba(0.20, 0.85, 0.55, 0.08)
                                border.width: 1
                                border.color: finder.purchaseColor(finder.selectedItem)
                                Label {
                                    id: purchaseExplanation
                                    anchors.fill: parent; anchors.margins: 7
                                    text: PresentationLabels.label(appWindow, finder.selectedItem.purchaseStatus || "ACQUISITION UNKNOWN")
                                          + " · " + String(finder.selectedItem.purchaseReason || "")
                                    color: finder.purchaseColor(finder.selectedItem)
                                    font.pixelSize: UiMetrics.caption; font.bold: true
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
                                            text: PresentationLabels.label(appWindow, modelData); color: textSecondary
                                            font.pixelSize: UiMetrics.caption; font.bold: true
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
                                    color: orange; font.pixelSize: UiMetrics.caption; font.bold: true
                                }
                                Item { Layout.fillWidth: true }
                                Label {
                                    text: appWindow.tf("shipyard.results_count", "%1 RESULTS", [finder.results.length])
                                    color: finder.results.length ? green : muted
                                    font.pixelSize: UiMetrics.caption; font.bold: true
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true; Layout.preferredHeight: 25
                                radius: 5; color: inputBackground
                                RowLayout {
                                    anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                                    Label { Layout.fillWidth: true; text: appWindow.t("shipyard.station_system", "STATION / SYSTEM"); color: muted; font.pixelSize: UiMetrics.caption; font.bold: true }
                                    Label { Layout.preferredWidth: 90; text: appWindow.t("shipyard.distance", "DISTANCE"); color: muted; font.pixelSize: UiMetrics.caption; font.bold: true }
                                    Label { Layout.preferredWidth: 124; text: appWindow.t("shipyard.access", "ACCESS"); color: muted; font.pixelSize: UiMetrics.caption; font.bold: true }
                                    Label { Layout.preferredWidth: 105; text: appWindow.t("shipyard.price", "PRICE"); color: muted; font.pixelSize: UiMetrics.caption; font.bold: true }
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
                                                  ? appWindow.error
                                                  : index === 0 ? orange : borderTone
                                    RowLayout {
                                        anchors.fill: parent; anchors.margins: 10; spacing: 10
                                        ColumnLayout {
                                            Layout.fillWidth: true; spacing: 2
                                            Label {
                                                Layout.fillWidth: true
                                                text: String(modelData.station || "")
                                                color: textPrimary; font.pixelSize: UiMetrics.caption; font.bold: true
                                                elide: Text.ElideRight
                                            }
                                            Label {
                                                Layout.fillWidth: true
                                                text: String(modelData.system || "") + " · "
                                                    + String(modelData.stationType || "UNKNOWN") + " · PAD "
                                                    + String(modelData.landingPadSize || "UNKNOWN")
                                                color: muted; font.pixelSize: UiMetrics.caption; elide: Text.ElideRight
                                            }
                                            Label {
                                                Layout.fillWidth: true
                                                text: String(modelData.recommendationReason || modelData.reason || "")
                                                color: String(modelData.accessTone || "") === "LOCKED"
                                                       ? finder.accessColor(modelData) : textSecondary
                                                font.pixelSize: UiMetrics.caption; font.bold: true
                                                elide: Text.ElideRight
                                            }
                                            Label {
                                                Layout.fillWidth: true
                                                text: String(modelData.accessReason || modelData.reason || "")
                                                color: finder.accessColor(modelData); font.pixelSize: UiMetrics.caption
                                                elide: Text.ElideRight
                                            }
                                        }
                                        ColumnLayout {
                                            Layout.preferredWidth: 90; spacing: 2
                                            Label { text: finder.distanceLabel(modelData); color: textSecondary; font.pixelSize: UiMetrics.caption; font.bold: true }
                                            Label { text: finder.arrivalLabel(modelData); color: muted; font.pixelSize: UiMetrics.caption }
                                        }
                                        Label {
                                            Layout.preferredWidth: 124
                                            text: PresentationLabels.label(appWindow, modelData.accessStatus || "UNKNOWN")
                                            color: finder.accessColor(modelData); font.pixelSize: UiMetrics.caption; font.bold: true
                                            wrapMode: Text.Wrap
                                        }
                                        ColumnLayout {
                                            Layout.preferredWidth: 105; spacing: 2
                                            Label { text: finder.priceLabel(modelData); color: finder.priceColor(modelData); font.pixelSize: UiMetrics.caption; font.bold: true }
                                            Label { text: PresentationLabels.label(appWindow, modelData.priceStatus || "UNKNOWN"); color: finder.priceColor(modelData); font.pixelSize: UiMetrics.caption; font.bold: true }
                                            Label { text: String(modelData.dataAgeLabel || "AGE UNKNOWN"); color: muted; font.pixelSize: UiMetrics.caption }
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
                                Label { text: String(modelData.title); color: modelData.tone; font.pixelSize: UiMetrics.caption; font.bold: true }
                                Label { width: parent.width; text: String(modelData.detail); color: textSecondary; font.pixelSize: UiMetrics.caption; elide: Text.ElideRight }
                            }
                        }
                    }
                }
                Item { Layout.preferredHeight: 6 }
            }
        }
    }
}
