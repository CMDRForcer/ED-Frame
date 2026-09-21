import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest import mock

from ed_companion.phase14.controller import CockpitController
from ed_companion.phase14.state import ProfileContext


class _Signal:
    def __init__(self):
        self.calls = []

    def emit(self, payload):
        self.calls.append(payload)


class WishlistUnexpectedlyEmptyRetryTests(unittest.TestCase):
    """Retry only when persisted plans are absent from the built state."""

    @staticmethod
    def _profile_context(root):
        directory = Path(root) / "profile-test"
        directory.mkdir(parents=True, exist_ok=True)
        return ProfileContext("CMDR Test", "test", directory, str(Path(root) / "journal"))

    @staticmethod
    def _write_plans(context, ship, plans):
        (context.directory / "ship_blueprints.json").write_text(
            json.dumps({ship: plans}), encoding="utf-8",
        )

    @staticmethod
    def _controller():
        controller = CockpitController.__new__(CockpitController)
        controller._shutdown_complete = False
        controller._network_threads = set()
        controller._network_threads_lock = threading.Lock()
        controller._refresh_in_flight = False
        controller._refresh_dirty = True
        controller._refresh_revision = 0
        controller._profile_generation = 1
        controller.package_root = Path(".")
        controller._selected_ship = "Python Mk II"
        controller._follow_active_ship = False
        controller._armed_plan_id = ""
        controller._trader_preference = "confirmed"
        controller._hge_sightings = []
        controller._eddn_context = {}
        controller._eddn_queue = []
        controller._eddn_config = {}
        controller._hge_revision = 0
        controller._eddn_revision = 0
        controller._journal_state_ready = False
        controller._build_state_find_rows = mock.Mock(return_value=[])
        controller._build_hge_candidate_rows = mock.Mock(return_value=[])
        controller.refreshStateReady = _Signal()
        controller.refreshStateFailed = _Signal()
        controller.startupStateReady = _Signal()
        controller.startupStateFailed = _Signal()
        return controller

    def test_launch_state_refresh_retries_when_disk_has_plans_the_state_is_missing(self):
        with TemporaryDirectory() as directory:
            context = self._profile_context(directory)
            self._write_plans(context, "Python Mk II", [[{"Name": "Overcharged"}]])
            controller = self._controller()
            empty_state = {
                "ship": "Python Mk II", "activeShip": "Python Mk II",
                "activeShipKnown": True, "blueprints": [],
                "_profileContext": context,
            }
            populated_state = {
                "ship": "Python Mk II", "activeShip": "Python Mk II",
                "activeShipKnown": True, "blueprints": [{"planId": "p1"}],
                "_profileContext": context,
            }

            with mock.patch(
                "ed_companion.phase14.controller.build_state",
                side_effect=[empty_state, populated_state],
            ) as build_state_mock, mock.patch(
                "ed_companion.phase14.controller.logbook_entries", return_value=[],
            ), mock.patch(
                "ed_companion.phase14.controller.threading.Thread"
            ) as thread_cls:
                thread_cls.side_effect = lambda target, **_kw: mock.Mock(start=target)
                controller._launch_state_refresh()

        self.assertEqual(build_state_mock.call_count, 2)
        published_state = controller.refreshStateReady.calls[0][1]
        self.assertEqual(published_state["blueprints"], [{"planId": "p1"}])

    def test_launch_state_refresh_does_not_retry_a_genuinely_empty_wishlist(self):
        with TemporaryDirectory() as directory:
            context = self._profile_context(directory)
            controller = self._controller()
            empty_state = {
                "ship": "Python Mk II", "activeShip": "Python Mk II",
                "activeShipKnown": True, "blueprints": [],
                "_profileContext": context,
            }

            with mock.patch(
                "ed_companion.phase14.controller.build_state",
                side_effect=[empty_state],
            ) as build_state_mock, mock.patch(
                "ed_companion.phase14.controller.logbook_entries", return_value=[],
            ), mock.patch(
                "ed_companion.phase14.controller.threading.Thread"
            ) as thread_cls:
                thread_cls.side_effect = lambda target, **_kw: mock.Mock(start=target)
                controller._launch_state_refresh()

        self.assertEqual(build_state_mock.call_count, 1)
        published_state = controller.refreshStateReady.calls[0][1]
        self.assertEqual(published_state["blueprints"], [])

    def test_launch_state_refresh_retry_still_empty_publishes_the_empty_result(self):
        with TemporaryDirectory() as directory:
            context = self._profile_context(directory)
            self._write_plans(context, "Python Mk II", [[{"Name": "Overcharged"}]])
            controller = self._controller()
            empty_state = {
                "ship": "Python Mk II", "activeShip": "Python Mk II",
                "activeShipKnown": True, "blueprints": [],
                "_profileContext": context,
            }

            with mock.patch(
                "ed_companion.phase14.controller.build_state",
                side_effect=[empty_state, dict(empty_state)],
            ) as build_state_mock, mock.patch(
                "ed_companion.phase14.controller.logbook_entries", return_value=[],
            ), mock.patch(
                "ed_companion.phase14.controller.threading.Thread"
            ) as thread_cls:
                thread_cls.side_effect = lambda target, **_kw: mock.Mock(start=target)
                controller._launch_state_refresh()

        self.assertEqual(build_state_mock.call_count, 2)
        published_state = controller.refreshStateReady.calls[0][1]
        self.assertEqual(published_state["blueprints"], [])

    def test_initial_state_load_also_retries_on_the_same_mismatch(self):
        with TemporaryDirectory() as directory:
            context = self._profile_context(directory)
            self._write_plans(context, "Python Mk II", [[{"Name": "Overcharged"}]])
            controller = self._controller()
            controller.profile_context = context
            empty_state = {
                "ship": "Python Mk II", "activeShip": "Python Mk II",
                "activeShipKnown": True, "blueprints": [],
                "_profileContext": context,
            }
            populated_state = {
                "ship": "Python Mk II", "activeShip": "Python Mk II",
                "activeShipKnown": True, "blueprints": [{"planId": "p1"}],
                "_profileContext": context,
            }

            with mock.patch(
                "ed_companion.phase14.controller.build_state",
                side_effect=[empty_state, populated_state],
            ) as build_state_mock, mock.patch(
                "ed_companion.phase14.controller.logbook_entries", return_value=[],
            ), mock.patch(
                "ed_companion.phase14.controller.rebuild_eddn_context", return_value={},
            ), mock.patch(
                "ed_companion.phase14.controller.profiled_journal_events", return_value=[],
            ), mock.patch(
                "ed_companion.phase14.controller.threading.Thread"
            ) as thread_cls:
                thread_cls.side_effect = lambda target, **_kw: mock.Mock(start=target)
                controller._start_initial_state_load()

        self.assertEqual(build_state_mock.call_count, 2)
        published_state = controller.startupStateReady.calls[0][2]
        self.assertEqual(published_state["blueprints"], [{"planId": "p1"}])


if __name__ == "__main__":
    unittest.main()
