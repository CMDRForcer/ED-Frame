import QtQuick
import "../components/UiMetrics.js" as UiMetrics
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ColumnLayout {
    id: explorationPage
    required property var appWindow
    required property real sidebarWidth

    readonly property var findings: (cockpit.explorationFindings || []).filter(function(row) {
        return row.hasScan === true
    })
    readonly property var systems: (cockpit.explorationSystems || []).filter(function(row) {
        return Number(row.bodyCount || 0) > 0
    })
    readonly property var summary: cockpit.explorationSummary || ({})
    property string selectedSystemId: ""
    property bool valueFirst: true

    readonly property color cyan: appWindow.cyan
    readonly property color green: appWindow.green
    readonly property color orange: appWindow.orange
    readonly property color danger: appWindow.danger
    readonly property color textPrimary: appWindow.textPrimary
    readonly property color textSecondary: appWindow.textSecondary
    readonly property color muted: appWindow.muted
    readonly property color panelRaised: appWindow.panelRaised
    readonly property color borderTone: appWindow.borderTone
    readonly property color inputBackground: appWindow.inputBackground
    readonly property color warningBackground: appWindow.warningBackground
    readonly property color successBackground: appWindow.successBackground
    readonly property string monoFont: "Consolas"

    readonly property var displayedFindings: {
        var filtered = findings.filter(function(row) {
            return !selectedSystemId || row.systemKey === selectedSystemId
        })
        return filtered.slice(0).sort(function(a, b) {
            if (valueFirst) {
                var valueDelta = Number(b.estimatedValueMax || -1)
                                 - Number(a.estimatedValueMax || -1)
                if (valueDelta !== 0)
                    return valueDelta
            }
            var systemDelta = String(a.systemName || "").localeCompare(
                                  String(b.systemName || ""))
            if (systemDelta !== 0)
                return systemDelta
            return Number(a.bodyId || 0) - Number(b.bodyId || 0)
        })
    }

    function formatCr(value) {
        return Number(value || 0).toLocaleString(Qt.locale(), "f", 0) + " CR"
    }
    function formatValueRange(minimum, maximum, status) {
        if (status === "unavailable" || minimum === null || maximum === null
                || minimum === undefined || maximum === undefined)
            return appWindow.t("exploration.value_unavailable", "VALUE UNAVAILABLE")
        if (Number(minimum) === Number(maximum))
            return formatCr(minimum)
        return formatCr(minimum) + " – " + formatCr(maximum)
    }
    function tagLabel(tag) {
        var labels = {
            "EARTH_LIKE": appWindow.t("exploration.tag_earthlike", "EARTH-LIKE"),
            "WATER_WORLD": appWindow.t("exploration.tag_water", "WATER WORLD"),
            "AMMONIA_WORLD": appWindow.t("exploration.tag_ammonia", "AMMONIA WORLD"),
            "TERRAFORMABLE": appWindow.t("exploration.tag_terraformable", "TERRAFORMABLE"),
            "NEUTRON_STAR": appWindow.t("exploration.tag_neutron", "NEUTRON STAR"),
            "BLACK_HOLE": appWindow.t("exploration.tag_black_hole", "BLACK HOLE"),
            "WHITE_DWARF": appWindow.t("exploration.tag_white_dwarf", "WHITE DWARF"),
            "POSSIBLE_FIRST_DISCOVERY": appWindow.t("exploration.tag_first_discovery", "FIRST DISCOVERY POSSIBLE"),
            "DISCOVERY_STATUS_UNKNOWN": appWindow.t("exploration.tag_discovery_unknown", "DISCOVERY STATUS UNKNOWN"),
            "MAPPED": appWindow.t("exploration.tag_mapped", "MAPPED"),
            "POSSIBLE_FIRST_MAPPING": appWindow.t("exploration.tag_first_mapping", "FIRST MAPPING POSSIBLE"),
            "MAPPING_STATUS_UNKNOWN": appWindow.t("exploration.tag_mapping_unknown", "MAPPING STATUS UNKNOWN"),
            "EFFICIENCY_BONUS": appWindow.t("exploration.tag_efficiency", "EFFICIENCY BONUS"),
            "BIOLOGICAL_SIGNALS": appWindow.t("exploration.tag_biological", "BIOLOGICAL SIGNALS"),
            "GEOLOGICAL_SIGNALS": appWindow.t("exploration.tag_geological", "GEOLOGICAL SIGNALS")
        }
        return labels[tag] || tag
    }
    function tagLine(tags) {
        return (tags || []).map(function(tag) { return tagLabel(tag) }).join("  ·  ")
    }
    function findingDetail(row) {
        var details = []
        if (row.distanceFromArrivalLs !== null && row.distanceFromArrivalLs !== undefined)
            details.push(appWindow.tf("exploration.distance_ls", "%1 LS FROM ARRIVAL", [Number(row.distanceFromArrivalLs).toLocaleString(Qt.locale(), "f", 1)]))
        if (row.massEarths !== null && row.massEarths !== undefined)
            details.push(appWindow.tf("exploration.mass_earths", "%1 EARTH MASSES", [Number(row.massEarths).toLocaleString(Qt.locale(), "f", 3)]))
        if (row.stellarMass !== null && row.stellarMass !== undefined)
            details.push(appWindow.tf("exploration.mass_solar", "%1 SOLAR MASSES", [Number(row.stellarMass).toLocaleString(Qt.locale(), "f", 3)]))
        if (row.biologicalSignalCount)
            details.push(appWindow.tf("exploration.bio_count", "%1 BIOLOGICAL", [row.biologicalSignalCount]))
        if (row.geologicalSignalCount)
            details.push(appWindow.tf("exploration.geo_count", "%1 GEOLOGICAL", [row.geologicalSignalCount]))
        return details.join("  ·  ")
    }

    objectName: "qa-page-exploration"
    anchors.fill: parent
    anchors.leftMargin: sidebarWidth + (appWindow.compactSidebar ? 18 : 26)
    anchors.rightMargin: appWindow.compactSidebar ? 18 : 26
    anchors.topMargin: appWindow.compactSidebar ? 18 : 26
    anchors.bottomMargin: appWindow.compactSidebar ? 18 : 26
    spacing: 14

    WorkspaceHeader {
        appWindow: explorationPage.appWindow
        eyebrow: appWindow.t("exploration.workspace", "UNIVERSAL CARTOGRAPHICS")
        title: appWindow.t("exploration.title", "EXPLORATION DATA")
        subtitle: appWindow.t("exploration.subtitle", "Unsold Journal scans · values are transparent estimates")
        statusText: findings.length
                    ? appWindow.tf("exploration.status_unsold", "%1 UNSOLD", [summary.bodyCount || 0]) : ""
        statusTone: findings.length ? orange : cyan
    }

    GridLayout {
        Layout.fillWidth: true
        columns: appWindow.narrowWorkspace ? 2 : 4
        columnSpacing: 10
        rowSpacing: 10
        Repeater {
            model: [
                {
                    "label": appWindow.t("exploration.stat_value", "EST. VALUE AT RISK"),
                    "value": explorationPage.formatValueRange(
                                 summary.estimatedValueMin, summary.estimatedValueMax,
                                 summary.valueStatus),
                    "tone": orange
                },
                {
                    "label": appWindow.t("exploration.stat_systems", "UNSOLD SYSTEMS"),
                    "value": String(summary.systemCount || 0),
                    "tone": cyan
                },
                {
                    "label": appWindow.t("exploration.stat_bodies", "SCANNED BODIES"),
                    "value": String(summary.bodyCount || 0),
                    "tone": cyan
                },
                {
                    "label": appWindow.t("exploration.stat_mapped", "MAPPED BODIES"),
                    "value": String(summary.mappedCount || 0),
                    "tone": green
                }
            ]
            delegate: ShadowCard {
                required property var modelData
                Layout.fillWidth: true
                Layout.preferredHeight: 82
                accent: modelData.tone
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 6
                    Label {
                        Layout.fillWidth: true
                        text: modelData.value
                        color: modelData.tone
                        font.family: monoFont
                        font.pixelSize: 17
                        font.bold: true
                        elide: Text.ElideRight
                    }
                    Label {
                        text: modelData.label
                        color: muted
                        font.pixelSize: UiMetrics.caption
                        font.bold: true
                    }
                }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 14

        ShadowCard {
            Layout.fillWidth: true
            Layout.preferredWidth: 1
            Layout.fillHeight: true
            accent: cyan
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 9
                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        Layout.fillWidth: true
                        text: appWindow.t("exploration.systems", "UNSOLD SYSTEMS")
                        color: cyan; font.pixelSize: 11; font.bold: true
                    }
                    Label {
                        text: String(systems.length)
                        color: muted; font.family: monoFont; font.pixelSize: UiMetrics.caption
                    }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: borderTone }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 54
                    radius: 9
                    color: selectedSystemId === "" ? inputBackground : panelRaised
                    border.width: selectedSystemId === "" ? 1.5 : 1
                    border.color: selectedSystemId === "" ? cyan : borderTone
                    Column {
                        anchors.fill: parent; anchors.margins: 10; spacing: 3
                        Label {
                            text: appWindow.t("exploration.all_systems", "ALL SYSTEMS")
                            color: selectedSystemId === "" ? cyan : textPrimary
                            font.pixelSize: 11; font.bold: true
                        }
                        Label {
                            text: explorationPage.formatValueRange(
                                      summary.estimatedValueMin, summary.estimatedValueMax,
                                      summary.valueStatus)
                            color: muted; font.family: monoFont; font.pixelSize: UiMetrics.caption
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: selectedSystemId = ""
                        Accessible.name: appWindow.t("exploration.show_all", "Show all unsold systems")
                    }
                }

                EmptyState {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: systems.length === 0
                    symbol: "◎"
                    title: appWindow.t("exploration.none", "NO UNSOLD CARTOGRAPHY DATA")
                    detail: appWindow.t("exploration.none_help", "Use the Discovery Scanner or FSS. Unsold scans appear here until the Journal confirms a sale or ship-loss rebuy.")
                    tone: cyan
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: systems.length > 0
                    clip: true
                    contentWidth: availableWidth
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ColumnLayout {
                        width: parent.width
                        spacing: 7
                        Repeater {
                            model: systems
                            delegate: Rectangle {
                                id: systemRow
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: systemColumn.implicitHeight + 20
                                radius: 9
                                color: selectedSystemId === modelData.id ? inputBackground : panelRaised
                                border.width: selectedSystemId === modelData.id ? 1.5 : 1
                                border.color: selectedSystemId === modelData.id ? cyan : borderTone
                                ColumnLayout {
                                    id: systemColumn
                                    anchors.left: parent.left; anchors.right: parent.right
                                    anchors.top: parent.top; anchors.margins: 10; spacing: 4
                                    Label {
                                        Layout.fillWidth: true
                                        text: systemRow.modelData.name || appWindow.t("exploration.unknown_system", "UNKNOWN SYSTEM")
                                        color: selectedSystemId === systemRow.modelData.id ? cyan : textPrimary
                                        font.pixelSize: 11; font.bold: true; elide: Text.ElideRight
                                    }
                                    Label {
                                        text: explorationPage.formatValueRange(
                                                  systemRow.modelData.estimatedValueMin,
                                                  systemRow.modelData.estimatedValueMax,
                                                  systemRow.modelData.unvaluedBodyCount ? "partial" : "range")
                                        color: orange; font.family: monoFont; font.pixelSize: UiMetrics.caption; font.bold: true
                                    }
                                    Label {
                                        text: appWindow.tf("exploration.system_counts", "%1 BODIES · %2 MAPPED",
                                                           [systemRow.modelData.bodyCount || 0,
                                                            systemRow.modelData.mappedCount || 0])
                                        color: muted; font.pixelSize: UiMetrics.caption
                                    }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: selectedSystemId = systemRow.modelData.id
                                    Accessible.name: appWindow.tf("exploration.show_system", "Show findings in %1", [systemRow.modelData.name || ""])
                                }
                            }
                        }
                    }
                }
            }
        }

        ShadowCard {
            Layout.fillWidth: true
            Layout.preferredWidth: 3
            Layout.fillHeight: true
            accent: orange
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 9
                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        Layout.fillWidth: true
                        text: appWindow.t("exploration.findings", "CARTOGRAPHY FINDINGS")
                        color: orange; font.pixelSize: 11; font.bold: true
                    }
                    Label {
                        text: appWindow.tf("exploration.shown", "%1 SHOWN", [displayedFindings.length])
                        color: muted; font.family: monoFont; font.pixelSize: UiMetrics.caption
                    }
                    Rectangle {
                        implicitWidth: valueSortLabel.implicitWidth + 18
                        implicitHeight: 26; radius: 6
                        color: valueFirst ? warningBackground : panelRaised
                        border.width: 1; border.color: valueFirst ? orange : borderTone
                        Label {
                            id: valueSortLabel; anchors.centerIn: parent
                            text: appWindow.t("exploration.sort_value", "VALUE FIRST")
                            color: valueFirst ? orange : muted; font.pixelSize: UiMetrics.caption; font.bold: true
                        }
                        MouseArea {
                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                            onClicked: valueFirst = !valueFirst
                            Accessible.name: appWindow.t("exploration.toggle_sort", "Toggle value-first sorting")
                        }
                    }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: borderTone }

                EmptyState {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: displayedFindings.length === 0
                    symbol: "◇"
                    title: appWindow.t("exploration.no_findings", "NO FINDINGS FOR THIS FILTER")
                    detail: appWindow.t("exploration.no_findings_help", "Choose another system or scan additional bodies with the FSS.")
                    tone: orange
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: displayedFindings.length > 0
                    clip: true
                    contentWidth: availableWidth
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ColumnLayout {
                        width: parent.width
                        spacing: 8
                        Repeater {
                            model: displayedFindings
                            delegate: Rectangle {
                                id: findingRow
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: findingContent.implicitHeight + 22
                                radius: 10
                                color: panelRaised
                                border.width: modelData.highValue ? 1.6 : 1
                                border.color: modelData.highValue ? orange : borderTone
                                ColumnLayout {
                                    id: findingContent
                                    anchors.left: parent.left; anchors.right: parent.right
                                    anchors.top: parent.top; anchors.margins: 12; spacing: 6
                                    RowLayout {
                                        Layout.fillWidth: true; spacing: 10
                                        ColumnLayout {
                                            Layout.fillWidth: true; spacing: 2
                                            Label {
                                                Layout.fillWidth: true
                                                text: findingRow.modelData.bodyName || appWindow.t("exploration.unknown_body", "UNKNOWN BODY")
                                                color: textPrimary; font.pixelSize: 13; font.bold: true
                                                elide: Text.ElideRight
                                            }
                                            Label {
                                                Layout.fillWidth: true
                                                text: (findingRow.modelData.systemName || "")
                                                      + "  ·  " + (findingRow.modelData.findingClass || "")
                                                color: cyan; font.pixelSize: UiMetrics.caption; font.bold: true
                                                elide: Text.ElideRight
                                            }
                                        }
                                        ColumnLayout {
                                            spacing: 1
                                            Label {
                                                Layout.alignment: Qt.AlignRight
                                                text: findingRow.modelData.valueStatus === "range"
                                                      ? appWindow.t("exploration.estimate_range", "ESTIMATE RANGE")
                                                      : appWindow.t("exploration.estimate", "ESTIMATE")
                                                color: muted; font.pixelSize: UiMetrics.caption; font.bold: true
                                            }
                                            Label {
                                                Layout.alignment: Qt.AlignRight
                                                text: explorationPage.formatValueRange(
                                                          findingRow.modelData.estimatedValueMin,
                                                          findingRow.modelData.estimatedValueMax,
                                                          findingRow.modelData.valueStatus)
                                                color: findingRow.modelData.highValue ? orange : textSecondary
                                                font.family: monoFont; font.pixelSize: 12; font.bold: true
                                            }
                                        }
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        visible: explorationPage.findingDetail(findingRow.modelData).length > 0
                                        text: explorationPage.findingDetail(findingRow.modelData)
                                        color: textSecondary; font.pixelSize: UiMetrics.caption
                                        wrapMode: Text.WordWrap
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        visible: (findingRow.modelData.tags || []).length > 0
                                        text: explorationPage.tagLine(findingRow.modelData.tags)
                                        color: orange; font.pixelSize: UiMetrics.caption; font.bold: true
                                        wrapMode: Text.WordWrap
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        visible: findingRow.modelData.valueStatus === "unavailable"
                                        text: appWindow.t("exploration.missing_evidence", "The Journal did not provide enough mass data for a safe estimate.")
                                        color: muted; font.pixelSize: UiMetrics.caption; wrapMode: Text.WordWrap
                                    }
                                }
                            }
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    text: appWindow.t("exploration.estimate_notice", "ESTIMATES · Final payout can change with first-discovery races. Fleet Carrier reduction is not included.")
                    color: muted; font.pixelSize: UiMetrics.caption; wrapMode: Text.WordWrap
                }
            }
        }
    }
}
