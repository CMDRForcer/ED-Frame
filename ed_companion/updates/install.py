"""Recoverable directory swap; profile storage is never an install target."""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

from ed_companion.persistence import atomic_write
from .package import UpdateError, verify_directory


def related(left, right):
    left, right = Path(left).resolve(), Path(right).resolve()
    return left == right or left in right.parents or right in left.parents


def assert_plain_tree(root):
    root = Path(root)
    for path in (root, *root.rglob('*')):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise UpdateError('location')


def tree_bytes(root):
    root = Path(root)
    return sum(path.stat().st_size for path in root.rglob('*') if path.is_file()) if root.exists() else 0


def validate_target(target, data_root, cache):
    target, data_root, cache = map(lambda p: Path(p).resolve(), (target, data_root, cache))
    if (target.parent == target or not (target/'ED-Frame.exe').is_file()
            or related(target, data_root) or related(target, cache)
            or related(target, data_root.parent/'EDEngineeringCompanion')):
        raise UpdateError('location')
    assert_plain_tree(target)
    return target


def write_json(path, payload):
    if not atomic_write(path, json.dumps(payload, indent=2)+'\n'):
        raise UpdateError('save')


def prepare_install(package, target, data_root, version, *, parent_pid=None):
    package, data_root = Path(package).resolve(), Path(data_root).resolve()
    cache = data_root.parent/'ED-Frame-updates'
    target = validate_target(target, data_root, cache)
    job_dir = package.parent
    if job_dir.parent != cache.resolve() or len(job_dir.name) != 32:
        raise UpdateError('location')
    verify_directory(package, version)
    legacy = data_root.parent/'EDEngineeringCompanion'
    required = tree_bytes(package) + tree_bytes(target) + tree_bytes(data_root) + tree_bytes(legacy) + 64 * 1024 * 1024
    if shutil.disk_usage(cache).free < required or shutil.disk_usage(target.parent).free < tree_bytes(package)+64*1024*1024:
        raise UpdateError('space')
    candidate = target.parent/('.edframe-new-'+job_dir.name)
    backup = target.parent/('.edframe-old-'+job_dir.name)
    if candidate.exists() or backup.exists():
        raise UpdateError('location')
    # Candidate and old program folder share a volume, including USB installs.
    shutil.copytree(package, candidate)
    verify_directory(candidate, version)
    helper = job_dir/'helper'
    helper.mkdir()
    shutil.copy2(target/'ED-Frame.exe', helper/'ED-Frame.exe')
    shutil.copytree(target/'_internal', helper/'_internal')
    job = {'format':1, 'id':job_dir.name, 'version':version, 'target':str(target),
           'candidate':str(candidate), 'old':str(backup), 'data_root':str(data_root),
           'parent_pid':int(parent_pid or os.getpid()), 'token':secrets.token_hex(32)}
    write_json(job_dir/'job.json', job)
    return job_dir/'job.json'


def load_job(path):
    path = Path(path).resolve()
    job = json.loads(path.read_text(encoding='utf-8'))
    data_root = Path(job['data_root']).resolve()
    cache = data_root.parent/'ED-Frame-updates'
    if (job.get('format') != 1 or data_root.name != 'ED-Frame' or path.name != 'job.json' or path.parent.parent != cache.resolve()
            or job.get('id') != path.parent.name or len(job['id']) != 32
            or not all(c in '0123456789abcdef' for c in job['id'])
            or not isinstance(job['token'],str) or len(job['token']) != 64):
        raise UpdateError('location')
    target = Path(job['target']).resolve()
    if (related(target,data_root) or related(target,cache) or target.parent == target
            or related(target,data_root.parent/'EDEngineeringCompanion')):
        raise UpdateError('location')
    if (Path(job['candidate']).resolve() != target.parent/('.edframe-new-'+job['id'])
            or Path(job['old']).resolve() != target.parent/('.edframe-old-'+job['id'])):
        raise UpdateError('location')
    job['directory'] = str(path.parent)
    return job


class InstallTransaction:
    def __init__(self, job_path):
        self.job_path = Path(job_path)
        self.job = load_job(job_path)
        self.target = Path(self.job['target'])
        self.candidate = Path(self.job['candidate'])
        self.old = Path(self.job['old'])
        self.directory = Path(self.job['directory'])
        self.data = Path(self.job['data_root'])

    def phase(self, value):
        write_json(self.directory/'transaction.json', {'phase':value})

    def backup_data(self):
        snapshot = self.directory/'userdata'
        snapshot.mkdir(exist_ok=True)
        roots = (self.data, self.data.parent/'EDEngineeringCompanion')
        needed = sum(tree_bytes(root) for root in roots) + 64 * 1024 * 1024
        if shutil.disk_usage(self.directory).free < needed:
            raise UpdateError('space')
        for root in roots:
            if root.exists():
                assert_plain_tree(root)
                destination = snapshot/root.name
                if destination.exists():
                    raise UpdateError('location')
                shutil.copytree(root,destination)
        self.phase('backed_up')

    def swap(self):
        validate_target(self.target,self.data,self.directory.parent)
        verify_directory(self.candidate,self.job['version'])
        if self.old.exists():
            raise UpdateError('location')
        self.phase('moving_old')
        self.target.rename(self.old)
        self.phase('moving_new')
        self.candidate.rename(self.target)
        self.phase('starting')

    def rollback(self):
        # Preserve failed new files and profile writes too, never delete them.
        if self.old.exists():
            if self.target.exists():
                failed = self.target.parent/('.edframe-failed-'+self.job['id'])
                if failed.exists():
                    raise UpdateError('location')
                self.target.rename(failed)
            self.old.rename(self.target)
            snapshot = self.directory/'userdata'
            for name in ('ED-Frame','EDEngineeringCompanion'):
                saved = snapshot/name
                live = self.data.parent/name
                if saved.exists():
                    restore = self.directory/('restore-'+name)
                    shutil.copytree(saved,restore)
                    if live.exists():
                        live.rename(self.directory/('failed-userdata-'+name))
                    restore.rename(live)
        self.phase('rolled_back')

    def execute(self, launch_and_check):
        try:
            self.backup_data()
            self.swap()
            if not launch_and_check(self.job):
                raise UpdateError('startup')
            self.phase('complete')
            write_json(self.directory/'result.json', {'status':'complete','version':self.job['version'],
                'old':str(self.old),'userdata':str(self.directory/'userdata')})
            return True
        except Exception as error:
            try:
                self.rollback()
                write_json(self.directory/'result.json', {'status':'rolled_back',
                    'code':getattr(error,'code','install'),'version':self.job['version']})
            except Exception:
                write_json(self.directory/'result.json', {'status':'recovery_required','code':'install',
                    'old':str(self.old),'userdata':str(self.directory/'userdata')})
                raise
            return False


def launch_helper(job_path):
    job_path = Path(job_path).resolve()
    job = load_job(job_path)
    helper = job_path.parent/'helper/ED-Frame.exe'
    # Only the copied runtime runs the helper; neither running directory moves.
    subprocess.Popen([str(helper),'--edframe-update-helper',str(job_path)],cwd=helper.parent,
        creationflags=(subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                       | subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else 0)


def report_startup_ready(version):
    """A new GUI acknowledges this exact transaction, never arbitrary env paths."""
    value = os.environ.pop('EDFRAME_UPDATE_READY_FILE','')
    token = os.environ.pop('EDFRAME_UPDATE_READY_TOKEN','')
    if not value or not token:
        return
    ready = Path(value).resolve()
    job = load_job(ready.parent/'job.json')
    if (ready.name != 'ready.json' or not secrets.compare_digest(job['token'],token)
            or job['version'] != version or Path(sys.executable).resolve().parent != Path(job['target']).resolve()):
        raise UpdateError('startup')
    write_json(ready, {'token':token,'version':version,'pid':os.getpid(),'status':'ready'})
