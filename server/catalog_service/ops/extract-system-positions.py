"""Extract exact public system names from a gzip JSON-lines Spansh dump.

No database writes. No complete dump is saved. Output is a small JSON snapshot.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import requests


def extract_lines(lines, names):
    requested = {name.strip().casefold(): name for name in names}
    found, conflicts = {}, set()
    for line in lines:
        text = line.decode('utf-8').strip() if isinstance(line, bytes) else line.strip()
        if text in {'', '[', ']'}:
            continue
        row = json.loads(text.rstrip(','))
        key = str(row.get('name') or '').strip().casefold()
        if key not in requested:
            continue
        coords = row.get('coords') or {}
        address = row.get('id64')
        if not (type(address) is int and address > 0 and all(
            type(coords.get(k)) in (int, float) and math.isfinite(coords[k])
            for k in ('x', 'y', 'z')
        )):
            continue
        value = {'name': row['name'], 'id64': address,
                 'coords': {k: coords[k] for k in ('x', 'y', 'z')},
                 'updateTime': row.get('updateTime')}
        if key in found and (found[key]['coords'] != value['coords']
                             or found[key]['id64'] != value['id64']):
            conflicts.add(key)
        found[key] = value
    return [{'system': name, 'resolved': key in found and key not in conflicts,
             'data': found.get(key) if key not in conflicts else None,
             'status': 'CONFLICT' if key in conflicts else 'FOUND' if key in found else 'NOT_IN_DUMP'}
            for key, name in requested.items()]


class HashedReader:
    def __init__(self, raw, maximum):
        self.raw, self.maximum, self.count = raw, maximum, 0
        self.digest = hashlib.sha256()

    def read(self, size=-1):
        data = self.raw.read(size)
        self.count += len(data)
        if self.count > self.maximum:
            raise ValueError('Dump exceeds allowed compressed-byte budget')
        self.digest.update(data)
        return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--targets', required=True)
    parser.add_argument('--url', default='https://downloads.spansh.co.uk/systems_1month.json.gz')
    parser.add_argument('--max-bytes', type=int, default=200_000_000)
    args = parser.parse_args()
    if not args.url.startswith('https://downloads.spansh.co.uk/'):
        raise ValueError('Only the public Spansh download host is supported')
    names = [row['system'] for row in json.loads(Path(args.targets).read_text(encoding='utf-8'))['results']]
    with requests.get(args.url, stream=True, timeout=(15, 60)) as response:
        response.raise_for_status()
        if int(response.headers.get('Content-Length', 0)) > args.max_bytes:
            raise ValueError('Dump exceeds byte budget before download')
        response.raw.decode_content = False
        reader = HashedReader(response.raw, args.max_bytes)
        with gzip.GzipFile(fileobj=reader) as stream:
            results = extract_lines(stream, names)
        # Successful full gzip traversal validates its footer/CRC.
        snapshot = {'sourceUrl': args.url,
                    'retrievedAt': datetime.now(timezone.utc).isoformat(),
                    'dumpLastModified': response.headers.get('Last-Modified'),
                    'dumpETag': response.headers.get('ETag'),
                    'compressedBytesRead': reader.count,
                    'dumpSha256': reader.digest.hexdigest(),
                    'scope': 'System coordinates only; no ring or overlap verification',
                    'results': results}
    print(json.dumps(snapshot, ensure_ascii=True))


if __name__ == '__main__':
    main()
