import threading
import time
import unittest
from unittest import mock

from ed_companion.phase14.controller import CockpitController


class ShutdownWaitsForInFlightRefreshTests(unittest.TestCase):
    """Journal-state workers must finish before controller shutdown."""

    @staticmethod
    def _controller():
        controller = CockpitController.__new__(CockpitController)
        controller._shutdown_complete = False
        controller._network_threads = set()
        controller._network_threads_lock = threading.Lock()
        controller._eddn_stop = threading.Event()
        controller._eddn_thread = None
        for timer_name in (
            "timer", "refreshDebounceTimer", "craftConfirmationTimer",
            "hgeBatchTimer", "_frontier_watchdog",
        ):
            setattr(controller, timer_name, mock.Mock())
        controller.flushHgeObservationBatch = mock.Mock()
        controller._save_eddn = mock.Mock()
        controller._save_eddn_cursor = mock.Mock()
        controller._save_hge_cache = mock.Mock()
        controller._save_inara_journal_cache = mock.Mock()
        controller._save_inara_receipts = mock.Mock()
        controller._save_ui_config = mock.Mock()
        return controller

    def test_shutdown_joins_an_in_flight_journal_state_refresh_thread(self):
        controller = self._controller()
        completed = threading.Event()

        def slow_refresh_worker():
            time.sleep(0.15)
            completed.set()

        started = controller._start_network_worker(
            slow_refresh_worker, "journal-state-1",
        )
        self.assertTrue(started)
        self.assertFalse(completed.is_set())

        controller.shutdown()

        self.assertTrue(
            completed.is_set(),
            "shutdown() returned before the in-flight refresh finished.",
        )

    def test_shutdown_is_idempotent_and_does_not_hang_with_no_workers(self):
        controller = self._controller()

        controller.shutdown()
        controller.shutdown()

        controller._save_ui_config.assert_called_once()


if __name__ == "__main__":
    unittest.main()
