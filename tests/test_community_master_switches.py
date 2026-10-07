import unittest
from pathlib import Path
from types import SimpleNamespace
from ed_companion.phase14.controller_eddn import EddnMixin


class CommunityMasterSwitchTests(unittest.TestCase):
    def load(self, saved):
        stub = SimpleNamespace(eddn_config_file="unused", _read_local_json=lambda *args: saved)
        return EddnMixin._load_eddn_config(stub)

    def test_new_profile_defaults_to_all_enabled(self):
        config = self.load({})
        self.assertTrue(all(config[key] for key in ("consent", "upload_enabled", "listener_enabled")))

    def test_explicit_disable_is_preserved_and_disables_whole_group(self):
        for key in ("consent", "upload_enabled", "listener_enabled"):
            config = self.load({key: False})
            self.assertFalse(any(config[field] for field in ("consent", "upload_enabled", "listener_enabled")))

    def test_one_ui_toggle_per_service(self):
        root = Path(__file__).resolve().parents[1]
        qml = (root / "Main.qml").read_text(encoding="utf-8-sig")
        self.assertNotIn("id: eddnUploadBox", qml)
        self.assertNotIn("id: eddnListenerBox", qml)
        self.assertIn("cockpit.saveEddnConfig(checked, checked, checked)", qml)
        for field in ("Catalog", "YieldSharing", "SignalSharing", "StationPriceSharing"):
            self.assertIn(f"cockpit.setEdFrame{field}Enabled(checked)", qml)


if __name__ == "__main__":
    unittest.main()
