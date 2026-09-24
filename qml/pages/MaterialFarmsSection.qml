import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ColumnLayout {
    id: farmSection
    required property var appWindow
    required property var hostPage
    property bool showDeleted: false
    spacing: 12
    function clearMaterialFilter() {
        hostPage.selectedFarmMaterial = ""
        farmMaterialFilter.currentIndex = 0
    }

    Dialog {
        id: farmEditDialog
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(500, appWindow.width - 40)
        modal: true
        padding: 20
        title: appWindow.t("nav.farm_edit_title", "EDIT FARM SITE")
        property string siteId: ""
        property string sourceMaterialKey: ""
        property string editError: ""
        property bool edited: false

        function edit(site) {
            siteId = site.siteId
            sourceMaterialKey = site.sourceMaterialKey
            editError = ""
            edited = site.edited
            systemField.text = site.system
            bodyField.text = site.body
            latitudeField.text = site.latitude === null ? "" : String(site.latitude)
            longitudeField.text = site.longitude === null ? "" : String(site.longitude)
            methodField.text = site.method
            materialField.currentIndex = hostPage.farmAllMaterials.findIndex(function(row) {
                return row.key === site.materialKey
            })
            open()
        }
        function submit() {
            var material = hostPage.farmAllMaterials[materialField.currentIndex]
            if (!material)
                return
            if (cockpit.editMaterialFarmSite(siteId, sourceMaterialKey, material.key,
                                             systemField.text, bodyField.text,
                                             latitudeField.text, longitudeField.text,
                                             methodField.text)) {
                farmSection.clearMaterialFilter()
                close()
            } else {
                editError = hostPage.nav.message
            }
        }

        background: Rectangle {
            radius: 12
            color: appWindow.panel
            border.color: appWindow.borderTone
        }
        contentItem: ColumnLayout {
            spacing: 9
            CockpitComboBox {
                id: materialField
                Layout.fillWidth: true
                model: hostPage.farmAllMaterials
                textRole: "name"
                valueRole: "key"
            }
            RowLayout {
                Layout.fillWidth: true
                TextField {
                    id: systemField
                    Layout.fillWidth: true
                    maximumLength: 100
                    placeholderText: appWindow.t("nav.farm_system", "System")
                }
                TextField {
                    id: bodyField
                    Layout.preferredWidth: 130
                    maximumLength: 100
                    placeholderText: appWindow.t("nav.farm_body", "Body")
                }
            }
            RowLayout {
                Layout.fillWidth: true
                TextField {
                    id: latitudeField
                    Layout.fillWidth: true
                    placeholderText: appWindow.t("nav.latitude", "Latitude ±90")
                }
                TextField {
                    id: longitudeField
                    Layout.fillWidth: true
                    placeholderText: appWindow.t("nav.longitude", "Longitude ±180")
                }
            }
            Label {
                Layout.fillWidth: true
                text: appWindow.t("nav.farm_coordinates_optional", "Leave both coordinates empty if the location is unknown.")
                color: appWindow.muted
                font.pixelSize: 10
                wrapMode: Text.WordWrap
            }
            TextArea {
                id: methodField
                Layout.fillWidth: true
                Layout.preferredHeight: 100
                wrapMode: TextEdit.Wrap
                placeholderText: appWindow.t("nav.farm_method", "Farming notes")
            }
            Label {
                visible: !!farmEditDialog.editError
                Layout.fillWidth: true
                text: farmEditDialog.editError
                      ? appWindow.t(farmEditDialog.editError, "Could not save this farm site.") : ""
                color: appWindow.orange
                wrapMode: Text.WordWrap
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    visible: farmEditDialog.edited
                    text: appWindow.t("nav.farm_restore", "RESTORE ORIGINAL")
                    onClicked: {
                        if (cockpit.restoreMaterialFarmSite(farmEditDialog.siteId,
                                                            farmEditDialog.sourceMaterialKey)) {
                            farmSection.clearMaterialFilter()
                            farmEditDialog.close()
                        } else {
                            farmEditDialog.editError = hostPage.nav.message
                        }
                    }
                }
                Item { Layout.fillWidth: true }
                Button {
                    text: appWindow.t("nav.cancel", "CANCEL")
                    onClicked: farmEditDialog.close()
                }
                Button {
                    text: appWindow.t("nav.save", "SAVE")
                    onClicked: farmEditDialog.submit()
                }
            }
        }
    }

    Dialog {
        id: farmDeleteDialog
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(440, appWindow.width - 40)
        modal: true
        padding: 20
        title: appWindow.t("nav.farm_delete_title", "REMOVE FARM SITE?")
        property string siteId: ""
        property string sourceMaterialKey: ""
        property string deleteError: ""
        function confirm(site) {
            siteId = site.siteId
            sourceMaterialKey = site.sourceMaterialKey
            deleteError = ""
            open()
        }
        background: Rectangle {
            radius: 12
            color: appWindow.panel
            border.color: appWindow.borderTone
        }
        contentItem: ColumnLayout {
            spacing: 12
            Label {
                Layout.fillWidth: true
                text: appWindow.t("nav.farm_delete_hint", "This hides the farm entry from your list. You can restore the bundled entry later.")
                color: appWindow.textSecondary
                wrapMode: Text.WordWrap
            }
            Label {
                visible: !!farmDeleteDialog.deleteError
                Layout.fillWidth: true
                text: farmDeleteDialog.deleteError
                      ? appWindow.t(farmDeleteDialog.deleteError, "Could not remove this farm site.") : ""
                color: appWindow.orange
                wrapMode: Text.WordWrap
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Button {
                    text: appWindow.t("nav.cancel", "CANCEL")
                    onClicked: farmDeleteDialog.close()
                }
                Button {
                    text: appWindow.t("nav.remove", "REMOVE")
                    onClicked: {
                        if (cockpit.removeMaterialFarmSite(farmDeleteDialog.siteId,
                                                           farmDeleteDialog.sourceMaterialKey)) {
                            farmSection.clearMaterialFilter()
                            farmDeleteDialog.close()
                        } else {
                            farmDeleteDialog.deleteError = hostPage.nav.message
                        }
                    }
                }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        CockpitComboBox {
            id: farmMaterialFilter
            Layout.fillWidth: true
            model: [{"key": "", "name": appWindow.t("nav.all_materials", "ALL MATERIALS")}].concat(hostPage.farmMaterials)
            textRole: "name"
            valueRole: "key"
            onActivated: hostPage.selectedFarmMaterial = currentValue
        }
        CockpitComboBox {
            Layout.preferredWidth: 220
            model: [appWindow.t("nav.sort_distance", "NEAREST FIRST"),
                    appWindow.t("nav.sort_material_distance", "MATERIAL + DISTANCE")]
            onActivated: hostPage.farmSortMode = currentIndex === 0 ? "distance" : "material"
        }
    }
    Label {
        Layout.fillWidth: true
        text: appWindow.t("nav.farm_hint", "Bundled catalog with your local edits · straight-line system distance, not a jump route. Availability may change in-game.")
        color: appWindow.muted
        font.pixelSize: 11
        wrapMode: Text.WordWrap
    }
    Label {
        visible: hostPage.visibleFarmSites.length === 0
        text: appWindow.t("nav.no_farms", "No cataloged farm site for this material.")
        color: appWindow.muted
        font.pixelSize: 12
    }
    Repeater {
        model: farmSection.visible ? hostPage.visibleFarmSites : []
        delegate: ShadowCard {
            required property var modelData
            Layout.fillWidth: true
            Layout.preferredHeight: 138
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 4
                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        Layout.fillWidth: true
                        text: modelData.materialName
                        color: appWindow.textPrimary
                        font.pixelSize: 13
                        font.bold: true
                    }
                    Label {
                        visible: modelData.edited
                        text: appWindow.t("nav.farm_edited", "EDITED")
                        color: appWindow.orange
                        font.pixelSize: 10
                        font.bold: true
                    }
                    Label {
                        text: modelData.distanceLy === null || modelData.distanceLy === undefined
                              ? appWindow.t("nav.distance_unknown", "Distance unavailable")
                              : Number(modelData.distanceLy).toFixed(1) + " ly"
                        color: modelData.distanceLy === null ? appWindow.muted : appWindow.accentSecondary
                        font.pixelSize: 12
                        font.bold: true
                    }
                }
                Label {
                    Layout.fillWidth: true
                    text: modelData.system + " · " + modelData.body + " · "
                          + (modelData.latitude === null || modelData.longitude === null
                             ? appWindow.t("nav.coordinates_unknown", "COORDINATES UNKNOWN")
                             : hostPage.coordinate(modelData.latitude) + ", "
                               + hostPage.coordinate(modelData.longitude))
                    color: appWindow.textSecondary
                    font.pixelSize: 11
                    elide: Text.ElideRight
                }
                Label {
                    Layout.fillWidth: true
                    text: modelData.method
                    color: appWindow.muted
                    font.pixelSize: 10
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    wrapMode: Text.WordWrap
                }
                RowLayout {
                    Layout.fillWidth: true
                    Item { Layout.fillWidth: true }
                    Button {
                        text: appWindow.t("nav.copy_system", "COPY SYSTEM")
                        onClicked: cockpit.copySystem(modelData.system)
                    }
                    Button {
                        text: appWindow.t("nav.use_waypoint", "USE AS WAYPOINT")
                        enabled: modelData.latitude !== null && modelData.longitude !== null
                        onClicked: cockpit.activateMaterialFarmSite(modelData.siteId, modelData.sourceMaterialKey)
                    }
                    Button {
                        text: appWindow.t("nav.edit", "EDIT")
                        onClicked: farmEditDialog.edit(modelData)
                    }
                    Button {
                        text: appWindow.t("nav.remove", "REMOVE")
                        onClicked: farmDeleteDialog.confirm(modelData)
                    }
                }
            }
        }
    }
    Button {
        visible: hostPage.farmDeletedSites.length > 0
        Layout.fillWidth: true
        text: (farmSection.showDeleted ? "▾  " : "▸  ")
              + appWindow.tf("nav.farm_deleted", "REMOVED FARM SITES (%1)",
                             [hostPage.farmDeletedSites.length])
        onClicked: farmSection.showDeleted = !farmSection.showDeleted
    }
    Repeater {
        model: farmSection.visible && farmSection.showDeleted ? hostPage.farmDeletedSites : []
        delegate: ShadowCard {
            required property var modelData
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            RowLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 10
                Label {
                    Layout.fillWidth: true
                    text: modelData.materialName + " · " + modelData.system + " · " + modelData.body
                    color: appWindow.muted
                    elide: Text.ElideRight
                }
                Button {
                    text: appWindow.t("nav.farm_restore", "RESTORE ORIGINAL")
                    onClicked: cockpit.restoreMaterialFarmSite(modelData.siteId,
                                                                modelData.sourceMaterialKey)
                }
            }
        }
    }
}
