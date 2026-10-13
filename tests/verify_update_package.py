"""Real Windows helper/startup tests in disposable workspace folders only."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

from ed_companion import APP_VERSION
from ed_companion.updates.install import prepare_install
from ed_companion.updates.package import write_manifest, verify_directory

ROOT=Path(__file__).resolve().parents[1]
WORK=(ROOT/'.test-tmp/update-native').resolve()
WORK.mkdir(parents=True,exist_ok=True)
PACKAGE=(ROOT/'dist/ED-Frame').resolve()
verify_directory(PACKAGE,APP_VERSION)
assert WORK.is_relative_to(ROOT) and PACKAGE.is_relative_to(ROOT)
assert not (PACKAGE/'_internal/icuuc.dll').exists()
assert not (PACKAGE/'_internal/icudt78.dll').exists()
results=[]
for mode in ('success','failed-start'):
    case=WORK/(mode+'-'+uuid4().hex[:8]);case.mkdir()
    target=case/'program/ED-Frame'
    shutil.copytree(PACKAGE,target)
    local=case/'local'
    data=local/'ED-Frame';data.mkdir(parents=True)
    originals={}
    for label in ('alpha','beta'):
        profile=data/('profile-'+label);profile.mkdir()
        for name,payload in (('ship_blueprints.json',json.dumps([{'id':label,'slot':'PowerPlant','goal':'G5'}]).encode()),
                ('phase14_graphics.json',b'{"theme":"navy","onboarding_complete":true}'),
                ('inara_credentials.dat',b'private encrypted fixture')):
            (profile/name).write_bytes(payload)
            originals[f'profile-{label}/{name}']=payload
    install_id=str(uuid4())
    (data/'usage_ping.json').write_text(json.dumps({'install_id':install_id}),encoding='utf-8')
    journal=case/'journal';journal.mkdir()
    shutil.copy2(ROOT/'tests/fixtures/smoke_journal.ndjson',journal/'Journal.2026-08-23T170000.01.log')
    settings={'renderer_mode':'software','onboarding_complete':True,'onboarding_version':1,
        'edframe_catalog_enabled':False,'journal_auto':False,'background_mode':False}
    from unittest.mock import patch
    from ed_companion.phase14.state import resolve_profile_context, runtime_data_dir
    with patch.dict(os.environ, {'LOCALAPPDATA':str(local),
            'ED_FRAME_JOURNAL_DIR':str(journal),'ED_FRAME_PROFILE_FID':'F0000000'}):
        actual_profile=runtime_data_dir(resolve_profile_context())
    for destination in (data,actual_profile):
        destination.mkdir(exist_ok=True)
        (destination/'phase14_graphics.json').write_text(json.dumps(settings),encoding='utf-8')
        (destination/'eddn_config.json').write_text('{"consent":false,"upload_enabled":false,"listener_enabled":false}')
    job_dir=local/'ED-Frame-updates'/uuid4().hex
    shutil.copytree(PACKAGE,job_dir/'package')
    if mode=='failed-start':
        (job_dir/'package/ED-Frame.exe').write_bytes(b'Invalid Windows executable fixture')
        write_manifest(job_dir/'package',APP_VERSION)
    locker=r'''
import ctypes,sys
from ctypes import wintypes
api=ctypes.WinDLL('kernel32',use_last_error=True)
api.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
api.CreateFileW.restype=wintypes.HANDLE
handle=api.CreateFileW(sys.argv[1],0x80000000,1,None,3,0,None)
assert handle not in (None,ctypes.c_void_p(-1).value)
print('LOCKED',flush=True)
sys.stdin.read(1)
api.CloseHandle.argtypes=[wintypes.HANDLE]
api.CloseHandle(handle)
'''
    parent=subprocess.Popen([sys.executable,'-c',locker,str(target/'ED-Frame.exe')],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    assert parent.stdout.readline().strip()=='LOCKED'
    job=prepare_install(job_dir/'package',target,data,APP_VERSION,parent_pid=parent.pid)
    env={**os.environ,'LOCALAPPDATA':str(local),'ED_FRAME_JOURNAL_DIR':str(journal),
        'ED_FRAME_PROFILE_FID':'F0000000','ED_FRAME_SINGLE_INSTANCE_NAME':'ED-Frame-update-native-'+case.name,
        'EDFRAME_NO_USAGE_PING':'1','EDFRAME_NO_UPDATES':'1','PHASE14_SMOKE_TEST':'1',
        'PHASE14_PREVIEW_SKIP_ONBOARDING':'1','QT_QPA_PLATFORM':'offscreen',
        'PHASE14_SMOKE_REPORT_PATH':str(case/'app-smoke.json')}
    helper=subprocess.Popen([str(job_dir/'helper/ED-Frame.exe'),'--edframe-update-helper',str(job)],
        cwd=job_dir/'helper',env=env,creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(2)
    assert not (job_dir/'transaction.json').exists(),'Helper swapped while parent was running'
    parent.stdin.write('x');parent.stdin.flush()
    parent.wait(timeout=10)
    code=helper.wait(timeout=150)
    receipt=json.loads((job_dir/'result.json').read_text(encoding='utf-8'))
    assert receipt['status']==('complete' if mode=='success' else 'rolled_back'),receipt
    assert code==(0 if mode=='success' else 1),code
    for name,payload in originals.items():
        assert (data/name).read_bytes()==payload, 'Profile changed: '+name
        assert (job_dir/'userdata/ED-Frame'/name).read_bytes()==payload
    assert json.loads((data/'usage_ping.json').read_text())['install_id']==install_id
    deadline=time.monotonic()+90
    while not (case/'app-smoke.json').exists():
        assert time.monotonic()<deadline,'Restarted app did not complete smoke'
        time.sleep(.5)
    smoke=json.loads((case/'app-smoke.json').read_text(encoding='utf-8'))
    assert smoke['status']=='PASS',smoke
    results.append({'case':mode,'helperExit':code,'receipt':receipt['status'],
        'profilesAndCredentialsPreserved':True,'installIdPreserved':True,
        'parentExitWaitVerified':True,'appSmoke':smoke['status'],'areas':len(smoke['areas'])})
    print(json.dumps(results[-1]),flush=True)
(ROOT/'outputs').mkdir(exist_ok=True)
(ROOT/'outputs/update-native-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
