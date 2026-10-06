import tempfile
import unittest
from pathlib import Path

from ed_companion.phase14.controller_commander import CommanderMixin


class _CommanderFleetHarness(CommanderMixin):
    def __init__(self, root: Path):
        self._state_revision = 7
        self._derived_cache = {}
        self._fleet_images = {}
        self.fleet_images_dir = root
        self._ship_catalog = [{
            "symbol": "Krait_MkII",
            "name": "Krait Mk II",
        }]
        self._state = {"fleet": [{
            "id": "42",
            "type": "Krait_MkII",
            "name": "Test ship",
            "isCurrent": True,
        }]}

    @staticmethod
    def _ship_asset_key(value):
        return str(value or "").casefold().replace("_", "")


class CommanderFleetProjectionTests(unittest.TestCase):
    def test_projection_is_reused_until_state_or_image_mapping_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = _CommanderFleetHarness(Path(directory))
            first = controller._commander_fleet()
            second = controller._commander_fleet()
            self.assertIs(first, second)
            self.assertEqual(first[0]["type"], "Krait Mk II")

            controller._fleet_images["42"] = "missing.png"
            third = controller._commander_fleet()
            self.assertIsNot(first, third)


if __name__ == "__main__":
    unittest.main()
