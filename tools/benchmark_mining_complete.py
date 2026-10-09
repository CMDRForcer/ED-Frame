"""Frozen public inputs, populated SQLite markets and complete route workers.

Preparation only reads the named source catalogs/databases. All app writes are
inside a new .test-tmp output. CPU trials have no HTTP or QObject controller.
Use benchmark_mining_baseline.py separately for real Qt/QML publication.
"""
from __future__ import annotations
import argparse
import cProfile
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pstats
import shutil
import sqlite3
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.benchmark_mining_baseline import memory, PROFILE

ORIGIN = [110.9375, -113.0625, 41.21875]
FILES = ('mining_finder_catalog.json', 'mining_powerplay_catalog.json',
         'mining_powerplay_observations.json', 'mining_market_cache.json')


def digest(rows):
    result = hashlib.sha256()
    count = 0
    for row in rows:
        result.update(json.dumps(row, sort_keys=True, ensure_ascii=False,
                                 separators=(',', ':')).encode())
        count += 1
    return {'count': count, 'sha256': result.hexdigest()}


def backup(source, destination):
    with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True) as src:
        src.execute('PRAGMA query_only=ON')
        with sqlite3.connect(destination) as dst:
            src.backup(dst)


def prepare(args):
    if args.output.exists():
        raise ValueError('Preparation requires a new output directory')
    profile = args.output / 'local' / 'ED-Frame' / PROFILE
    profile.mkdir(parents=True)
    for name in FILES:
        source = args.ring_source / name
        if not source.exists() and name == 'mining_market_cache.json':
            source = args.market_source / name
        if source.exists():
            shutil.copy2(source, profile / name)
    for name, source in (('mining_ring_catalog.sqlite3', args.ring_source),
                         ('mining_market_catalog.sqlite3', args.market_source)):
        backup(source / name, profile / name)
    recovery = args.market_source / 'mining_market_catalog.backup.sqlite3.gz'
    if recovery.exists():
        shutil.copy2(recovery, profile / recovery.name)
    with sqlite3.connect(profile / 'mining_market_catalog.sqlite3') as db:
        markets = db.execute('SELECT COUNT(*) FROM market_current').fetchone()[0]
        if not markets:
            raise ValueError('A populated market store is required')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Market integrity check failed')
    config = {'onboarding_complete': True, 'background_mode': False, 'journal_auto': False,
              'last_page': 12, 'renderer_mode': 'software', 'edframe_catalog_enabled': True,
              'edframe_yield_sharing_enabled': False, 'edframe_signal_sharing_enabled': False,
              'edframe_station_price_sharing_enabled': False, 'interface_language': 'en'}
    (profile / 'phase14_graphics.json').write_text(json.dumps(config), encoding='utf-8')
    (profile / 'eddn_config.json').write_text(json.dumps({'consent': False,
        'upload_enabled': False, 'listener_enabled': False, 'hge_classifier_version': 2}), encoding='utf-8')
    journal = args.output / 'journal'
    journal.mkdir()
    shutil.copy2(ROOT / 'tests/fixtures/smoke_journal.ndjson', journal / 'Journal.2026-08-23T190000.01.log')
    clock = datetime.now(timezone.utc).isoformat()
    hashes = {}
    for path in profile.iterdir():
        if path.name in FILES or path.suffix == '.sqlite3':
            with path.open('rb') as handle:
                hashes[path.name] = hashlib.file_digest(handle, 'sha256').hexdigest()
    manifest = {'clock': clock, 'marketRows': markets, 'inputs': hashes,
                'mode': 'public frozen copies; original profile never instantiated'}
    (args.output / 'fixture.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (args.output / 'source-inventory.json').write_text(json.dumps(manifest), encoding='utf-8')
    print(json.dumps({'prepared': True, 'marketRows': markets, 'clock': clock}), flush=True)


def install_clock(value):
    frozen = datetime.fromisoformat(value)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen.astimezone(tz) if tz else frozen.replace(tzinfo=None)
    stack = ExitStack()
    for module in ('mining_finder', 'mining_planner', 'mining_market_store', 'mining_powerplay'):
        stack.enter_context(patch('ed_companion.navigation.' + module + '.datetime', Clock))
    stack.enter_context(patch('ed_companion.phase14.controller_navigation.datetime', Clock))
    stack.enter_context(patch('time.time', return_value=frozen.timestamp()))
    return stack


def cpu(args):
    if args.output.exists():
        raise ValueError('Each trial requires a new output')
    args.output.mkdir(parents=True)
    manifest = json.loads((args.fixture / 'fixture.json').read_text(encoding='utf-8'))
    source = args.fixture / 'local/ED-Frame' / PROFILE
    shutil.copy2(source / 'mining_market_catalog.sqlite3', args.output / 'markets.sqlite3')
    import requests
    requests.Session.request = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError('HTTP forbidden'))
    from ed_companion.navigation.catalog_json import load_catalog_snapshot
    from ed_companion.navigation.mining_ring_store import RingCatalogStore
    from ed_companion.navigation.mining_market_store import MarketCatalogStore
    from ed_companion.navigation.mining_planner import PowerplayIndexCache
    from ed_companion.navigation.mining_geometry import MiningGeometryCache
    if args.baseline_navigation:
        import ed_companion.phase14.controller_navigation as old_navigation
        exec(compile(args.baseline_navigation.read_text(encoding='utf-8'),
                     str(args.baseline_navigation), 'exec'), old_navigation.__dict__)
    from ed_companion.phase14.controller import CockpitController
    from ed_companion.phase14.controller_navigation import NavigationMixin
    started = time.perf_counter()
    view = RingCatalogStore(source / 'mining_ring_catalog.sqlite3', PROFILE.removeprefix('profile-')).view()
    view.signals()
    store = MarketCatalogStore(args.output / 'markets.sqlite3')
    facade = NavigationMixin()
    facade._state = {'system': 'Shanteneri', 'currentPosition': ORIGIN}
    facade._network_threads_lock = True
    facade._mining_rows = lambda: view
    facade._mining_rows_cache_key = ('complete-frozen',)
    facade._valid_star_position = CockpitController._valid_star_position
    facade._known_mining_origin = lambda _name: {'system': 'Shanteneri', 'coordinates': ORIGIN}
    facade._mining_market_store = store
    facade._mining_powerplay_catalog = load_catalog_snapshot(source / FILES[1], {})
    facade._mining_powerplay_observations = load_catalog_snapshot(source / FILES[2], [])
    facade._mining_powerplay_index_cache = PowerplayIndexCache()
    facade._mining_powerplay_index_scope = 'complete-frozen'
    facade._mining_geometry_cache = MiningGeometryCache()
    result = {'commodity': args.commodity, 'radius': args.radius, 'clock': manifest['clock'],
              'inputs': manifest['inputs'], 'marketStoreRows': store.count(),
              'ringStoreRows': len(view), 'readySeconds': time.perf_counter() - started,
              'readyMemory': memory(), 'trials': []}
    stages = []
    def timed(label, original):
        def call(*a, **k):
            began = time.perf_counter()
            value = original(*a, **k)
            stages.append({'stage': label, 'seconds': time.perf_counter() - began,
                           'rows': len(value) if hasattr(value, '__len__') else None})
            return value
        return call
    facade._mining_find_page = timed('candidates', facade._mining_find_page)
    facade._mining_market_rows_for_query = timed('markets', facade._mining_market_rows_for_query)
    facade._mining_powerplay_index_cache.index_for = timed('powerplay-index', facade._mining_powerplay_index_cache.index_for)
    import ed_companion.phase14.controller_navigation as navigation
    arguments = ('Shanteneri', args.commodity, args.radius, 'ALL RESERVES', 'ANY RING',
                 True, 'LASER', 'POWERPLAY MERITS', 5000, 500000, 1, 100, False, True,
                 False, False, 'L', 'Aisling Duval', 'REINFORCE', 'ANY', 'ANY')
    with install_clock(manifest['clock']), patch.object(navigation, 'plan_mining_routes', timed('ranking', navigation.plan_mining_routes)):
        for trial in range(args.trials):
            facade._mining_find_cache_key = None
            facade._mining_plan_market_rows = {}
            stages.clear()
            began = time.perf_counter()
            rows = facade._compute_mining_plan_routes(*arguments)
            facade.miningMarketDiagnostics('Shanteneri', args.commodity, args.radius, 5000, 500000, 1, 'L')
            seconds = time.perf_counter() - began
            identity = digest(rows)
            if trial and identity != result['trials'][0]['result']:
                raise AssertionError('Frozen repeated result changed')
            result['trials'].append({'seconds': seconds, 'stages': list(stages),
                'result': identity, 'memory': memory()})
            print(json.dumps({'trial': trial, 'commodity': args.commodity, 'radius': args.radius,
                              'seconds': round(seconds, 3), 'stages': stages}), flush=True)
        if args.profile:
            facade._mining_find_cache_key = None
            facade._mining_plan_market_rows = {}
            profiler = cProfile.Profile()
            profiler.runcall(facade._compute_mining_plan_routes, *arguments)
            profiler.dump_stats(args.output / 'search.prof')
            with (args.output / 'profile.txt').open('w', encoding='utf-8') as handle:
                pstats.Stats(profiler, stream=handle).sort_stats('cumulative').print_stats(45)
        (args.output / 'routes.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    result['finalMemory'] = memory()
    (args.output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--ring-source', type=Path)
    parser.add_argument('--market-source', type=Path)
    parser.add_argument('--fixture', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--radius', type=int, choices=(250, 500), default=250)
    parser.add_argument('--commodity', choices=('Platinum', 'ALL COMMODITIES'), default='Platinum')
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--profile', action='store_true')
    parser.add_argument('--baseline-navigation', type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if not args.output.is_relative_to(ROOT / '.test-tmp') or args.output == ROOT / '.test-tmp':
        parser.error('Only new isolated .test-tmp outputs are allowed')
    if args.prepare:
        if not args.ring_source or not args.market_source:
            parser.error('Both named public sources are required')
        prepare(args)
    else:
        if not args.fixture or not args.fixture.resolve().is_relative_to(ROOT / '.test-tmp') or args.trials < 1:
            parser.error('An isolated prepared fixture and positive trials are required')
        cpu(args)


if __name__ == '__main__':
    main()
