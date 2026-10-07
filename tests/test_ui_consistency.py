"""Contracts for shared presentation metrics and bounded finder layouts."""
import re
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class UiConsistencyTests(unittest.TestCase):
    def test_material_ready_state_reserves_its_content_height(self):
        main = (ROOT / "Main.qml").read_text(encoding="utf-8-sig")
        self.assertIn("Layout.minimumHeight: materialReadyState.implicitHeight + 24", main)
        block = main.split("id: materialReadyState", 1)[1].split("symbol:", 1)[0]
        self.assertIn("height: implicitHeight", block)
        empty = (ROOT / "qml/components/EmptyState.qml").read_text(encoding="utf-8-sig")
        self.assertIn("Layout.minimumHeight: implicitHeight", empty)

    def test_shared_control_metrics_are_used(self):
        for file in ("qml/components/CockpitComboBox.qml", "Main.qml",
                     "qml/pages/ShipyardPage.qml"):
            source = (ROOT / file).read_text(encoding="utf-8-sig")
            self.assertIn("UiMetrics.controlHeight", source, file)
            self.assertIn("UiMetrics.body", source, file)

    def test_audited_pages_have_no_tiny_fixed_captions(self):
        for page in ("ShipyardPage", "MiningFinderPage", "PowerplayPage",
                     "ExplorationPage", "ExobiologyPage"):
            source = (ROOT / "qml/pages" / (page + ".qml")).read_text(encoding="utf-8-sig")
            self.assertIsNone(re.search(r"font\.pixelSize:\s*(7|8|9|10)(?!\d)", source), page)

    def test_category_bar_wraps_and_filter_viewport_is_bounded(self):
        shipyard = (ROOT / "qml/pages/ShipyardPage.qml").read_text(encoding="utf-8-sig")
        mining = (ROOT / "qml/pages/MiningFinderPage.qml").read_text(encoding="utf-8-sig")
        self.assertIn('Flow {\n                    objectName: "qa-outfitting-category-flow"', shipyard)
        self.assertIn('objectName: "qa-mining-filter-viewport"', mining)
        self.assertIn("contentWidth: availableWidth", mining)
        self.assertIn("ScrollBar.horizontal.policy: ScrollBar.AlwaysOff", mining)

    def test_mining_search_action_has_reserved_non_scrolling_space(self):
        mining = (ROOT / "qml/pages/MiningFinderPage.qml").read_text(encoding="utf-8-sig")
        self.assertIn('objectName: "qa-mining-search-action"', mining)
        self.assertIn("anchors.bottomMargin: miningFinderPage.searchGoalExpanded ? 62 : 10", mining)
        self.assertIn("height: UiMetrics.controlHeight", mining)

    def test_legacy_workspaces_use_shared_headers(self):
        main = (ROOT / "Main.qml").read_text(encoding="utf-8-sig")
        for qa_name in ("qa-workspace-header-operations", "qa-header-wishlist",
                        "qa-header-engineering", "qa-header-materials", "qa-header-engineers"):
            self.assertRegex(main, r'WorkspaceHeader\s*\{\s*qaName: "' + qa_name + '"')
        self.assertIn("Layout.preferredHeight: sharedSettingsHeader.implicitHeight", main)

    def test_engineering_search_is_layout_managed(self):
        main = (ROOT / "Main.qml").read_text(encoding="utf-8-sig")
        search = main.split("id: blueprintSearch", 1)[1].split("background:", 1)[0]
        self.assertIn("Layout.fillWidth: true", search)
        self.assertNotIn("anchors.right:", search)
        self.assertNotIn("width: 360", search)

    def test_operations_support_cards_stack_on_small_windows(self):
        main = (ROOT / "Main.qml").read_text(encoding="utf-8-sig")
        support = main.split('objectName: "qa-operations-support-cards"', 1)[1].split("ShadowCard {", 1)[0]
        self.assertIn("columns: window.narrowWorkspace ? 1 : 2", support)
        viewport = main.split("id: operationsViewport", 1)[1].split("GridLayout {", 1)[0]
        self.assertIn("contentWidth: availableWidth", viewport)
        self.assertIn("ScrollBar.horizontal.policy: ScrollBar.AlwaysOff", viewport)

    def test_logbook_captions_are_not_tiny(self):
        source = (ROOT / "qml/pages/LogbookPage.qml").read_text(encoding="utf-8-sig")
        self.assertIsNone(re.search(r"font\.pixelSize:\s*(7|8|9|10)(?!\d)", source))

    def test_legacy_dialogs_and_finance_use_readable_captions(self):
        source = (ROOT / "Main.qml").read_text(encoding="utf-8-sig")
        self.assertIsNone(re.search(r"font\.pixelSize:\s*(7|8|9|10)(?!\d)", source))
        self.assertNotIn("9px 'Segoe UI'", source)
        self.assertIn("property real plotTop: 90", source)
        self.assertIn("height: 72", source)

    def test_all_literal_qml_translation_keys_exist_in_every_language(self):
        catalogs = {lang: json.loads((ROOT / "ed_data/i18n" / (lang + ".json")).read_text(encoding="utf-8-sig"))
                    for lang in ("en", "de", "es", "fr")}
        for path in [ROOT / "Main.qml", *(ROOT / "qml").rglob("*.qml")]:
            source = path.read_text(encoding="utf-8-sig")
            for key in re.findall(r'\b(?:t|tf)\(\s*"([^"]+)"\s*,', source):
                for lang, catalog in catalogs.items():
                    self.assertIn(key, catalog, f"{path.name}: {lang}: {key}")

    def test_display_labels_do_not_change_domain_values(self):
        labels = (ROOT / "qml/components/PresentationLabels.js").read_text(encoding="utf-8-sig")
        self.assertIn("window.t(keys[raw], raw) : raw", labels)
        source = (ROOT / "qml/pages/ShipyardPage.qml").read_text(encoding="utf-8-sig")
        self.assertIn('tone === "LOCKED") return appWindow.error', source)
        self.assertIn('moduleGroup === "TECH BROKER"', source)
        for key in re.findall(r'"(presentation\.label_\d+)"', labels):
            for lang in ("en", "de", "es", "fr"):
                catalog = json.loads((ROOT / "ed_data/i18n" / (lang + ".json")).read_text(encoding="utf-8-sig"))
                self.assertIn(key, catalog)


if __name__ == "__main__":
    unittest.main()
