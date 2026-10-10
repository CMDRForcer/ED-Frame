"""Fill same-system markets that regional price-only top lists omit.

Runs in the existing network worker. Uses exact public system names, bounded
concurrency and a short profile-scoped cache, including successful empty checks.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
import time

from .mining_commodities import MINING_COMMODITIES, mining_commodity_id, mining_ring_type_key, mining_ring_types_for_method
from .mining_finder import is_belt_candidate
from .mining_market import EDFRAME_CATALOG_BASE, latest_market_rows, project_edframe_catalog_markets
from .mining_planner import _merit_status, _powerplay_index, _market_filter_assessment, _spatial_cell

MAX_TARGETS = 64


class MeritMarketCache:
    def __init__(self, *, clock=time.monotonic):
        self._clock = clock
        self._entries = OrderedDict()
        self._lock = Lock()
        self._legacy_until = 0

    def grouped_available(self):
        with self._lock:
            return self._clock() >= self._legacy_until

    def legacy_server(self):
        with self._lock:
            self._legacy_until = self._clock() + 600

    def get(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self._clock() >= entry[0]:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return deepcopy(entry[1])

    def put(self, key, rows):
        with self._lock:
            self._entries[key] = (self._clock() + (300 if rows else 600), deepcopy(rows))
            self._entries.move_to_end(key)
            while len(self._entries) > 128 or sum(len(entry[1]) for entry in self._entries.values()) > 4000:
                self._entries.popitem(last=False)


def _merit_market_jobs(candidates, powerplay, markets, query, context, *, now=None):
    """Only target compatible rings and routes with explicit current/last-known control."""
    now = now or datetime.now(timezone.utc)
    power = str(context.get('power') or '').strip()
    goal = str(context.get('goal') or '').upper()
    commodity = mining_commodity_id(query.get('commodity'))
    if not power or power.casefold() in {'any', 'unconfirmed'} or goal not in {'REINFORCE', 'UNDERMINE', 'ACQUIRE'}:
        return []
    method = str(context.get('method') or 'LASER').upper()
    broad = bool(context.get('allCommodities')) or commodity == 'allcommodities'
    if not broad and not commodity:
        return []
    commodities = [key for key, value in MINING_COMMODITIES.items() if method in value['methods']] if broad else [commodity]
    by_ring = {}
    for identifier in commodities:
        for ring_type in mining_ring_types_for_method(identifier, method):
            by_ring.setdefault(mining_ring_type_key(ring_type), []).append(identifier)
    available = {(str(row.get('system') or '').strip().casefold(), mining_commodity_id(row.get('commodity')))
                 for row in markets if mining_commodity_id(row.get('commodity')) in commodities
                 and _market_filter_assessment(row, landing_pad=query['landingPad'],
                     min_demand=query['minDemand'], max_demand=0,
                     max_market_age_hours=query['maxMarketAgeHours'], now=now)['matchesFilters']}
    prices = {}
    for row in markets:
        identifier = mining_commodity_id(row.get('commodity'))
        prices[identifier] = max(prices.get(identifier, 0), float(row.get('sellPrice') or 0))
    index = _powerplay_index(powerplay)
    targets = {}
    unoccupied = [fact for fact in index['bySystem'].values()
                  if fact.get('controlPowerState') == 'Unoccupied']
    target_cells = {}
    for target in unoccupied:
        cell = _spatial_cell(target.get('coordinates'))
        if cell is not None:
            target_cells.setdefault(cell, []).append(target)
    for candidate in candidates:
        compatible = by_ring.get(mining_ring_type_key(candidate.get('ringType')), ())
        if is_belt_candidate(candidate) or not compatible:
            continue
        possibilities = [{'system': candidate.get('system')}]
        if goal == 'ACQUIRE':
            cell = _spatial_cell(candidate.get('coordinates'))
            possibilities = []
            if cell is not None:
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for dz in (-1, 0, 1):
                            possibilities.extend(target_cells.get((cell[0]+dx, cell[1]+dy, cell[2]+dz), ()))
        for target in possibilities:
            name = str(target.get('system') or '').strip()
            if not name:
                continue
            status, score, _distance = _merit_status(candidate, target, power, goal,
                str(context.get('opposingPower') or 'ANY'), index, now=now)
            if score is None or score <= 0:
                continue
            hotspots = {mining_commodity_id(row.get('commodity')) for row in candidate.get('hotspots', ())}
            for identifier in compatible:
                key = (name.casefold(), identifier)
                if key in available:
                    continue
                rank = (status.startswith('PROVISIONAL'), identifier not in hotspots,
                        -prices.get(identifier, 0) if broad else 0,
                        float(candidate.get('distanceLy') or 0), name.casefold(), identifier)
                old = targets.get(key)
                if old is None or rank < old[0]:
                    targets[key] = (rank, name, identifier)
    # A partial broad ring snapshot must not decide which controlled systems
    # can receive exact ring/market data. Seed only explicit eligible regional
    # systems with independently known coordinates, never guessed ownership.
    origin = context.get('_originCoordinates')
    if broad and goal in {'REINFORCE','UNDERMINE'} and len(origin or []) == 3:
        for fact in index['bySystem'].values():
            coordinates = fact.get('coordinates')
            if len(coordinates or []) != 3:
                continue
            distance = sum((a-b)**2 for a,b in zip(coordinates,origin))**0.5
            if distance > query['nearbyLy']:
                continue
            name = fact['system']
            status, score, _ = _merit_status({'system':name},{'system':name},power,goal,
                str(context.get('opposingPower') or 'ANY'),index,now=now)
            if score is None or score <= 0:
                continue
            for identifier in commodities:
                key=(name.casefold(),identifier)
                if key not in available and key not in targets:
                    targets[key]=((status.startswith('PROVISIONAL'),True,-prices.get(identifier,0),
                                  distance,name.casefold(),identifier),name,identifier)
    return [(name, identifier) for _rank, name, identifier in sorted(targets.values())]


def merit_market_targets(candidates, powerplay, markets, query, context, *, now=None):
    return [name for name, _commodity in _merit_market_jobs(candidates, powerplay, markets, query, context, now=now)]


def _grouped_market_jobs(jobs, query, context, *, session_factory, cache, is_current):
    """At most eight sequential public batches; every pair has explicit coverage."""
    coverage = {'requested': len(jobs), 'checked': 0, 'cacheHits': 0,
                'failed': [], 'deferred': [], 'bounded': False,
                'batchRequests': 0, 'transport': 'grouped', '_powerplayFacts': [], '_siteCandidates': []}
    additions, targets = [], OrderedDict()
    def cache_key(name, symbol):
        return (name.casefold(), symbol, query['maxMarketAgeHours'],
                query['minDemand'], query['landingPad'])
    for name, symbol in jobs:
        reused = cache.get(cache_key(name, symbol)) if cache is not None else None
        if reused is not None:
            additions.extend(reused)
            coverage['checked'] += 1
            coverage['cacheHits'] += 1
        else:
            targets.setdefault(name, []).append(symbol)
    names = list(targets)
    started = time.monotonic()
    with session_factory() as session:
        if not callable(getattr(session, 'post', None)):
            return None  # Older provider adapters retain the exact GET path.
        for offset in range(0, min(len(names), 1600), 200):
            if time.monotonic() - started > 20 or (is_current is not None and not is_current()):
                coverage['deferred'].extend(names[offset:])
                break
            selected = names[offset:offset + 200]
            body = {'targets': [{'system': name, 'commodities': targets[name]} for name in selected],
                    'power': context['power'], 'goal': context['goal'],
                    'opposingPower': context.get('opposingPower') or 'ANY',
                    'method': context.get('method') or 'LASER', 'minDemand': query['minDemand'],
                    'maxAgeHours': max(1, min(2160, query['maxMarketAgeHours'])),
                    'landingPad': query['landingPad'] if query['landingPad'] in {'S', 'M', 'L'} else 'ANY'}
            try:
                response = session.post(EDFRAME_CATALOG_BASE + '/v1/mining/merit-markets',
                                        json=body, timeout=(2, 12))
                if response.status_code in {404, 405}:
                    if cache is not None:
                        cache.legacy_server()
                    return None
                response.raise_for_status()
                payload = response.json()
                if (not isinstance(payload, dict) or payload.get('protocol') != 1
                        or payload.get('hasMore') is not False or not isinstance(payload.get('results'), list)
                        or len(payload['results']) > 8000):
                    raise ValueError('Incomplete mining market batch')
                covered = {row['system'].casefold(): row for row in payload.get('coverage', [])
                           if isinstance(row, dict) and isinstance(row.get('system'), str)}
                if set(covered) != {name.casefold() for name in selected}:
                    raise ValueError('Missing exact system coverage')
                rows = project_edframe_catalog_markets(payload)
                allowed = {(name.casefold(), symbol) for name in selected for symbol in targets[name]}
                grouped = {}
                for row in rows:
                    key = (str(row.get('system') or '').casefold(), row['commodity'])
                    if key not in allowed:
                        raise ValueError('Unrequested market in batch')
                    grouped.setdefault(key, []).append(row)
                if is_current is not None and not is_current():
                    coverage['deferred'].extend(names[offset:])
                    break
                coverage['batchRequests'] += 1
                for name in selected:
                    for symbol in targets[name]:
                        rows_for_pair = grouped.get((name.casefold(), symbol), [])
                        additions.extend(rows_for_pair)
                        coverage['checked'] += 1
                        if cache is not None and covered[name.casefold()].get('queried') is True:
                            cache.put(cache_key(name, symbol), rows_for_pair)
                from .mining_powerplay import _public_powerplay_rows
                coverage['_powerplayFacts'].extend(_public_powerplay_rows(payload.get('powerplay', [])))
                from .mining_finder import project_edframe_mining_candidates
                ring_sources=payload.get('rings', [])
                if not isinstance(ring_sources,list) or len(ring_sources)>5000:
                    raise ValueError('Invalid exact ring batch')
                rings=project_edframe_mining_candidates({'results':ring_sources},context.get('_originCoordinates'))
                if any(row['system'].casefold() not in covered for row in rings):
                    raise ValueError('Unrequested ring in batch')
                coverage['_siteCandidates'].extend(rings)
                if payload.get('ringHasMore'):
                    coverage['ringBounded']=True
            except Exception:
                # A failed request is not proof of an empty market; retain a retry.
                coverage['failed'].extend(selected)
                coverage['deferred'].extend(names[offset + len(selected):])
                if not additions and offset == 0:
                    return None
                break
        else:
            coverage['deferred'].extend(names[1600:])
    coverage['bounded'] = bool(coverage['failed'] or coverage['deferred'] or coverage.get('ringBounded'))
    coverage['addedRows'] = len(additions)
    return additions, coverage


def fill_merit_markets(candidates, powerplay, markets, query, context, *, session_factory,
                      cache=None, is_current=None, max_workers=2, known_markets=()):
    jobs = _merit_market_jobs(candidates, powerplay, latest_market_rows(markets, known_markets), query, context)
    if jobs and (cache is None or cache.grouped_available()):
        grouped = _grouped_market_jobs(jobs, query, context, session_factory=session_factory,
                                       cache=cache, is_current=is_current)
        if grouped is not None:
            return latest_market_rows(markets, grouped[0]), grouped[1]
    selected = jobs[:MAX_TARGETS]
    coverage = {'requested': len(jobs), 'checked': 0, 'cacheHits': 0,
                'failed': [], 'deferred': [name for name, _commodity in jobs[MAX_TARGETS:]], 'bounded': len(jobs) > MAX_TARGETS}
    started = time.monotonic()
    def fetch(job):
        name, commodity = job
        if time.monotonic() - started > 20 or (is_current is not None and not is_current()):
            return [], 'cancelled'
        key = (name.casefold(), commodity, query['maxMarketAgeHours'],
               query['minDemand'], query['landingPad'])
        reused = cache.get(key) if cache is not None else None
        if reused is not None:
            return reused, 'cached'
        try:
            with session_factory() as session:
                response = session.get(EDFRAME_CATALOG_BASE + '/v1/markets/search',
                    params={'system': name, 'commodity': commodity,
                            'max_age_hours': max(1, min(2160, query['maxMarketAgeHours'])),
                            'min_demand': query['minDemand'], 'landing_pad':
                                query['landingPad'] if query['landingPad'] in {'S', 'M', 'L'} else None,
                            'exclude_fleet_carriers': True, 'limit': 200}, timeout=(2, 4))
                response.raise_for_status()
                rows = project_edframe_catalog_markets(response.json(), commodity)
                if any(str(row.get('system') or '').strip().casefold() != name.casefold() for row in rows):
                    raise ValueError('Exact market response contains another system')
            if is_current is not None and not is_current():
                return [], 'cancelled'
            if cache is not None:
                cache.put(key, rows)
            return rows, 'fetched'
        except Exception:
            return [], 'failed'
    additions = []
    with ThreadPoolExecutor(max_workers=max(1, min(2, int(max_workers))),
                            thread_name_prefix='mining-merit-markets') as pool:
        for (name, _commodity), (rows, state) in zip(selected, pool.map(fetch, selected)):
            if state in {'failed', 'cancelled'}:
                coverage['failed'].append(name)
                coverage['bounded'] = True
            else:
                coverage['checked'] += 1
                coverage['cacheHits'] += state == 'cached'
                additions.extend(rows)
    coverage['addedRows'] = len(additions)
    return latest_market_rows(markets, additions), coverage
