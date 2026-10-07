"""Stream public populated-system rings into a validated snapshot, then add missing rings.

Extract and apply are separate: no live writes until the full gzip CRC and hashes pass.
Existing mining-site rows and prospector ownership are never overwritten.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
from ed_companion.navigation.mining_commodities import mining_commodity_id

SOURCE = 'https://downloads.spansh.co.uk/galaxy_populated.json.gz'


def project_rings(system):
    name, address, coords = system.get('name'), system.get('id64'), system.get('coords') or {}
    if not name or type(address) is not int or address <= 0:
        return []
    if not all(type(coords.get(k)) in (int, float) and math.isfinite(coords[k]) for k in ('x', 'y', 'z')):
        return []
    result = []
    for body in system.get('bodies') or []:
        observed = body.get('updateTime')
        try:
            parsed = datetime.fromisoformat(str(observed).replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                continue
        except ValueError:
            continue
        for ring in body.get('rings') or []:
            ring_name = ring.get('name') or ''
            if not ring_name.casefold().startswith(name.casefold() + ' ') or ring.get('type') not in ('Metallic', 'Metal Rich', 'Rocky', 'Icy'):
                continue
            signal_data = ring.get('signals') or {}
            signal_time = signal_data.get('updateTime')
            try:
                signal_date = datetime.fromisoformat(str(signal_time).replace('Z', '+00:00'))
                if signal_date.tzinfo is None:
                    signal_date = None
            except ValueError:
                signal_date = None
            hotspots = []
            for commodity, count in (signal_data.get('signals') or {}).items():
                if signal_date is not None and type(count) is int and count > 0:
                    hotspots.append({'commodity': mining_commodity_id(commodity), 'count': count,
                                     'observedAt': signal_data.get('updateTime')})
            result.append({'systemAddress': address, 'system': name, **coords,
                           'ring': ring_name, 'body': body.get('name'),
                           'ringType': ring['type'], 'reserveLevel': body.get('reserveLevel'),
                           'distanceToArrivalLs': body.get('distanceToArrival'),
                           'ringMetadataObservedAt': observed,
                           'observedAt': min(parsed, signal_date).isoformat() if hotspots else observed,
                           'hotspots': hotspots,
                           'source': 'Spansh populated-system bulk dump',
                           'sourceUrl': SOURCE, 'evidence': 'CATALOG_CANDIDATE'})
    return result


class HashedReader:
    def __init__(self, raw):
        self.raw, self.count, self.digest = raw, 0, hashlib.sha256()

    def read(self, size=-1):
        data = self.raw.read(size)
        self.count += len(data)
        if self.count > 6_000_000_000:
            raise ValueError('Compressed download exceeds 6 GB budget')
        self.digest.update(data)
        return data


def extract(path):
    import requests
    systems = rings = 0
    digest = hashlib.sha256()
    with path.open('xb') as output, requests.get(SOURCE, stream=True, timeout=(15, 90)) as response:
        response.raise_for_status()
        if int(response.headers.get('Content-Length', 0)) > 6_000_000_000:
            raise ValueError('Dump exceeds budget')
        response.raw.decode_content = False
        reader = HashedReader(response.raw)
        with gzip.GzipFile(fileobj=reader) as stream:
            for line in stream:
                line = line.strip()
                if line in (b'[', b']', b''):
                    continue
                system = json.loads(line.rstrip(b','))
                systems += 1
                for row in project_rings(system):
                    payload = (json.dumps(row, ensure_ascii=True) + '\n').encode()
                    output.write(payload)
                    digest.update(payload)
                    rings += 1
                if systems % 5000 == 0:
                    print(json.dumps({'systems': systems, 'rings': rings, 'bytes': reader.count}), flush=True)
    manifest = {'sourceUrl': SOURCE, 'retrievedAt': datetime.now(timezone.utc).isoformat(),
                'sourceLastModified': response.headers.get('Last-Modified'),
                'sourceETag': response.headers.get('ETag'),
                'compressedBytes': reader.count, 'dumpSha256': reader.digest.hexdigest(),
                'snapshotSha256': digest.hexdigest(), 'systems': systems, 'rings': rings,
                'scope': 'Populated systems only; hotspot counts do not prove overlaps'}
    with path.with_suffix('.manifest.json').open('x', encoding='utf-8') as output:
        json.dump(manifest, output, indent=2)
    print(json.dumps(manifest), flush=True)


def normalize_snapshot_row(row):
    row = dict(row)
    metadata_time = row.get('ringMetadataObservedAt') or row['observedAt']
    dates = [datetime.fromisoformat(metadata_time.replace('Z', '+00:00'))]
    hotspots = []
    for hotspot in row.get('hotspots') or []:
        try:
            date = datetime.fromisoformat(str(hotspot.get('observedAt')).replace('Z', '+00:00'))
            if date.tzinfo is None:
                continue
        except ValueError:
            continue
        dates.append(date)
        hotspots.append(hotspot)
    row['ringMetadataObservedAt'] = metadata_time
    row['observedAt'] = min(dates).isoformat()
    row['hotspots'] = hotspots
    return row


def apply(path):
    from edframe_catalog.database import connection
    manifest = json.loads(path.with_suffix('.manifest.json').read_text())
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    if manifest['sourceUrl'] != SOURCE or digest.hexdigest() != manifest['snapshotSha256']:
        raise ValueError('Snapshot provenance/hash mismatch')
    with connection() as conn:
        conn.execute("SET LOCAL statement_timeout='120000ms'")
        conn.execute('CREATE TEMP TABLE ring_import (data JSONB) ON COMMIT DROP')
        count = 0
        with conn.cursor().copy('COPY ring_import (data) FROM STDIN') as copy, path.open() as source:
            for line in source:
                copy.write_row((json.dumps(normalize_snapshot_row(json.loads(line))),))
                count += 1
        if count != manifest['rings']:
            raise ValueError('Snapshot count mismatch')
        conn.execute('''CREATE TEMP VIEW ring_import_unique AS
            SELECT DISTINCT ON (LOWER(data->>'system'), LOWER(data->>'ring')) data
            FROM ring_import ORDER BY LOWER(data->>'system'), LOWER(data->>'ring'),
                (data->>'ringMetadataObservedAt')::TIMESTAMPTZ DESC''')
        conn.execute('''CREATE TABLE IF NOT EXISTS ring_reference_metadata (
            system_name TEXT NOT NULL, ring_name TEXT NOT NULL, system_address BIGINT NOT NULL,
            ring_type TEXT, reserve_level TEXT, source TEXT NOT NULL, observed_at TIMESTAMPTZ NOT NULL,
            provenance JSONB NOT NULL, ring_snapshot JSONB NOT NULL,
            PRIMARY KEY(system_name, ring_name))''')
        conn.execute('CREATE INDEX IF NOT EXISTS ring_reference_system_idx ON ring_reference_metadata(LOWER(system_name))')
        conn.execute('''INSERT INTO ring_reference_metadata
            SELECT data->>'system',data->>'ring',(data->>'systemAddress')::BIGINT,
                   data->>'ringType',data->>'reserveLevel',data->>'source',
                   (data->>'ringMetadataObservedAt')::TIMESTAMPTZ,%s::JSONB,data FROM ring_import_unique
            ON CONFLICT(system_name,ring_name) DO UPDATE SET
                ring_type=EXCLUDED.ring_type,reserve_level=EXCLUDED.reserve_level,
                observed_at=EXCLUDED.observed_at,provenance=EXCLUDED.provenance,
                ring_snapshot=EXCLUDED.ring_snapshot
            WHERE EXCLUDED.observed_at > ring_reference_metadata.observed_at''', (json.dumps(manifest),))
        inserted = conn.execute('''INSERT INTO mining_sites
            (identity,system_address,system_name,x,y,z,body_id,body_name,ring_name,
             ring_type,reserve_level,distance_to_arrival_ls,hotspots,evidence,source,observed_at,received_at)
            SELECT 'spansh-ring:'||(data->>'systemAddress')||':'||LOWER(data->>'ring'),
                (data->>'systemAddress')::BIGINT,data->>'system',
                (data->>'x')::FLOAT8,(data->>'y')::FLOAT8,(data->>'z')::FLOAT8,
                NULL,data->>'body',data->>'ring',data->>'ringType',data->>'reserveLevel',
                (data->>'distanceToArrivalLs')::FLOAT8,data->'hotspots',
                'CATALOG_CANDIDATE',data->>'source',(data->>'observedAt')::TIMESTAMPTZ,%s
            FROM ring_import_unique r WHERE NOT EXISTS (
                SELECT 1 FROM mining_sites m WHERE LOWER(m.system_name)=LOWER(r.data->>'system')
                  AND LOWER(m.ring_name)=LOWER(r.data->>'ring'))
            ON CONFLICT(identity) DO NOTHING''', (manifest['retrievedAt'],)).rowcount
        print(json.dumps({'snapshotRings': count, 'newSites': inserted,
                          'existingSitesOverwritten': 0, 'provenance': manifest}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('extract', 'apply'))
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    (extract if args.mode == 'extract' else apply)(args.snapshot)
