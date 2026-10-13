"""Drive the real update UI, offline, using the existing smoke infrastructure."""
import json
import unittest

from tests.test_onboarding import SCRIPT as ONBOARDING_SCRIPT
from tests.test_qml_smoke_load import _run_smoke

SCRIPT = ONBOARDING_SCRIPT[:ONBOARDING_SCRIPT.index('original_init =')] + r'''
from ed_companion.updates.package import UpdateError

def ready(self):
    wizard(self).finish()
    self.controller.updateTimer.stop()
    self.controller._updates.release = dict(version='1.0.11', notes='Example release notes',
        page='https://github.com/CMDRForcer/ED-Frame/releases/tag/1.0.11')
    self.controller._update_status = 'available'
    self.controller.updateChanged.emit()
    self._find('qa-update-notice-open').clicked.emit()
    return True

def narrow(self):
    self.window.setWidth(1120)
    self.window.setHeight(700)
    return True

def layout(self, theme, language, scale):
    self.controller.setTheme(theme)
    self.controller.setInterfaceLanguage(language)
    self.controller.setUiScale(scale)
    dialog=self._find('qa-dialog-about')
    assert dialog.property('visible')
    bounds=json.loads(evaluate(dialog, 'JSON.stringify((function(){var p=background.mapToItem(null,0,0);return [p.x,p.y,background.width*scale,background.height*scale]})())'))
    assert bounds[0]>=-2 and bounds[1]>=-2, bounds
    assert bounds[0]+bounds[2]<=self.window.width()+2, bounds
    assert bounds[1]+bounds[3]<=self.window.height()+2, bounds
    assert self._find('qa-update-status').property('text')
    assert self._find('qa-update-check').property('enabled')
    icon=self._find('qa-update-notice-open')
    assert icon.width() <= icon.parentItem().width()+1, 'Compact notice overflows sidebar'
    assert not self._find('qa-update-auto-download').property('enabled'), 'Source builds cannot auto-install'
    return True

def settings(self):
    box=self._find('qa-update-auto-check')
    box.setProperty('checked',False);box.toggled.emit()
    assert not self.controller.updateInfo['enabled']
    assert not json.loads(self.controller._updates.path.read_text())['enabled']
    assert self.controller._updates.path.parent==local
    return True

def check(self):
    self.controller._updates.check = lambda **kwargs: None
    self._find('qa-update-check').clicked.emit()
    return True

def checked(self):
    return self.controller.updateInfo['status']=='current'

def error(self):
    def fail(**kwargs):raise UpdateError('network')
    self.controller._updates.check=fail
    self._find('qa-update-check').clicked.emit()
    return True

def failed(self):
    return self.controller.updateInfo['status']=='error' and self.controller.updateInfo['error']=='network'

def download(self):
    self.controller._updates.release=dict(version='1.0.11',notes='Notes')
    self.controller._update_status='available'
    self.controller._updates.download=lambda **kwargs: local/'prepared-fixture'
    self.controller.updateChanged.emit()
    self._find('qa-update-download').clicked.emit()
    return True

def downloaded(self):
    if self.controller.updateInfo['status']!='ready':return False
    assert self._find('qa-update-install').property('visible')
    assert not self._find('qa-update-install').property('enabled')
    assert self.controller._pending_update_job is None
    self._find('qa-dialog-about').close()
    self._find('qa-update-notice-later').clicked.emit()
    assert self.controller.updateInfo['dismissed']
    self.controller._update_package=None
    return True

original_init=main.SmokeTestRunner.__init__
def init(self,*args,**kwargs):
    original_init(self,*args,**kwargs)
    self.steps=[('ready',lambda:ready(self)),('narrow-window',lambda:narrow(self))]
    themes=('arctic_alloy','navy','neon_vector','orbital_dawn','crimson_dark','crimson_light')
    for theme in themes:
        for language in ('en','de','es','fr'):
            for scale in (1.0,1.15,1.5):
                self.steps.append((f'{theme}-{language}-{scale}',lambda t=theme,l=language,s=scale:layout(self,t,l,s)))
    self.steps += [('settings',lambda:settings(self)),('check',lambda:check(self)),
        ('checked',lambda:checked(self)),('error',lambda:error(self)),('failed',lambda:failed(self)),
        ('download',lambda:download(self)),('downloaded',lambda:downloaded(self))]
main.SmokeTestRunner.__init__=init
def poll(self):
    label,check=self.current
    try:passed=bool(check());error=''
    except Exception as exc:passed=False;error=str(exc)
    if passed or error or time.monotonic()>=self.deadline:
        self.results.append(dict(area=label,status='PASS' if passed else 'FAIL',error=error))
        self.step_index+=1
        QTimer.singleShot(100,self._next)
    else:QTimer.singleShot(50,self._poll)
main.SmokeTestRunner._poll=poll
raise SystemExit(main.run())
'''


class UpdateQmlTests(unittest.TestCase):
    def test_update_ui_and_background_results_in_all_themes_languages_and_scales(self):
        completed,report=_run_smoke(script=SCRIPT,extra_env={
            'EDFRAME_NO_UPDATES':'1','EDFRAME_NO_USAGE_PING':'1','PHASE14_SMOKE_ASYNC_PAGES':'0'})
        self.assertIsNotNone(report,completed.stdout+completed.stderr)
        failed=[row for row in report['areas'] if row['status']!='PASS']
        self.assertEqual(failed,[],json.dumps(failed,ensure_ascii=False))
        self.assertEqual(completed.returncode,0)
