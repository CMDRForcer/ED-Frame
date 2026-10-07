"""Frozen, attributed community reports; never promoted to verified sightings."""
from collections import defaultdict
import csv
from functools import lru_cache
import io
import json
from pathlib import Path
import re
from math import isfinite, sqrt


def ring_key(system, ring):
    system = str(system or '').strip().casefold()
    ring = str(ring or '').strip().casefold()
    if ring.startswith(system + ' '):
        ring = ring[len(system):].strip()
    # Both "AB 8 A Ring" and "AB8 Ring A" occur in the source.
    ring = re.sub(r'\bring\s+([a-z])\b', r'\1 ring', ring)
    return system, re.sub(r'\s+', '', ring)


def parse_catalog(snapshot):
    reports = []
    for line, raw in enumerate(csv.DictReader(io.StringIO(snapshot['csv'])), 2):
        system, ring = (raw.get('System') or '').strip(), (raw.get('Ring') or '').strip()
        note = (raw.get('RES/Pt HS?') or '').strip()
        if not system or not ring:
            continue
        explicit = ((raw.get('For edtools list') or '') + ' ' + note).casefold()
        commodity = next((identifier for token, identifier in (
            ('painite', 'painite'), ('bromelite', 'bromellite'),
            ('bromellite', 'bromellite'), ('tritium', 'tritium'),
            ('ltd', 'lowtemperaturediamond'), ('platinum', 'platinum'),
        ) if re.search(r'\b' + token + r'\b', explicit)), 'platinum')
        types = [name for token, name in (
            ('haz', 'HAZARDOUS'), ('high', 'HIGH'), ('reg', 'REGULAR'), ('low', 'LOW'),
        ) if re.search(r'\b' + token + r'\b', note.casefold())]
        reports.append({
            'system': system, 'ring': ring, 'commodity': commodity,
            'commodityExplicit': bool(re.search(
                r'\b(platinum|painite|bromelite|bromellite|tritium|ltd)\b', explicit)),
            'reportedResTypes': types, 'reportedOverlap': note,
            'reportedHotspotCount': (raw.get('HS') or '').strip(),
            'reportedPlatinumPercentage': (raw.get('Pt %') or '').strip() or None,
            'sourceUrl': snapshot['sourceUrl'], 'sourceRevision': snapshot['sourceRevision'],
            'sourceRow': line, 'sourceFileModifiedAt': snapshot['sourceFileModifiedAt'],
            'importedAt': snapshot['importedAt'], 'verifiedAt': None,
            'status': 'COMMUNITY_REPORTED_UNDATED',
            'rawFields': {key: value for key, value in raw.items() if key is not None},
        })
    return reports


@lru_cache(maxsize=4)
def bundled_file(name):
    package = Path(__file__).resolve()
    paths = [package.parents[1] / 'ed_data' / name]
    if len(package.parents) > 3:
        paths.append(package.parents[3] / 'ed_data' / name)
    path = next((path for path in paths if path.is_file()), None)
    if path is None:
        raise FileNotFoundError('Bundled community RES overlap catalog missing')
    return path


@lru_cache(maxsize=1)
def catalog():
    return parse_catalog(json.loads(bundled_file('community_res_overlaps.json').read_text(encoding='utf-8')))


@lru_cache(maxsize=1)
def imported_system_positions():
    """One-time coordinate import; never evidence that a ring exists or is active."""
    snapshot = json.loads(bundled_file('community_res_system_positions_spansh.json').read_text(encoding='utf-8'))
    allowed = {r['system'].casefold() for r in catalog()}
    positions = {}
    for row in snapshot['results']:
        data = row.get('data') or {}
        key = str(row.get('system') or '').strip().casefold()
        coords = data.get('coords') or {}
        if (not row.get('resolved') or key not in allowed
                or str(data.get('name', '')).casefold() != key
                or type(data.get('id64')) is not int or data['id64'] <= 0
                or not all(type(coords.get(k)) in (int, float) and isfinite(coords[k])
                           for k in ('x', 'y', 'z'))):
            continue
        positions[key] = {
            'name': data['name'], 'system_address': data['id64'],
            **{k: coords[k] for k in ('x', 'y', 'z')},
            'observed_at': data.get('updateTime'),
            'positionEvidence': {
                'source': 'Spansh public coordinate snapshot',
                'sourceUrl': row.get('sourceUrl') or snapshot['sourceUrl'],
                'observedAt': data.get('updateTime'),
                'retrievedAt': row.get('retrievedAt') or snapshot['retrievedAt'],
                'dumpSha256': None if row.get('sourceUrl') else snapshot['dumpSha256'],
            },
        }
    return positions


def attach_overlap_reports(rows, reports=None):
    index = defaultdict(list)
    for report in catalog() if reports is None else reports:
        index[ring_key(report['system'], report['ring'])].append(report)
    for row in rows:
        matches = index.get(ring_key(row.get('system'), row.get('ring')), [])
        if matches:
            row['communityOverlapReports'] = [dict(report) for report in matches]
    # Deliberately do not set resType, evidence, yieldStats or observedAt.
    return rows


def overlap_site_identities(conn, commodity):
    reports = [report for report in catalog() if report['commodity'] == commodity]
    if not reports:
        return []
    keys = {ring_key(report['system'], report['ring']) for report in reports}
    rows = conn.execute(
        'SELECT identity, system_name AS system, ring_name AS ring FROM mining_sites '
        'WHERE LOWER(system_name) = ANY(%s)',
        (sorted({report['system'].casefold() for report in reports}),),
    ).fetchall()
    return [row['identity'] for row in rows if ring_key(row['system'], row['ring']) in keys]


def community_reference_candidates(conn, existing, *, commodity=None, system=None,
                                   origin=None, radius=None, limit=200):
    """Locate historical ring references, not new confirmed ring observations."""
    if limit <= 0:
        return []
    reports = [r for r in catalog() if (not commodity or r['commodity'] == commodity.casefold())
               and (not system or r['system'].casefold() == system.strip().casefold())]
    if not reports:
        return []
    positions = conn.execute(
        'SELECT name, system_address, x, y, z, observed_at FROM systems '
        'WHERE LOWER(name) = ANY(%s)',
        (sorted({r['system'].casefold() for r in reports}),),
    ).fetchall()
    by_system = {p['name'].casefold(): p for p in positions
                 if all(isinstance(p.get(k), (int, float)) and isfinite(p[k])
                        for k in ('x', 'y', 'z'))}
    for key, position in imported_system_positions().items():
        by_system.setdefault(key, position)
    grouped = defaultdict(list)
    for report in reports:
        grouped[ring_key(report['system'], report['ring'])].append(report)
    seen = {ring_key(r.get('system'), r.get('ring')) for r in existing}
    result = []
    for key, matches in grouped.items():
        if key in seen or key[0] not in by_system:
            continue
        position = by_system[key[0]]
        distance = sqrt(sum((position[k] - origin[i]) ** 2
                            for i, k in enumerate(('x', 'y', 'z')))) if origin else None
        if radius is not None and (distance is None or distance > radius):
            continue
        ring = re.sub(r'\bRing\s+([A-Za-z])\b', r'\1 Ring', matches[0]['ring'])
        ring = re.sub(r'([A-Za-z]+)(\d+)', r'\1 \2', ring)
        result.append({
            'system': position['name'], 'systemAddress': position['system_address'],
            'x': position['x'], 'y': position['y'], 'z': position['z'],
            'ring': position['name'] + ' ' + ring, 'bodyId': None, 'body': None,
            'ringType': None, 'reserveLevel': None, 'distanceToArrivalLs': None,
            'observedAt': None, 'receivedAt': None, 'hotspots': [], 'yieldStats': [],
            'prospectorSampleCount': 0, 'evidence': 'CATALOG_CANDIDATE',
            'source': 'Community historical ring reference · ring unverified',
            'ringAssociationStatus': 'COMMUNITY_REFERENCE_ONLY',
            'systemPositionEvidence': position.get('positionEvidence') or {
                'source': 'ED-Frame systems catalog', 'observedAt': position.get('observed_at')},
            'communityOverlapReports': matches, 'distanceLy': distance,
        })
    result.sort(key=lambda r: (r['distanceLy'] is None, r['distanceLy'] or 0,
                              r['system'].casefold(), r['ring'].casefold()))
    return result[:max(0, limit)]
