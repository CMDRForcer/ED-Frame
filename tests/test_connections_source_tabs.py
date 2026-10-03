import inspect
import unittest
from pathlib import Path

from ed_companion.phase14.controller_navigation import NavigationMixin


ROOT = Path(__file__).resolve().parents[1]


class ConnectionSourceTabTests(unittest.TestCase):
    def test_each_remote_catalog_source_has_its_own_tab(self):
        qml = (ROOT / "Main.qml").read_text(encoding="utf-8")
        for label in (
            'text: "EDDN"',
            'text: "ED-FRAME"',
            'text: "SPANSH"',
            'text: "EDSM"',
        ):
            self.assertIn(label, qml)
        self.assertNotIn('"EDDN & STATE FINDS"', qml)
        self.assertNotIn('"SPANSH & EDSM"', qml)
        self.assertIn(
            "visible: connectionsPage.connectionMode === 3", qml
        )
        self.assertIn(
            "visible: connectionsPage.connectionMode === 4", qml
        )
        self.assertIn(
            "visible: connectionsPage.connectionMode === 5", qml
        )

    def test_spansh_refresh_no_longer_starts_edsm_refresh(self):
        source = inspect.getsource(NavigationMixin.updateSpanshCatalogs)
        self.assertNotIn("refreshMiningPowerplayCatalog", source)
        self.assertIn("updateTraderCatalog", source)
        self.assertIn("updateTechBrokerCatalog", source)
        self.assertIn("refreshMiningFinder", source)

    def test_edframe_has_a_global_service_status_card(self):
        source = (ROOT / "ed_companion" / "phase14" / "controller.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"name": "ED-FRAME SERVER"', source)
        self.assertIn('else "ONLINE" if self._edframe_catalog_online', source)

    def test_edframe_tab_exposes_offline_catalog_sync_progress(self):
        qml = (ROOT / "Main.qml").read_text(encoding="utf-8")
        mining_qml = (
            ROOT / "qml" / "pages" / "MiningFinderPage.qml"
        ).read_text(encoding="utf-8")
        self.assertIn("cockpit.edFrameCatalogSyncStatus", qml)
        self.assertIn("cockpit.edFrameCatalogSyncBusy", qml)
        self.assertIn("cockpit.edFrameCatalogSyncStatus", mining_qml)
        controller_source = (
            ROOT / "ed_companion" / "phase14" / "controller_navigation.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"CATALOG SYNC"', controller_source)


if __name__ == "__main__":
    unittest.main()
