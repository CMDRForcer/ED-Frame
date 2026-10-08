"""Load the real Main.qml headless so QML runtime errors fail CI.

The other QML tests only parse the source text. This drives the actual
``phase14_main`` smoke runner under the offscreen platform, in a throwaway
``LOCALAPPDATA`` and with a unique single-instance name so it never touches a
running app or the user's profile.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ed_companion.diagnostics import filtered_log_lines, is_benign_qt_message

ROOT = Path(__file__).resolve().parents[1]


def _run_smoke(extra_env=None, timeout=240, script=None):
    with tempfile.TemporaryDirectory(prefix="edec-qml-smoke-") as scratch:
        env = {
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "LOCALAPPDATA": scratch,
            "ED_FRAME_SINGLE_INSTANCE_NAME": f"ED-Frame-qml-smoke-{os.getpid()}",
            "PHASE14_SMOKE_TEST": "1",
        }
        env.update(extra_env or {})
        command = ([sys.executable, "-c", script] if script else
                   [sys.executable, str(ROOT / "phase14_main.py")])
        completed = subprocess.run(
            command, cwd=ROOT,
            env=env, capture_output=True, text=True, timeout=timeout,
        )
    report = None
    for line in completed.stdout.splitlines():
        if line.startswith("PHASE14_SMOKE_REPORT="):
            report = json.loads(line[len("PHASE14_SMOKE_REPORT="):])
    return completed, report


class QmlSmokeLoadTests(unittest.TestCase):
    def test_delegate_failure_is_only_benign_paired_with_incubation_teardown(self):
        teardown = "Object or context destroyed during incubation"
        delegate = "QML Component: Cannot create delegate"

        self.assertTrue(is_benign_qt_message(teardown))
        self.assertFalse(is_benign_qt_message(delegate))
        # Teardown observed before the delegate failure.
        self.assertTrue(is_benign_qt_message(delegate, teardown))
        self.assertTrue(
            is_benign_qt_message(
                delegate, "an unrelated Qt message", True
            )
        )
        # Qt does not guarantee the order - the delegate failure is
        # observed just as often *before* its teardown message.
        self.assertTrue(is_benign_qt_message(delegate, next_message=teardown))
        self.assertFalse(
            is_benign_qt_message(delegate, next_message="an unrelated Qt message")
        )
        self.assertEqual(filtered_log_lines([teardown, delegate]), [])
        self.assertEqual(filtered_log_lines([delegate, teardown]), [])
        self.assertEqual(filtered_log_lines([delegate]), [delegate])

    def test_main_qml_loads_without_runtime_errors(self):
        completed, report = _run_smoke({"PHASE14_SMOKE_ASYNC_PAGES": "0"})
        self.assertIsNotNone(report, completed.stdout + completed.stderr)
        self.assertEqual(report["status"], "PASS", json.dumps(report, ensure_ascii=False))
        self.assertEqual(completed.returncode, 0)

    def test_rapid_engineer_modes_and_page_unloads_restore_real_list_delegates(self):
        script = r'''
import time
import phase14_main as main
from PySide6.QtCore import QTimer
from PySide6.QtQml import QQmlEngine, QQmlExpression

original_init = main.SmokeTestRunner.__init__

def engineer_mode(runner, unlock, broker):
    if not runner._engineer_state(unlock, broker):
        return False
    page = runner._find("qa-page-engineers")
    view = "guardianList" if broker else "unlockStepList" if unlock else "engineerList"
    expression = QQmlExpression(QQmlEngine.contextForObject(page), page,
        view + ".count > 0 && " + view + ".currentItem !== null")
    ready, _undefined = expression.evaluate()
    if expression.hasError():
        raise RuntimeError(expression.error().toString())
    return bool(ready)

def init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    # The lightweight first-frame state intentionally has no broker guide.
    # Wait for its real background publication before stressing delegates;
    # otherwise the first broker check measures cold startup, not page unload.
    self.startup_deadline = time.monotonic() + 30.0
    self.steps = [("startup-broker-data", lambda: bool(
        self.controller._journal_state_ready and self.controller.techBrokerGuide
    ))]
    for cycle in range(75):
        self.steps.extend([
            (f"engineers-{cycle}-overview", lambda: engineer_mode(self, False, False)),
            (f"engineers-{cycle}-guide", lambda: engineer_mode(self, True, False)),
            (f"engineers-{cycle}-brokers", lambda: engineer_mode(self, False, True)),
            (f"engineers-{cycle}-unload", lambda: self._page(0, "qa-page-operations")),
        ])

def poll(self):
    label, check = self.current
    if label == "startup-broker-data":
        self.deadline = self.startup_deadline
    try:
        ready = bool(check())
    except Exception as exc:
        self.results.append({"area": label, "status": "FAIL", "error": str(exc)})
        self.step_index += 1
        QTimer.singleShot(0, self._next)
        return
    if ready:
        self.results.append({"area": label, "status": "PASS"})
        self.step_index += 1
        QTimer.singleShot(0, self._next)
    elif time.monotonic() >= self.deadline:
        self.results.append({"area": label, "status": "FAIL", "error": "list readiness timeout"})
        self.step_index += 1
        QTimer.singleShot(0, self._next)
    else:
        QTimer.singleShot(10, self._poll)

main.SmokeTestRunner.__init__ = init
main.SmokeTestRunner._poll = poll
raise SystemExit(main.run())
'''
        for asynchronous in ("0", "1"):
            with self.subTest(asynchronous=asynchronous):
                completed, report = _run_smoke(
                    {"PHASE14_SMOKE_ASYNC_PAGES": asynchronous}, script=script,
                )
                self.assertIsNotNone(report, completed.stdout + completed.stderr)
                failed = [row for row in report["areas"] if row["status"] != "PASS"]
                self.assertEqual(failed, [], json.dumps(failed, ensure_ascii=False))
                self.assertEqual(completed.returncode, 0)

    def test_production_asynchronous_page_loaders_restore_controls_without_errors(self):
        completed, report = _run_smoke({"PHASE14_SMOKE_ASYNC_PAGES": "1"})
        self.assertIsNotNone(report, completed.stdout + completed.stderr)
        self.assertEqual(report["status"], "PASS", json.dumps(report, ensure_ascii=False))
        self.assertEqual(completed.returncode, 0)

    def test_injected_qml_error_is_detected(self):
        """Guard the guard: a deliberate QML error must fail the smoke load."""
        completed, report = _run_smoke(
            {"PHASE14_SMOKE_INJECT_QML_ERROR": "1"}
        )
        self.assertIsNotNone(report, completed.stdout + completed.stderr)
        self.assertEqual(report["status"], "FAIL")
        self.assertNotEqual(completed.returncode, 0)


if __name__ == "__main__":
    unittest.main()
