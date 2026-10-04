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
    property bool ringsOnly: true
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
    property bool appliedRingsOnly: true
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
    property bool searchGoalExpanded: true
    property int searchRevision: 0
    property int _miningRevisionSnapshot: cockpit.miningRevision
    property real _listScrollY: 0
    property int selectedRouteIndex: 0
    property string selectedRouteKey: ""
    readonly property int activeRouteIndex: {
        if (!resultRows.length) return 0
        if (selectedRouteKey) {
            for (let index = 0; index < resultRows.length; ++index)
                if (routeKey(resultRows[index]) === selectedRouteKey)
                    return index
        }
        return Math.max(0, Math.min(selectedRouteIndex,
                                    resultRows.length - 1))
    }

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
    readonly property var systemSuggestions: {
        let revision = _miningRevisionSnapshot
        return cockpit.miningSystemSuggestions(startSystem, 8)
    }
    readonly property var resultRows: {
        let revision = _miningRevisionSnapshot + searchRevision
        if (searchRevision === 0)
            return []
        return cockpit.miningPlanRoutes(
                    appliedStartSystem, appliedCommodityFilter, appliedNearbyLy,
                    appliedReserveFilter, appliedRingFilter,
                    appliedRingsOnly,
                    appliedMiningMethod,
                    appliedOptimization, appliedMinDemand, appliedMaxDemand,
                    appliedMaxMarketAgeHours, appliedResultLimit,
                    appliedRequireHotspot, appliedPreferRes,
                    appliedPreferSecondary, appliedRequireSystemState,
                    appliedLandingPad, appliedPower || powerName,
                    appliedPowerGoal, appliedOpposingPower,
                    appliedSystemState)
    }
    readonly property var marketDiagnostics: {
        let revision = _miningRevisionSnapshot + searchRevision
        if (searchRevision === 0)
            return ({})
        return cockpit.miningMarketDiagnostics(
                    appliedStartSystem, appliedCommodityFilter,
                    appliedNearbyLy, appliedMinDemand, appliedMaxDemand,
                    appliedMaxMarketAgeHours, appliedLandingPad)
    }
    readonly property bool marketQueryPending: searchRevision > 0
            && cockpit.miningMarketSyncBusy
            && !Boolean(marketDiagnostics.cacheMatches)
    readonly property var bestRoute: resultRows.length
            ? resultRows[activeRouteIndex] : ({})
    readonly property var catalogCoverage: cockpit.miningCacheSummary || ({})
    readonly property var routeCoverage: {
        let rows = resultRows
        if (searchRevision === 0)
            return {"percent": -1, "marketPercent": -1, "meritPercent": -1}
        if (!rows.length)
            return {"percent": 0, "marketPercent": 0, "meritPercent": 0}
        let known = 0
        let possible = 0
        let markets = 0
        let merits = 0
        let meritRequired = appliedOptimization === "POWERPLAY MERITS"
        for (let index = 0; index < rows.length; ++index) {
            let row = rows[index]
            possible += meritRequired ? 6 : 5
            known += Boolean(row.system && (row.ring || row.body)) ? 1 : 0
            known += row.distanceLy !== null
                    && row.distanceLy !== undefined ? 1 : 0
            known += Boolean(row.selectedCommodityName
                             || appliedCommodityFilter !== "ALL COMMODITIES") ? 1 : 0
            known += Boolean(row.targetMatch) ? 1 : 0
            known += Boolean(row.marketKnown) ? 1 : 0
            markets += Boolean(row.marketKnown) ? 1 : 0
            if (meritRequired) {
                known += Boolean(row.meritKnown) ? 1 : 0
                merits += Boolean(row.meritKnown) ? 1 : 0
            }
        }
        return {
            "percent": Math.round(100 * known / possible),
            "marketPercent": Math.round(100 * markets / rows.length),
            "meritPercent": meritRequired
                              ? Math.round(100 * merits / rows.length) : -1
        }
    }
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
    readonly property int routeRankWidth: 30
    readonly property int routeSaleWidth: 250
    readonly property int routePriceWidth: 110
    readonly property int routeDemandWidth: 100
    readonly property int routeStatusWidth: 126
    readonly property int routeSelectWidth: 64

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
    function compactNumber(value) {
        let number = Number(value || 0)
        if (number >= 1000000)
            return (number / 1000000).toLocaleString(Qt.locale(), "f", 1) + "M"
        if (number >= 1000)
            return (number / 1000).toLocaleString(Qt.locale(), "f", 1) + "K"
        return formatNumber(number)
    }
    function formatDistance(value) {
        return value === null || value === undefined
                ? appWindow.t("status.distance_unknown", "Unknown")
                : Number(value).toLocaleString(Qt.locale(), "f", 1) + " LY"
    }
    function formatLs(value) {
        return value === null || value === undefined
                ? appWindow.t("status.distance_unknown", "Unknown")
                : formatNumber(value) + " LS"
    }
    function formatAge(seconds) {
        if (seconds === null || seconds === undefined)
            return appWindow.t("mining.market_age_unknown", "AGE UNKNOWN")
        if (seconds < 60) return Math.max(1, Math.round(seconds)) + " S"
        if (seconds < 3600) return Math.round(seconds / 60) + " MIN"
        return Math.round(seconds / 3600) + " H"
    }
    function yieldQuality(row) {
        if (row && row.yieldMeasured) {
            let average = Number(row.yieldAverageProportion || 0)
                    .toLocaleString(Qt.locale(), "f", 1) + "%"
            return average + " · " + formatNumber(row.yieldHitCount)
                    + "/" + formatNumber(row.yieldSampleCount)
        }
        return row && row.yieldStars ? String(row.yieldStars) : "—"
    }
    function yieldEvidence(row) {
        if (!row) return "—"
        let evidence = String(row.yieldEvidenceLabel || "")
        let mining = String(row.targetMatchName || "")
        return evidence && mining && evidence !== mining
                ? evidence + " · " + mining : (evidence || mining || "—")
    }
    function marketName(row) {
        if (!row.marketKnown && row.sameSystemSaleRequired)
            return appWindow.t("mining.market_same_system_missing", "NO VERIFIED SAME-SYSTEM MARKET")
        if (!row.marketKnown && marketFiltersBlockRoute())
            return appWindow.t("mining.market_filtered", "NO MARKET MATCHES ACTIVE FILTERS")
        return row.marketKnown
                ? String(row.station || row.sellSystem || "MARKET CONFIRMED")
                : appWindow.t("mining.market_missing", "NO VERIFIED MARKET DATA")
    }
    function marketRouteName(row) {
        let market = marketName(row)
        if (!row.marketKnown) return market
        let system = String(row.sellSystem || "").trim()
        if (!system || system.toLowerCase() === market.toLowerCase())
            return market
        return system + " · " + market
    }
    function marketStationSummary(row) {
        let details = []
        let pad = String(row.landingPadSize || "").toUpperCase()
        if (pad) details.push(pad + " PAD")
        let type = String(row.stationType || "").trim()
        if (type) details.push(type)
        if (row.stationDistanceLs !== null
                && row.stationDistanceLs !== undefined)
            details.push(formatLs(row.stationDistanceLs))
        return details.join(" · ")
    }
    function marketFiltersBlockRoute() {
        return marketDiagnostics.cacheMatches
                && Number(marketDiagnostics.total || 0) > 0
                && Number(marketDiagnostics.eligible || 0) === 0
    }
    function marketDetail(row) {
        let commodity = String(row.selectedCommodityName
                               || appliedCommodityFilter)
        if (!row.marketKnown && row.sameSystemSaleRequired)
            return appWindow.tf("mining.market_same_system_help", "%1 requires a verified %2 market in %3; the targeted check is pending", [appliedPowerGoal, commodity, String(row.system || appWindow.t("status.unknown", "UNKNOWN"))])
        if (!row.marketKnown && marketFiltersBlockRoute())
            return String(marketDiagnostics.summary || "")
        if (!row.marketKnown)
            return appWindow.t("mining.market_missing_help", "Mining location remains usable · profit and merit ratings stay unknown")
        let stationSummary = marketStationSummary(row)
        let stationDetail = stationSummary ? "  ·  " + stationSummary : ""
        let quality = row.marketMatchesFilters ? "" : String(
                          row.marketQualityStatus || "MARKET KNOWN") + "  ·  "
        return quality + formatNumber(row.sellPrice) + " CR/T  ·  "
                + (row.demandInfinite
                   ? appWindow.t("mining.demand_infinite", "∞ DEMAND")
                   : appWindow.tf("mining.demand_value", "%1 T DEMAND", [formatNumber(row.demand)]))
                + stationDetail + "  ·  " + formatAge(row.marketAgeSeconds)
    }
    function secondaryMiningSummary(row) {
        let resources = row.secondaryCommodities || []
        if (!resources.length)
            return appWindow.t("mining.no_secondary_evidence", "NO ADDITIONAL RESOURCE EVIDENCE")
        let labels = []
        for (let index = 0; index < resources.length; ++index) {
            let resource = resources[index]
            let detail = String(resource.evidenceLabel || "")
            if (resource.averageProportion !== null
                    && resource.averageProportion !== undefined)
                detail += (detail ? " · " : "")
                        + Number(resource.averageProportion).toLocaleString(
                            Qt.locale(), "f", 1) + "% AVG"
            labels.push(String(resource.name || "UNKNOWN")
                        + (detail ? " (" + detail + ")" : ""))
        }
        return appWindow.t("mining.also_found", "ALSO") + ": "
                + labels.join(" · ")
    }
    function secondarySaleSummary(row) {
        let resources = row.secondaryCommodities || []
        if (!resources.length)
            return appWindow.t("mining.no_secondary_sale", "NO ADDITIONAL RESOURCES TO CHECK")
        let labels = []
        for (let index = 0; index < resources.length; ++index) {
            let resource = resources[index]
            labels.push(String(resource.name || "UNKNOWN") + " "
                        + (resource.marketKnown
                           ? formatNumber(resource.sellPrice) + " CR/T"
                           : appWindow.t("mining.sale_unverified", "SALE UNVERIFIED")))
        }
        return appWindow.t("mining.also_at_station", "ALSO AT THIS STATION")
                + ": " + labels.join(" · ")
    }
    function secondaryCompactSummary(row) {
        let names = row.secondaryCommodityNames || []
        return names.length
                ? appWindow.t("mining.also_found", "ALSO") + ": "
                  + names.join(", ") : ""
    }
    function verificationColor(row) {
        let state = String(row && row.powerplayVerificationState !== undefined
                           ? row.powerplayVerificationState : "")
        if (state === "VERIFIED") return green
        if (state === "INELIGIBLE") return muted
        if (state === "POWERPLAY_DATA_MISSING") return cyan
        return orange
    }
    function verificationShortLabel(row) {
        if (!row) return appWindow.t("status.unknown", "UNKNOWN")
        let explicitLabel = row.powerplayVerificationLabel === undefined
                || row.powerplayVerificationLabel === null
                ? "" : String(row.powerplayVerificationLabel)
        if (explicitLabel) return explicitLabel
        let state = row.powerplayVerificationState === undefined
                || row.powerplayVerificationState === null
                ? "" : String(row.powerplayVerificationState)
        if (state === "VERIFIED")
            return appWindow.t("mining.powerplay_verified", "VERIFIED")
        if (state === "KNOWN")
            return appWindow.t("mining.powerplay_known", "ROUTE KNOWN")
        if (state === "INELIGIBLE")
            return appWindow.t("mining.powerplay_ineligible", "NOT ELIGIBLE")
        if (state === "POWERPLAY_DATA_MISSING") return "POWERPLAY DATA MISSING"
        if (state === "MARKET_TOO_OLD") return "MARKET TOO OLD"
        if (state === "MARKET_OUTSIDE_FILTERS") return "MARKET OUTSIDE FILTERS"
        if (state === "NO_MARKET_DATA") return "NO MARKET DATA"
        if (state === "NOT_YET_CHECKED") return "NOT YET CHECKED"
        if (state === "MARKET_CHECK_RUNNING") return "MARKET CHECK RUNNING"
        return appWindow.t("status.unknown", "UNKNOWN")
    }
    function verificationReason(row) {
        if (!row || row.pendingReason === undefined
                || row.pendingReason === null)
            return ""
        return String(row.pendingReason)
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
    function routeKey(row) {
        return String(row.systemAddress || row.system || "") + "|"
                + String(row.bodyId === undefined ? row.body || "" : row.bodyId)
                + "|" + String(row.ring || "")
    }
    function selectRoute(row) {
        let index = routeIndex(row)
        if (index >= 0) {
            selectedRouteIndex = index
            selectedRouteKey = routeKey(row)
        }
    }
    function isExactSystemSuggestion(value) {
        let key = String(value || "").trim().toLowerCase()
        for (let index = 0; index < systemSuggestions.length; ++index)
            if (String(systemSuggestions[index]).toLowerCase() === key)
                return true
        return false
    }
    function chooseStartSystem(value) {
        let selected = String(value || "")
        startSystem = selected
        startSystemField.text = selected
        startSystemField.cursorPosition = selected.length
        startSystemField.forceActiveFocus()
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
        appliedRingsOnly = ringsOnly
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
        selectedRouteKey = ""
        searchRevision += 1
    }
    function executeSearch() {
        applySearch()
        searchGoalExpanded = false
        // Snapshot typed values before yielding. The page may be reloaded or
        // navigated away from before callLater runs; reading its properties
        // from the delayed closure would then pass undefined to the C++ slot.
        let verificationRoutes = []
        for (let index = 0; index < resultRows.length; ++index)
            verificationRoutes.push(resultRows[index])
        let verificationStartSystem = String(appliedStartSystem || "")
        let verificationCommodity = String(appliedCommodityFilter || "")
        let verificationMaxAge = Number(appliedMaxMarketAgeHours || 0)
        let verificationMinDemand = Number(appliedMinDemand || 0)
        let verificationLandingPad = String(appliedLandingPad || "ANY")
        cockpit.refreshMiningMarkets(
                    appliedStartSystem, appliedCommodityFilter,
                    appliedNearbyLy, appliedMinDemand,
                    appliedMaxMarketAgeHours, appliedLandingPad)
        Qt.callLater(function() {
            cockpit.verifyMiningRoutes(
                        verificationRoutes,
                        verificationStartSystem,
                        verificationCommodity,
                        verificationMaxAge,
                        verificationMinDemand,
                        verificationLandingPad)
        })
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
            implicitHeight: 20
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
        width: miningFinderPage.availableWorkspaceWidth
        x: miningFinderPage.sidebarWidth + miningFinderPage.pageMargin
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
        StatusBadge {
            id: catalogCoverageBadge
            compact: true
            visible: Number(catalogCoverage.total || 0) > 0
            statusText: appWindow.tf(
                "mining.catalog_quality_badge",
                "LOCAL %1 · DATA %2% · ROUTES %3",
                [compactNumber(catalogCoverage.total),
                 Number(catalogCoverage.recordCompleteness || 0),
                 routeCoverage.percent < 0
                 ? "—" : String(routeCoverage.percent) + "%"])
            tone: Number(catalogCoverage.recordCompleteness || 0) >= 85
                  && (routeCoverage.percent < 0 || routeCoverage.percent >= 75)
                  ? green
                  : Number(catalogCoverage.recordCompleteness || 0) >= 65
                    ? cyan : orange
            ToolTip.visible: catalogCoverageHover.hovered
            ToolTip.delay: 250
            ToolTip.text: appWindow.t(
                "mining.catalog_quality_scope",
                "Stored-record completeness — not total galaxy coverage")
                + "\n" + appWindow.tf(
                "mining.catalog_quality_counts",
                "%1 rings in %2 systems · %3 markets · %4 Powerplay links",
                [formatNumber(catalogCoverage.total),
                 formatNumber(catalogCoverage.systems),
                 formatNumber(catalogCoverage.marketTotal),
                 formatNumber(catalogCoverage.powerplayTotal)])
                + "\n" + appWindow.tf(
                "mining.catalog_quality_fields",
                "Coordinates %1% · ring names %2% · ring types %3% · reserves %4% · resource evidence %5% · current %6%",
                [
                 Number(catalogCoverage.coordinatesPercent || 0),
                 Number(catalogCoverage.ringPercent || 0),
                 Number(catalogCoverage.ringTypePercent || 0),
                 Number(catalogCoverage.reservePercent || 0),
                 Number(catalogCoverage.resourceEvidencePercent || 0),
                 Number(catalogCoverage.currentPercent || 0)])
                + "\n" + appWindow.tf(
                "mining.catalog_quality_routes",
                "Current routes: market %1 · Powerplay %2",
                [
                 routeCoverage.marketPercent < 0
                 ? "—" : String(routeCoverage.marketPercent) + "%",
                 routeCoverage.meritPercent < 0
                 ? "—" : String(routeCoverage.meritPercent) + "%"])
            HoverHandler { id: catalogCoverageHover }
        }
        StatusBadge {
            id: edFrameServerBadge
            compact: true
            statusText: !cockpit.edFrameCatalogEnabled
                        ? appWindow.t("mining.server_off", "SERVER OFF · LOCAL ACTIVE")
                        : cockpit.edFrameCatalogBusy
                          ? appWindow.t("mining.server_checking", "SERVER · CHECKING…")
                          : cockpit.edFrameCatalogSyncBusy
                            ? appWindow.t("mining.server_syncing", "SERVER · SYNCING CATALOG…")
                          : cockpit.edFrameCatalogOnline
                            ? appWindow.tf(
                                "mining.server_online",
                                "SERVER ONLINE · %1 MARKETS",
                                [compactNumber(cockpit.edFrameCatalogStats.markets || 0)])
                            : appWindow.t(
                                "mining.server_offline",
                                "SERVER OFFLINE · LOCAL ACTIVE")
            tone: cockpit.edFrameCatalogOnline ? green
                  : (cockpit.edFrameCatalogBusy
                     || cockpit.edFrameCatalogSyncBusy) ? cyan : orange
            ToolTip.visible: edFrameServerHover.hovered
            ToolTip.delay: 250
            ToolTip.text: cockpit.edFrameCatalogStatus
                              + (cockpit.edFrameCatalogLastSuccess
                                 ? "\n" + appWindow.t(
                                     "mining.server_last_success",
                                     "Last successful contact")
                                   + " · " + cockpit.edFrameCatalogLastSuccess
                                 : "")
                              + "\n" + cockpit.edFrameCatalogSyncStatus
            HoverHandler { id: edFrameServerHover }
        }
        StatusBadge {
            compact: true
            statusText: appWindow.t("mining.current_action", "ACTION")
                        + " · " + cockpit.miningCurrentAction
            tone: cockpit.miningSyncBusy || cockpit.miningMarketSyncBusy
                  || cockpit.miningVerificationBusy
                  || cockpit.edFrameCatalogBusy
                  || cockpit.edFrameCatalogSyncBusy ? orange : cyan
        }
    }

    Rectangle {
        objectName: "qa-mining-config"
        Layout.fillWidth: true
        Layout.minimumHeight: miningFinderPage.searchGoalExpanded
                              ? (miningFinderPage.compactFilters ? 540 : 340)
                              : 48
        Layout.preferredHeight: miningFinderPage.searchGoalExpanded
                                ? (miningFinderPage.compactFilters ? 560 : 350)
                                : 48
        Layout.maximumHeight: miningFinderPage.searchGoalExpanded
                              ? (miningFinderPage.compactFilters ? 580 : 350)
                              : 48
        radius: 12
        color: panelRaised
        border.width: 1
        border.color: orange

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 10
            spacing: 6

            RowLayout {
                Layout.fillWidth: true
                Label {
                    text: (miningFinderPage.searchGoalExpanded ? "⌃  " : "⌄  ")
                          + appWindow.t("mining.define_goal", "1 · DEFINE SEARCH GOAL")
                    color: orange; font.pixelSize: 11; font.bold: true
                }
                Item { Layout.fillWidth: miningFinderPage.searchGoalExpanded }
                Label {
                    Layout.fillWidth: !miningFinderPage.searchGoalExpanded
                    Layout.minimumWidth: 0
                    text: miningFinderPage.searchGoalExpanded
                          ? appWindow.t("mining.one_search_note", "ONE SEARCH · WEIGHTED BY YOUR GOAL")
                          : appWindow.tf(
                                "mining.collapsed_summary",
                                "%1 · %2 · %3 · %4 LY · %5 RESULTS",
                                [appliedCommodityFilter, appliedMiningMethod,
                                 displayOptimization(appliedOptimization),
                                 appliedNearbyLy, resultRows.length])
                    color: muted; font.pixelSize: 9; font.bold: true
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignRight
                }
                Button {
                    id: toggleSearchGoalButton
                    implicitWidth: miningFinderPage.searchGoalExpanded ? 94 : 126
                    implicitHeight: 26
                    text: miningFinderPage.searchGoalExpanded
                          ? appWindow.t("mining.collapse_search", "COLLAPSE")
                          : appWindow.t("mining.edit_search", "EDIT SEARCH")
                    onClicked: miningFinderPage.searchGoalExpanded =
                                   !miningFinderPage.searchGoalExpanded
                    contentItem: Label {
                        text: toggleSearchGoalButton.text
                        color: toggleSearchGoalButton.hovered ? cyan : textSecondary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.pixelSize: 8; font.bold: true
                    }
                    background: Rectangle {
                        radius: 6; color: inputBackground
                        border.width: 1
                        border.color: toggleSearchGoalButton.hovered
                                      ? cyan : borderTone
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true; height: 1; color: divider
                visible: miningFinderPage.searchGoalExpanded
            }

            GridLayout {
                Layout.fillWidth: true
                visible: miningFinderPage.searchGoalExpanded
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
                        implicitHeight: 34
                        text: miningFinderPage.startSystem
                        placeholderText: cockpit.system
                                         || appWindow.t("status.unknown", "UNKNOWN")
                        selectByMouse: true
                        maximumLength: 96
                        leftPadding: 11
                        rightPadding: 11
                        color: textPrimary
                        font.pixelSize: 11
                        onTextEdited: {
                            miningFinderPage.startSystem = text
                            systemSuggestionList.currentIndex = 0
                        }
                        onAccepted: {
                            if (systemSuggestionsPopup.visible
                                    && systemSuggestionList.currentIndex >= 0) {
                                miningFinderPage.chooseStartSystem(
                                            miningFinderPage.systemSuggestions[
                                                systemSuggestionList.currentIndex])
                            } else {
                                miningFinderPage.executeSearch()
                            }
                        }
                        Keys.onPressed: function(event) {
                            if (!systemSuggestionsPopup.visible)
                                return
                            if (event.key === Qt.Key_Down) {
                                systemSuggestionList.currentIndex = Math.min(
                                            systemSuggestionList.count - 1,
                                            systemSuggestionList.currentIndex + 1)
                                event.accepted = true
                            } else if (event.key === Qt.Key_Up) {
                                systemSuggestionList.currentIndex = Math.max(
                                            0,
                                            systemSuggestionList.currentIndex - 1)
                                event.accepted = true
                            } else if (event.key === Qt.Key_Escape) {
                                startSystemField.focus = false
                                event.accepted = true
                            }
                        }
                        background: Rectangle {
                            radius: 7
                            color: inputBackground
                            border.width: startSystemField.activeFocus ? 2 : 1
                            border.color: startSystemField.activeFocus
                                          ? cyan : borderTone
                        }
                        Popup {
                            id: systemSuggestionsPopup
                            parent: startSystemField
                            x: 0
                            y: startSystemField.height + 4
                            width: startSystemField.width
                            height: Math.min(298,
                                             systemSuggestionList.contentHeight + 10)
                            padding: 5
                            z: 1000
                            visible: startSystemField.activeFocus
                                     && startSystemField.text.trim().length > 0
                                     && miningFinderPage.systemSuggestions.length > 0
                                     && !miningFinderPage.isExactSystemSuggestion(
                                         startSystemField.text)
                            closePolicy: Popup.CloseOnEscape
                                         | Popup.CloseOnPressOutsideParent
                            contentItem: ListView {
                                id: systemSuggestionList
                                clip: true
                                model: miningFinderPage.systemSuggestions
                                currentIndex: count > 0 ? 0 : -1
                                highlightMoveDuration: 70
                                ScrollBar.vertical: CockpitScrollBar {
                                    trackThickness: 10
                                    thumbThickness: 7
                                }
                                delegate: ItemDelegate {
                                    required property int index
                                    width: systemSuggestionList.width
                                    height: 36
                                    highlighted: systemSuggestionList.currentIndex
                                                 === index
                                    hoverEnabled: true
                                    onHoveredChanged: {
                                        if (hovered)
                                            systemSuggestionList.currentIndex = index
                                    }
                                    onClicked: miningFinderPage.chooseStartSystem(
                                                   miningFinderPage.systemSuggestions[index])
                                    contentItem: Label {
                                        text: String(
                                            miningFinderPage.systemSuggestions[index])
                                        color: highlighted ? textPrimary : textSecondary
                                        font.pixelSize: 10
                                        font.bold: highlighted
                                        verticalAlignment: Text.AlignVCenter
                                        elide: Text.ElideRight
                                    }
                                    background: Rectangle {
                                        radius: 5
                                        color: highlighted
                                               ? appWindow.active : "transparent"
                                        border.width: highlighted ? 1 : 0
                                        border.color: cyan
                                    }
                                }
                            }
                            background: Rectangle {
                                radius: 8
                                color: appWindow.cardRaised
                                border.width: 1
                                border.color: cyan
                            }
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 4
                    Label { text: appWindow.t("mining.target_commodity", "TARGET COMMODITY"); color: muted; font.pixelSize: 9; font.bold: true }
                    CockpitComboBox {
                        id: commodityBox; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; implicitHeight: 34
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
                        id: methodBox; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; implicitHeight: 34
                        model: ["LASER", "CORE", "SUBSURFACE", "RHINO SURFACE"]
                        currentIndex: model.indexOf(miningFinderPage.miningMethod)
                        onActivated: { miningFinderPage.miningMethod = currentText; miningFinderPage.resetForMethod() }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 4
                    Label { text: appWindow.t("mining.optimize_for", "OPTIMIZE FOR"); color: orange; font.pixelSize: 9; font.bold: true }
                    CockpitComboBox {
                        id: optimizationBox; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; implicitHeight: 34
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
                        Layout.preferredWidth: 1; implicitHeight: 34
                        model: miningFinderPage.powerOptions
                        currentIndex: powerOverride
                                      ? Math.max(0, model.indexOf(powerOverride)) : 0
                        onActivated: miningFinderPage.powerOverride =
                                         currentIndex === 0 ? "" : currentText
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true; height: 1; color: divider
                visible: miningFinderPage.searchGoalExpanded
            }
            GridLayout {
                Layout.fillWidth: true
                visible: miningFinderPage.searchGoalExpanded
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
                                id: ringBox; Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 30
                                model: miningFinderPage.ringOptions
                                currentIndex: model.indexOf(miningFinderPage.ringFilter)
                                onActivated: miningFinderPage.ringFilter = currentText
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 2
                            Label { text: appWindow.t("mining.reserve_quality", "RESERVE QUALITY"); color: muted; font.pixelSize: 8; font.bold: true }
                            CockpitComboBox {
                                id: reserveBox; Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 30
                                model: ["PRISTINE + MAJOR", "PRISTINE", "MAJOR", "ALL RESERVES"]
                                currentIndex: model.indexOf(miningFinderPage.reserveFilter)
                                onActivated: miningFinderPage.reserveFilter = currentText
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 2
                            Label { text: appWindow.t("mining.landing_pad", "LANDING PAD"); color: muted; font.pixelSize: 8; font.bold: true }
                            CockpitComboBox {
                                id: padBox; Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 30
                                model: ["LARGE", "MEDIUM", "ANY"]
                                currentIndex: model.indexOf(miningFinderPage.landingPad)
                                onActivated: miningFinderPage.landingPad = currentText
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 2
                            Label { text: appWindow.t("mining.powerplay_goal", "POWERPLAY GOAL"); color: muted; font.pixelSize: 8; font.bold: true }
                            CockpitComboBox {
                                id: goalBox; Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 30
                                model: ["REINFORCE", "ACQUIRE", "UNDERMINE"]
                                currentIndex: model.indexOf(miningFinderPage.powerGoal)
                                onActivated: miningFinderPage.powerGoal = currentText
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: 2
                            Label { text: appWindow.t("mining.opposing_power", "OPPOSING POWER"); color: muted; font.pixelSize: 8; font.bold: true }
                            CockpitComboBox {
                                id: opposingPowerBox; Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 30
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
                                id: systemStateBox; Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 30
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
                            text: appWindow.t("mining.rings_only", "RINGS ONLY")
                            checkable: true; checked: miningFinderPage.ringsOnly
                            enabled: miningFinderPage.miningMethod !== "RHINO SURFACE"
                            opacity: enabled ? 1.0 : 0.45
                            onClicked: miningFinderPage.ringsOnly = checked
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
                visible: miningFinderPage.searchGoalExpanded
                Label {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 1
                    text: appWindow.tf("mining.search_summary", "4 · CALCULATE · %1 · %2 · %3 · %4 LY · DEMAND ≥ %5 T", [commodityFilter, miningMethod, displayOptimization(optimization), nearbyLy, formatNumber(minDemand)])
                    color: textSecondary; font.pixelSize: 9; elide: Text.ElideRight
                }
                Button {
                    id: findRouteButton
                    Layout.minimumWidth: 180; Layout.preferredWidth: 220; Layout.maximumWidth: 220; implicitHeight: 34
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
                  : (miningFinderPage.searchRevision > 0
                     && miningFinderPage.marketDiagnostics.cacheMatches
                     ? String(miningFinderPage.marketDiagnostics.summary || "")
                     : cockpit.miningMarketSyncStatus)
            color: (!cockpit.miningMarketSyncBusy
                    && miningFinderPage.searchRevision > 0
                    && miningFinderPage.marketDiagnostics.cacheMatches
                    && Number(miningFinderPage.marketDiagnostics.eligible || 0) === 0)
                   || cockpit.miningMarketSyncStatus.toLowerCase().indexOf("fail") >= 0
                   ? orange : muted
            font.pixelSize: 9; elide: Text.ElideRight
            ToolTip.visible: marketStatusHover.hovered && truncated
            ToolTip.text: text
            HoverHandler { id: marketStatusHover }
        }
        Label {
            Layout.minimumWidth: 0
            Layout.maximumWidth: 220
            visible: miningFinderPage.searchRevision > 0
            text: cockpit.miningVerificationBusy
                  ? appWindow.tf(
                        "mining.verifying_progress",
                        "VERIFYING %1/%2 SYSTEMS",
                        [cockpit.miningVerificationCompleted,
                         cockpit.miningVerificationTotal])
                  : cockpit.miningVerificationStatus
            color: cockpit.miningVerificationBusy ? cyan : muted
            font.pixelSize: 9
            font.bold: cockpit.miningVerificationBusy
            elide: Text.ElideRight
            ToolTip.visible: verificationStatusHover.hovered && truncated
            ToolTip.text: cockpit.miningVerificationStatus
            HoverHandler { id: verificationStatusHover }
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
        Layout.minimumHeight: 250
        Layout.preferredHeight: 280
        Layout.maximumHeight: 280
        spacing: 10
        visible: resultRows.length > 0 && !marketQueryPending

        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            radius: 11; color: panelRaised; border.width: 1; border.color: orange
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 10; spacing: 5
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 3
                        Label {
                            text: activeRouteIndex === 0
                                  ? appWindow.t("mining.best_for_goal", "BEST ROUTE FOR YOUR GOAL")
                                  : appWindow.t("mining.selected_route", "SELECTED ROUTE")
                            color: orange; font.pixelSize: 10; font.bold: true
                        }
                        Label { text: String(bestRoute.selectedCommodityName || appliedCommodityFilter) + " · " + appliedMiningMethod + " · " + String(bestRoute.ringTypeName || "UNKNOWN RING"); color: textPrimary; font.pixelSize: 16; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                    Rectangle {
                        visible: appliedOptimization === "POWERPLAY MERITS"
                        implicitWidth: powerplayVerificationLabel.implicitWidth + 16
                        implicitHeight: 26
                        radius: 6
                        color: inputBackground
                        border.width: 1
                        border.color: verificationColor(bestRoute)
                        ToolTip.visible: bestVerificationHover.hovered
                                             && verificationReason(bestRoute) !== ""
                        ToolTip.text: verificationReason(bestRoute)
                        HoverHandler { id: bestVerificationHover }
                        Label {
                            id: powerplayVerificationLabel
                            anchors.centerIn: parent
                            text: verificationShortLabel(bestRoute)
                            color: verificationColor(bestRoute)
                            font.pixelSize: 9
                            font.bold: true
                        }
                    }
                    Label { text: appWindow.tf("mining.overall_rating", "OVERALL %1 / 5", [Number(bestRoute.overallScore || 0).toLocaleString(Qt.locale(), "f", 1)]); color: green; font.pixelSize: 11; font.bold: true }
                    Button {
                        id: copyBestSystemButton
                        implicitWidth: 104; implicitHeight: 32
                        text: appWindow.t("mining.copy_mine", "COPY MINE")
                        onClicked: cockpit.copySystem(String(bestRoute.system || ""))
                        contentItem: Label {
                            text: copyBestSystemButton.text
                            color: copyBestSystemButton.hovered ? textPrimary : textSecondary
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            font.pixelSize: 9; font.bold: true
                        }
                        background: Rectangle {
                            radius: 6; color: copyBestSystemButton.hovered ? appWindow.hover : inputBackground
                            border.width: 1; border.color: copyBestSystemButton.hovered ? cyan : borderTone
                        }
                    }
                    Button {
                        id: copySellSystemButton
                        implicitWidth: 104; implicitHeight: 32
                        text: appWindow.t("mining.copy_sell", "COPY SELL")
                        visible: Boolean(bestRoute.marketKnown && bestRoute.sellSystem)
                        onClicked: cockpit.copySystem(String(bestRoute.sellSystem || ""))
                        contentItem: Label {
                            text: copySellSystemButton.text
                            color: copySellSystemButton.hovered ? textPrimary : textSecondary
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            font.pixelSize: 9; font.bold: true
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
                        Layout.fillWidth: true; Layout.preferredHeight: appliedPreferSecondary ? 84 : 66; radius: 8; color: backgroundSecondary
                        ColumnLayout { anchors.fill: parent; anchors.margins: 7; spacing: 2
                            Label { text: appWindow.t("mining.mine_step", "1 · MINE"); color: cyan; font.pixelSize: 10; font.bold: true }
                            Label { text: String(bestRoute.system || "UNKNOWN") + " · " + String(bestRoute.ring || bestRoute.body || ""); color: textPrimary; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                            Label { text: String(bestRoute.selectedCommodityName || appliedCommodityFilter) + " · " + String(bestRoute.reserveName || "UNKNOWN") + " · " + formatDistance(bestRoute.distanceLy); color: textSecondary; font.pixelSize: 10; Layout.fillWidth: true; elide: Text.ElideRight }
                            Label { visible: appliedPreferSecondary; text: secondaryMiningSummary(bestRoute); color: cyan; font.pixelSize: 9; Layout.fillWidth: true; elide: Text.ElideRight }
                        }
                    }
                    Label { text: appWindow.t("mining.route_arrow", "→"); color: orange; font.pixelSize: 19; font.bold: true }
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: appliedPreferSecondary ? 84 : 66; radius: 8; color: backgroundSecondary
                        ColumnLayout { anchors.fill: parent; anchors.margins: 7; spacing: 2
                            Label { text: appWindow.t("mining.sell_step", "2 · SELL"); color: cyan; font.pixelSize: 10; font.bold: true }
                            Label { text: marketRouteName(bestRoute); color: bestRoute.marketKnown ? textPrimary : orange; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                            Label { text: marketDetail(bestRoute); color: textSecondary; font.pixelSize: 10; Layout.fillWidth: true; elide: Text.ElideRight }
                            Label { visible: appliedPreferSecondary; text: secondarySaleSummary(bestRoute); color: orange; font.pixelSize: 9; Layout.fillWidth: true; elide: Text.ElideRight }
                        }
                    }
                }
                GridLayout {
                    Layout.fillWidth: true; columns: 4; columnSpacing: 7
                    Repeater {
                        model: [
                            {"label": bestRoute.yieldMeasured
                                      ? appWindow.t("mining.yield_measured", "MEASURED YIELD")
                                      : appWindow.t("mining.yield_quality", "YIELD ESTIMATE"),
                             "value": yieldQuality(bestRoute)},
                            {"label": appWindow.t("mining.profitability", "PROFITABILITY"), "value": bestRoute.profitStars},
                            {"label": appWindow.t("mining.merit_fit", "MERIT SUITABILITY"), "value": bestRoute.meritStars},
                            {"label": appWindow.t("mining.data_confidence", "DATA CONFIDENCE"), "value": bestRoute.dataStars}
                        ]
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true; Layout.preferredHeight: 42; radius: 7; color: inputBackground
                            ColumnLayout { anchors.fill: parent; anchors.margins: 5; spacing: 1
                                Label { text: modelData.label; color: muted; font.pixelSize: 9; font.bold: true }
                                Label { text: modelData.value || "—"; color: orange; font.pixelSize: 13; font.bold: true }
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
                            Layout.fillWidth: true; Layout.preferredHeight: 40
                            radius: 7; color: backgroundSecondary
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 5; spacing: 1
                                Label { text: modelData.label; color: muted; font.pixelSize: 9; font.bold: true }
                                Label { text: modelData.value; color: textPrimary; font.pixelSize: 11; font.bold: true }
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
                anchors.fill: parent; anchors.margins: 10; spacing: 5
                Label { text: appWindow.t("mining.why_route", "WHY THIS ROUTE?"); color: orange; font.pixelSize: 10; font.bold: true }
                Repeater {
                    model: [
                        {"ok": bestRoute.meritKnown, "title": appWindow.t("mining.reason_merit", "Powerplay suitability"), "detail": (bestRoute.meritKnown || (bestRoute.sameSystemSaleRequired && !bestRoute.marketKnown)) ? bestRoute.meritStatus : (miningFinderPage.marketFiltersBlockRoute() ? appWindow.t("mining.reason_merit_filtered", "Unknown — active market filters leave no sell route to verify") : appWindow.t("mining.reason_merit_unknown", "Unknown — no merit claim is made"))},
                        {"ok": bestRoute.targetMatch === "LOCAL_YIELD" || bestRoute.targetMatch === "HOTSPOT", "title": appWindow.t("mining.reason_method", "Mining evidence"), "detail": yieldEvidence(bestRoute)},
                        {"ok": bestRoute.marketKnown, "title": appWindow.t("mining.reason_market", "Market demand"), "detail": bestRoute.marketKnown ? String(bestRoute.marketQualityStatus || "MARKET KNOWN") + " · " + (bestRoute.demandInfinite ? "∞" : formatNumber(bestRoute.demand) + " T") + " · " + String(bestRoute.marketSource || "EDDN") : miningFinderPage.marketDetail(bestRoute)},
                        {"ok": !bestRoute.stale, "title": appWindow.t("mining.reason_age", "Data freshness"), "detail": bestRoute.confirmationStatus || "—"}
                    ]
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.fillHeight: false
                        Layout.minimumHeight: 38
                        Layout.maximumHeight: 46
                        spacing: 7
                        Label { text: modelData.ok ? "✓" : "!"; color: modelData.ok ? green : orange; font.pixelSize: 14; font.bold: true }
                        ColumnLayout { Layout.fillWidth: true; spacing: 1
                            Label { text: modelData.title; color: textPrimary; font.pixelSize: 11; font.bold: true }
                            Label { Layout.fillWidth: true; text: modelData.detail; color: textSecondary; font.pixelSize: 10; elide: Text.ElideRight }
                        }
                    }
                }
                Item { Layout.fillHeight: true }
            }
        }
    }

    Item {
        objectName: "qa-mining-empty"
        Layout.fillWidth: true
        Layout.minimumHeight: 180
        Layout.preferredHeight: 200
        Layout.maximumHeight: 220
        visible: resultRows.length === 0 || marketQueryPending

        EmptyState {
            width: Math.min(parent.width, 720)
            anchors.centerIn: parent
            symbol: "◇"
            title: marketQueryPending
                   ? (!Boolean(marketDiagnostics.originKnown)
                      ? appWindow.t("mining.origin_loading", "RESOLVING START SYSTEM")
                      : appWindow.t("mining.market_loading", "CHECKING SAME-SYSTEM MARKETS"))
                   : (searchRevision === 0
                      ? appWindow.t("mining.empty_initial", "READY TO PLAN A MINING ROUTE")
                      : (!Boolean(marketDiagnostics.originKnown)
                         ? appWindow.t("mining.origin_unknown", "START SYSTEM COULD NOT BE RESOLVED")
                         : appWindow.t("mining.empty", "NO MATCHING MINING EVIDENCE")))
            detail: marketQueryPending
                    ? (!Boolean(marketDiagnostics.originKnown)
                       ? appWindow.t("mining.origin_loading_help", "Coordinates are loading so the selected search radius can be applied safely.")
                       : appWindow.t("mining.market_loading_help", "EDDN market evidence is loading. Routes appear only after the current search can be evaluated."))
                    : (searchRevision === 0
                       ? appWindow.t("mining.empty_initial_help", "Choose your goal and filters above, then select FIND BEST ROUTE. Market and Powerplay data load when the search starts.")
                       : (!Boolean(marketDiagnostics.originKnown)
                          ? appWindow.t("mining.origin_unknown_help", "Check the system name or retry when the coordinate source is available. No galaxy-wide fallback search was started.")
                          : appWindow.t("mining.empty_unified_help", "Widen the radius or relax hotspot, reserve and method filters. Unknown market data never hides a valid mining location.")))
            tone: cyan
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 120
        visible: resultRows.length > 0 && !marketQueryPending
        spacing: 5
        RowLayout {
            Layout.fillWidth: true
            Label { text: appWindow.tf("mining.alternatives", "%1 ALTERNATIVES", [alternativeRows.length]); color: orange; font.pixelSize: 12; font.bold: true }
            Item { Layout.fillWidth: true }
            Label { text: appWindow.t("mining.sort_goal", "SORTED BY SELECTED GOAL · UNKNOWN VALUES LAST"); color: muted; font.pixelSize: 9; font.bold: true }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 31; color: panelRaised; radius: 7
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 11; anchors.rightMargin: 11; spacing: 10
                Label { Layout.minimumWidth: routeRankWidth; Layout.preferredWidth: routeRankWidth; Layout.maximumWidth: routeRankWidth; text: appWindow.t("mining.rank", "#"); color: muted; font.pixelSize: 9; font.bold: true }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; text: appWindow.t("mining.location", "MINING LOCATION"); color: muted; font.pixelSize: 9; font.bold: true }
                Label { Layout.minimumWidth: routeSaleWidth; Layout.preferredWidth: routeSaleWidth; Layout.maximumWidth: routeSaleWidth; text: appWindow.t("mining.sale", "SALE"); color: muted; font.pixelSize: 9; font.bold: true }
                Label { Layout.minimumWidth: routePriceWidth; Layout.preferredWidth: routePriceWidth; Layout.maximumWidth: routePriceWidth; text: appWindow.t("mining.price_per_tonne", "PRICE / T"); color: muted; font.pixelSize: 9; font.bold: true }
                Label { Layout.minimumWidth: routeDemandWidth; Layout.preferredWidth: routeDemandWidth; Layout.maximumWidth: routeDemandWidth; text: appWindow.t("mining.demand", "DEMAND"); color: muted; font.pixelSize: 9; font.bold: true }
                Label {
                    Layout.minimumWidth: routeStatusWidth
                    Layout.preferredWidth: routeStatusWidth
                    Layout.maximumWidth: routeStatusWidth
                    text: appliedOptimization === "POWERPLAY MERITS"
                          ? appWindow.t("mining.merit_fit", "MERIT FIT")
                          : appWindow.t("mining.market_age", "DATA AGE")
                    color: muted; font.pixelSize: 9; font.bold: true
                }
                Label { Layout.minimumWidth: routeSelectWidth; Layout.preferredWidth: routeSelectWidth; Layout.maximumWidth: routeSelectWidth; text: appWindow.t("mining.select", "SELECT"); color: muted; font.pixelSize: 9; font.bold: true; horizontalAlignment: Text.AlignHCenter }
            }
        }
        ListView {
            id: routesList
            Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 5; clip: true
            reuseItems: true
            cacheBuffer: 240
            model: alternativeRows
            section.property: "verificationGroupLabel"
            section.criteria: ViewSection.FullString
            section.delegate: Rectangle {
                width: routesList.width
                height: appliedOptimization === "POWERPLAY MERITS" ? 31 : 0
                visible: appliedOptimization === "POWERPLAY MERITS"
                color: "transparent"
                Label {
                    anchors.left: parent.left
                    anchors.leftMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    text: section
                    color: section === "POWERPLAY VERIFIED" ? green
                           : (section === "POWERPLAY DATA MISSING" ? cyan
                              : (section === "OUTSIDE FILTERS"
                                 || section === "MARKET DATA MISSING / STALE"
                                 || section === "POWERPLAY ROUTE KNOWN · MARKET DATA LIMITED"
                                 ? orange : muted))
                    font.pixelSize: 10
                    font.bold: true
                }
            }
            ScrollBar.vertical: CockpitScrollBar {
                trackThickness: 12
                thumbThickness: 8
                policy: ScrollBar.AlwaysOn
            }
            onContentYChanged: miningFinderPage._listScrollY = contentY
            delegate: Rectangle {
                id: routeRow
                required property var modelData
                required property int index
                width: routesList.width; height: 68; radius: 8
                color: routeHover.hovered ? appWindow.hover : panelRaised
                border.width: routeHover.hovered ? 2 : 1
                border.color: routeHover.hovered ? cyan
                                                     : (modelData.stale ? orange : borderTone)
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 11; anchors.rightMargin: 11; spacing: 10
                    Label { Layout.minimumWidth: routeRankWidth; Layout.preferredWidth: routeRankWidth; Layout.maximumWidth: routeRankWidth; text: String(routeIndex(modelData) + 1); color: orange; font.family: monoFont; font.pixelSize: 12; font.bold: true }
                    ColumnLayout { Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 2
                        Label { Layout.fillWidth: true; text: String(modelData.system || "UNKNOWN") + " · " + String(modelData.ring || modelData.body || ""); color: textPrimary; font.pixelSize: 11; font.bold: true; elide: Text.ElideRight }
                        Label { Layout.fillWidth: true; text: String(modelData.selectedCommodityName || appliedCommodityFilter) + " · " + String(modelData.reserveName || "UNKNOWN") + " · " + String(modelData.targetMatchName || "") + (appliedPreferSecondary && secondaryCompactSummary(modelData) ? " · " + secondaryCompactSummary(modelData) : ""); color: textSecondary; font.pixelSize: 9; elide: Text.ElideRight }
                    }
                    ColumnLayout { Layout.minimumWidth: routeSaleWidth; Layout.preferredWidth: routeSaleWidth; Layout.maximumWidth: routeSaleWidth; spacing: 2
                        Label { Layout.fillWidth: true; text: marketName(modelData); color: modelData.marketKnown ? textPrimary : orange; font.pixelSize: 10; font.bold: true; elide: Text.ElideRight }
                        Label { text: String(modelData.sellSystem || "") + (marketStationSummary(modelData) ? " · " + marketStationSummary(modelData) : ""); color: textSecondary; font.pixelSize: 9; elide: Text.ElideRight }
                    }
                    Label { Layout.minimumWidth: routePriceWidth; Layout.preferredWidth: routePriceWidth; Layout.maximumWidth: routePriceWidth; text: modelData.marketKnown ? formatNumber(modelData.sellPrice) + " CR" : "—"; color: modelData.marketMatchesFilters ? green : (modelData.marketKnown ? orange : muted); font.pixelSize: 10; font.bold: true }
                    Label { Layout.minimumWidth: routeDemandWidth; Layout.preferredWidth: routeDemandWidth; Layout.maximumWidth: routeDemandWidth; text: modelData.marketKnown ? (modelData.demandInfinite ? "∞" : formatNumber(modelData.demand) + " T") : "—"; color: textPrimary; font.pixelSize: 10; font.bold: true }
                    Label {
                        id: routeVerificationStatus
                        Layout.minimumWidth: routeStatusWidth
                        Layout.preferredWidth: routeStatusWidth
                        Layout.maximumWidth: routeStatusWidth
                        text: appliedOptimization === "POWERPLAY MERITS"
                              ? verificationShortLabel(modelData)
                              : (modelData.marketKnown ? formatAge(modelData.marketAgeSeconds) : "—")
                        color: appliedOptimization === "POWERPLAY MERITS"
                               ? verificationColor(modelData)
                               : (modelData.stale ? orange : green)
                        font.pixelSize: 9; font.bold: true
                        elide: Text.ElideRight
                        ToolTip.visible: routeVerificationHover.hovered
                                             && verificationReason(modelData) !== ""
                        ToolTip.text: verificationReason(modelData)
                        HoverHandler { id: routeVerificationHover }
                    }
                    Label { Layout.minimumWidth: routeSelectWidth; Layout.preferredWidth: routeSelectWidth; Layout.maximumWidth: routeSelectWidth; text: appWindow.t("mining.use_route", "USE"); color: routeHover.hovered ? cyan : textSecondary; font.pixelSize: 10; font.bold: true; horizontalAlignment: Text.AlignHCenter }
                }
                HoverHandler {
                    id: routeHover
                    cursorShape: Qt.PointingHandCursor
                }
                TapHandler {
                    acceptedButtons: Qt.LeftButton
                    gesturePolicy: TapHandler.DragThreshold
                    onTapped: miningFinderPage.selectRoute(modelData)
                }
            }
        }
    }
    }
}
