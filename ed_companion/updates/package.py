"""Strict package validation shared by download preparation and the helper."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

MANIFEST = 'ED-Frame-update.json'
MAX_UNPACKED = 2 * 1024 ** 3
MAX_FILES = 8000
PRIVATE_NAMES = {
    'phase14_graphics.json', 'updates.json', 'usage_ping.json', 'journal_path.txt',
    'ship_blueprints.json', 'ship_metadata.json', 'desired_outfitting.json',
    'inara_config.json', 'inara_credentials.dat', 'frontier_credentials.dat',
    'eddn_config.json', 'phase14.log', 'logbook_notes.json', 'session_history.json',
}


class UpdateError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise UpdateError('package')
    parts = PurePosixPath(name).parts
    if name.startswith('/') or not parts or any(
        part in ('.', '..') or part.endswith((' ', '.')) or
        re.search(r'[\x00-\x1f:<>"|?*]', part) or
        re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part, re.I)
        for part in parts
    ) or any(part.casefold().startswith('profile-') or
             part.casefold() in ('ed-frame', 'edengineeringcompanion') for part in parts):
        raise UpdateError('package')
    if parts[-1].casefold() in PRIVATE_NAMES or re.fullmatch(r'Journal.*\.log', parts[-1], re.I):
        raise UpdateError('package')
    return '/'.join(parts)


def file_hash(path, cancel=None):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            if cancel and cancel():
                raise UpdateError('cancelled')
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest(data, version):
    try:
        info = json.loads(data)
        if (info.get('format') != 1 or info.get('app') != 'ED-Frame'
                or info.get('platform') != 'windows' or info.get('version') != version
                or info.get('entry') != 'ED-Frame.exe'):
            raise ValueError()
        files = info['files']
        if not isinstance(files, dict) or not 3 <= len(files) <= MAX_FILES:
            raise ValueError()
        for name, digest in files.items():
            if safe_name(name) != name or not re.fullmatch(r'[a-f0-9]{64}', digest):
                raise ValueError()
        if len({name.casefold() for name in files}) != len(files):
            raise ValueError()
        if 'ED-Frame.exe' not in files or not any(name.startswith('_internal/') for name in files):
            raise ValueError()
        return info
    except (ValueError, TypeError, KeyError, AttributeError):
        raise UpdateError('package') from None


def extract_package(archive, destination, version, cancel=None):
    destination = Path(destination)
    if destination.exists():
        raise UpdateError('package')
    try:
        with zipfile.ZipFile(archive) as zip_file:
            members = zip_file.infolist()
            if len(members) > MAX_FILES * 2 or sum(row.file_size for row in members) > MAX_UNPACKED:
                raise UpdateError('package')
            names = {}
            for member in members:
                name = safe_name(member.filename.rstrip('/'))
                if name.casefold() in names or stat.S_ISLNK(member.external_attr >> 16) or member.flag_bits & 1:
                    raise UpdateError('package')
                names[name.casefold()] = member
            metadata = names.get(MANIFEST.casefold())
            if not metadata or metadata.file_size > 2 * 1024 * 1024:
                raise UpdateError('package')
            info = read_manifest(zip_file.read(metadata), version)
            expected = set(info['files']) | {MANIFEST}
            actual = {member.filename for member in members if not member.is_dir()}
            if expected != actual:
                raise UpdateError('package')
            destination.mkdir(parents=True)
            for member in members:
                if cancel and cancel():
                    raise UpdateError('cancelled')
                if member.is_dir():
                    continue
                target = destination / member.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with zip_file.open(member) as source, target.open('xb') as output:
                    while chunk := source.read(1024 * 1024):
                        if cancel and cancel():
                            raise UpdateError('cancelled')
                        digest.update(chunk)
                        output.write(chunk)
                if member.filename != MANIFEST and digest.hexdigest() != info['files'][member.filename]:
                    raise UpdateError('checksum')
        return info
    except (zipfile.BadZipFile, RuntimeError):
        raise UpdateError('package') from None


def verify_directory(directory, version):
    directory = Path(directory)
    info = read_manifest((directory / MANIFEST).read_bytes(), version)
    actual = set()
    for path in directory.rglob('*'):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise UpdateError('package')
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
    if actual != set(info['files']) | {MANIFEST}:
        raise UpdateError('package')
    for name, digest in info['files'].items():
        if file_hash(directory / name) != digest:
            raise UpdateError('checksum')
    return info


def write_manifest(directory, version):
    directory = Path(directory)
    files = {path.relative_to(directory).as_posix(): file_hash(path)
             for path in sorted(directory.rglob('*')) if path.is_file() and path.name != MANIFEST}
    info = {'format': 1, 'app': 'ED-Frame', 'platform': 'windows',
            'version': version, 'entry': 'ED-Frame.exe', 'files': files}
    read_manifest(json.dumps(info), version)
    (directory / MANIFEST).write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    return info
