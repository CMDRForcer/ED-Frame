import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from ed_companion.integrations.frontier_credentials import (
    FrontierCredentialError,
)
from ed_companion.integrations.inara_credentials import (
    InaraCredentialError,
    InaraCredentialStore,
)
from ed_companion.phase14.controller import CockpitController


PROTECTED_PREFIX = b"protected:"


def _fake_protect(value):
    return PROTECTED_PREFIX + value[::-1]


def _fake_unprotect(value):
    if not value.startswith(PROTECTED_PREFIX):
        raise FrontierCredentialError("invalid protected value")
    return value[len(PROTECTED_PREFIX):][::-1]


class InaraCredentialStoreTests(unittest.TestCase):
    def test_round_trip_never_writes_plaintext_and_clear_removes_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "inara_credentials.dat"
            store = InaraCredentialStore(
                path, protect=_fake_protect, unprotect=_fake_unprotect
            )

            store.save("INARA-SECRET-123456")

            self.assertNotIn("INARA-SECRET-123456", path.read_text("ascii"))
            self.assertEqual(store.load(), "INARA-SECRET-123456")
            store.clear()
            self.assertFalse(path.exists())

    def test_corrupt_protected_value_is_rejected_without_disclosure(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "inara_credentials.dat"
            path.write_text("aW52YWxpZA==", encoding="ascii")
            store = InaraCredentialStore(
                path, protect=_fake_protect, unprotect=_fake_unprotect
            )

            with self.assertRaises(InaraCredentialError) as raised:
                store.load()

            self.assertNotIn("invalid", str(raised.exception).lower())

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI is Windows-only")
    def test_windows_dpapi_round_trip(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "inara_credentials.dat"
            store = InaraCredentialStore(path)

            store.save("INARA-DPAPI-SECRET-123456")

            self.assertNotIn(
                "INARA-DPAPI-SECRET-123456", path.read_text("ascii")
            )
            self.assertEqual(store.load(), "INARA-DPAPI-SECRET-123456")


class InaraCredentialMigrationTests(unittest.TestCase):
    def _controller(self, directory):
        controller = CockpitController.__new__(CockpitController)
        controller.inara_config_file = Path(directory) / "inara_config.json"
        controller._inara_credential_protect = _fake_protect
        controller._inara_credential_unprotect = _fake_unprotect
        return controller

    def test_plaintext_config_is_migrated_once_and_restart_loads_secure_key(self):
        with TemporaryDirectory() as directory:
            controller = self._controller(directory)
            controller.inara_config_file.write_text(json.dumps({
                "api_key": "LEGACY-INARA-SECRET-123456",
                "commander_name": "Test Commander",
                "consent": True,
                "auto_sync": True,
            }), encoding="utf-8")

            loaded = controller._load_inara_config()

            self.assertEqual(
                loaded["api_key"], "LEGACY-INARA-SECRET-123456"
            )
            public = json.loads(
                controller.inara_config_file.read_text(encoding="utf-8")
            )
            self.assertNotIn("api_key", public)
            encrypted = controller._inara_credential_store().path.read_text(
                encoding="ascii"
            )
            self.assertNotIn("LEGACY-INARA-SECRET-123456", encrypted)

            restarted = self._controller(directory)
            reloaded = restarted._load_inara_config()
            self.assertEqual(
                reloaded["api_key"], "LEGACY-INARA-SECRET-123456"
            )

    def test_failed_migration_preserves_legacy_key_and_connection_data(self):
        with TemporaryDirectory() as directory:
            controller = self._controller(directory)
            controller._inara_credential_protect = (
                lambda _value: (_ for _ in ()).throw(
                    FrontierCredentialError("DPAPI unavailable")
                )
            )
            original = {
                "api_key": "LEGACY-INARA-SECRET-123456",
                "commander_name": "Test Commander",
                "consent": True,
            }
            controller.inara_config_file.write_text(
                json.dumps(original), encoding="utf-8"
            )

            loaded = controller._load_inara_config()

            self.assertEqual(
                loaded["api_key"], "LEGACY-INARA-SECRET-123456"
            )
            self.assertFalse(controller._inara_key_protected)
            self.assertEqual(
                json.loads(controller.inara_config_file.read_text("utf-8")),
                original,
            )

    def test_full_api_key_is_not_exposed_as_qml_property(self):
        self.assertFalse(hasattr(CockpitController, "inaraApiKey"))
        self.assertTrue(hasattr(CockpitController, "inaraKeyConfigured"))

    def test_clear_key_removes_secure_file_and_disables_auto_sync(self):
        with TemporaryDirectory() as directory:
            controller = self._controller(directory)
            controller._inara_config = {
                "api_key": "INARA-SECRET-123456",
                "commander_name": "Test Commander",
                "frontier_id": "F-TEST",
                "consent": True,
                "auto_sync": True,
                "request_times": [],
            }
            controller._inara_credential_store().save(
                controller._inara_config["api_key"]
            )
            controller._inara_key_protected = True
            controller._sync_eddn_profile = lambda: True
            controller._discard_inara_pending = mock.Mock()
            controller.connectionChanged = mock.Mock()
            controller._save_inara_config()

            controller.clearInaraKey()

            self.assertEqual(controller._inara_config["api_key"], "")
            self.assertFalse(controller._inara_config["auto_sync"])
            self.assertFalse(controller._inara_credential_store().path.exists())
            public = json.loads(
                controller.inara_config_file.read_text(encoding="utf-8")
            )
            self.assertNotIn("api_key", public)
            self.assertFalse(public["auto_sync"])
            controller._discard_inara_pending.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
