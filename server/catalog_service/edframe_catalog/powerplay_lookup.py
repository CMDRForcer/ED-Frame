"""Bounded Spansh supplementation of explicit, dated system control."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from math import isfinite
import threading
import time

import requests

from ed_companion.navigation.mining_powerplay import (
    POWERPLAY_STATES, SPANSH_POWERPLAY_SOURCE, project_spansh_powerplay,
)
from ed_companion.navigation.mining_powerplay_policy import POWERPLAY_CURRENT_HOURS
from .database import connection, upsert_powerplay_snapshot


def current_control(rows, now):
    if not isinstance(rows, list):
        return False
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        state, controller = row.get('powerState'), row.get('controllingPower', '')
        coordinates = row.get('coordinates')
        if (not isinstance(state, str) or not isinstance(controller, str)
                or not isinstance(coordinates, (list, tuple))):
            continue
        try:
            stamp = datetime.fromisoformat(str(row.get('observedAt') or '').replace('Z', '+00:00'))
            age = (now - stamp).total_seconds()
        except (TypeError, ValueError):
            continue
        if (-300 <= age <= POWERPLAY_CURRENT_HOURS * 3600 and state in POWERPLAY_STATES
                and (controller.strip() or state == 'Unoccupied')
                and not (controller.strip() and state == 'Unoccupied')
                and len(coordinates) == 3
                and all(type(value) in (float, int) and isfinite(value)
                        for value in coordinates)):
            return True
    return False


class SpanshPowerplayLookup:
    """Two outbound lanes per worker, single-flight per system, bounded cooldowns."""
    def __init__(self, clock=time.monotonic, capacity=1024):
        self.clock, self.capacity = clock, capacity
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(2)
        self.cache = OrderedDict()
        self.active = set()

    def lookup(self, name, address, *, get=None, now=None):
        now = now or datetime.now(timezone.utc)
        if isinstance(address, bool) or not isinstance(address, int) or not 0 < address < 2**64:
            return {'state': 'NO_ADDRESS', 'rows': []}
        key = (name.casefold(), address)
        with self.lock:
            cached = self.cache.get(key)
            if cached and cached[0] > self.clock():
                self.cache.move_to_end(key)
                result = cached[1]
                if not result['rows'] or current_control(result['rows'], now):
                    return result
            if key in self.active or not self.slots.acquire(blocking=False):
                return {'state': 'BUSY', 'rows': []}
            self.active.add(key)
        result = None
        try:
            started = self.clock()
            response = (get or requests.get)(f'https://spansh.co.uk/api/dump/{address}',
                headers={'User-Agent': 'ED-Frame catalog Powerplay lookup (+https://github.com/CMDRForcer/ED-Frame)'},
                timeout=(3, 5), stream=True, allow_redirects=False)
            try:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError('Unexpected upstream status')
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 2 * 1024**2 or self.clock() - started > 8:
                        raise ValueError('Upstream response budget exceeded')
                    chunks.append(chunk)
                payload = json.loads(b''.join(chunks))
            finally:
                response.close()
            rows = project_spansh_powerplay(payload, name, address, now=now)
            data = payload.get('system') if isinstance(payload, dict) else None
            stamp = data.get('date') if isinstance(data, dict) else None
            state = 'FETCHED' if rows else 'MISSING'
            observed_at = rows[0]['observedAt'] if rows else None
            if rows and not current_control(rows, now):
                rows, state = [], 'STALE'
            if not rows and isinstance(stamp, str):
                try:
                    observed = datetime.fromisoformat(str(stamp).replace('Z', '+00:00'))
                    if ((now - observed).total_seconds() > POWERPLAY_CURRENT_HOURS * 3600
                            and project_spansh_powerplay(payload, name, address, now=observed)):
                        state = 'STALE'
                        observed_at = stamp
                except (ValueError, TypeError):
                    pass
            result = {'state': state, 'rows': rows,
                      'observedAt': observed_at}
            ttl = 3600 if rows else 600
        except Exception:
            result, ttl = {'state': 'ERROR', 'rows': []}, 120
        finally:
            with self.lock:
                if result is not None:
                    self.cache[key] = (self.clock() + ttl, result)
                    self.cache.move_to_end(key)
                    while len(self.cache) > self.capacity:
                        self.cache.popitem(last=False)
                self.active.discard(key)
            self.slots.release()
        return result


LOOKUP = SpanshPowerplayLookup()


def _stored(conn, names):
    return {row['identity']: row for row in conn.execute('''
        SELECT identity, system_name, system_address, observed_at, facts
        FROM mining_powerplay WHERE identity = ANY(%s)
    ''', (names,)).fetchall()}


def lookup_powerplay_systems(names, *, lookup=None, now=None):
    now = now or datetime.now(timezone.utc)
    lookup = lookup or LOOKUP
    with connection() as conn:
        conn.execute("SET LOCAL statement_timeout='5s'")
        stored = _stored(conn, names)
        # Bulk mining imports can know an id64 before a Location/FSDJump has
        # populated systems. All three name lookups use existing indexes.
        addresses = conn.execute('''
            SELECT name, system_address FROM systems
            WHERE LOWER(name) = ANY(%s) AND system_address IS NOT NULL
            UNION ALL
            SELECT system_name AS name, system_address FROM mining_sites
            WHERE LOWER(system_name) = ANY(%s) AND system_address IS NOT NULL
            UNION ALL
            SELECT system_name AS name, system_address FROM stations
            WHERE LOWER(system_name) = ANY(%s) AND system_address IS NOT NULL
        ''', (names, names, names)).fetchall()
    resolved = {}
    for row in addresses:
        address = row['system_address']
        if type(address) is int and 0 < address < 2**64:
            resolved.setdefault(row['name'].casefold(), set()).add(address)
    for name, row in stored.items():
        address = row.get('system_address')
        if type(address) is int and 0 < address < 2**64:
            resolved.setdefault(name, set()).add(address)
    missing = [name for name in names if not current_control(stored.get(name, {}).get('facts'), now)]

    def fetch(name):
        options = resolved.get(name) or set()
        address = next(iter(options)) if len(options) == 1 else None
        return lookup.lookup(name, address, now=now)

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='powerplay-spansh') as pool:
        fetched = dict(zip(missing, pool.map(fetch, missing)))
    # HTTP has finished before opening a write transaction. Re-read afterwards:
    # a concurrent/newer EDDN observation remains authoritative for this system.
    with connection() as conn:
        conn.execute("SET LOCAL statement_timeout='5s'")
        for name, result in fetched.items():
            if result['rows']:
                row = result['rows'][0]
                coords = row['coordinates']
                upsert_powerplay_snapshot(conn, {
                    'identity': name, 'system_name': row['system'], 'system_address': row['systemAddress'],
                    'x': coords[0], 'y': coords[1], 'z': coords[2],
                    'observed_at': row['observedAt'], 'received_at': now.isoformat(),
                    'facts': json.dumps(result['rows']),
                }, allow_equal=False)
        final = _stored(conn, names)
    rows, diagnostics = [], []
    for name in names:
        retained = final.get(name, {})
        facts = retained.get('facts') or []
        usable = current_control(facts, now)
        fetched_rows = fetched.get(name, {}).get('rows') or []
        state = 'CURRENT' if usable else fetched.get(name, {}).get('state', 'MISSING')
        if usable and fetched_rows and facts == fetched_rows:
            state = 'FETCHED'
        if not usable and state == 'FETCHED':
            state = 'MISSING'  # A newer retained snapshot won the storage race.
        if usable:
            rows.extend(facts)
        diagnostics.append({'system': retained.get('system_name') or name, 'state': state,
            'source': facts[0].get('source') if usable else SPANSH_POWERPLAY_SOURCE,
            'observedAt': facts[0].get('observedAt') if usable
                else fetched.get(name, {}).get('observedAt')})
    return {'generatedAt': now.isoformat(), 'selection': 'systems', 'hasMore': False,
            'results': rows, 'lookup': diagnostics}
