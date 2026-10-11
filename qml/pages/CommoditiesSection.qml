import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../components/UiMetrics.js" as UiMetrics

Item {
    id: finder
    objectName: "commodityFinder"
    required property var appWindow
    component CommodityButton: CockpitAction {
        appWindow: finder.appWindow
        accentColor: primary ? appWindow.orange : appWindow.accent
    }
    component FilterField: Item {
        id: field
        default property alias controls: fieldLayout.data
        property string caption: ""
        implicitHeight: 20 + UiMetrics.controlHeight
        Layout.fillWidth: true; Layout.minimumWidth: 0
        Layout.alignment: Qt.AlignBottom
        ColumnLayout {
            id: fieldLayout
            anchors.fill: parent
            spacing: 4
            Label {
                Layout.fillWidth: true; Layout.minimumWidth: 0
                Layout.preferredHeight: 16
                text: field.caption
                color: finder.appWindow.textSecondary; font.pixelSize: 12
                elide: Text.ElideRight
                ToolTip.visible: captionHover.hovered && truncated
                ToolTip.text: text
                HoverHandler { id: captionHover }
            }
        }
    }
    readonly property var catalog: cockpit.commodityCatalog || []
    property bool filtersReady: false
    property string filterLanguage: ""
    readonly property var filterDraft: ({
        category: String(category.currentValue || "ALL"), commodity: String(commodity.currentValue || ""),
        nameFilter: search.text, origin: origin.text, direction: direction.currentIndex,
        radius: radius.currentIndex, quantity: quantity.value, age: age.currentIndex,
        pad: pad.currentIndex, excludeCarriers: carriers.checked, sorting: sorting.currentIndex
    })
    onFilterDraftChanged: if (filtersReady && filterLanguage === String(cockpit.interfaceLanguage)
                             && typeof appWindow.commodityFinderState !== "undefined")
        appWindow.commodityFinderState = filterDraft
    Connections {
        target: cockpit
        function onUiChanged() { Qt.callLater(finder.restoreFilters) }
    }
    function restoreFilters() {
        filtersReady = false
        var saved = appWindow.commodityFinderState || ({})
        if (Object.keys(saved).length) {
            search.text = saved.nameFilter
            category.currentIndex = Math.max(0, category.indexOfValue(saved.category))
            commodity.currentIndex = Math.max(0, commodity.indexOfValue(saved.commodity))
            origin.text = saved.origin; direction.currentIndex = saved.direction
            radius.currentIndex = saved.radius; quantity.value = saved.quantity
            age.currentIndex = saved.age; pad.currentIndex = saved.pad
            carriers.checked = saved.excludeCarriers; sorting.currentIndex = saved.sorting
        }
        filterLanguage = String(cockpit.interfaceLanguage)
        filtersReady = true
    }
    readonly property var lastSearch: cockpit.commodityLastSearch || ({})
    readonly property bool emptySearch: lastSearch.count === 0 && !cockpit.commodityBusy
    function runSearch() {
        if (!commodity.currentValue || cockpit.commodityBusy) return
        cockpit.searchCommodities(String(commodity.currentValue), String(direction.currentValue),
            [25,50,100,250,500,1000,2000,0][radius.currentIndex], quantity.value,
            [1,6,24,72,168][age.currentIndex], ["ANY","S","M","L"][pad.currentIndex],
            carriers.checked, origin.text.trim(), String(sorting.currentValue))
    }
    readonly property var categories: {
        var keys = []
        catalog.forEach(function(row) {
            if (row.category) keys.push(row.category)
            if (row.tradeCategory) keys.push(row.tradeCategory)
        })
        return ["ALL"].concat(Array.from(new Set(keys)).sort())
    }
    readonly property var filteredChoices: catalog.filter(function(r) {
        var query = search.text.trim().toLowerCase()
        return (category.currentValue === "ALL" || r.category === category.currentValue
            || r.tradeCategory === category.currentValue)
            && (!query || r.name.toLowerCase().indexOf(query) >= 0 || r.id.indexOf(query) >= 0)
    })
    readonly property var choices: category.currentValue === "Rare Goods" && filteredChoices.length
        ? [{id:"ALL_RARE_GOODS", name:appWindow.t("common.all", "ALL")}].concat(filteredChoices)
        : filteredChoices
    onVisibleChanged: if (visible) cockpit.loadCommodityCatalog()
    Component.onCompleted: { restoreFilters(); if (visible) cockpit.loadCommodityCatalog() }
    // Keep wrapping inside a viewport so navigation and filter layouts do
    // not repeatedly resize each other while switching between sections.
    CardSurface {
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        height: filterViewport.height
        tone: appWindow.accent; color: appWindow.panel
    }
    ColumnLayout {
        anchors.fill: parent
        spacing: 10
        Flickable {
            id: filterViewport
            objectName: "commodityFilterViewport"
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(contentHeight, Math.max(80, finder.height * 0.58))
            clip: true; contentWidth: width; contentHeight: filterContent.implicitHeight + 32
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: CockpitScrollBar {}
            ColumnLayout {
                id: filterContent
                x: 16; y: 16; width: Math.max(0, filterViewport.width - 32)
                spacing: 10
        GridLayout {
            Layout.fillWidth: true
            columns: finder.width >= 850 ? 4 : 2
            columnSpacing: 10; rowSpacing: 10
            FilterField {
                Layout.preferredWidth: 200
                caption: appWindow.t("commodities.category", "Commodity category")
                CockpitComboBox {
                    id: category; appWindow: finder.appWindow; Layout.fillWidth: true
                    Layout.preferredWidth: 200; Layout.minimumWidth: 0
                    font.pixelSize: 13
                    objectName: "commodityCategory"
                    model: finder.categories.map(function(key) {
                        return {key:key, label:key === "ALL" ? appWindow.t("common.all", "ALL")
                                : key === "Rare Goods" ? appWindow.t("commodities.rare", "RARE GOODS")
                                : appWindow.t("commodities.category." + key, key)}
                    })
                    textRole: "label"; valueRole: "key"
                    Accessible.name: appWindow.t("commodities.category", "Commodity category")
                }
            }
            FilterField {
                Layout.preferredWidth: 260
                caption: appWindow.t("commodities.choose", "Choose commodity")
                CockpitComboBox {
                    id: commodity; appWindow: finder.appWindow; Layout.fillWidth: true
                    objectName: "commodityChoice"
                    Layout.preferredWidth: 260; Layout.minimumWidth: 0
                    font.pixelSize: 13
                    model: finder.choices; textRole: "name"; valueRole: "id"
                    Accessible.name: appWindow.t("commodities.choose", "Choose commodity")
                }
            }
            FilterField {
                Layout.preferredWidth: 320
                caption: appWindow.t("commodities.filter", "Filter names")
                TextField {
                    id: search; Layout.fillWidth: true
                    objectName: "commoditySearch"
                    Layout.preferredWidth: 440; Layout.minimumWidth: 0
                    implicitHeight: 42; font.pixelSize: 14
                    placeholderText: appWindow.t("commodities.search", "Filter names or symbols…")
                    color: appWindow.textPrimary
                    placeholderTextColor: appWindow.textSecondary
                    background: Rectangle { radius: 6; color: appWindow.inputBackground; border.color: appWindow.borderTone }
                }
            }
            CommodityButton {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignBottom
                Layout.preferredWidth: 220; Layout.maximumWidth: 260; Layout.minimumWidth: 0
                text: appWindow.t("commodities.refresh", "REFRESH CATALOG")
                enabled: !cockpit.commodityBusy
                onClicked: cockpit.refreshCommodityCatalog()
            }
        }
        GridLayout {
            Layout.fillWidth: true
            columns: finder.width >= 700 ? 3 : 2
            columnSpacing: 10; rowSpacing: 10
            FilterField {
                Layout.preferredWidth: 460
                Layout.columnSpan: finder.width >= 700 ? 1 : 2
                caption: appWindow.t("commodities.origin", "Start system · blank uses Journal")
                TextField {
                    id: origin; objectName: "commodityOrigin"
                    Layout.fillWidth: true; Layout.minimumWidth: 0
                    implicitHeight: 42; font.pixelSize: 14; maximumLength: 100
                    enabled: !cockpit.commodityBusy
                    placeholderText: String(cockpit.system || "") || appWindow.t("commodities.origin_placeholder", "Enter an exact system name…")
                    color: appWindow.textPrimary; placeholderTextColor: appWindow.textSecondary
                    Accessible.name: appWindow.t("commodities.origin", "Start system · blank uses Journal")
                    onAccepted: if (!cockpit.commodityBusy && commodity.currentValue) finder.runSearch()
                    background: Rectangle { radius: 6; color: appWindow.inputBackground; border.color: appWindow.borderTone }
                }
            }
            CommodityButton {
                objectName: "commodityUseJournal"
                Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 200
                Layout.alignment: Qt.AlignBottom
                text: appWindow.t("commodities.use_journal", "USE CURRENT SYSTEM")
                enabled: !cockpit.commodityBusy
                onClicked: origin.clear()
            }
            FilterField {
                Layout.preferredWidth: 220
                caption: appWindow.t("commodities.sort", "Sort offers")
                CockpitComboBox {
                    id: sorting; objectName: "commoditySort"; appWindow: finder.appWindow
                    Layout.fillWidth: true; Layout.minimumWidth: 0; font.pixelSize: 13
                    model: [{key:"PRICE", label:appWindow.t("commodities.sort_price", "Best price")},
                        {key:"DISTANCE", label:appWindow.t("commodities.sort_distance", "Nearest first")},
                        {key:"AGE", label:appWindow.t("commodities.sort_age", "Freshest first")}]
                    textRole: "label"; valueRole: "key"
                }
            }
        }
        Label {
            Layout.fillWidth: true; wrapMode: Text.WordWrap
            Layout.minimumHeight: implicitHeight
            visible: finder.catalog.length > 0 && finder.choices.length === 0
            text: appWindow.t("commodities.no_match", "No matching commodity · clear the name filter or choose another category.")
            color: appWindow.orange; font.pixelSize: 12
        }
        GridLayout {
            Layout.fillWidth: true
            columns: finder.width >= 1000 ? 5 : 3
            columnSpacing: 10; rowSpacing: 10
            FilterField {
                Layout.preferredWidth: 240
                caption: appWindow.t("commodities.direction", "Trade direction")
                CockpitComboBox {
                    id: direction; appWindow: finder.appWindow; Layout.fillWidth: true
                    objectName: "commodityDirection"
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 240; Layout.alignment: Qt.AlignBottom; font.pixelSize: 13
                    model: [{key:"BUY",name:appWindow.t("commodities.buy", "BUY · available stock")},
                    {key:"SELL",name:appWindow.t("commodities.sell", "SELL · demand")}]
                    textRole: "name"; valueRole: "key"
                }
            }
            FilterField {
                Layout.preferredWidth: 140
                caption: appWindow.t("nav.services.radius", "Search radius")
                CockpitComboBox {
                    id: radius; appWindow: finder.appWindow; Layout.fillWidth: true
                    objectName: "commodityRadius"
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 140; Layout.alignment: Qt.AlignBottom; font.pixelSize: 13
                    model: ["25 LY", "50 LY", "100 LY", "250 LY", "500 LY", "1000 LY", "2000 LY",
                        appWindow.t("commodities.unlimited", "UNLIMITED")]; currentIndex: 2
                }
            }
            FilterField {
                Layout.preferredWidth: 140
                caption: appWindow.t("nav.services.pad", "Required landing pad")
                CockpitComboBox {
                    id: pad; appWindow: finder.appWindow; Layout.fillWidth: true
                    objectName: "commodityPad"
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 140; Layout.alignment: Qt.AlignBottom; font.pixelSize: 13
                    model: [appWindow.t("nav.services.pad_any", "ANY PAD"), "S", "M", "L"]
                }
            }
            FilterField {
                Layout.fillWidth: true; Layout.preferredWidth: 160; Layout.alignment: Qt.AlignBottom
                caption: appWindow.t("commodities.quantity", "Minimum tonnes")
                SpinBox {
                    id: quantity; Layout.fillWidth: true; implicitHeight: 42
                    objectName: "commodityQuantity"
                    Layout.minimumWidth: 0
                    from: 1; to: 1000000; value: 1; editable: true
                    font.pixelSize: 13
                    Accessible.name: appWindow.t("commodities.quantity", "Minimum tonnes")
                    palette.base: appWindow.inputBackground
                    palette.text: appWindow.textPrimary
                    palette.button: appWindow.panelRaised
                    palette.buttonText: appWindow.textPrimary
                }
            }
            FilterField {
                Layout.preferredWidth: 140
                caption: appWindow.t("commodities.age", "Maximum quote age")
                CockpitComboBox {
                    id: age; appWindow: finder.appWindow; Layout.fillWidth: true
                    objectName: "commodityAge"
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 140; Layout.alignment: Qt.AlignBottom; font.pixelSize: 13
                    model: ["1 h", "6 h", "24 h", "72 h", "168 h"]; currentIndex: 2
                    Accessible.name: appWindow.t("commodities.age", "Maximum quote age")
                }
            }
        }
        Label {
            objectName: "commodityUnlimitedHint"
            Layout.fillWidth: true; Layout.minimumHeight: implicitHeight
            visible: radius.currentIndex === 7
            wrapMode: Text.WordWrap; font.pixelSize: 12; color: appWindow.textSecondary
            text: appWindow.t("commodities.unlimited_hint", "Search all known markets without a distance limit. Up to 100 offers in the selected order; distances are still shown.")
        }
        Label {
            objectName: "commodityCarrierHint"
            Layout.fillWidth: true; Layout.minimumHeight: implicitHeight
            visible: carriers.checked && direction.currentValue === "BUY"
            wrapMode: Text.WordWrap; font.pixelSize: 12; color: appWindow.orange
            text: appWindow.t("commodities.carriers_excluded", "Fleet Carriers are excluded. Include them to find player offers for mined and mission-reward commodities.")
        }
        Text {
            id: statusText
            Layout.fillWidth: true; Layout.minimumHeight: statusMeasure.implicitHeight; Layout.preferredHeight: statusMeasure.implicitHeight
            wrapMode: Text.WordWrap; font.pixelSize: 13
            text: cockpit.commodityStatus || ""; color: appWindow.accentSecondary
        }
        Text {
            id: hintText
            Layout.fillWidth: true; Layout.minimumHeight: hintMeasure.implicitHeight; Layout.preferredHeight: hintMeasure.implicitHeight
            wrapMode: Text.WordWrap; font.pixelSize: 12
            text: appWindow.t("commodities.hint", "Station and carrier offers. Best price: BUY cheapest, SELL highest. Sorting applies to all matching markets. Stock and docking access can change.")
            objectName: "commodityHint"
            color: appWindow.textSecondary
        }
        // Measure wrapping at the final available width, independent of the
        // layout's first (unconstrained) text measurement and resize cache.
        Text { id: statusMeasure; visible: false; width: finder.width; text: statusText.text; font: statusText.font; wrapMode: Text.WordWrap }
        Text { id: hintMeasure; visible: false; width: finder.width; text: hintText.text; font: hintText.font; wrapMode: Text.WordWrap }
        Label {
            objectName: "commoditySearchFilters"
            Layout.fillWidth: true; Layout.minimumHeight: implicitHeight
            visible: !!finder.lastSearch.system
            wrapMode: Text.WordWrap; font.pixelSize: 12; color: appWindow.textSecondary
            text: appWindow.t("commodities.used_filters", "Last search filters") + ": " + String(finder.lastSearch.system || "")
                + " · " + (finder.lastSearch.radius == null ? appWindow.t("commodities.unlimited", "UNLIMITED") : String(finder.lastSearch.radius) + " LY")
                + " · ≥ " + String(finder.lastSearch.quantity) + " T · ≤ " + String(finder.lastSearch.ageHours) + " h"
                + " · " + appWindow.t("nav.services.pad_short", "PAD") + " " + String(finder.lastSearch.pad)
                + " · " + (finder.lastSearch.excludeCarriers ? appWindow.t("nav.services.exclude_carriers", "Exclude Fleet Carriers")
                    : appWindow.t("commodities.with_carriers", "Carriers included"))
                + " · " + appWindow.t("commodities.sort_" + ({PRICE:"price",DISTANCE:"distance",AGE:"age"}[finder.lastSearch.sortBy] || "price"), "Best price")
        }
        Flow {
            Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height
            visible: finder.emptySearch
            spacing: 8
            CommodityButton {
                objectName: "commodityIncludeCarriers"
                visible: finder.lastSearch.excludeCarriers === true
                text: appWindow.t("commodities.include_carriers", "INCLUDE CARRIERS + SEARCH")
                onClicked: { carriers.checked = false; finder.runSearch() }
            }
            CommodityButton {
                objectName: "commodityExpandRadius"
                visible: finder.lastSearch.radius != null
                text: appWindow.t("commodities.expand_radius", "EXPAND RADIUS + SEARCH")
                onClicked: { radius.currentIndex = Math.min(7, radius.currentIndex + 1); finder.runSearch() }
            }
            CommodityButton {
                objectName: "commodityIncreaseAge"
                visible: finder.lastSearch.ageHours < 168
                text: appWindow.t("commodities.increase_age", "ALLOW 7 DAYS + SEARCH")
                onClicked: { age.currentIndex = 4; finder.runSearch() }
            }
            CommodityButton {
                objectName: "commodityReduceQuantity"
                visible: finder.lastSearch.quantity > 1
                text: appWindow.t("commodities.reduce_quantity", "FROM 1 TONNE + SEARCH")
                onClicked: { quantity.value = 1; finder.runSearch() }
            }
        }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            CheckBox {
                id: carriers; checked: false
                objectName: "commodityExcludeCarriers"
                Layout.fillWidth: true; Layout.minimumWidth: 0
                text: appWindow.t("nav.services.exclude_carriers", "Exclude Fleet Carriers")
                palette.windowText: appWindow.textPrimary
            }
            CommodityButton {
                objectName: "commodityTradeRoute"
                Layout.preferredWidth: 190; Layout.maximumWidth: finder.width * 0.3
                text: appWindow.t("trade.with_commodity", "TRADE THIS COMMODITY")
                enabled: !!commodity.currentValue && commodity.currentValue !== "ALL_RARE_GOODS"
                onClicked: {
                    appWindow.tradeRouteCommodity = String(commodity.currentValue)
                    appWindow.tradeRouteOrigin = origin.text.trim()
                    appWindow.tradeRouteSeedRevision += 1
                    appWindow.navCommoditiesOpen = false
                    appWindow.navStationServicesOpen = false
                    appWindow.navTradeRoutesOpen = true
                }
            }
            CommodityButton {
                objectName: "commodityFind"
                pictogram: "search"
                Layout.preferredWidth: 220; Layout.maximumWidth: finder.width * 0.5
                primary: true
                text: appWindow.t("commodities.find", "FIND OFFERS")
                enabled: !cockpit.commodityBusy && !!commodity.currentValue
                onClicked: finder.runSearch()
            }
        }
        ListView {
            id: offers; Layout.fillWidth: true; Layout.fillHeight: true
            objectName: "commodityOffers"
            clip: true; spacing: 8; model: cockpit.commodityRows || []
            ScrollBar.vertical: CockpitScrollBar {}
            delegate: CommodityOfferCard {
                required property var modelData
                required property int index
                appWindow: finder.appWindow
                offerData: modelData; rank: index + 1
                preferredPrice: index === 0 && finder.lastSearch.sortBy === "PRICE"
                width: offers.width
                onCopySystem: function(system) { cockpit.copySystem(system) }
            }
            ColumnLayout {
                objectName: "commodityEmptyState"
                anchors.centerIn: parent
                width: Math.max(0, offers.width - 24)
                visible: offers.count === 0 && !cockpit.commodityBusy
                spacing: 6
                Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter; font.bold: true
                    color: appWindow.muted
                    text: finder.catalog.length === 0
                        ? appWindow.t("commodities.no_catalog", "NO COMMODITY CATALOG")
                        : finder.emptySearch ? appWindow.t("commodities.no_filtered_offers", "NO OFFERS WITH THESE FILTERS")
                        : appWindow.t("commodities.no_offers", "NO OFFERS SHOWN")
                }
                Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter; font.pixelSize: 12
                    color: appWindow.textSecondary
                    text: finder.catalog.length === 0
                        ? appWindow.t("commodities.no_catalog_help", "Enable the ED-Frame catalog server in Connections, then refresh the catalog.")
                        : appWindow.t("commodities.no_offers_help", "Choose a commodity and search. If no offers are found, include carriers, increase the radius or quote age, or reduce the minimum tonnes.")
                }
            }
        }
    }
}
