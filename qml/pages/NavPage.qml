import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ColumnLayout {
    id: navPage
    required property var appWindow
    required property real sidebarWidth
    readonly property var nav: cockpit.surfaceNav || ({})
    readonly property var position: nav.position || ({})
    readonly property var guide: nav.guidance || ({})
    readonly property var targets: nav.targets || []
    readonly property var farmSites: nav.farmSites || []
    readonly property var farmMaterials: nav.farmMaterials || []
    readonly property var farmAllMaterials: nav.farmAllMaterials || []
    readonly property var farmDeletedSites: nav.farmDeletedSites || []
    property string selectedFarmMaterial: ""
    property string farmSortMode: "distance"
    property bool farmsExpanded: false
    readonly property var visibleFarmSites: {
        var selected = navPage.selectedFarmMaterial
        var sortMode = navPage.farmSortMode
        var rows = navPage.farmSites.filter(function(row) {
            return !selected || row.materialKey === selected
        })
        rows.sort(function(left, right) {
            if (sortMode === "material") {
                var materialOrder = left.materialName.localeCompare(right.materialName)
                if (materialOrder !== 0)
                    return materialOrder
            }
            var leftDistance = left.distanceLy === null || left.distanceLy === undefined
                               ? Number.MAX_VALUE : Number(left.distanceLy)
            var rightDistance = right.distanceLy === null || right.distanceLy === undefined
                                ? Number.MAX_VALUE : Number(right.distanceLy)
            if (leftDistance !== rightDistance)
                return leftDistance - rightDistance
            return left.system.localeCompare(right.system) || left.body.localeCompare(right.body)
        })
        return rows
    }
    readonly property var activeTarget: targets.find(function(row) {
        return row.id === navPage.nav.activeId
    }) || ({})

    function coordinate(value) {
        return Number(value).toFixed(5) + "°"
    }
    function distance(value) {
        return value >= 1000 ? (value / 1000).toFixed(2) + " km" : value + " m"
    }

    objectName: "qa-page-nav"
    anchors.fill: parent
    anchors.leftMargin: sidebarWidth + (appWindow.compactSidebar ? 18 : 26)
    anchors.rightMargin: appWindow.compactSidebar ? 18 : 26
    anchors.topMargin: appWindow.compactSidebar ? 18 : 26
    anchors.bottomMargin: appWindow.compactSidebar ? 18 : 26
    spacing: 14

    WorkspaceHeader {
        appWindow: navPage.appWindow
        eyebrow: appWindow.t("nav.workspace", "NAVIGATION")
        title: appWindow.t("nav.title", "NAV")
        subtitle: appWindow.t("nav.subtitle", "Surface navigation and saved coordinates")
        statusText: Object.keys(navPage.position).length > 0
                    ? appWindow.t("nav.position_live", "SURFACE POSITION")
                    : appWindow.t("nav.position_missing", "POSITION UNAVAILABLE")
        statusTone: Object.keys(navPage.position).length > 0 ? appWindow.green : appWindow.orange
    }

    RowLayout {
        Layout.fillWidth: true
        Button {
            text: navOverlaySettings.visible
                  ? appWindow.t("nav.overlay_hide", "HIDE NAV OVERLAY")
                  : appWindow.t("nav.overlay_show", "SHOW NAV OVERLAY")
            onClicked: navOverlaySettings.toggleVisible()
        }
        Button {
            text: navOverlaySettings.locked
                  ? appWindow.t("nav.overlay_unlock", "UNLOCK")
                  : appWindow.t("nav.overlay_lock", "LOCK POSITION")
            onClicked: navOverlaySettings.toggleLocked()
        }
        Button {
            text: navOverlaySettings.clickThrough
                  ? appWindow.t("nav.overlay_click_off", "CLICK-THROUGH OFF")
                  : appWindow.t("nav.overlay_click_on", "CLICK-THROUGH ON")
            onClicked: navOverlaySettings.toggleClickThrough()
        }
        Item { Layout.fillWidth: true }
    }
    Label {
        Layout.fillWidth: true
        text: appWindow.t("nav.overlay_hint", "Floating compass for borderless-windowed play. You can also control it from the tray menu.")
        color: appWindow.muted
        font.pixelSize: 11
        wrapMode: Text.WordWrap
    }

    Dialog {
        id: renameDialog
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(440, appWindow.width - 40)
        modal: true
        padding: 20
        title: appWindow.t("nav.rename_title", "RENAME WAYPOINT")
        property string targetId: ""
        property string targetName: ""
        property string renameError: ""

        function edit(target) {
            targetId = target.id
            targetName = target.name
            renameError = ""
            open()
            renameField.forceActiveFocus()
            renameField.selectAll()
        }
        function submit() {
            if (!renameField.text.trim() || renameField.text.length > 80)
                return
            if (cockpit.renameSurfaceTarget(targetId, renameField.text))
                close()
            else
                renameError = navPage.nav.message
        }

        background: Rectangle {
            radius: 12
            color: appWindow.panel
            border.color: appWindow.borderTone
        }
        contentItem: ColumnLayout {
            spacing: 12
            TextField {
                id: renameField
                Layout.fillWidth: true
                text: renameDialog.targetName
                maximumLength: 80
                selectByMouse: true
                onAccepted: renameDialog.submit()
            }
            Label {
                visible: !!renameDialog.renameError
                Layout.fillWidth: true
                text: renameDialog.renameError
                      ? appWindow.t(renameDialog.renameError, "Could not rename this waypoint.") : ""
                color: appWindow.orange
                wrapMode: Text.WordWrap
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Button {
                    text: appWindow.t("nav.cancel", "CANCEL")
                    onClicked: renameDialog.close()
                }
                Button {
                    text: appWindow.t("nav.save", "SAVE")
                    enabled: !!renameField.text.trim() && renameField.text.length <= 80
                    onClicked: renameDialog.submit()
                }
            }
        }
    }

    ScrollView {
        id: navScroll
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        contentWidth: availableWidth
        ScrollBar.vertical: CockpitScrollBar {}

        ColumnLayout {
            width: navScroll.availableWidth
            spacing: 14

            Label {
                text: appWindow.t("nav.surface", "SURFACE NAV")
                color: appWindow.accentSecondary
                font.pixelSize: 12
                font.bold: true
            }

            ShadowCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 245
                accent: navPage.guide.arrived ? appWindow.green : appWindow.accentSecondary
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 22
                    Item {
                        Layout.preferredWidth: 195
                        Layout.preferredHeight: 195
                        Canvas {
                            id: compass
                            anchors.fill: parent
                            onPaint: {
                                var ctx = getContext("2d")
                                ctx.clearRect(0, 0, width, height)
                                var x = width / 2, y = height / 2
                                ctx.strokeStyle = appWindow.borderTone
                                ctx.lineWidth = 2
                                ctx.beginPath()
                                ctx.arc(x, y, 78, 0, Math.PI * 2)
                                ctx.stroke()
                                ctx.strokeStyle = appWindow.muted
                                for (var i = 0; i < 4; i++) {
                                    var a = i * Math.PI / 2
                                    ctx.beginPath()
                                    ctx.moveTo(x + Math.sin(a) * 68, y - Math.cos(a) * 68)
                                    ctx.lineTo(x + Math.sin(a) * 77, y - Math.cos(a) * 77)
                                    ctx.stroke()
                                }
                                if (navPage.guide.turnDeg === undefined || navPage.guide.wrongBody)
                                    return
                                ctx.save()
                                ctx.translate(x, y)
                                ctx.rotate(Number(navPage.guide.turnDeg) * Math.PI / 180)
                                ctx.fillStyle = navPage.guide.arrived ? appWindow.green : appWindow.accentSecondary
                                ctx.beginPath()
                                ctx.moveTo(0, -60)
                                ctx.lineTo(16, 17)
                                ctx.lineTo(0, 7)
                                ctx.lineTo(-16, 17)
                                ctx.closePath()
                                ctx.fill()
                                ctx.restore()
                            }
                        }
                        Connections {
                            target: cockpit
                            function onSurfaceNavChanged() { compass.requestPaint() }
                        }
                        Label {
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.bottom: parent.bottom
                            text: appWindow.t("nav.forward", "FORWARD")
                            color: appWindow.muted
                            font.pixelSize: 10
                            font.bold: true
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 9
                        Label {
                            Layout.fillWidth: true
                            text: navPage.activeTarget.name || appWindow.t("nav.no_target", "NO ACTIVE TARGET")
                            color: appWindow.textPrimary
                            font.pixelSize: 20
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        Label {
                            Layout.fillWidth: true
                            text: !navPage.activeTarget.id
                                  ? appWindow.t("nav.choose_target", "Save or select a coordinate to start guidance.")
                                  : navPage.guide.wrongBody
                                    ? appWindow.t("nav.wrong_body", "Target is on another body or in another system.")
                                    : Object.keys(navPage.position).length === 0
                                      ? appWindow.t("nav.wait_position", "Waiting for surface coordinates from Elite Dangerous.")
                                      : navPage.guide.turnDeg === undefined
                                        ? appWindow.t("nav.wait_heading", "Waiting for ship or suit heading.")
                                        : navPage.guide.arrived
                                          ? appWindow.t("nav.arrived", "TARGET REACHED")
                                          : navPage.guide.turnDeg > 5
                                            ? appWindow.tf("nav.turn_right", "TURN RIGHT %1°", [Math.round(navPage.guide.turnDeg)])
                                            : navPage.guide.turnDeg < -5
                                              ? appWindow.tf("nav.turn_left", "TURN LEFT %1°", [Math.round(-navPage.guide.turnDeg)])
                                              : appWindow.t("nav.go_straight", "GO STRAIGHT")
                            color: navPage.guide.arrived ? appWindow.green : appWindow.accentSecondary
                            font.pixelSize: 15
                            font.bold: true
                            wrapMode: Text.WordWrap
                        }
                        Label {
                            text: navPage.guide.distanceM === undefined
                                  ? appWindow.t("nav.distance_unknown", "Distance unavailable")
                                  : appWindow.tf("nav.distance", "Distance · %1", [navPage.distance(navPage.guide.distanceM)])
                            color: appWindow.textSecondary
                            font.pixelSize: 13
                        }
                        Label {
                            text: navPage.guide.bearingDeg === undefined
                                  ? ""
                                  : appWindow.tf("nav.bearing", "Bearing %1° · Heading %2°",
                                                 [Math.round(navPage.guide.bearingDeg),
                                                  navPage.guide.headingDeg === undefined ? "—" : Math.round(navPage.guide.headingDeg)])
                            color: appWindow.muted
                            font.pixelSize: 11
                        }
                        Label {
                            Layout.fillWidth: true
                            text: navPage.position.body
                                  ? appWindow.tf("nav.position", "%1 · %2, %3",
                                                 [navPage.position.body,
                                                  navPage.coordinate(navPage.position.latitude),
                                                  navPage.coordinate(navPage.position.longitude)])
                                  : appWindow.t("nav.no_position", "No current surface position")
                            color: appWindow.muted
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            ShadowCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 155
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 9
                    Label {
                        text: appWindow.t("nav.add_target", "SAVE COORDINATES")
                        color: appWindow.textPrimary
                        font.pixelSize: 13
                        font.bold: true
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 9
                        TextField {
                            id: targetName
                            Layout.fillWidth: true
                            placeholderText: appWindow.t("nav.name", "Name (optional)")
                        }
                        TextField {
                            id: targetLatitude
                            Layout.preferredWidth: 130
                            placeholderText: appWindow.t("nav.latitude", "Latitude ±90")
                        }
                        TextField {
                            id: targetLongitude
                            Layout.preferredWidth: 140
                            placeholderText: appWindow.t("nav.longitude", "Longitude ±180")
                        }
                        Button {
                            text: appWindow.t("nav.save", "SAVE")
                            onClicked: {
                                if (cockpit.saveSurfaceTarget(targetName.text, targetLatitude.text, targetLongitude.text)) {
                                    targetName.clear()
                                    targetLatitude.clear()
                                    targetLongitude.clear()
                                }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Button {
                            text: appWindow.t("nav.save_here", "SAVE CURRENT POSITION")
                            enabled: !!navPage.position.body
                            onClicked: cockpit.saveCurrentSurfacePosition()
                        }
                        Label {
                            Layout.fillWidth: true
                            text: navPage.nav.message
                                  ? appWindow.t(navPage.nav.message, "Could not save this waypoint.")
                                  : appWindow.t("nav.input_hint", "Signed decimal degrees; dot or comma accepted. Targets belong to the current body.")
                            color: navPage.nav.message ? appWindow.orange : appWindow.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }

            Label {
                text: appWindow.t("nav.saved", "SAVED WAYPOINTS")
                color: appWindow.accentSecondary
                font.pixelSize: 12
                font.bold: true
            }
            Label {
                visible: navPage.targets.length === 0
                text: appWindow.t("nav.empty", "No surface waypoints saved yet.")
                color: appWindow.muted
                font.pixelSize: 12
            }
            Repeater {
                model: navPage.targets
                delegate: ShadowCard {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 74
                    accent: modelData.id === navPage.nav.activeId ? appWindow.green : "transparent"
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 10
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3
                            Label {
                                Layout.fillWidth: true
                                text: modelData.name
                                color: appWindow.textPrimary
                                font.pixelSize: 13
                                font.bold: true
                                elide: Text.ElideRight
                            }
                            Label {
                                Layout.fillWidth: true
                                text: modelData.system + " · " + modelData.body + " · "
                                      + navPage.coordinate(modelData.latitude) + ", "
                                      + navPage.coordinate(modelData.longitude)
                                color: appWindow.muted
                                font.pixelSize: 10
                                elide: Text.ElideRight
                            }
                        }
                        Button {
                            text: modelData.id === navPage.nav.activeId
                                  ? appWindow.t("nav.active", "ACTIVE")
                                  : appWindow.t("nav.navigate", "NAVIGATE")
                            enabled: modelData.id !== navPage.nav.activeId
                            onClicked: cockpit.activateSurfaceTarget(modelData.id)
                        }
                        Button {
                            text: appWindow.t("nav.rename", "RENAME")
                            onClicked: renameDialog.edit(modelData)
                        }
                        Button {
                            text: appWindow.t("nav.remove", "REMOVE")
                            onClicked: cockpit.removeSurfaceTarget(modelData.id)
                        }
                    }
                }
            }
            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                text: (navPage.farmsExpanded ? "▾  " : "▸  ")
                      + appWindow.t("nav.farms", "RAW MATERIAL FARMS")
                onClicked: navPage.farmsExpanded = !navPage.farmsExpanded
            }
            MaterialFarmsSection {
                Layout.fillWidth: true
                visible: navPage.farmsExpanded
                appWindow: navPage.appWindow
                hostPage: navPage
            }
        }
    }
}
