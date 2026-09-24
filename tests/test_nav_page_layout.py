"""Guard the Nav page's primary workflow against a farm-list takeover."""

from pathlib import Path
import unittest


NAV_PAGE = Path(__file__).resolve().parents[1] / "qml" / "pages" / "NavPage.qml"
FARMS_SECTION = NAV_PAGE.with_name("MaterialFarmsSection.qml")


class NavPageLayoutTests(unittest.TestCase):
    def test_waypoints_precede_collapsed_material_farms(self):
        source = NAV_PAGE.read_text(encoding="utf-8")
        self.assertIn("property bool farmsExpanded: false", source)
        self.assertLess(
            source.index('text: appWindow.t("nav.add_target"'),
            source.index('text: appWindow.t("nav.saved"'),
        )
        self.assertLess(
            source.index('text: appWindow.t("nav.saved"'),
            source.index("MaterialFarmsSection {"),
        )
        self.assertIn("visible: navPage.farmsExpanded", source)
        self.assertIn("onClicked: navPage.farmsExpanded = !navPage.farmsExpanded", source)
        self.assertIn("farmSection.visible ? hostPage.visibleFarmSites : []",
                      FARMS_SECTION.read_text(encoding="utf-8"))

    def test_farm_editor_and_recoverable_delete_are_wired_to_controller(self):
        source = FARMS_SECTION.read_text(encoding="utf-8")
        self.assertIn("cockpit.editMaterialFarmSite(", source)
        self.assertIn("cockpit.removeMaterialFarmSite(", source)
        self.assertIn("cockpit.restoreMaterialFarmSite(", source)
        self.assertIn("farmDeleteDialog.confirm(modelData)", source)
        self.assertIn("hostPage.farmDeletedSites", source)

    def test_nav_overlay_has_direct_recovery_controls(self):
        source = NAV_PAGE.read_text(encoding="utf-8")
        self.assertIn("navOverlaySettings.toggleVisible()", source)
        self.assertIn("navOverlaySettings.toggleLocked()", source)
        self.assertIn("navOverlaySettings.toggleClickThrough()", source)


if __name__ == "__main__":
    unittest.main()
