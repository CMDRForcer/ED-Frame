"""Public, frozen MeritMiner parity check through the real app search pipeline.

Writes only a named directory under .test-tmp; never opens a user profile.
--fetch captures public inputs; subsequent runs are offline and reproducible.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from uuid import uuid4
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def evaluate(inputs, directory):
    from ed_companion.navigation.mining_market_store import MarketCatalogStore
    from ed_companion.phase14.controller import CockpitController
    from ed_companion.phase14.controller_navigation import NavigationMixin
    frozen = datetime.fromisoformat(inputs['clock'])

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen.astimezone(tz) if tz else frozen.replace(tzinfo=None)

    source = inputs['edframe']
    # Every evaluation begins empty; rerunning the baseline must never retain
    # quotes introduced by a later enrichment evaluation.
    store = MarketCatalogStore(directory / ('markets-' + uuid4().hex + '.sqlite3'))
    store.ingest(source.get('markets', []), create_backup=False)
    facade = NavigationMixin()
    origin = source['origin']
    facade._state = {'system': 'HIP 3254', 'currentPosition': origin['coordinates']}
    facade._network_threads_lock = True
    facade._mining_rows = lambda: source['serverCandidates']
    facade._mining_rows_cache_key = ('meritminer-parity', inputs['clock'])
    facade._valid_star_position = CockpitController._valid_star_position
    facade._known_mining_origin = lambda _name: origin
    facade._mining_market_store = store
    facade._mining_powerplay_catalog = {}
    facade._mining_powerplay_observations = source['serverPowerplay']
    query = inputs['query']
    arguments = ('HIP 3254', query['commodity'], query['nearbyLy'], 'ALL RESERVES', 'ANY RING', True,
                 'LASER', 'POWERPLAY MERITS', 5000, 0, 48, 100, False, False,
                 False, False, 'L', 'Aisling Duval', 'REINFORCE', 'ANY', 'ANY')
    with ExitStack() as stack:
        for module in ('ed_companion.navigation.mining_planner',
                       'ed_companion.navigation.mining_finder',
                       'ed_companion.phase14.controller_navigation'):
            stack.enter_context(patch(module + '.datetime', Clock))
        stack.enter_context(patch('time.time', return_value=frozen.timestamp()))
        started = time.perf_counter()
        rows = facade._compute_mining_plan_routes(*arguments)
        seconds = time.perf_counter() - started
    expected = {row['name'].casefold() for row in inputs['meritminer']}
    verified = {row['system'].casefold() for row in rows
                if row.get('powerplayVerificationState') == 'VERIFIED'}
    result = {'clock': inputs['clock'], 'planSeconds': seconds,
              'ringInputs': len(source['serverCandidates']),
              'marketInputs': store.count(),
              'powerplayInputs': len(source['serverPowerplay']),
              'meritminerSystems': sorted(expected),
              'verifiedAppSystems': sorted(verified),
              'missingMeritminerSystems': sorted(expected - verified),
              'coverage': {key: source.get(key) for key in
                           ('siteCoverage', 'powerplayCoverage', 'providerStatus')},
              'routes': rows}
    return result


def capture(directory, radius):
    import requests
    from ed_companion.navigation.mining_refresh import fetch_mining_refresh
    params = {'system': 'HIP 3254', 'distance': radius, 'limit': 30,
              'controlling_power': 'Aisling Duval', 'power_goal': 'Reinforce',
              'opposing_power': 'Any', 'signal_type': 'Platinum',
              'ring_type_filter': 'All', 'reserve_level': 'All',
              'maxUpdateAge': 48, 'maxUpdateUnit': 'hours',
              'minDemand': 5000, 'maxDemand': 0, 'landingPadSize': 'L',
              'selected_materials[]': 'Default', 'mining_types[]': 'Laser Surface',
              'system_state[]': 'Any'}
    response = requests.get('https://meritminer.cc/search', params=params, timeout=30)
    response.raise_for_status()
    competitor = response.json()
    if not isinstance(competitor, list):
        raise ValueError('MeritMiner search did not return a result list')
    query = {'startSystem': 'hip 3254', 'commodity': 'platinum', 'nearbyLy': radius,
             'minDemand': 5000, 'maxMarketAgeHours': 48, 'landingPad': 'L'}
    began = time.perf_counter()
    public = fetch_mining_refresh(query, session_factory=requests.Session,
        merit_context={'power': 'Aisling Duval', 'goal': 'REINFORCE', 'method': 'LASER'})
    if not public.get('success') or public.get('siteError') or public.get('powerplayError'):
        raise ValueError('Incomplete public source capture: ' + str(public))
    result = {'clock': datetime.now(timezone.utc).isoformat(), 'query': query,
              'meritminerQuery': params, 'meritminerUrl': response.url,
              'captureSeconds': time.perf_counter() - began,
              'meritminer': competitor, 'edframe': public}
    (directory / 'public-inputs.json').write_text(
        json.dumps(result, ensure_ascii=False), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--enrich', action='store_true')
    parser.add_argument('--label', default='result')
    parser.add_argument('--radius', type=int, choices=(250, 500), default=250)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not directory.is_relative_to(ROOT / '.test-tmp'):
        parser.error('Only .test-tmp directories are allowed')
    if not args.label.replace('-', '').isalnum():
        parser.error('Use an alphanumeric result label')
    directory.mkdir(parents=True, exist_ok=True)
    inputs = capture(directory, args.radius) if args.fetch else json.loads(
        (directory / 'public-inputs.json').read_text(encoding='utf-8'))
    if args.enrich:
        import requests
        from ed_companion.navigation.mining_merit_markets import fill_merit_markets
        source = inputs['edframe']
        source['markets'], source['meritMarketCoverage'] = fill_merit_markets(
            source['serverCandidates'], source['serverPowerplay'], source['markets'], inputs['query'],
            {'power': 'Aisling Duval', 'goal': 'REINFORCE', 'method': 'LASER',
             'allCommodities': inputs['query']['commodity'] == 'allcommodities',
             '_originCoordinates': source['origin']['coordinates']},
            session_factory=requests.Session)
        from ed_companion.navigation.mining_finder import merge_mining_candidates
        from ed_companion.navigation.mining_powerplay import merge_powerplay_observations
        coverage = source['meritMarketCoverage']
        source['serverCandidates'] = merge_mining_candidates(
            [*source['serverCandidates'], *coverage.pop('_siteCandidates', [])])
        source['serverPowerplay'] = merge_powerplay_observations(
            source['serverPowerplay'], coverage.pop('_powerplayFacts', []), limit=100_000)
        inputs['clock'] = datetime.now(timezone.utc).isoformat()
        (directory / 'enriched-inputs.json').write_text(json.dumps(inputs, ensure_ascii=False), encoding='utf-8')
    with patch('requests.Session.request', side_effect=RuntimeError('Offline evaluation')):
        result = evaluate(inputs, directory)
    (directory / (args.label + '.json')).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('routes', 'coverage')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
