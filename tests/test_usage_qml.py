"""Exercise the real usage information and About installation ID offline."""
import json
import unittest

from tests.test_onboarding import SCRIPT as ONBOARDING_SCRIPT
from tests.test_qml_smoke_load import _run_smoke

SCRIPT = ONBOARDING_SCRIPT[:ONBOARDING_SCRIPT.index('original_init =')] + r'''
from PySide6.QtGui import QGuiApplication

def ready(self):
    wizard(self).finish()
    return True

def settings_about(self):
    self._find('qa-settings-about').clicked.emit()
    assert self._find('qa-dialog-about').property('visible')
    return True

def identifier(self):
    from uuid import UUID
    identity = self.controller.usageInstallId
    if not identity:
        return False
    assert UUID(identity).version == 4
    assert self._find('qa-usage-install-id').property('text') == identity
    self._find('qa-usage-copy-id').clicked.emit()
    assert QGuiApplication.clipboard().text() == identity
    saved = json.loads(self.controller._usage_ping.path.read_text())
    assert saved['install_id'] == identity
    assert 'last_attempt_day' not in saved, 'About must never send a ping'
    assert self.controller._usage_ping.path.parent == local
    self._find('qa-dialog-about').close()
    return True

def connections(self):
    if not self._page(6, 'qa-page-connections'):
        return False
    self._find('qa-page-connections').setProperty('connectionMode', 3)
    return True

def information(self):
    assert self._find('qa-usage-counting-setting') is None
    assert self._find('qa-usage-counting-info') is not None
    return True

def reopen(self):
    self.controller.reopenOnboarding()
    wizard(self).setProperty('stepIndex', 2)
    return True

def onboarding_binding(self):
    control = self._find('qa-onboarding-usage-info')
    if control is None:
        return False
    assert self._find('qa-onboarding-usage') is None
    assert self.controller.usageInstallId
    wizard(self).finish()
    return True

original_init = main.SmokeTestRunner.__init__
def init(self,*args,**kwargs):
    original_init(self,*args,**kwargs)
    self.steps=[('ready',lambda:ready(self)),
                ('settings',lambda:self._page(5,'qa-page-settings')),
                ('settings-about',lambda:settings_about(self)),
                ('about-id-copy',lambda:identifier(self)),
                ('connections',lambda:connections(self)),
                ('connections-information',lambda:information(self)),
                ('reopen-onboarding',lambda:reopen(self)),
                ('onboarding-binding',lambda:onboarding_binding(self))]
main.SmokeTestRunner.__init__=init
raise SystemExit(main.run())
'''


class UsageQmlTests(unittest.TestCase):
    def test_settings_onboarding_explain_automatic_counting_and_about_has_id(self):
        completed, report = _run_smoke(script=SCRIPT, extra_env={'EDFRAME_NO_USAGE_PING':'1'})
        self.assertIsNotNone(report, completed.stdout + completed.stderr)
        failed = [row for row in report['areas'] if row['status'] != 'PASS']
        self.assertEqual(failed, [], json.dumps(failed, ensure_ascii=False))
        self.assertEqual(completed.returncode, 0)
