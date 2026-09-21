import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from ed_companion.phase14.state_fleet import (
    _read_ship_blueprints_defensively,
    reconcile_fleet_cache,
)
from ed_companion.phase14.state import current_ship


class DefensiveShipBlueprintsReadTests(unittest.TestCase):
    """Keep transient read failures separate from legitimate empty plans."""

    def test_trusts_a_missing_file_immediately_without_reading(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ship_blueprints.json"
            with mock.patch(
                "ed_companion.phase14.state_fleet.read_json",
            ) as read_json_mock, mock.patch(
                "ed_companion.phase14.state_fleet.time.sleep",
            ) as sleep_mock:
                result = _read_ship_blueprints_defensively(path)

        self.assertEqual(result, {})
        read_json_mock.assert_not_called()
        sleep_mock.assert_not_called()

    def test_retries_and_recovers_from_a_transient_empty_read(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ship_blueprints.json"
            real_content = {"Python Mk II": [[{"Name": "Overcharged"}]]}
            path.write_text(json.dumps(real_content), encoding="utf-8")

            with mock.patch(
                "ed_companion.phase14.state_fleet.read_json",
                side_effect=[{}, {}, real_content],
            ) as read_json_mock, mock.patch(
                "ed_companion.phase14.state_fleet.time.sleep",
            ) as sleep_mock:
                result = _read_ship_blueprints_defensively(path)

        self.assertEqual(result, real_content)
        self.assertEqual(read_json_mock.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_trusts_a_genuinely_empty_file_without_delay(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ship_blueprints.json"
            path.write_text("{}", encoding="utf-8")

            with mock.patch(
                "ed_companion.phase14.state_fleet.read_json",
                return_value={},
            ) as read_json_mock, mock.patch(
                "ed_companion.phase14.state_fleet.time.sleep",
            ) as sleep_mock:
                result = _read_ship_blueprints_defensively(path)

        self.assertEqual(result, {})
        read_json_mock.assert_called_once_with(path, {})
        sleep_mock.assert_not_called()

    def test_gives_up_after_repeated_empty_reads_of_an_existing_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ship_blueprints.json"
            path.write_text(
                json.dumps({"Python Mk II": [[{"Name": "Overcharged"}]]}),
                encoding="utf-8",
            )

            with mock.patch(
                "ed_companion.phase14.state_fleet.read_json", return_value={},
            ) as read_json_mock, mock.patch(
                "ed_companion.phase14.state_fleet.time.sleep",
            ):
                result = _read_ship_blueprints_defensively(path)

        self.assertEqual(result, {})
        self.assertEqual(read_json_mock.call_count, 5)


class ReconcileFleetCacheDataLossTests(unittest.TestCase):
    def test_a_transient_empty_read_does_not_wipe_real_plans_on_disk(self):
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            real_plans = {"Python Mk II": [[{
                "Name": "Overcharged",
                "_Planner": {"slot": "PowerPlant", "ship_id": "45"},
            }]]}
            (data_dir / "ship_blueprints.json").write_text(
                json.dumps(real_plans), encoding="utf-8",
            )
            (data_dir / "ship_metadata.json").write_text(json.dumps({
                "Python Mk II": {
                    "id": 45, "type": "Python Mk II", "name": "",
                    "status": "active", "is_current": True,
                },
            }), encoding="utf-8")
            fleet_state = {
                "active_id": "45",
                "ships": [{
                    "id": 45, "label": "Python Mk II", "type": "Python Mk II",
                    "name": "", "status": "active",
                }],
            }

            from ed_companion.phase14.state_core import read_json as real_read_json

            calls = {"blueprints": 0}

            def flaky_read_json(path, default):
                if str(path).endswith("ship_blueprints.json"):
                    calls["blueprints"] += 1
                    # Model a short-lived read failure before the intact
                    # file becomes readable again.
                    return {} if calls["blueprints"] <= 2 else real_read_json(
                        path, default
                    )
                return real_read_json(path, default)

            with mock.patch(
                "ed_companion.phase14.state_fleet.read_json",
                side_effect=flaky_read_json,
            ), mock.patch(
                "ed_companion.phase14.state_fleet.time.sleep",
            ):
                migrated, _aliases = reconcile_fleet_cache(data_dir, fleet_state)

            self.assertEqual(migrated, real_plans)
            on_disk = json.loads(
                (data_dir / "ship_blueprints.json").read_text(encoding="utf-8")
            )
            self.assertEqual(on_disk, real_plans)


class CurrentShipWishlistReadTests(unittest.TestCase):
    def test_second_read_after_binding_migration_is_also_defensive(self):
        """The file can survive reconciliation intact while the immediate
        follow-up read alone glitches empty.  The selected ship must still
        receive its imported plans instead of publishing an empty Wishlist.
        """
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            plans = [[{
                "Name": "Overcharged Weapon",
                "_Planner": {"slot": "LargeHardpoint1", "ship_id": "45"},
            }]]
            fleet_state = {
                "active_id": "45",
                "ships": [{
                    "id": 45, "label": "Python Mk II",
                    "type": "Python Mk II", "name": "", "status": "active",
                }],
            }

            with mock.patch(
                "ed_companion.phase14.state.reconcile_fleet_cache",
                return_value=({"Python Mk II": plans}, {}),
            ), mock.patch(
                "ed_companion.phase14.state.migrate_wishlist_bindings",
            ), mock.patch(
                "ed_companion.phase14.state.read_json", return_value={},
            ), mock.patch(
                "ed_companion.phase14.state._read_ship_blueprints_defensively",
                return_value={"Python Mk II": plans},
            ) as defensive_read:
                ship, selected, ships = current_ship(
                    data_dir, fleet_state, "Python Mk II", [],
                )

        self.assertEqual(ship, "Python Mk II")
        self.assertEqual(selected, plans)
        self.assertEqual(ships, ["Python Mk II"])
        defensive_read.assert_called_once_with(
            data_dir / "ship_blueprints.json"
        )


if __name__ == "__main__":
    unittest.main()
