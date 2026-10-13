"""Real, offline Main.qml onboarding checks using disposable profiles."""
import json
from pathlib import Path
import re
import unittest

from ed_companion.phase14.onboarding import onboarding_state
from tests.test_qml_smoke_load import _run_smoke

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r'''
import json
import os
from pathlib import Path
import shutil
import time
from unittest.mock import Mock
import requests
import urllib.request

def offline(*args, **kwargs):
    raise RuntimeError('Onboarding tests must remain offline')
requests.Session.request = offline
urllib.request.urlopen = offline
local = Path(os.environ['LOCALAPPDATA']) / 'ED-Frame'
local.mkdir(parents=True, exist_ok=True)
journal = local / 'journal-fixture'
journal.mkdir()
shutil.copyfile('tests/fixtures/smoke_journal.ndjson', journal / 'Journal.2026-08-23T170000.01.log')
os.environ['ED_FRAME_JOURNAL_DIR'] = str(journal)
mode = os.environ.get('ONBOARDING_TEST_MODE', 'wizard')
config = dict(renderer_mode='software', onboarding_complete=mode == 'legacy',
              journal_auto=False, background_mode=False, ui_scale=1.15,
              edframe_catalog_enabled=False, edframe_yield_sharing_enabled=False,
              edframe_signal_sharing_enabled=False, edframe_station_price_sharing_enabled=False)
(local / 'phase14_graphics.json').write_text(json.dumps(config))
(local / 'eddn_config.json').write_text(json.dumps(dict(
    consent=False, upload_enabled=False, listener_enabled=False)))
from ed_companion.phase14.state import resolve_profile_context, runtime_data_dir
profile_dir = runtime_data_dir(resolve_profile_context())
profile_dir.mkdir(parents=True, exist_ok=True)
if profile_dir != local:
    for name in ('phase14_graphics.json', 'eddn_config.json'):
        shutil.copyfile(local / name, profile_dir / name)
if mode == 'preview':
    os.environ['PHASE14_PREVIEW_SKIP_ONBOARDING'] = '1'
else:
    os.environ.pop('PHASE14_PREVIEW_SKIP_ONBOARDING', None)

import phase14_main as main
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
from PySide6.QtGui import QFontDatabase

class TestApplication(main.QApplication):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisym.ttf', 'SegUIVar.ttf'):
            if (fonts / name).is_file():
                QFontDatabase.addApplicationFont(str(fonts / name))
main.QApplication = TestApplication

def evaluate(obj, source):
    expr = QQmlExpression(QQmlEngine.contextForObject(obj), obj, source)
    value, _ = expr.evaluate()
    assert not expr.hasError(), expr.error().toString()
    return value

def wizard(runner):
    return runner._find('qa-dialog-onboarding')

def setup(runner, theme, scale, language='de', narrow=False):
    runner.controller.setTheme(theme)
    runner.controller.setInterfaceLanguage(language)
    runner.controller.setUiScale(scale)
    runner.window.setMinimumWidth(480 if narrow else 1120)
    runner.window.setMinimumHeight(420 if narrow else 700)
    runner.window.resize(680 if narrow else 1480, 560 if narrow else 900)
    if not wizard(runner).property('visible'):
        runner.controller.reopenOnboarding()
    return True

def show_page(runner, page):
    w = wizard(runner)
    w.setProperty('stepIndex', page)
    return True

def inspect_page(runner, page):
    w = wizard(runner)
    if not w.property('visible') or w.property('stepIndex') != page:
        return False
    assert w.property('pageCount') == 9
    scroll = runner._find('qa-onboarding-scroll')
    loader = runner._find('qa-onboarding-page')
    if not evaluate(loader, 'status === Loader.Ready && item !== null'):
        return False
    assert scroll.width() > 100 and scroll.height() > 30
    if page == 7:
        assert evaluate(scroll, 'contentHeight > availableHeight && ScrollBar.vertical.size < 1'), 'Tour must scroll'
    # The viewport is bounded by the scaled window; content scrolls vertically.
    assert evaluate(w, 'width <= parent.width && height <= parent.height')
    assert evaluate(w, """(function() {
        var top = background.mapToItem(null, 0, 0);
        var bottom = background.mapToItem(null, background.width, background.height);
        return top.x >= -1 && top.y >= -1
            && bottom.x <= window.width + 1 && bottom.y <= window.height + 1;
    })()"""), 'Scaled popup extends beyond the physical window'
    for name in ('skip', 'back', 'next'):
        button = runner._find('qa-onboarding-' + name)
        assert button and button.property('visible')
        assert evaluate(button, 'Accessible.name.length > 0')
        assert evaluate(button, 'y >= 0 && y + height <= parent.height + 1')
    # Check the rendered text widths, not only the surrounding card rectangles.
    # Keep Loader-owned items in QML. Exporting transient items as Python
    # wrappers can change their ownership during subsequent page destruction.
    error = evaluate(loader, r"""(function walk(node) {
        if (node.visible && node.truncated === true) return node.text;
        if (node.visible && node.text !== undefined && node.width > width + 1) return node.text;
        var children = node.children || [];
        for (var i = 0; i < children.length; i++) {
            var error = walk(children[i]);
            if (error) return error;
        }
        return '';
    })(item)""")
    assert not error, error
    if page >= 4:
        entries = json.loads(evaluate(w, 'JSON.stringify(tourPage.entries)'))
        for entry in entries:
            assert visual_control(runner, 'qa-onboarding-area-' + entry['id'])
            assert visual_control(runner, 'qa-onboarding-open-' + entry['id'])
    return True

def visual_control(runner, name, click=False):
    # Repeater delegates have a visual parent but need not be QObject children.
    loader = runner._find('qa-onboarding-page')
    action = 'node.clicked(); return true;' if click else 'return true;'
    return evaluate(loader, """(function find(node) {
        if (node.objectName === %s) { %s }
        var children = node.children || [];
        for (var i=0; i<children.length; i++) if (find(children[i])) return true;
        return false;
    })(item)""" % (json.dumps(name), action))

def tour_contract(runner):
    w = wizard(runner)
    navigation = json.loads(evaluate(runner.window, 'JSON.stringify(primaryNavigation)'))
    pages = json.loads(evaluate(w, 'JSON.stringify(tourPages)'))
    ids = [entry['id'] for page in pages for entry in page['entries']]
    assert len(ids) == len(set(ids)) == len(navigation)
    assert set(ids) == {entry['id'] for entry in navigation}
    for page in pages:
        assert page['entries'] == [entry for entry in navigation if entry['id'] in {row['id'] for row in page['entries']}]
    evaluate(w, 'navigationItems = navigationItems.concat([{id:"future-area", label:"Future area", page:0}])')
    assert w.property('pageCount') == 10
    assert evaluate(w, 'tourPages[5].id === "other" && tourPages[5].entries[0].id === "future-area"')
    evaluate(w, 'navigationItems = Qt.binding(function() { return window.primaryNavigation })')
    return True

def skip(runner, page, escape=False):
    w = wizard(runner)
    assert w.property('stepIndex') == page
    if escape:
        QTest.keyClick(runner.window, Qt.Key_Escape)
    else:
        runner._find('qa-onboarding-skip').clicked.emit()
    assert runner.controller.onboardingComplete
    assert not w.property('visible')
    saved = json.loads(runner.controller.config_file.read_text())
    assert saved['onboarding_complete'] is True and saved['onboarding_version'] == 1
    return True

def change_settings(runner):
    runner.controller.refreshEdFrameCatalogStatus = Mock()
    runner.controller._ensure_eddn_listener = Mock()
    runner.controller._baseline_eddn_journal_files = Mock(return_value=False)
    runner.controller.saveEddnConfig(True, True, False)
    assert runner._find('qa-onboarding-eddn-partial').property('visible')
    runner.controller.setTheme('crimson_light')
    runner.controller.setInterfaceLanguage('fr')
    assert wizard(runner).property('stepIndex') == 2, 'Settings updates must not reset the page'
    # Drive the actual controls through the same signals as a user toggle.
    for name in ('catalog', 'eddn'):
        switch = runner._find('qa-onboarding-' + name)
        evaluate(switch, 'checked = true; toggled()')
    assert runner.controller.edFrameCatalogEnabled and runner.controller.eddnConsent
    assert runner._find('qa-onboarding-usage') is None
    assert runner._find('qa-onboarding-usage-info') is not None
    return True

def change_journal_setting(runner):
    switch = runner._find('qa-onboarding-journal-auto')
    evaluate(switch, 'checked = true; toggled()')
    assert runner.controller.journalAuto
    assert wizard(runner).property('stepIndex') == 1
    return True

def persisted_settings(runner):
    saved = json.loads(runner.controller.config_file.read_text())
    assert saved['theme'] == 'crimson_light' and saved['interface_language'] == 'fr'
    assert saved['journal_auto'] is True
    for key in ('edframe_catalog_enabled', 'edframe_yield_sharing_enabled',
                'edframe_signal_sharing_enabled', 'edframe_station_price_sharing_enabled'):
        assert saved[key] is True
    eddn = json.loads(runner.controller.eddn_config_file.read_text())
    assert eddn['consent'] and eddn['upload_enabled'] and eddn['listener_enabled']
    return True

def open_area(runner, entry):
    assert visual_control(runner, 'qa-onboarding-open-' + entry['id'], True)
    assert runner.controller.onboardingComplete and not wizard(runner).property('visible')
    assert runner.window.property('currentPage') == entry['page'], entry
    return True

def navigation_buttons(runner):
    w = wizard(runner)
    w.setProperty('stepIndex', 4)
    runner._find('qa-onboarding-back').clicked.emit()
    assert w.property('stepIndex') == 3
    runner._find('qa-onboarding-next').clicked.emit()
    assert w.property('stepIndex') == 4
    w.setProperty('stepIndex', 8)
    runner._find('qa-onboarding-next').clicked.emit()
    assert runner.controller.onboardingComplete and not w.property('visible')
    return True

def keyboard_navigation(runner):
    w = wizard(runner)
    w.setProperty('stepIndex', 0)
    evaluate(runner._find('qa-onboarding-next'), 'forceActiveFocus()')
    QTest.keyClick(runner.window, Qt.Key_Space)
    assert w.property('stepIndex') == 1
    QTest.keyClick(runner.window, Qt.Key_Tab)
    assert runner.window.activeFocusItem() is not None
    return True

def no_automatic_wizard(runner):
    assert runner.controller.onboardingComplete, str(runner.controller.config_file)
    assert not wizard(runner).property('visible'), 'Completed profile opened a wizard'
    runner.controller.setTheme('neon_vector')
    assert not wizard(runner).property('visible')
    if mode == 'legacy':
        assert json.loads(runner.controller.config_file.read_text())['onboarding_version'] == 1
    return True

original_init = main.SmokeTestRunner.__init__
def init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    if mode in ('legacy', 'preview'):
        self.steps = [('completed-profile-or-preview', lambda: no_automatic_wizard(self))]
        return
    self.steps = [('auto-open', lambda: bool(wizard(self).property('visible'))),
                  ('tour-contract', lambda: tour_contract(self))]
    themes = list(json.loads(evaluate(self.window, 'JSON.stringify(Object.keys(themeSets))')))
    for theme in themes:
        self.steps.append(('theme-' + theme, lambda t=theme: setup(self, t, 1.15)))
        for page in range(9):
            self.steps.extend([(f'{theme}-show-{page}', lambda p=page: show_page(self, p)),
                               (f'{theme}-page-{page}', lambda p=page: inspect_page(self, p))])
    for language in ('en', 'de', 'es', 'fr'):
        for scale in (1.0, 1.15, 1.5):
            self.steps.append((f'narrow-{language}-{scale}', lambda l=language,s=scale: setup(self, 'crimson_light', s, l, True)))
            for page in range(9):
                self.steps.extend([(f'narrow-{language}-{scale}-show-{page}', lambda p=page: show_page(self, p)),
                                   (f'narrow-{language}-{scale}-page-{page}', lambda p=page: inspect_page(self, p))])
    self.steps.extend([
        ('normal-size', lambda: setup(self, 'navy', 1.0)),
        ('show-first', lambda: show_page(self, 0)),
        ('skip-first', lambda: skip(self, 0)),
        ('reopen', lambda: setup(self, 'navy', 1.0)),
        ('show-journal', lambda: show_page(self, 1)),
        ('change-journal', lambda: change_journal_setting(self)),
        ('show-connections', lambda: show_page(self, 2)),
        ('change-settings', lambda: change_settings(self)),
        ('skip-third', lambda: skip(self, 2)),
        ('retained-settings', lambda: persisted_settings(self)),
        ('reopen-tour', lambda: setup(self, 'navy', 1.0)),
        ('show-tour', lambda: show_page(self, 6)),
        ('skip-tour-escape', lambda: skip(self, 6, True)),
        ('reopen-buttons', lambda: setup(self, 'navy', 1.0)),
        ('keyboard-navigation', lambda: keyboard_navigation(self)),
        ('back-next-finish', lambda: navigation_buttons(self)),
    ])
    pages = json.loads(evaluate(wizard(self), 'JSON.stringify(tourPages)'))
    for page_index, page in enumerate(pages, 4):
        for entry in page['entries']:
            self.steps.extend([
                ('reopen-' + entry['id'], lambda: setup(self, 'navy', 1.0)),
                ('show-' + entry['id'], lambda p=page_index: show_page(self, p)),
                ('open-' + entry['id'], lambda e=entry: open_area(self, e)),
            ])
main.SmokeTestRunner.__init__ = init
def poll(self):
    label, check = self.current
    if os.environ.get('ONBOARDING_TEST_TRACE') == '1':
        print('ONBOARDING_STEP=' + label, flush=True)
    try:
        ready = bool(check())
    except Exception as exc:
        self.results.append(dict(area=label, status='FAIL', error=str(exc)))
        self.step_index += 1
        QTimer.singleShot(750 if label.startswith('open-') else 50, self._next)
        return
    if ready or time.monotonic() >= self.deadline:
        self.results.append(dict(area=label, status='PASS' if ready else 'FAIL',
                                 error='' if ready else 'readiness timeout'))
        self.step_index += 1
        QTimer.singleShot(750 if label.startswith('open-') else 50, self._next)
    else:
        QTimer.singleShot(50, self._poll)
main.SmokeTestRunner._poll = poll
raise SystemExit(main.run())
'''


class OnboardingTests(unittest.TestCase):
    def test_version_policy_preserves_legacy_completed_profiles(self):
        self.assertEqual(onboarding_state({'onboarding_complete': True}), (True, 1))
        self.assertEqual(onboarding_state({}), (False, 1))
        self.assertEqual(onboarding_state({'onboarding_complete': False, 'onboarding_version': 1}), (False, 1))
        self.assertEqual(onboarding_state({'onboarding_complete': True, 'onboarding_version': 1}, current_version=2), (False, 1))
        self.assertEqual(onboarding_state({'onboarding_complete': True}, current_version=2), (False, 1))
        self.assertEqual(onboarding_state({'onboarding_complete': True, 'onboarding_version': 2}, current_version=2), (True, 2))
        self.assertEqual(onboarding_state({}, preview_skip=True), (True, 1))
        for malformed in (None, 'bad', float('inf')):
            self.assertEqual(onboarding_state({'onboarding_complete': True, 'onboarding_version': malformed}), (True, 1))

    def test_all_wizard_translation_keys_exist_in_four_languages(self):
        catalogs = {lang: json.loads((ROOT / 'ed_data/i18n' / f'{lang}.json').read_text(encoding='utf-8-sig'))
                    for lang in ('en', 'de', 'es', 'fr')}
        keys = {key for key in catalogs['en'] if key.startswith('onboarding.')}
        qml = (ROOT / 'qml/components/OnboardingWizard.qml').read_text()
        static_keys = set(re.findall(r'window\.t\("([^"]+)"\s*,', qml))
        keys.update(static_keys)
        for language, catalog in catalogs.items():
            for key in keys:
                self.assertIn(key, catalog, (language, key))
                self.assertTrue(catalog[key].strip(), (language, key))
            self.assertNotIn('stay disabled until', catalog['onboarding.network'])
        navigation = (ROOT / 'Main.qml').read_text(encoding='utf-8-sig').split('property var primaryNavigation:', 1)[1].split('property var navigationOrder:', 1)[0]
        for area in re.findall(r'"id":\s*"([^"]+)"', navigation):
            self.assertIn('onboarding.area.' + area, catalogs['en'])

    def check_smoke(self, mode):
        completed, report = _run_smoke({'ONBOARDING_TEST_MODE': mode, 'PHASE14_SMOKE_ASYNC_PAGES': '0'}, script=SCRIPT)
        self.assertIsNotNone(report, f'exit={completed.returncode}\n' + completed.stdout + completed.stderr)
        failed = [row for row in report['areas'] if row['status'] != 'PASS']
        self.assertEqual(failed, [], json.dumps(failed, ensure_ascii=False))
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_real_wizard_all_themes_scales_tour_skip_and_navigation(self):
        self.check_smoke('wizard')

    def test_completed_profile_does_not_open_wizard(self):
        self.check_smoke('legacy')

    def test_preview_skip_still_suppresses_wizard(self):
        self.check_smoke('preview')

    def test_folder_picker_uses_existing_path_setter(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from PySide6.QtCore import QUrl
        from ed_companion.phase14.controller_ui_settings import UiSettingsMixin
        controller = SimpleNamespace(setJournalPath=Mock())
        folder = str(ROOT / 'Journal folder with spaces')
        UiSettingsMixin.setJournalFolder(controller, QUrl.fromLocalFile(folder))
        controller.setJournalPath.assert_called_once_with(QUrl.fromLocalFile(folder).toLocalFile())
        controller.setJournalPath.reset_mock()
        UiSettingsMixin.setJournalFolder(controller, QUrl('https://example.invalid'))
        controller.setJournalPath.assert_not_called()
