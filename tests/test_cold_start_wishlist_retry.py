from pathlib import Path
import unittest
from unittest import mock

from ed_companion.phase14.controller import CockpitController


class _Signal:
    def __init__(self):
        self.calls = []

    def emit(self, payload):
        self.calls.append(payload)


class ColdStartWishlistRetryTests(unittest.TestCase):
    """A real incident: right after an app launch, the very first Journal
    refresh could resolve the correct ship but publish an empty Wishlist
    even though ship_blueprints.json genuinely had plans for it - fixed
    only by manually restarting the app. The fleet/CAPI snapshot behind
    ship <-> label resolution isn't always fully settled on the first
    pass. _launch_state_refresh() must retry once, only on that first
    refresh, when it sees a resolved ship with an unexpectedly empty
    Wishlist."""

    @staticmethod
    def _controller():
        controller = CockpitController.__new__(CockpitController)
        controller._refresh_in_flight = False
        controller._refresh_dirty = True
        controller._refresh_revision = 0
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
        controller.refreshStateReady = _Signal()
        controller.refreshStateFailed = _Signal()
        return controller

    def test_first_refresh_retries_once_when_ship_resolved_but_wishlist_empty(self):
        controller = self._controller()
        empty_state = {"ship": "Python Mk II", "activeShip": "Python Mk II",
                        "activeShipKnown": True, "blueprints": []}
        populated_state = {"ship": "Python Mk II", "activeShip": "Python Mk II",
                            "activeShipKnown": True,
                            "blueprints": [{"planId": "p1"}]}

        with mock.patch(
            "ed_companion.phase14.controller.build_state",
            side_effect=[empty_state, populated_state],
        ) as build_state_mock, mock.patch(
            "ed_companion.phase14.controller.logbook_entries", return_value=[],
        ), mock.patch(
            "ed_companion.phase14.controller.threading.Thread"
        ) as thread_cls:
            thread_cls.side_effect = lambda target, **_kw: mock.Mock(
                start=target,
            )
            controller._launch_state_refresh()

        self.assertEqual(build_state_mock.call_count, 2)
        self.assertEqual(len(controller.refreshStateReady.calls), 1)
        published_state = controller.refreshStateReady.calls[0][1]
        self.assertEqual(published_state["blueprints"], [{"planId": "p1"}])

    def test_second_refresh_does_not_retry_a_genuinely_empty_wishlist(self):
        controller = self._controller()
        controller._journal_state_ready = True
        empty_state = {"ship": "Python Mk II", "activeShip": "Python Mk II",
                        "activeShipKnown": True, "blueprints": []}

        with mock.patch(
            "ed_companion.phase14.controller.build_state",
            side_effect=[empty_state],
        ) as build_state_mock, mock.patch(
            "ed_companion.phase14.controller.logbook_entries", return_value=[],
        ), mock.patch(
            "ed_companion.phase14.controller.threading.Thread"
        ) as thread_cls:
            thread_cls.side_effect = lambda target, **_kw: mock.Mock(
                start=target,
            )
            controller._launch_state_refresh()

        self.assertEqual(build_state_mock.call_count, 1)
        published_state = controller.refreshStateReady.calls[0][1]
        self.assertEqual(published_state["blueprints"], [])

    def test_retry_that_is_still_empty_publishes_the_empty_result(self):
        controller = self._controller()
        empty_state = {"ship": "Python Mk II", "activeShip": "Python Mk II",
                        "activeShipKnown": True, "blueprints": []}
        still_empty_state = dict(empty_state)

        with mock.patch(
            "ed_companion.phase14.controller.build_state",
            side_effect=[empty_state, still_empty_state],
        ) as build_state_mock, mock.patch(
            "ed_companion.phase14.controller.logbook_entries", return_value=[],
        ), mock.patch(
            "ed_companion.phase14.controller.threading.Thread"
        ) as thread_cls:
            thread_cls.side_effect = lambda target, **_kw: mock.Mock(
                start=target,
            )
            controller._launch_state_refresh()

        self.assertEqual(build_state_mock.call_count, 2)
        published_state = controller.refreshStateReady.calls[0][1]
        self.assertEqual(published_state["blueprints"], [])


if __name__ == "__main__":
    unittest.main()
