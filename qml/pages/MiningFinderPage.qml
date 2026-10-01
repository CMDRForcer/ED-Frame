import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: miningFinderPage
    required property var appWindow
    required property real sidebarWidth

    property string commodityFilter: "Platinum"
    property string startSystem: String(cockpit.system || "")
    property string miningMethod: "LASER"
    property string optimization: "POWERPLAY MERITS"
    property string ringFilter: "ANY RING"
    property string reserveFilter: "ALL RESERVES"
    property string landingPad: "LARGE"
    property string powerGoal: "REINFORCE"
    property string powerOverride: ""
    property int nearbyLy: 250
    property int resultLimit: 30
    property int minDemand: 5000
    property int maxDemand: 500000
    property int maxMarketAgeHours: 1
    property string opposingPower: "ANY"
    property string systemState: "ANY"
    property bool preferRes: true
    property bool requireHotspot: false
    property bool preferSecondary: false
    property bool requireSystemState: false
    property string appliedCommodityFilter: "Platinum"
    property string appliedStartSystem: String(cockpit.system || "")
    property string appliedMiningMethod: "LASER"
    property string appliedOptimization: "POWERPLAY MERITS"
    property string appliedRingFilter: "ANY RING"
    property string appliedReserveFilter: "ALL RESERVES"
    property string appliedLandingPad: "LARGE"
    property string appliedPowerGoal: "REINFORCE"
    property string appliedPower: ""
    property int appliedNearbyLy: 250
    property int appliedResultLimit: 30
    property int appliedMinDemand: 5000
    property int appliedMaxDemand: 500000
    property int appliedMaxMarketAgeHours: 1
    property string appliedOpposingPower: "ANY"
    property string appliedSystemState: "ANY"
    property bool appliedPreferRes: true
    property bool appliedRequireHotspot: false
    property bool appliedPreferSecondary: false
    property bool appliedRequireSystemState: false
    property int searchRevision: 0
    property int _miningRevisionSnapshot: cockpit.miningRevision
    property real _listScrollY: 0
    property int selectedRouteIndex: 0
    readonly property int activeRouteIndex: resultRows.length
            ? Math.max(0, Math.min(selectedRouteIndex,
                                   resultRows.length - 1)) : 0

    readonly property var powerplay: cockpit.powerplayOverview || ({})
    readonly property string powerName: String(powerplay.power || "")
    readonly property var powerOptions: {
        let detected = powerName || appWindow.t("mining.power_unknown", "UNCONFIRMED")
        let rows = [
            "Aisling Duval", "Arissa Lavigny-Duval", "Denton Patreus",
            "Zemina Torval", "Felicia Winters", "Jerome Archer",
            "Edmund Mahon", "Nakato Kaine", "Pranav Antal",
            "Archon Delaine", "Yuri Grom", "Li Yong-Rui"
        ]
        let result = [detected]
        for (let index = 0; index < rows.length; ++index)
            if (rows[index] !== detected) result.push(rows[index])
        return result
    }
    readonly property var opposingPowerOptions: {
        let result = ["ANY"]
        for (let index = 0; index < powerOptions.length; ++index) {
            let value = String(powerOptions[index] || "")
            if (value && value !== "UNCONFIRMED"
                    && value !== (powerOverride || powerName))
                result.push(value)
        }
        return result
    }
    readonly property var systemStateOptions: [
        "ANY", "NONE", "BOOM", "BUST", "CIVIL LIBERTY", "CIVIL UNREST",
        "CIVIL WAR", "ELECTION", "EXPANSION", "FAMINE", "INVESTMENT",
        "LOCKDOWN", "OUTBREAK", "PUBLIC HOLIDAY", "RETREAT", "WAR"
    ]
    readonly property var readiness: cockpit.miningLoadoutReadiness(miningMethod)
    readonly property var commodityOptions: {
        let revision = _miningRevisionSnapshot
        return cockpit.miningCommodityFiltersForMethod(miningMethod)
    }
    readonly property var ringOptions: {
        let revision = _miningRevisionSnapshot
        return cockpit.miningRingFiltersForCommodity(
                    commodityFilter, miningMethod)
    }
    readonly property var resultRows: {
        let revision = _miningRevisionSnapshot + searchRevision
        return cockpit.miningPlanRoutes(
                    appliedStartSystem, appliedCommodityFilter, appliedNearbyLy,
                    appliedReserveFilter, appliedRingFilter,
                    appliedMiningMethod,
                    appliedOptimization, appliedMinDemand, appliedMaxDemand,
                    appliedMaxMarketAgeHours, appliedResultLimit,
                    appliedRequireHotspot, appliedPreferRes,
                    appliedPreferSecondary, appliedRequireSystemState,
                    appliedLandingPad, appliedPower || powerName,
                    appliedPowerGoal, appliedOpposingPower,
                    appliedSystemState)
    }
    readonly property var bestRoute: resultRows.length
            ? resultRows[activeRouteIndex] : ({})
    readonly property var alternativeRows: {
        let rows = []
        for (let index = 0; index < resultRows.length; ++index)
            if (index !== activeRouteIndex) rows.push(resultRows[index])
        return rows
    }

    readonly property color cyan: appWindow.cyan
    readonly property color green: appWindow.green
    readonly property color orange: appWindow.orange
    readonly property color textPrimary: appWindow.textPrimary
    readonly property color textSecondary: appWindow.textSecondary
    readonly property color muted: appWindow.muted
    readonly property color panelRaised: appWindow.panelRaised
    readonly property color backgroundSecondary: appWindow.backgroundSecondary
    readonly property color inputBackground: appWindow.inputBackground
    readonly property color borderTone: appWindow.borderTone
    readonly property color divider: appWindow.divider
    readonly property color warningBackground: appWindow.warningBackground
    readonly property color successBackground: appWindow.successBackground
    readonly property string monoFont: "Consolas"
    readonly property real pageMargin: appWindow.compactSidebar ? 18 : 26
    readonly property real availableWorkspaceWidth: Math.max(
        0, width - sidebarWidth - pageMargin * 2)
    readonly property bool compactFilters: availableWorkspaceWidth < 1180

    objectName: "qa-page-mining-finder"
    anchors.fill: parent

    function displayOptimization(value) {
        if (value === "POWERPLAY MERITS") return appWindow.t("mining.optimize_merits", "POWERPLAY MERITS")
        if (value === "BEST YIELD") return appWindow.t("mining.optimize_yield", "BEST YIELD")
        if (value === "HIGHEST PROFIT") return appWindow.t("mining.optimize_profit", "HIGHEST PROFIT")
        return appWindow.t("mining.optimize_distance", "SHORTEST ROUTE")
    }
    function formatNumber(value) {
        return Number(value || 0).toLocaleString(Qt.locale(), "f", 0)
    }
    function formatDistance(value) {
        return value === null || value === undefined
                ? appWindow.t("status.distance_unknown", "Unknown")
                : Number(value).toLocaleString(Qt.locale(), "f", 1) + " LY"
    }
    function formatAge(seconds) {
        if (seconds === null || seconds === undefined)
            return appWindow.t("mining.market_age_unknown", "AGE UNKNOWN")
        if (seconds < 60) return Math.max(1, Math.round(seconds)) + " S"
        if (seconds < 3600) return Math.round(seconds / 60) + " MIN"
        return Math.round(seconds / 3600) + " H"
    }
    function marketName(row) {
        return row.marketKnown
                ? String(row.station || row.sellSystem || "MARKET CONFIRMED")
                : appWindow.t("mining.market_missing", "NO VERIFIED MARKET DATA")
    }
    function marketDetail(row) {
        if (!row.marketKnown)
            return appWindow.t("mining.market_missing_help", "Mining location remains usable · profit and merit ratings stay unknown")
        return formatNumber(row.sellPrice) + " CR/T  ·  "
                + (row.demandInfinite
                   ? appWindow.t("mining.demand_infinite", "∞ DEMAND")
                   : appWindow.tf("mining.demand_value", "%1 T DEMAND", [formatNumber(row.demand)]))
                + "  ·  " + formatAge(row.marketAgeSeconds)
    }
    function routeIndex(row) {
        for (let index = 0; index < resultRows.length; ++index) {
            let candidate = resultRows[index]
            if (String(candidate.system) === String(row.system)
                    && String(candidate.ring) === String(row.ring)
                    && String(candidate.station) === String(row.station)
                    && String(candidate.sellSystem) === String(row.sellSystem))
                return index
        }
        return -1
    }
    function selectRoute(row) {
        let index = routeIndex(row)
        if (index >= 0) selectedRouteIndex = index
    }
    function resetForMethod() {
        let rows = cockpit.miningCommodityFiltersForMethod(miningMethod)
        commodityFilter = rows.indexOf("Platinum") >= 0
                ? "Platinum" : (rows.length > 1 ? rows[1] : rows[0])
        if (miningMethod === "RHINO SURFACE") {
            reserveFilter = "ALL RESERVES"
            requireHotspot = false
        } else {
            reserveFilter = "ALL RESERVES"
            requireHotspot = false
        }
        resetRingFilter()
    }
    function resetRingFilter() {
        let rows = cockpit.miningRingFiltersForCommodity(
                    commodityFilter, miningMethod)
        ringFilter = rows.indexOf("ANY RING") >= 0
                ? "ANY RING" : (rows.length ? rows[0] : "ANY RING")
    }
    function applySearch() {
        appliedStartSystem = startSystem.trim() || String(cockpit.system || "")
        appliedCommodityFilter = commodityFilter
        appliedMiningMethod = miningMethod
        appliedOptimization = optimization
        appliedRingFilter = ringFilter
        appliedReserveFilter = reserveFilter
        appliedLandingPad = landingPad
        appliedPowerGoal = powerGoal
        appliedPower = powerOverride || powerName
        appliedNearbyLy = nearbyLy
        appliedResultLimit = resultLimit
        appliedMinDemand = minDemand
        appliedMaxDemand = maxDemand
        appliedMaxMarketAgeHours = maxMarketAgeHours
        appliedOpposingPower = opposingPower
        appliedSystemState = systemState
        appliedPreferRes = preferRes
        appliedRequireHotspot = requireHotspot
        appliedPreferSecondary = preferSecondary
        appliedRequireSystemState = systemState !== "ANY"
        selectedRouteIndex = 0
        searchRevision += 1
    }
    function executeSearch() {
        applySearch()
        cockpit.refreshMiningMarkets(
                    appliedStartSystem, appliedCommodityFilter,
                    appliedNearbyLy, appliedMinDemand,
                    appliedMaxMarketAgeHours, appliedLandingPad)
        _miningRevisionSnapshot = cockpit.miningRevision
    }

    Connections {
        target: cockpit
        function onMiningChanged() {
            if (!cockpit.miningMarketSyncBusy)
                miningFinderPage._miningRevisionSnapshot = cockpit.miningRevision
        }
    }

    component SmoothFilterSlider: ColumnLayout {
        id: sliderField
        property string labelText: ""
        property string suffix: ""
        property real minimumValue: 0
        property real maximumValue: 100
        property real increment: 1
        property real committedValue: minimumValue
        readonly property bool dragging: smoothSlider.pressed
        readonly property real displayedValue: {
            let steps = Math.round(
                    (smoothSlider.value - minimumValue) / increment)
            return Math.max(minimumValue, Math.min(
                                maximumValue,
                                minimumValue + steps * increment))
        }
        signal valueCommitted(real amount)

        Layout.fillWidth: true
        Layout.minimumWidth: 0
        Layout.preferredWidth: 1
        spacing: 1

        RowLayout {
            Layout.fillWidth: true
            Label {
                text: sliderField.labelText
                color: muted; font.pixelSize: 8; font.bold: true
            }
            Item { Layout.fillWidth: true }
            Label {
                text: miningFinderPage.formatNumber(
                          sliderField.displayedValue) + sliderField.suffix
                color: orange; font.pixelSize: 9; font.bold: true
            }
        }
        Slider {
            id: smoothSlider
            Layout.fillWidth: true
            implicitHeight: 24
            from: sliderField.minimumValue
            to: sliderField.maximumValue
            stepSize: sliderField.increment
            snapMode: Slider.NoSnap
            live: true
            value: sliderField.committedValue
            onPressedChanged: {
                if (!pressed)
                    sliderField.valueCommitted(sliderField.displayedValue)
            }
        }
    }

    Timer {
        interval: 2000
        repeat: true
        running: appWindow.currentPage === 12
        onTriggered: {
            if (commodityBox.popup.visible || methodBox.popup.visible
                    || optimizationBox.popup.visible || powerBox.popup.visible
                    || reserveBox.popup.visible || opposingPowerBox.popup.visible
                    || systemStateBox.popup.visible
                    || padBox.popup.visible || goalBox.popup.visible
                    || radiusSlider.dragging || resultCountSlider.dragging
                    || demandSlider.dragging || maxDemandSlider.dragging
                    || marketAgeSlider.dragging
                    || routesList.moving || routesList.dragging)
                return
            miningFinderPage._miningRevisionSnapshot = cockpit.miningRevision
        }
    }

    ColumnLayout {
        id: pageContent
        objectName: "qa-mining-content"
        width: Math.min(miningFinderPage.availableWorkspaceWidth, 1580)
        x: miningFinderPage.sidebarWidth + miningFinderPage.pageMargin
           + Math.max(0, (miningFinderPage.availableWorkspaceWidth - width) / 2)
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: miningFinderPage.pageMargin
        anchors.bottomMargin: miningFinderPage.pageMargin
        spacing: 10

    WorkspaceHeader {
        qaName: "qa-mining-header"
        Layout.minimumHeight: miningFinderPage.compactFilters ? 104 : 76
        Layout.maximumHeight: miningFinderPage.compactFilters ? 104 : 76
        appWindow: miningFinderPage.appWindow
        eyebrow: appWindow.t("mining.eyebrow", "UNIVERSAL MINING PLANNER")
        title: appWindow.t("mining.title", "MINING FINDER")
        subtitle: appWindow.t("mining.subtitle_unified", "One finder for targeted mining, yield, profit, short routes and Powerplay merits")
        statusText: cockpit.miningSyncBusy
                    ? appWindow.t("mining.refreshing", "REFRESHING…")
                    : appWindow.tf("mining.live_results", "%1 RESULTS", [resultRows.length])
        statusTone: cockpit.miningSyncBusy ? orange : green
    }

    Rectangle {
        objectName: "qa-mining-config"
        Layout.fillWidth: true
        Layout.minimumHeight: miningFinderPage.compactFilters ? 650 : 430
        Layout.preferredHeight: miningFinderPage.compactFilters ? 650 : 430
        Layout.maximumHeight: miningFinderPage.compactFilters ? 650 : 430
        radius: 12
        color: panelRaised
        border.width: 1
        border.color: orange

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 13
            spacing: 9

            RowLayout {
                Layout.fillWidth: true
                Label { text: appWindow.t("mining.define_goal", "1 · DEFINE SEARCH GOAL"); color: orange; font.pixelSize: 11; font.bold: true }
                Item { Layout.fillWidth: true }
                Label {
                    text: appWindow.t("mining.one_search_note", "ONE SEARCH · WEIGHTED BY YOUR GOAL")
                    color: muted; font.pixelSize: 9; font.bold: true
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: divider }

            GridLayout {
                Layout.fillWidth: true
                columns: miningFinderPage.compactFilters ? 2 : 5
                uniformCellWidths: true
                columnSpacing: 9
                rowSpacing: 8
                ColumnLayout {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 4
                    Label { text: appWindow.t("mining.start_system", "START SYSTEM"); color: muted; font.pixelSize: 9; font.bold: true }
                    TextField {
                        id: startSystemField
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        implicitHeight: 38
                        text: miningFinderPage.startSystem
                        placeholderText: cockpit.system
                                         || appWindow.t("status.unknown", "UNKNOWN")
                        selectByMouse: true
                        maximumLength: 96
                        leftPadding: 11
                        rightPadding: 11
                        color: textPrimary
                        font.pixelSize: 11
                        onTextEdited: miningFinderPage.startSystem = text
                        onAccepted: miningFinderPage.executeSearch()
                        background: Rectangle {
                            radius: 7
                            color: inputBackground
                            border.width: startSystemField.activeFocus ? 2 : 1
                            border.color: startSystemField.activeFocus
                                          ? cyan : borderTone
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 4
                    Label { text: appWindow.t("mining.target_commodity", "TARGET COMMODITY"); color: muted; font.pixelSize: 9; font.bold: true }
                    CockpitComboBox {
                        id: commodityBox; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; implicitHeight: 38
                        model: miningFinderPage.commodityOptions
                        currentIndex: Math.max(0, model.indexOf(miningFinderPage.commodityFilter))
                        onActivated: {
                            miningFinderPage.commodityFilter = currentText
                            miningFinderPage.resetRingFilter()
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 4
                    Label { text: appWindow.t("mining.method", "MINING METHOD"); color: muted; font.pixelSize: 9; font.bold: true }
                    CockpitComboBox {
                        id: methodBox; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; implicitHeight: 38
                        model: ["LASER", "CORE", "SUBSURFACE", "RHINO SURFACE"]
                        currentIndex: model.indexOf(miningFinderPage.miningMethod)
                        onActivated: { miningFinderPage.miningMethod = currentText; miningFinderPage.resetForMethod() }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 4
                    Label { text: appWindow.t("mining.optimize_for", "OPTIMIZE FOR"); color: orange; font.pixelSize: 9; font.bold: true }
                    CockpitComboBox {
                        id: optimizationBox; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; implicitHeight: 38
                        model: ["POWERPLAY MERITS", "BEST YIELD", "HIGHEST PROFIT", "SHORTEST ROUTE"]
                        currentIndex: model.indexOf(miningFinderPage.optimization)
                        onActivated: miningFinderPage.optimization = currentText
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 4
                    Label { text: appWindow.t("mining.power_merits", "POWER · FOR MERITS"); color: muted; font.pixelSize: 9; font.bold: true }
                    CockpitComboBox {
                        id: powerBox
                        Layout.fillWidth: true; Layout.minimumWidth: 0
                        Layout.preferredWidth: 1; implicitHeight: 38
                        model: miningFinderPage.powerOptions
                        currentIndex: powerOverride
                                      ? Math.max(0, model.indexOf(powerOverride)) : 0
                        onActivated: miningFinderPage.powerOverride =
                                         currentIndex === 0 ? "" : currentText
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: divider }
            GridLayout {
                Layout.fillWidth: true
                columns: miningFinderPage.compactFilters ? 1 : 2
                columnSpacing: 16
                rowSpacing: 8

                ColumnLayout {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 6
                    Label {
                        text: appWindow.t("mining.range_market_group", "2 · RANGE AND MARKET QUALITY")
                        color: cyan; font.pixelSize: 9; font.bold: true
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        uniformCellWidths: true
                        columnSpacing: 12
                        rowSpacing: 6
                        SmoothFilterSlider {
                            id: radiusSlider
                            labelText: appWindow.t("mining.search_radius", "SEARCH RADIUS")
                            suffix: " LY"
                            minimumValue: 25; maximumValue: 500; increment: 25
                            committedValue: miningFinderPage.nearbyLy
                            onValueCommitted: amount => miningFinderPage.nearbyLy = amount
                        }
                        SmoothFilterSlider {
                            id: resultCountSlider
                            labelText: appWindow.t("mining.result_count", "RESULTS")
                            minimumValue: 5; maximumValue: 100; increment: 5
                            committedValue: miningFinderPage.resultLimit
                            onValueCommitted: amount => miningFinderPage.resultLimit = amount
                        }
                        SmoothFilterSlider {
                            id: demandSlider
                            labelText: appWindow.t("mining.min_demand", "MIN. DEMAND")
                            suffix: " T"
                            minimumValue: 0; maximumValue: 25000; increment: 1000
                            committedValue: miningFinderPage.minDemand
                            onValueCommitted: amount => miningFinderPage.minDemand = amount
                        }
                        SmoothFilterSlider {
                            id: maxDemandSlider
                            labelText: appWindow.t("mining.max_demand", "MAX. DEMAND")
                            suffix: " T"
                            minimumValue: 0; maximumValue: 500000; increment: 5000
                            committedValue: miningFinderPage.maxDemand
                            onValueCommitted: amount => miningFinderPage.maxDemand = amount
                        }
                        SmoothFilterSlider {
                            id: marketAgeSlider
                            labelText: appWindow.t("mining.max_market_age", "MAX. MARKET AGE")
                            suffix: " H"
                            minimumValue: 1; maximumValue: 168; increment: 1
                            committedValue: miningFinderPage.maxMarketAgeHours
                            onValueCommitted: amount => miningFinderPage.maxMarketAgeHours = amount
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 6
                    Label {
                        text: appWindow.t("mining.ring_ship_power_group", "3 · RING, SHIP AND POWERPLAY")
                        color: cyan; font.pixelSize: 9; font.bold: true
                    }
                    GridLayout {
                        Layout.fillWidth: true; columns: 2; uniformCellWidths: true; columnSpacing: 7; rowSpacing: 7
                        ColumnLayout {
                            Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 2
                            Label { text: appWindow.t("mining.ring_type", "RING TYPE"); color: muted; font.pixelSize: 8; font.bold: true }
                            CockpitComboBox {
                                id: ringBox; Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 34
                                model: miningFinderPage.ringOptions
                                currentIndex: model.indexOf(miningFinderPage.ringFilter)
                                onActivated: miningFinderPage.ringFilter = currentText
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 2
                            Label { text: appWindow.t("mining.reserve_quality", "RESERVE QUALITY"); color: muted; font.pixelSize: 8; font.bold: true }
                            CockpitComboBox {
                                id: reserveBox; Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 34
                                model: ["PRISTINE + MAJOR", "PRISTINE", "MAJOR", "ALL RESERVES"]
                                currentIndex: model.indexOf(miningFinderPage.reserveFilter)
                                onActivated: miningFinderPage.reserveFilter = currentText
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 2
                            Label { text: appWindow.t("mining.landing_pad", "LANDING PAD"); color: muted; font.pixelSize: 8; font.bold: true }
                            CockpitComboBox {
                                id: padBox; Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 34
                                model: ["LARGE", "MEDIUM", "ANY"]
                                currentIndex: model.indexOf(miningFinderPage.landingPad)
                                onActivated: miningFinderPage.landingPad = currentText
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 2
                            Label { text: appWindow.t("mining.powerplay_goal", "POWERPLAY GOAL"); color: muted; font.pixelSize: 8; font.bold: true }
                            CockpitComboBox {
                                id: goalBox; Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 34
                                model: ["REINFORCE", "ACQUIRE", "UNDERMINE"]
                                currentIndex: model.indexOf(miningFinderPage.powerGoal)
                                onActivated: miningFinderPage.powerGoal = currentText
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 2
                            Label { text: appWindow.t("mining.opposing_power", "OPPOSING POWER"); color: muted; font.pixelSize: 8; font.bold: true }
                            CockpitComboBox {
                                id: opposingPowerBox; Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 34
                                model: miningFinderPage.opposingPowerOptions
                                enabled: miningFinderPage.powerGoal === "UNDERMINE"
                                opacity: enabled ? 1.0 : 0.45
                                currentIndex: Math.max(0, model.indexOf(miningFinderPage.opposingPower))
                                onActivated: miningFinderPage.opposingPower = currentText
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 2
                            Label { text: appWindow.t("mining.system_state", "SYSTEM STATE"); color: muted; font.pixelSize: 8; font.bold: true }
                            CockpitComboBox {
                                id: systemStateBox; Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 34
                                model: miningFinderPage.systemStateOptions
                                currentIndex: Math.max(0, model.indexOf(miningFinderPage.systemState))
                                onActivated: miningFinderPage.systemState = currentText
                            }
                        }
                    }
                    Flow {
                        Layout.fillWidth: true
                        Layout.preferredHeight: childrenRect.height
                        spacing: 7
                        Button {
                            text: appWindow.t("mining.prefer_res", "RES PREFERRED")
                            checkable: true; checked: miningFinderPage.preferRes
                            onClicked: miningFinderPage.preferRes = checked
                            background: Rectangle { radius: 6; color: parent.checked ? orange : inputBackground; border.width: 1; border.color: parent.checked ? orange : borderTone }
                            contentItem: Label { text: parent.text; color: parent.checked ? "#17100a" : textPrimary; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; font.pixelSize: 9; font.bold: true }
                        }
                        Button {
                            text: appWindow.t("mining.hotspot_required", "HOTSPOT REQUIRED")
                            checkable: true; checked: miningFinderPage.requireHotspot
                            enabled: miningFinderPage.miningMethod !== "RHINO SURFACE"
                            opacity: enabled ? 1.0 : 0.45
                            onClicked: miningFinderPage.requireHotspot = checked
                            background: Rectangle { radius: 6; color: parent.checked ? orange : inputBackground; border.width: 1; border.color: parent.checked ? orange : borderTone }
                            contentItem: Label { text: parent.text; color: parent.checked ? "#17100a" : textPrimary; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; font.pixelSize: 9; font.bold: true }
                        }
                        Button {
                            text: appWindow.t("mining.secondary_preferred", "MORE RESOURCES")
                            checkable: true; checked: miningFinderPage.preferSecondary
                            onClicked: miningFinderPage.preferSecondary = checked
                            background: Rectangle { radius: 6; color: parent.checked ? orange : inputBackground; border.width: 1; border.color: parent.checked ? orange : borderTone }
                            contentItem: Label { text: parent.text; color: parent.checked ? "#17100a" : textPrimary; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; font.pixelSize: 9; font.bold: true }
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Label {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 1
                    text: appWindow.tf("mining.search_summary", "4 · CALCULATE · %1 · %2 · %3 · %4 LY · DEMAND ≥ %5 T", [commodityFilter, miningMethod, displayOptimization(optimization), nearbyLy, formatNumber(minDemand)])
                    color: textSecondary; font.pixelSize: 9; elide: Text.ElideRight
                }
                Button {
                    id: findRouteButton
                    Layout.minimumWidth: 180; Layout.preferredWidth: 220; Layout.maximumWidth: 220; implicitHeight: 38
                    text: appWindow.t("mining.find_best_route", "FIND BEST ROUTE")
                    onClicked: {
                        miningFinderPage.executeSearch()
                    }
                    contentItem: Label {
                        text: findRouteButton.text; color: "#17100a"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.pixelSize: 10; font.bold: true
                    }
                    background: Rectangle {
                        radius: 7
                        color: findRouteButton.down ? Qt.darker(orange, 1.12) : orange
                    }
                }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.minimumHeight: 30
        Layout.preferredHeight: 30
        Layout.maximumHeight: 30
        spacing: 15
        Label { text: "● " + appWindow.t("mining.journal_current", "JOURNAL CURRENT"); color: green; font.pixelSize: 9; font.bold: true }
        Label { Layout.minimumWidth: 0; text: appWindow.t("mining.ring_sources", "RINGS · JOURNAL + EDDN + SPANSH"); color: muted; font.pixelSize: 9; elide: Text.ElideRight }
        Label {
            Layout.minimumWidth: 0
            text: cockpit.miningMarketSyncBusy
                  ? appWindow.t("mining.market_checking", "CHECKING EDDN MARKET DATA…")
                  : cockpit.miningMarketSyncStatus
            color: cockpit.miningMarketSyncStatus.toLowerCase().indexOf("fail") >= 0 ? orange : muted
            font.pixelSize: 9; elide: Text.ElideRight
        }
        Item { Layout.fillWidth: true }
        Label { text: readiness.ready ? "✓ " + appWindow.t("mining.loadout_ready", "LOADOUT READY") : "! " + appWindow.t("mining.loadout_incomplete", "LOADOUT INCOMPLETE"); color: readiness.ready ? green : orange; font.pixelSize: 9; font.bold: true }
        Button {
            id: refreshMiningButton
            implicitWidth: 170; implicitHeight: 28
            text: cockpit.miningSyncBusy ? appWindow.t("mining.refreshing", "REFRESHING…") : appWindow.t("mining.refresh", "REFRESH SYSTEM")
            enabled: !cockpit.miningSyncBusy
            onClicked: cockpit.refreshMiningFinder()
            contentItem: Label {
                text: refreshMiningButton.text
                color: refreshMiningButton.enabled ? textSecondary : muted
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                font.pixelSize: 8; font.bold: true
            }
            background: Rectangle {
                radius: 6; color: inputBackground
                border.width: 1; border.color: refreshMiningButton.hovered ? cyan : borderTone
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.minimumHeight: 318
        Layout.preferredHeight: 318
        Layout.maximumHeight: 318
        spacing: 10
        visible: resultRows.length > 0

        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            radius: 11; color: panelRaised; border.width: 1; border.color: orange
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 13; spacing: 7
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 3
                        Label {
                            text: activeRouteIndex === 0
                                  ? appWindow.t("mining.best_for_goal", "BEST ROUTE FOR YOUR GOAL")
                                  : appWindow.t("mining.selected_route", "SELECTED ROUTE")
                            color: orange; font.pixelSize: 9; font.bold: true
                        }
                        Label { text: appliedCommodityFilter + " · " + appliedMiningMethod + " · " + String(bestRoute.ringTypeName || "UNKNOWN RING"); color: textPrimary; font.pixelSize: 16; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                    Label { text: appWindow.tf("mining.overall_rating", "OVERALL %1 / 5", [Number(bestRoute.overallScore || 0).toLocaleString(Qt.locale(), "f", 1)]); color: green; font.pixelSize: 10; font.bold: true }
                    Button {
                        id: copyBestSystemButton
                        implicitWidth: 104; implicitHeight: 30
                        text: appWindow.t("mining.copy_mine", "COPY MINE")
                        onClicked: cockpit.copySystem(String(bestRoute.system || ""))
                        contentItem: Label {
                            text: copyBestSystemButton.text
                            color: copyBestSystemButton.hovered ? textPrimary : textSecondary
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            font.pixelSize: 8; font.bold: true
                        }
                        background: Rectangle {
                            radius: 6; color: copyBestSystemButton.hovered ? appWindow.hover : inputBackground
                            border.width: 1; border.color: copyBestSystemButton.hovered ? cyan : borderTone
                        }
                    }
                    Button {
                        id: copySellSystemButton
                        implicitWidth: 104; implicitHeight: 30
                        text: appWindow.t("mining.copy_sell", "COPY SELL")
                        visible: Boolean(bestRoute.marketKnown && bestRoute.sellSystem)
                        onClicked: cockpit.copySystem(String(bestRoute.sellSystem || ""))
                        contentItem: Label {
                            text: copySellSystemButton.text
                            color: copySellSystemButton.hovered ? textPrimary : textSecondary
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            font.pixelSize: 8; font.bold: true
                        }
                        background: Rectangle {
                            radius: 6; color: copySellSystemButton.hovered ? appWindow.hover : inputBackground
                            border.width: 1; border.color: copySellSystemButton.hovered ? cyan : borderTone
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: 72; radius: 8; color: backgroundSecondary
                        ColumnLayout { anchors.fill: parent; anchors.margins: 9; spacing: 3
                            Label { text: appWindow.t("mining.mine_step", "1 · MINE"); color: cyan; font.pixelSize: 9; font.bold: true }
                            Label { text: String(bestRoute.system || "UNKNOWN") + " · " + String(bestRoute.ring || bestRoute.body || ""); color: textPrimary; font.pixelSize: 11; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                            Label { text: String(bestRoute.reserveName || "UNKNOWN") + " · " + formatDistance(bestRoute.distanceLy); color: textSecondary; font.pixelSize: 9; Layout.fillWidth: true; elide: Text.ElideRight }
                        }
                    }
                    Label { text: appWindow.t("mining.route_arrow", "→"); color: orange; font.pixelSize: 19; font.bold: true }
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: 72; radius: 8; color: backgroundSecondary
                        ColumnLayout { anchors.fill: parent; anchors.margins: 9; spacing: 3
                            Label { text: appWindow.t("mining.sell_step", "2 · SELL"); color: cyan; font.pixelSize: 9; font.bold: true }
                            Label { text: marketName(bestRoute); color: bestRoute.marketKnown ? textPrimary : orange; font.pixelSize: 11; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                            Label { text: marketDetail(bestRoute); color: textSecondary; font.pixelSize: 9; Layout.fillWidth: true; elide: Text.ElideRight }
                        }
                    }
                }
                GridLayout {
                    Layout.fillWidth: true; columns: 4; columnSpacing: 7
                    Repeater {
                        model: [
                            {"label": appWindow.t("mining.yield_quality", "YIELD QUALITY"), "value": bestRoute.yieldStars},
                            {"label": appWindow.t("mining.profitability", "PROFITABILITY"), "value": bestRoute.profitStars},
                            {"label": appWindow.t("mining.merit_fit", "MERIT SUITABILITY"), "value": bestRoute.meritStars},
                            {"label": appWindow.t("mining.data_confidence", "DATA CONFIDENCE"), "value": bestRoute.dataStars}
                        ]
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true; Layout.preferredHeight: 44; radius: 7; color: inputBackground
                            ColumnLayout { anchors.fill: parent; anchors.margins: 7; spacing: 2
                                Label { text: modelData.label; color: muted; font.pixelSize: 8; font.bold: true }
                                Label { text: modelData.value || "—"; color: orange; font.pixelSize: 12; font.bold: true }
                            }
                        }
                    }
                }
                GridLayout {
                    Layout.fillWidth: true; columns: 4; columnSpacing: 7
                    Repeater {
                        model: [
                            {"label": appWindow.t("mining.price", "PRICE"), "value": bestRoute.marketKnown ? formatNumber(bestRoute.sellPrice) + " CR/T" : "—"},
                            {"label": appWindow.t("mining.outbound_distance", "MINING DISTANCE"), "value": formatDistance(bestRoute.distanceLy)},
                            {"label": appWindow.t("mining.route_distance", "MINE → SELL"), "value": formatDistance(bestRoute.mineToSellLy)},
                            {"label": appWindow.t("mining.price_age", "PRICE AGE"), "value": bestRoute.marketKnown ? formatAge(bestRoute.marketAgeSeconds) : appWindow.t("status.unknown", "UNKNOWN")}
                        ]
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true; Layout.preferredHeight: 42
                            radius: 7; color: backgroundSecondary
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 7; spacing: 2
                                Label { text: modelData.label; color: muted; font.pixelSize: 8; font.bold: true }
                                Label { text: modelData.value; color: textPrimary; font.pixelSize: 10; font.bold: true }
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.preferredWidth: Math.max(330, parent.width * 0.34)
            Layout.fillHeight: true; radius: 11; color: panelRaised
            border.width: 1; border.color: borderTone
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 13; spacing: 7
                Label { text: appWindow.t("mining.why_route", "WHY THIS ROUTE?"); color: orange; font.pixelSize: 9; font.bold: true }
                Repeater {
                    model: [
                        {"ok": bestRoute.meritKnown, "title": appWindow.t("mining.reason_merit", "Powerplay suitability"), "detail": bestRoute.meritKnown ? bestRoute.meritStatus : appWindow.t("mining.reason_merit_unknown", "Unknown — no merit claim is made")},
                        {"ok": bestRoute.targetMatch === "LOCAL_YIELD" || bestRoute.targetMatch === "HOTSPOT", "title": appWindow.t("mining.reason_method", "Mining evidence"), "detail": bestRoute.targetMatchName || "—"},
                        {"ok": bestRoute.marketKnown, "title": appWindow.t("mining.reason_market", "Market demand"), "detail": bestRoute.marketKnown ? (bestRoute.demandInfinite ? "∞" : formatNumber(bestRoute.demand) + " T") + " · " + String(bestRoute.marketSource || "EDDN") : appWindow.t("mining.reason_market_unknown", "Unknown — route remains a mining destination")},
                        {"ok": !bestRoute.stale, "title": appWindow.t("mining.reason_age", "Data freshness"), "detail": bestRoute.confirmationStatus || "—"}
                    ]
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true; spacing: 7
                        Label { text: modelData.ok ? "✓" : "!"; color: modelData.ok ? green : orange; font.pixelSize: 13; font.bold: true }
                        ColumnLayout { Layout.fillWidth: true; spacing: 1
                            Label { text: modelData.title; color: textPrimary; font.pixelSize: 10; font.bold: true }
                            Label { Layout.fillWidth: true; text: modelData.detail; color: textSecondary; font.pixelSize: 9; elide: Text.ElideRight }
                        }
                    }
                }
            }
        }
    }

    Item {
        objectName: "qa-mining-empty"
        Layout.fillWidth: true
        Layout.minimumHeight: 180
        Layout.preferredHeight: 200
        Layout.maximumHeight: 220
        visible: resultRows.length === 0

        EmptyState {
            width: Math.min(parent.width, 720)
            anchors.centerIn: parent
            symbol: "◇"
            title: appWindow.t("mining.empty", "NO MATCHING MINING EVIDENCE")
            detail: appWindow.t("mining.empty_unified_help", "Widen the radius or relax hotspot, reserve and method filters. Unknown market data never hides a valid mining location.")
            tone: cyan
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        visible: resultRows.length > 0
        spacing: 5
        RowLayout {
            Layout.fillWidth: true
            Label { text: appWindow.tf("mining.alternatives", "%1 ALTERNATIVES", [alternativeRows.length]); color: orange; font.pixelSize: 11; font.bold: true }
            Item { Layout.fillWidth: true }
            Label { text: appWindow.t("mining.sort_goal", "SORTED BY SELECTED GOAL · UNKNOWN VALUES LAST"); color: muted; font.pixelSize: 8; font.bold: true }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 27; color: panelRaised; radius: 7
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 11; anchors.rightMargin: 11; spacing: 10
                Label { Layout.preferredWidth: 30; text: appWindow.t("mining.rank", "#"); color: muted; font.pixelSize: 8; font.bold: true }
                Label { Layout.fillWidth: true; text: appWindow.t("mining.location", "MINING LOCATION"); color: muted; font.pixelSize: 8; font.bold: true }
                Label { Layout.preferredWidth: 210; text: appWindow.t("mining.sale", "SALE"); color: muted; font.pixelSize: 8; font.bold: true }
                Label { Layout.preferredWidth: 110; text: appWindow.t("mining.price_per_tonne", "PRICE / T"); color: muted; font.pixelSize: 8; font.bold: true }
                Label { Layout.preferredWidth: 100; text: appWindow.t("mining.demand", "DEMAND"); color: muted; font.pixelSize: 8; font.bold: true }
                Label {
                    Layout.preferredWidth: 90
                    text: appliedOptimization === "POWERPLAY MERITS"
                          ? appWindow.t("mining.merit_fit", "MERIT FIT")
                          : appWindow.t("mining.market_age", "DATA AGE")
                    color: muted; font.pixelSize: 8; font.bold: true
                }
                Label { Layout.preferredWidth: 64; text: appWindow.t("mining.select", "SELECT"); color: muted; font.pixelSize: 8; font.bold: true; horizontalAlignment: Text.AlignHCenter }
            }
        }
        ListView {
            id: routesList
            Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 5; clip: true
            model: alternativeRows
            ScrollBar.vertical: CockpitScrollBar {}
            onContentYChanged: miningFinderPage._listScrollY = contentY
            delegate: Rectangle {
                id: routeRow
                required property var modelData
                required property int index
                width: routesList.width; height: 58; radius: 8
                color: routeMouse.containsMouse ? appWindow.hover : panelRaised
                border.width: routeMouse.containsMouse ? 2 : 1
                border.color: routeMouse.containsMouse ? cyan
                                                     : (modelData.stale ? orange : borderTone)
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 11; anchors.rightMargin: 11; spacing: 10
                    Label { Layout.preferredWidth: 30; text: String(routeIndex(modelData) + 1); color: orange; font.family: monoFont; font.pixelSize: 11; font.bold: true }
                    ColumnLayout { Layout.fillWidth: true; spacing: 2
                        Label { Layout.fillWidth: true; text: String(modelData.system || "UNKNOWN") + " · " + String(modelData.ring || modelData.body || ""); color: textPrimary; font.pixelSize: 10; font.bold: true; elide: Text.ElideRight }
                        Label { Layout.fillWidth: true; text: String(modelData.reserveName || "UNKNOWN") + " · " + String(modelData.targetMatchName || ""); color: textSecondary; font.pixelSize: 8; elide: Text.ElideRight }
                    }
                    ColumnLayout { Layout.preferredWidth: 210; spacing: 2
                        Label { Layout.fillWidth: true; text: marketName(modelData); color: modelData.marketKnown ? textPrimary : orange; font.pixelSize: 9; font.bold: true; elide: Text.ElideRight }
                        Label { text: String(modelData.sellSystem || ""); color: textSecondary; font.pixelSize: 8; elide: Text.ElideRight }
                    }
                    Label { Layout.preferredWidth: 110; text: modelData.marketKnown ? formatNumber(modelData.sellPrice) + " CR" : "—"; color: modelData.marketKnown ? green : muted; font.pixelSize: 9; font.bold: true }
                    Label { Layout.preferredWidth: 100; text: modelData.marketKnown ? (modelData.demandInfinite ? "∞" : formatNumber(modelData.demand) + " T") : "—"; color: textPrimary; font.pixelSize: 9; font.bold: true }
                    Label {
                        Layout.preferredWidth: 90
                        text: appliedOptimization === "POWERPLAY MERITS"
                              ? String(modelData.meritStars || "—")
                              : (modelData.marketKnown ? formatAge(modelData.marketAgeSeconds) : "—")
                        color: appliedOptimization === "POWERPLAY MERITS"
                               ? (modelData.meritKnown ? green : orange)
                               : (modelData.stale ? orange : green)
                        font.pixelSize: 8; font.bold: true
                    }
                    Label { Layout.preferredWidth: 64; text: appWindow.t("mining.use_route", "USE"); color: routeMouse.containsMouse ? cyan : textSecondary; font.pixelSize: 9; font.bold: true; horizontalAlignment: Text.AlignHCenter }
                }
                MouseArea {
                    id: routeMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    preventStealing: false
                    cursorShape: Qt.PointingHandCursor
                    onClicked: miningFinderPage.selectRoute(modelData)
                }
            }
        }
    }
    }
}
