"""Real Qt startup, cancellation and callbacks during asynchronous loading."""
import unittest

from test_qml_smoke_load import _run_smoke


LOADER_SCRIPT = r'''
import json, tempfile, time
from pathlib import Path
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from ed_companion.qml_startup import QmlStartup

app = QGuiApplication([])
engine = QQmlApplicationEngine()
keepers = []
beats = []
timer = QTimer()
timer.timeout.connect(lambda: beats.append(time.monotonic()))
timer.start(5)

def until(predicate, seconds=10):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.001)
    assert predicate(), 'Qt startup readiness timeout'

def load(paths):
    loader = QmlStartup(engine, [QUrl.fromLocalFile(str(path)) for path in paths])
    ready, errors = [], []
    loader.ready.connect(ready.append)
    loader.failed.connect(errors.append)
    keepers.append(loader)
    loader.start()
    return loader, ready, errors

with tempfile.TemporaryDirectory() as scratch:
    root = Path(scratch)
    large = root/'Large.qml'
    small = root/'Small.qml'
    invalid = root/'Invalid.qml'
    required = root/'MissingTarget.qml'
    large.write_text('import QtQuick\nItem { property int marker: 1; '
        'property int count: content.children.length; '
        'Item { id: content; Repeater { model: 6000; Item {} } } }')
    small.write_text('import QtQuick\nItem { property int marker: 2 }')
    invalid.write_text('import QtQuick\nItem { malformed syntax }')
    required.write_text('import QtQuick\nItem { required property string target }')
    loader, ready, errors = load([large, small])
    loader.start()  # Starting twice must not duplicate roots or publication.
    until(lambda: ready or errors)
    assert not errors, errors
    assert len(ready) == 1 and len(ready[0]) == 2, ready
    assert [obj.property('marker') for obj in ready[0]] == [1, 2]
    assert ready[0][0].property('count') >= 6000
    assert all(obj.parent() is engine for obj in ready[0])
    assert len(beats) >= 2, 'QML creation did not yield to the event loop'
    until(lambda: loader._incubation.incubatingObjectCount() == 0)
    assert not loader._incubation.timer.isActive(), 'Idle incubation timer still running'

    failed, ready, errors = load([invalid])
    until(lambda: errors)
    assert len(errors) == 1 and not ready and failed._closed

    failed, ready, errors = load([required])
    until(lambda: errors)
    assert len(errors) == 1 and 'target' in errors[0] and not ready, errors

    cancelled, ready, errors = load([large, small])
    until(lambda: cancelled._incubator is not None and cancelled._incubator.isLoading())
    cancelled.cancel()
    cancelled.start()
    for _ in range(30):
        app.processEvents()
        time.sleep(.001)
    assert not ready and not errors and not cancelled.roots
    assert not cancelled._incubation.timer.isActive()

for loader in keepers:
    loader.cancel()
    for obj in loader.roots:
        obj.deleteLater()
app.processEvents()
print('PHASE14_SMOKE_REPORT='+json.dumps({'status':'PASS'}))
'''


CALLBACK_SCRIPT = r'''
import requests
import phase14_main as main
from PySide6.QtCore import QTimer

requests.Session.request = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('Offline QA'))
callback = 'edec://oauth/callback?code=fixture&state=fixture'
received = []
settings = {}
original_instance = main.SingleInstanceRuntime.__init__
original_start = main.QmlStartup.start
original_runner = main.SmokeTestRunner.__init__
original_settings = main.OverlaySettings

def overlay_settings(*a, **k):
    result = original_settings(*a, **k)
    settings[k.get('filename', 'overlay_settings.json')] = result
    return result

def instance(self, *a, **k):
    original_instance(self, *a, **k)
    main.qa_instance = self

def start(self):
    main.qa_instance.oauthCallbackReceived.emit(callback)
    main.qa_instance.activationRequested.emit()
    original_start(self)

main.SingleInstanceRuntime.__init__ = instance
main.QmlStartup.start = start
main.OverlaySettings = overlay_settings
main.CockpitController.acceptFrontierOAuthCallback = lambda self, url: received.append(url)

def check(runner):
    assert received == [callback], received
    assert runner.window.isVisible()
    runner.window.hide()
    main.qa_instance.activationRequested.emit()
    assert runner.window.isVisible()
    settings['overlay_settings.json'].visible = True
    settings['nav_overlay_settings.json'].visible = True
    return True

def overlays_visible(runner):
    assert runner.overlay_window.isVisible()
    assert runner.nav_overlay_window.isVisible()
    settings['overlay_settings.json'].visible = False
    settings['nav_overlay_settings.json'].visible = False
    return True

def overlays_hidden(runner):
    assert not runner.overlay_window.isVisible()
    assert not runner.nav_overlay_window.isVisible()
    return True

def init(self, *a, **k):
    original_runner(self, *a, **k)
    self.steps = [
        ('callbacks-during-startup', lambda: check(self)),
        ('overlay-visibility-bindings', lambda: overlays_visible(self)),
        ('overlay-hidden-again', lambda: overlays_hidden(self)),
    ]

main.SmokeTestRunner.__init__ = init
raise SystemExit(main.run())
'''


class QmlStartupTests(unittest.TestCase):
    def test_real_loader_yields_orders_roots_and_handles_failure_and_cancellation(self):
        completed, report = _run_smoke(script=LOADER_SCRIPT)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIsNotNone(report, completed.stdout + completed.stderr)
        self.assertEqual(report['status'], 'PASS', report)

    def test_oauth_and_activation_received_during_startup_are_preserved(self):
        completed, report = _run_smoke(
            {'PHASE14_SMOKE_ASYNC_PAGES': '1'}, script=CALLBACK_SCRIPT,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIsNotNone(report, completed.stdout + completed.stderr)
        self.assertEqual(report['status'], 'PASS', report)
