"""Cooperative CPU slices for large, lossless background transformations."""

import threading
import time


class WorkerBudget:
    """Give Qt a scheduling turn after ~8 ms; never sleep on the UI thread.

    A zero-duration yield can immediately resume the same competing worker on
    Windows. A short real pause makes room for input/QML callbacks instead.
    This does not cancel, truncate, reorder or change any record calculation.
    """

    def __init__(self):
        self._enabled = threading.current_thread() is not threading.main_thread()
        self._at = time.monotonic()
        self._checks = 0

    def checkpoint(self):
        self._checks += 1
        if not self._enabled or self._checks % 64:
            return
        now = time.monotonic()
        if now - self._at >= 0.008:
            time.sleep(0.001)
            self._at = time.monotonic()
