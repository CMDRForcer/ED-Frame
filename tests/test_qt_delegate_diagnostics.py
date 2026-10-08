"""Cancelled page incubation is paired narrowly; actual QML errors survive."""

from contextlib import contextmanager, ExitStack
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import phase14_main
from ed_companion.diagnostics import (
    filtered_log_lines, is_benign_qt_message, is_qt_delegate_failure,
)


COMPONENT = "QML Component: Cannot create delegate"
LOADER = "QML Loader (parent or ancestor of Component): Cannot create delegate"
TEARDOWN = "Object or context destroyed during incubation"


@contextmanager
def installed_handler(times=None):
    with TemporaryDirectory() as directory, ExitStack() as stack:
        stack.enter_context(patch.object(phase14_main, "diagnostics_dir", return_value=Path(directory)))
        registration = stack.enter_context(patch.object(phase14_main, "qInstallMessageHandler"))
        timers = stack.enter_context(patch.object(phase14_main.QTimer, "singleShot"))
        stack.enter_context(patch.object(sys, "excepthook", sys.excepthook))
        if times is not None:
            stack.enter_context(patch.object(phase14_main.time, "monotonic", side_effect=times))
        messages = []
        flush = phase14_main.install_diagnostics(messages)
        yield registration.call_args.args[0], flush, messages, timers


def context(source="Main.qml"):
    return SimpleNamespace(file=source, line=4474)


class QtDelegateDiagnosticsTests(unittest.TestCase):
    def test_component_and_ancestor_variants_require_a_teardown_pair(self):
        for message in (COMPONENT, LOADER, LOADER.replace("Loader", "QQuickRootItem")):
            with self.subTest(message=message):
                self.assertTrue(is_qt_delegate_failure(message))
                self.assertFalse(is_benign_qt_message(message))
                self.assertEqual(filtered_log_lines([message]), [message])
                self.assertEqual(filtered_log_lines([message, TEARDOWN]), [])
                self.assertEqual(filtered_log_lines([TEARDOWN, message]), [])
        for other in ("Cannot create delegate", "QML Loader: Cannot create delegate",
                      LOADER + ": Required property missing", "ReferenceError: Cannot create delegate"):
            self.assertFalse(is_qt_delegate_failure(other))

    def test_live_handler_pairs_both_orders_for_the_same_qml_source(self):
        for failure in (COMPONENT, LOADER):
            for messages in ((failure, TEARDOWN), (TEARDOWN, failure)):
                with self.subTest(messages=messages), installed_handler() as (handler, flush, saved, _timers):
                    for message in messages:
                        handler(None, context(), message)
                    flush()
                    self.assertEqual(saved, [])

    def test_unpaired_ancestor_error_reaches_the_runtime_report_and_timer(self):
        with installed_handler() as (handler, _flush, saved, timers):
            handler(None, context(), LOADER)
            self.assertEqual(saved, [])
            timers.call_args.args[1]()
            self.assertEqual([row["message"] for row in saved], [LOADER])

    def test_teardown_from_another_component_cannot_hide_a_failure_in_either_order(self):
        for failure_first in (True, False):
            with self.subTest(failure_first=failure_first), installed_handler() as (handler, flush, saved, _timers):
                entries = [(context("Broken.qml"), LOADER), (context("Other.qml"), TEARDOWN)]
                for source, message in entries if failure_first else reversed(entries):
                    handler(None, source, message)
                flush()
                self.assertEqual([row["source"] for row in saved], ["Broken.qml"])

    def test_pair_window_expires_and_unrelated_messages_break_adjacency(self):
        with installed_handler([100.0, 100.2]) as (handler, flush, saved, _timers):
            handler(None, context(), TEARDOWN)
            handler(None, context(), LOADER)
            flush()
            self.assertEqual([row["message"] for row in saved], [LOADER])
        with installed_handler() as (handler, flush, saved, _timers):
            handler(None, context(), TEARDOWN)
            handler(None, context(), "QML Text: unrelated diagnostic")
            handler(None, context(), LOADER)
            flush()
            self.assertEqual(saved[-1]["message"], LOADER)

    def test_one_teardown_cannot_suppress_two_failures_or_other_qml_errors(self):
        with installed_handler() as (handler, flush, saved, _timers):
            handler(None, context(), TEARDOWN)
            handler(None, context(), LOADER)
            handler(None, context(), LOADER)
            handler(None, context(), "ReferenceError: genuineMissingValue is not defined")
            flush()
            self.assertEqual([row["message"] for row in saved], [
                LOADER, "ReferenceError: genuineMissingValue is not defined",
            ])

    def test_older_flush_timer_does_not_prematurely_publish_a_new_failure(self):
        with installed_handler() as (handler, flush, saved, timers):
            handler(None, context(), LOADER)
            first_timer = timers.call_args.args[1]
            handler(None, context(), LOADER)
            self.assertEqual(len(saved), 1)
            first_timer()
            self.assertEqual(len(saved), 1)
            handler(None, context(), TEARDOWN)
            flush()
            self.assertEqual(len(saved), 1)

    def test_delayed_teardown_cannot_erase_an_unpaired_creation_failure(self):
        with installed_handler([100.0, 100.2]) as (handler, flush, saved, _timers):
            handler(None, context(), LOADER)
            handler(None, context(), TEARDOWN)
            flush()
            self.assertEqual([row["message"] for row in saved], [LOADER])

    def test_deferred_error_owns_its_context_values_after_qt_callback_returns(self):
        with installed_handler() as (handler, flush, saved, _timers):
            transient_context = context()
            handler(None, transient_context, LOADER)
            transient_context.file = "Invalidated.qml"
            transient_context.line = -1
            flush()
            self.assertEqual((saved[0]["source"], saved[0]["line"]), ("Main.qml", 4474))


if __name__ == "__main__":
    unittest.main()
