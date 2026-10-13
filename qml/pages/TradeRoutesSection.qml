import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: routes
    objectName: "tradeRoutesFinder"
    required property var appWindow
    readonly property var snapshot: cockpit.tradeRouteSnapshot || ({})
    readonly property var choices: [{id:"ALL",name:appWindow.t("trade.all", "ALL COMMODITIES")}].concat(cockpit.commodityCatalog || [])
    property int appliedSeedRevision: -1
    property bool filtersExpanded: true
    property bool filtersReady: false
    property string filterLanguage: ""
    readonly property var filterDraft: ({
        origin: origin.text, commodity: String(commodity.currentValue || "ALL"), capacity: cargo.value,
        budget: budget.text, radius: radius.currentIndex, leg: leg.currentIndex, age: age.currentIndex,
        pad: pad.currentIndex, excludeCarriers: carriers.checked, sorting: sorting.currentIndex,
        expanded: filtersExpanded, seedRevision: appliedSeedRevision, snapshot: appliedSnapshot
    })
    onFilterDraftChanged: if (filtersReady && filterLanguage === String(cockpit.interfaceLanguage)
                             && typeof appWindow.tradeRouteFinderState !== "undefined")
        appWindow.tradeRouteFinderState = filterDraft
    function restoreFilters() {
        filtersReady = false
        var saved = appWindow.tradeRouteFinderState || ({})
        if (Object.keys(saved).length) {
            origin.text = saved.origin
            commodity.currentIndex = Math.max(0, commodity.indexOfValue(saved.commodity))
            cargo.value = saved.capacity; budget.text = saved.budget
            radius.currentIndex = saved.radius; leg.currentIndex = saved.leg
            age.currentIndex = saved.age; pad.currentIndex = saved.pad
            carriers.checked = saved.excludeCarriers; sorting.currentIndex = saved.sorting
            filtersExpanded = saved.expanded; appliedSnapshot = saved.snapshot
            appliedSeedRevision = saved.seedRevision
        } else useShip()
        filterLanguage = String(cockpit.interfaceLanguage)
        filtersReady = true
    }
    property string appliedSnapshot: ""
    property var displayedRows: []
    property string displayedRowsKey: ""
    function syncRows() {
        var rows = cockpit.tradeRouteRows || []
        var key = JSON.stringify(rows)
        if (key !== displayedRowsKey) {
            displayedRowsKey = key
            displayedRows = rows
        }
    }
    Connections {
        target: cockpit
        function onTradeRoutesChanged() { routes.syncRows() }
        function onUiChanged() { restoreTimer.restart() }
    }
    // A page switch also saves UI settings. Cancel deferred restoration when
    // this page unloads, instead of calling into its destroyed QML context.
    Timer {
        id: restoreTimer
        interval: 0
        onTriggered: routes.restoreFilters()
    }
    onSnapshotChanged: {
        var stamp = String(snapshot.generatedAt || "")
        if (stamp && stamp !== appliedSnapshot) {
            filtersExpanded = false
            appliedSnapshot = stamp
        }
    }
    function cr(value) { return Number(value).toLocaleString(Qt.locale(), "f", 0) + " CR" }
    function ly(value) { return Number(value).toLocaleString(Qt.locale(), "f", 1) + " LY" }
    function tonnes(value) { return Number(value).toLocaleString(Qt.locale(), "f", 0) + " T" }
    function useShip() {
        var defaults = cockpit.tradeRouteDefaults || ({})
        cargo.value = Number(defaults.capacity || 100)
        budget.text = String(defaults.budget === undefined ? 10000000 : defaults.budget)
    }
    function seed() {
        if (appliedSeedRevision === appWindow.tradeRouteSeedRevision) return
        var symbol = appWindow.tradeRouteCommodity || "ALL"
        var index = choices.findIndex(function(row) { return row.id === symbol })
        if (index < 0) return
        origin.text = appWindow.tradeRouteOrigin || ""
        commodity.currentIndex = index
        appliedSeedRevision = appWindow.tradeRouteSeedRevision
    }
    function search() {
        if (cockpit.tradeRoutesBusy || Number(budget.text) < 1 || Number(budget.text) > 1000000000000) return
        cockpit.searchTradeRoutes(origin.text.trim(), String(commodity.currentValue || "ALL"), cargo.value,
            Number(budget.text), [25,50,100,250,500][radius.currentIndex], [25,50,100,250,500][leg.currentIndex],
            [1,6,24,72,168][age.currentIndex], ["ANY","S","M","L"][pad.currentIndex],
            carriers.checked, String(sorting.currentValue), false)
    }
    onVisibleChanged: if (visible) { cockpit.loadCommodityCatalog(); seed() }
    onChoicesChanged: if (visible) seed()
    Component.onCompleted: { restoreFilters(); syncRows(); if (visible) { cockpit.loadCommodityCatalog(); seed() } }
    component RouteButton: CockpitAction {
        appWindow: routes.appWindow
        accentColor: primary ? appWindow.orange : appWindow.accent
    }
    component Field: Item {
        id: field
        default property alias controls: contents.data
        property string caption: ""
        implicitHeight: 62; Layout.fillWidth: true; Layout.minimumWidth: 0
        ColumnLayout {
            id: contents; anchors.fill: parent; spacing: 4
            Label {
                Layout.fillWidth: true; Layout.preferredHeight: 16
                text: field.caption; color: routes.appWindow.textSecondary; font.pixelSize: 12
                elide: Text.ElideRight
                ToolTip.visible: captionHover.hovered && truncated; ToolTip.text: text
                HoverHandler { id: captionHover }
            }
        }
    }
    component Input: TextField {
        Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 42; font.pixelSize: 14
        color: routes.appWindow.textPrimary; placeholderTextColor: routes.appWindow.textSecondary
        background: Rectangle { radius: 6; color: routes.appWindow.inputBackground; border.color: routes.appWindow.borderTone }
    }
    CardSurface {
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        height: filters.height; visible: routes.filtersExpanded
        tone: appWindow.accent; color: appWindow.panel
    }
    ColumnLayout {
        anchors.fill: parent; spacing: 10
        Flickable {
            id: filters
            objectName: "tradeRouteFilterViewport"
            visible: routes.filtersExpanded
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(contentHeight, Math.max(80, routes.height * 0.46))
            contentWidth: width; contentHeight: filterContent.implicitHeight + 32
            clip: true; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: CockpitScrollBar {}
            ColumnLayout {
                id: filterContent; x: 16; y: 16; width: Math.max(0, filters.width - 32); spacing: 10
                GridLayout {
                    Layout.fillWidth: true; columns: routes.width >= 700 ? 3 : 2
                    columnSpacing: 10; rowSpacing: 10
                    Field {
                        Layout.preferredWidth: 440; Layout.columnSpan: routes.width >= 700 ? 1 : 2
                        caption: appWindow.t("commodities.origin", "Start system · blank uses Journal")
                        Input {
                            id: origin; objectName: "tradeRouteOrigin"; maximumLength: 100
                            enabled: !cockpit.tradeRoutesBusy
                            placeholderText: String(cockpit.system || "")
                            Accessible.name: appWindow.t("commodities.origin", "Start system · blank uses Journal")
                        }
                    }
                    RouteButton {
                        objectName: "tradeRouteUseJournal"; Layout.fillWidth: true; Layout.minimumWidth: 0
                        Layout.alignment: Qt.AlignBottom; Layout.preferredWidth: 200
                        text: appWindow.t("commodities.use_journal", "USE CURRENT SYSTEM")
                        enabled: !cockpit.tradeRoutesBusy
                        onClicked: origin.clear()
                    }
                    RouteButton {
                        objectName: "tradeRouteUseShip"; Layout.fillWidth: true; Layout.minimumWidth: 0
                        Layout.alignment: Qt.AlignBottom; Layout.preferredWidth: 220
                        text: appWindow.t("trade.use_ship", "USE SHIP VALUES")
                        enabled: !cockpit.tradeRoutesBusy
                        onClicked: routes.useShip()
                    }
                }
                GridLayout {
                    Layout.fillWidth: true; columns: routes.width >= 1000 ? 4 : 2
                    columnSpacing: 10; rowSpacing: 10
                    Field {
                        caption: appWindow.t("trade.outbound_commodity", "Outbound commodity")
                        CockpitComboBox {
                            id: commodity; objectName: "tradeRouteCommodity"; appWindow: routes.appWindow
                            Layout.fillWidth: true; Layout.minimumWidth: 0; font.pixelSize: 13
                            model: routes.choices; textRole: "name"; valueRole: "id"
                        }
                    }
                    Field {
                        caption: appWindow.t("trade.cargo", "Cargo limit (tonnes)")
                        SpinBox {
                            id: cargo; objectName: "tradeRouteCargo"
                            Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 42
                            from: 1; to: 100000; value: 100; editable: true; font.pixelSize: 13
                            palette.base: appWindow.inputBackground; palette.text: appWindow.textPrimary
                            palette.button: appWindow.panelRaised; palette.buttonText: appWindow.textPrimary
                        }
                    }
                    Field {
                        caption: appWindow.t("trade.budget", "Purchase budget (CR)")
                        Input {
                            id: budget; objectName: "tradeRouteBudget"; text: String(10000000); maximumLength: 13
                            validator: RegularExpressionValidator { regularExpression: /[0-9]{1,13}/ }
                            Accessible.name: appWindow.t("trade.budget", "Purchase budget (CR)")
                        }
                    }
                    Field {
                        caption: appWindow.t("trade.radius", "Find station A within")
                        CockpitComboBox {
                            id: radius; objectName: "tradeRouteRadius"; appWindow: routes.appWindow
                            Layout.fillWidth: true; Layout.minimumWidth: 0; font.pixelSize: 13
                            model: ["25 LY","50 LY","100 LY","250 LY","500 LY"]; currentIndex: 1
                        }
                    }
                    Field {
                        caption: appWindow.t("trade.max_leg", "Maximum A → B distance")
                        CockpitComboBox {
                            id: leg; objectName: "tradeRouteLegDistance"; appWindow: routes.appWindow
                            Layout.fillWidth: true; Layout.minimumWidth: 0; font.pixelSize: 13
                            model: ["25 LY","50 LY","100 LY","250 LY","500 LY"]; currentIndex: 2
                        }
                    }
                    Field {
                        caption: appWindow.t("commodities.age", "Maximum quote age")
                        CockpitComboBox {
                            id: age; objectName: "tradeRouteAge"; appWindow: routes.appWindow
                            Layout.fillWidth: true; Layout.minimumWidth: 0; font.pixelSize: 13
                            model: ["1 h","6 h","24 h","72 h","168 h"]; currentIndex: 2
                        }
                    }
                    Field {
                        caption: appWindow.t("nav.services.pad", "Required landing pad")
                        CockpitComboBox {
                            id: pad; objectName: "tradeRoutePad"; appWindow: routes.appWindow
                            Layout.fillWidth: true; Layout.minimumWidth: 0; font.pixelSize: 13
                            model: [appWindow.t("nav.services.pad_any", "ANY PAD"),"S","M","L"]
                        }
                    }
                    Field {
                        caption: appWindow.t("trade.sort", "Rank round trips")
                        CockpitComboBox {
                            id: sorting; objectName: "tradeRouteSort"; appWindow: routes.appWindow
                            Layout.fillWidth: true; Layout.minimumWidth: 0; font.pixelSize: 13
                            model: [{key:"PROFIT",name:appWindow.t("trade.profit", "Round-trip profit")},
                                {key:"UNIT_PROFIT",name:appWindow.t("trade.unit_profit", "Combined margin / T")},
                                {key:"DISTANCE",name:appWindow.t("trade.shortest", "Shortest total distance")}]
                            textRole: "name"; valueRole: "key"
                        }
                    }
                }
                CheckBox {
                    id: carriers; objectName: "tradeRouteExcludeCarriers"; checked: false
                    Layout.fillWidth: true; Layout.minimumWidth: 0
                    text: appWindow.t("nav.services.exclude_carriers", "Exclude Fleet Carriers")
                    palette.windowText: appWindow.textPrimary
                }
                Label {
                    Layout.fillWidth: true; Layout.minimumHeight: implicitHeight
                    text: appWindow.t("trade.hint", "Use free cargo space and check your budget. Ship values describe capacity, not necessarily empty space. Prices and docking access can change; profit is an estimate.")
                    wrapMode: Text.WordWrap; font.pixelSize: 12; color: appWindow.textSecondary
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            RouteButton {
                objectName: "tradeRouteToggleFilters"
                Layout.fillWidth: true; Layout.minimumWidth: 0
                Layout.maximumWidth: 190
                text: routes.filtersExpanded ? appWindow.t("trade.hide_filters", "HIDE FILTERS") : appWindow.t("trade.show_filters", "EDIT FILTERS")
                onClicked: routes.filtersExpanded = !routes.filtersExpanded
            }
            Item { Layout.fillWidth: true; Layout.minimumWidth: 0 }
            RouteButton {
                objectName: "tradeRouteRefresh"; Layout.preferredWidth: 180; Layout.maximumWidth: routes.width * 0.3
                pictogram: "refresh"
                text: appWindow.t("trade.refresh", "CHECK PRICES AGAIN")
                enabled: !cockpit.tradeRoutesBusy && !!routes.snapshot.system
                onClicked: cockpit.refreshTradeRoutes()
            }
            RouteButton {
                objectName: "tradeRouteFind"; Layout.preferredWidth: 200; Layout.maximumWidth: routes.width * 0.35
                pictogram: "search"
                primary: true; text: appWindow.t("trade.find", "FIND ROUND TRIPS")
                enabled: !cockpit.tradeRoutesBusy && Number(budget.text) >= 1 && Number(budget.text) <= 1000000000000
                onClicked: routes.search()
            }
        }
        Label {
            objectName: "tradeRouteStatus"; Layout.fillWidth: true; Layout.minimumHeight: implicitHeight
            text: cockpit.tradeRouteStatus || ""; color: appWindow.accentSecondary; font.pixelSize: 13; wrapMode: Text.WordWrap
        }
        Label {
            objectName: "tradeRouteCoverage"; Layout.fillWidth: true; Layout.minimumHeight: implicitHeight
            visible: !!routes.snapshot.system
            color: routes.snapshot.coverage && routes.snapshot.coverage.sampled ? appWindow.orange : appWindow.textSecondary
            font.pixelSize: 12; wrapMode: Text.WordWrap
            text: {
                var f = routes.snapshot.filters || ({})
                var c = routes.snapshot.coverage || ({})
                return String(routes.snapshot.system || "") + " · " + routes.tonnes(f.cargoTonnes || 0) + " · " + routes.cr(f.budgetCr || 0)
                    + " · " + String(f.radiusLy || 0) + " LY / " + String(f.maxLegLy || 0) + " LY · ≤ " + String(f.maxAgeHours || 0) + " h"
                    + " · " + String(f.landingPad || "ANY") + " PAD"
                    + " · " + appWindow.t(f.excludeCarriers ? "nav.services.exclude_carriers" : "commodities.with_carriers", f.excludeCarriers ? "Exclude Fleet Carriers" : "Carriers included")
                    + " · " + appWindow.t("trade.coverage", "Checked markets") + ": " + String(c.stations || 0) + " / " + String(c.availableStations || 0)
                    + (c.sampled ? " · " + appWindow.t("trade.sample", "Suggestions from a regional sample") : "")
                    + (routes.snapshot.cached ? " · " + appWindow.t("trade.cached", "Recent search snapshot") : "")
            }
        }
        ListView {
            id: list; objectName: "tradeRouteResults"
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 10
            model: routes.displayedRows
            ScrollBar.vertical: CockpitScrollBar {}
            delegate: TradeRouteCard {
                required property var modelData
                required property int index
                width: list.width
                appWindow: routes.appWindow
                routeData: modelData
                rank: index + 1
                selected: modelData.id === cockpit.selectedTradeRouteId
                onSelectRoute: cockpit.selectTradeRoute(String(modelData.id))
                onCopySystem: function(system) { cockpit.copySystem(system) }
            }
            ColumnLayout {
                objectName: "tradeRouteEmptyState"; anchors.centerIn: parent; width: Math.max(0,list.width-24)
                visible: list.count === 0 && !cockpit.tradeRoutesBusy
                Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter
                    text: appWindow.t("trade.no_routes", "NO ROUND TRIPS SHOWN"); font.bold: true; color: appWindow.muted
                }
                Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 12
                    text: appWindow.t("trade.no_routes_help", "Both directions need fresh prices, positive profit and available stock/demand. Try all commodities, a larger radius or older quotes, and check the server connection.")
                    color: appWindow.textSecondary
                }
            }
        }
    }
}
