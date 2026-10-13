"""One daily release check and cancellable, bounded background downloads."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
from urllib.parse import urlparse, urljoin
from uuid import uuid4

import requests

from ed_companion import APP_VERSION, is_development_build
from ed_companion.persistence import atomic_write, load_json_file
from .package import UpdateError, extract_package, file_hash, MAX_UNPACKED

API = 'https://api.github.com/repos/CMDRForcer/ED-Frame/releases/latest'
RELEASES = 'https://github.com/CMDRForcer/ED-Frame/releases/'
MAX_ARCHIVE = 512 * 1024 * 1024
REDIRECT_HOSTS = {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}


def version_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,4}', value):
        raise UpdateError('release')
    parts = tuple(map(int, value.split('.')))
    legacy = parts[:2] == (1, 5) and parts[2] <= 43
    return (0 if legacy else 1, *parts)


def release_info(payload):
    try:
        tag = payload['tag_name']
        version_key(tag)
        if payload.get('draft') or payload.get('prerelease'):
            raise ValueError()
        name = f'ED-Frame-{tag}-Windows.zip'
        assets = [asset for asset in payload['assets'] if asset['name'] == name]
        if len(assets) != 1:
            raise ValueError()
        asset = assets[0]
        url = asset['browser_download_url']
        if url != RELEASES + f'download/{tag}/{name}' or asset.get('state') != 'uploaded':
            raise ValueError()
        size = int(asset['size'])
        digest = asset.get('digest', '')
        if not 0 < size <= MAX_ARCHIVE or not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
            raise ValueError()
        return {'version': tag, 'url': url, 'size': size, 'sha256': digest[7:],
                'page': RELEASES + 'tag/' + tag, 'notes': str(payload.get('body', ''))[:12000]}
    except (KeyError, ValueError, TypeError, AttributeError):
        raise UpdateError('release') from None


class UpdateClient:
    def __init__(self, data_root, *, version=APP_VERSION):
        self.path = Path(data_root) / 'updates.json'
        self.cache = Path(data_root).parent / 'ED-Frame-updates'
        self.version = version
        self.lock = threading.RLock()
        saved = load_json_file(self.path, {})
        self.state = saved if isinstance(saved, dict) else {}
        self.release = None
        try:
            info = self.state.get('release')
            if info:
                self.release = release_info({'tag_name': info['version'], 'body': info['notes'],
                    'assets': [{'name': f"ED-Frame-{info['version']}-Windows.zip", 'state': 'uploaded',
                    'browser_download_url': info['url'], 'size': info['size'], 'digest': 'sha256:'+info['sha256']}]})
                if version_key(self.release['version']) <= version_key(version):
                    self.release = None
        except (UpdateError, KeyError, TypeError):
            self.state.pop('release', None)

    @property
    def enabled(self):
        return bool(self.state.get('enabled', True))

    @property
    def auto_download(self):
        return bool(self.state.get('auto_download', False))

    def save(self):
        with self.lock:
            if not atomic_write(self.path, json.dumps(self.state, indent=2) + '\n'):
                raise UpdateError('save')

    def setting(self, key, value):
        with self.lock:
            previous = dict(self.state)
            self.state[key] = bool(value)
            try:
                self.save()
            except UpdateError:
                self.state = previous
                raise

    def automatic_allowed(self):
        return (self.enabled and not is_development_build()
                and os.environ.get('EDFRAME_NO_UPDATES') != '1'
                and os.environ.get('PHASE14_SMOKE_TEST') != '1')

    def due(self):
        day = datetime.now(timezone.utc).date().isoformat()
        return self.automatic_allowed() and self.state.get('last_attempt_day', '') < day

    def check(self, *, manual=False, get=None):
        if os.environ.get('EDFRAME_NO_UPDATES') == '1':
            raise UpdateError('disabled')
        if not manual and not self.due():
            return self.release
        with self.lock:
            self.state['last_attempt_day'] = datetime.now(timezone.utc).date().isoformat()
            self.save()
        try:
            with (get or requests.get)(API, headers={'User-Agent': f'ED-Frame/{self.version}',
                    'Accept': 'application/vnd.github+json'}, timeout=5, stream=True,
                    allow_redirects=False) as response:
                if response.status_code != 200:
                    raise UpdateError('network')
                raw = bytearray()
                for chunk in response.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw) > 1024 * 1024:
                        raise UpdateError('release')
                info = release_info(json.loads(raw))
            with self.lock:
                self.release = info if version_key(info['version']) > version_key(self.version) else None
                self.state['release'] = self.release
                self.state['last_success'] = datetime.now(timezone.utc).isoformat()
                self.save()
            return self.release
        except (requests.RequestException, ValueError):
            raise UpdateError('network') from None

    def dismiss(self):
        with self.lock:
            self.state['dismissed'] = self.release['version'] if self.release else ''
            self.save()

    def download(self, *, cancel=lambda: False, progress=lambda value: None, get=None):
        if not self.release:
            raise UpdateError('release')
        info = dict(self.release)
        self.cache.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.cache).free < info['size'] + MAX_UNPACKED + 64 * 1024 * 1024:
            raise UpdateError('space')
        folder = self.cache / uuid4().hex
        folder.mkdir()
        archive = folder / 'package.zip'
        url = info['url']
        start = time.monotonic()
        response = None
        succeeded = False
        try:
            for _ in range(6):
                parsed = urlparse(url)
                if (parsed.scheme != 'https' or parsed.hostname not in REDIRECT_HOSTS
                        or parsed.username or parsed.password or parsed.port not in (None, 443)):
                    raise UpdateError('release')
                response = (get or requests.get)(url, headers={'User-Agent': f'ED-Frame/{self.version}'},
                    stream=True, timeout=(5, 15), allow_redirects=False)
                if response.status_code not in (301, 302, 303, 307, 308):
                    break
                location = response.headers.get('Location', '')
                response.close()
                url = urljoin(url, location)
            if response is None or response.status_code != 200:
                raise UpdateError('network')
            received = 0
            with archive.open('xb') as output:
                for chunk in response.iter_content(256 * 1024):
                    if cancel():
                        raise UpdateError('cancelled')
                    if time.monotonic() - start > 15 * 60:
                        raise UpdateError('network')
                    received += len(chunk)
                    if received > info['size']:
                        raise UpdateError('checksum')
                    output.write(chunk)
                    progress(min(.85, received / info['size'] * .85))
            if received != info['size'] or file_hash(archive, cancel) != info['sha256']:
                raise UpdateError('checksum')
            progress(.9)
            extract_package(archive, folder/'package', info['version'], cancel)
            progress(1.0)
            succeeded = True
            return folder/'package'
        except requests.RequestException:
            raise UpdateError('network') from None
        finally:
            if response is not None:
                response.close()
            if not succeeded and folder.resolve().parent == self.cache.resolve():
                # Only this freshly created, incomplete download; no profiles,
                # installed apps or previous-version backups exist here.
                shutil.rmtree(folder)
