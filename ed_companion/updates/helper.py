"""Early frozen entry point: wait for exit, swap, verify startup, recover."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

from .install import InstallTransaction, write_json
from .package import UpdateError


def wait_for_parent(pid, timeout=90):
    if os.name != 'nt':
        raise UpdateError('platform')
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x00100000,False,pid)
    if not handle:
        if ctypes.get_last_error()==87:
            return
        raise UpdateError('busy')
    try:
        if kernel.WaitForSingleObject(handle,int(timeout*1000)) != 0:
            raise UpdateError('busy')
    finally:
        kernel.CloseHandle(handle)


def launch_and_check(job):
    ready = Path(job['directory'])/'ready.json'
    if ready.exists():
        raise UpdateError('startup')
    env={**os.environ,'EDFRAME_UPDATE_READY_FILE':str(ready),'EDFRAME_UPDATE_READY_TOKEN':job['token']}
    # Give the newly launched app its normal UI and stable installation path.
    process=subprocess.Popen([str(Path(job['target'])/'ED-Frame.exe')],cwd=job['target'],env=env)
    deadline=time.monotonic()+90
    succeeded=False
    try:
        while time.monotonic()<deadline:
            if process.poll() is not None:
                return False
            if ready.exists():
                payload=json.loads(ready.read_text(encoding='utf-8'))
                if (payload.get('pid')==process.pid and payload.get('version')==job['version']
                        and payload.get('status')=='ready' and secrets.compare_digest(payload.get('token',''),job['token'])):
                    succeeded=True
                    return True
            time.sleep(.2)
        return False
    finally:
        # Stop only this failed child, even for a malformed ready receipt.
        if not succeeded and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)



def run_helper(job_path):
    transaction=InstallTransaction(job_path)
    try:
        wait_for_parent(transaction.job['parent_pid'])
        # Hold the existing single-instance socket while backing up/swapping.
        # A second normal app cannot enter and modify profiles during the swap.
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtNetwork import QLocalServer, QLocalSocket
        app=QCoreApplication([])
        name=os.environ.get('ED_FRAME_SINGLE_INSTANCE_NAME','ED-Frame-single-instance')
        probe=QLocalSocket()
        probe.connectToServer(name)
        if probe.waitForConnected(300):
            raise UpdateError('busy')
        probe.abort()
        QLocalServer.removeServer(name)
        gate=QLocalServer()
        if not gate.listen(name):raise UpdateError('busy')
        def launch(job):
            gate.close()
            QLocalServer.removeServer(name)
            return launch_and_check(job)
        succeeded=transaction.execute(launch)
        gate.close()
        if not succeeded and (transaction.target/'ED-Frame.exe').exists():
            subprocess.Popen([str(transaction.target/'ED-Frame.exe')],cwd=transaction.target)
        return 0 if succeeded else 1
    except Exception as error:
        write_json(transaction.directory/'result.json',{'status':'failed','code':getattr(error,'code','install')})
        return 2
