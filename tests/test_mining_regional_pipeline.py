"""Complete regional domains, legacy compatibility and fenced early merging."""
import copy
from datetime import datetime, timezone
import random
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from ed_companion.navigation.mining_finder import (
    fetch_edframe_mining_candidates, merge_mining_candidates,
    merge_mining_candidate_batch, mining_candidate_positions,
)
from ed_companion.navigation.mining_powerplay import fetch_edframe_powerplay
from ed_companion.navigation.mining_refresh import fetch_mining_refresh
from tests import test_mining_batch as batch_tests
from tests import test_mining_refresh as refresh_tests
from tests.test_mining_batch import ring
from tests.test_mining_refresh import QUERY, ORIGIN, Session, MODULE


class Response:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): pass
    def json(self): return self.payload


class RegionalPipelineTests(unittest.TestCase):
    def test_merge_matches_previous_algorithm_for_varied_local_and_community_facts(self):
        rng = random.Random(13)
        now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
        def sample(index):
            scope = rng.choice(['LOCAL', 'COMMUNITY'])
            return ring('Test %s A Ring' % (index % 19),
                        systemAddress=42, source='source-%s' % rng.randrange(4),
                        observedAt=rng.choice(['2026-10-08T10:00:00Z', '2020-01-01T00:00:00Z', '']),
                        evidence=rng.choice(['LOCAL_CONFIRMED', 'CATALOG_CANDIDATE', 'LIVE_REPORTED']),
                        learnedAt='2026-10-08T11:%02d:00Z' % rng.randrange(60),
                        yieldAggregationScope=scope, prospectorSampleCount=rng.randrange(30),
                        hotspots=[{'commodity': 'platinum', 'count': rng.randrange(1, 4)}],
                        yieldStats=[{'commodity': 'platinum', 'proportionSamples': rng.randrange(20),
                                     'averageProportion': rng.randrange(50), 'refinedCount': 2}],
                        observations=[{'source': 'nested', 'details': {'count': index}}])
        existing = merge_mining_candidates([sample(i) for i in range(80)], now=now)
        additions = [sample(i) for i in range(150)]
        original = copy.deepcopy([existing, additions])
        expected, displaced = list(existing), []
        positions = mining_candidate_positions(existing)
        for incoming in merge_mining_candidates(additions, now=now):
            from ed_companion.navigation.mining_finder import _candidate_identity
            key = _candidate_identity(incoming)
            index = positions.get(key)
            if index is None:
                positions[key] = len(expected); expected.append(incoming)
            else:
                displaced.append(expected[index])
                expected[index] = merge_mining_candidates([expected[index], incoming], now=now)[0]
        actual, old = merge_mining_candidate_batch(existing, additions, now=now)
        self.assertEqual((actual, old), (expected, displaced))
        self.assertEqual([existing, additions], original)

    def test_large_and_legacy_ring_pages_keep_full_coverage_and_original_budget(self):
        for page_size, pages in ((1000, 50), (5000, 10)):
            get = Mock(side_effect=lambda _url, **kw: Response({
                'results': [], 'hasMore': True,
                'nextOffset': kw['params']['offset'] + page_size,
                'nextCursor': str(kw['params']['offset'] + page_size),
            }))
            coverage = {}
            fetch_edframe_mining_candidates('Test', get, origin=[0, 0, 0],
                                            max_distance=250, diagnostics=coverage)
            self.assertEqual(get.call_count, pages)
            self.assertTrue(coverage['bounded'])
            self.assertFalse(coverage['complete'])
        self.assertEqual(get.call_args.kwargs['params']['offset'], 45000)

    def test_large_powerplay_pages_keep_twenty_thousand_system_budget(self):
        for size, pages in ((200, 100), (1000, 20)):
            def response(_url, **kwargs):
                return Response({'results': [], 'hasMore': True,
                                 'nextCursor': str(get.call_count), 'systemCount': size})
            get = Mock(side_effect=response)
            coverage = {}
            fetch_edframe_powerplay(origin=[0, 0, 0], max_distance=250, get=get, diagnostics=coverage)
            self.assertEqual(get.call_count, pages)
            self.assertEqual(coverage, {'bounded': True, 'pages': pages, 'complete': False})

    def test_bad_powerplay_continuation_retains_previous_valid_facts(self):
        fact = dict(system='Test', power='Aisling Duval', powerState='Stronghold',
                    observedAt=datetime.now(timezone.utc).isoformat())
        get = Mock(side_effect=[Response({'results': [fact], 'hasMore': True,
                                         'systemCount': 1, 'nextCursor': 'next'}),
                                Response({'results': [], 'hasMore': True, 'systemCount': 0})])
        coverage = {}
        rows = fetch_edframe_powerplay(origin=[0, 0, 0], max_distance=250, get=get, diagnostics=coverage)
        self.assertEqual(len(rows), 1)
        self.assertTrue(coverage['bounded'])
        self.assertFalse(coverage['complete'])
        self.assertIn('partialError', coverage)

    def test_complete_sites_prepare_while_other_domains_are_waiting(self):
        prepared = threading.Event()
        owner = []
        def slow(**_kwargs):
            self.assertTrue(prepared.wait(3)); return []
        def prepare(rows):
            owner.append(threading.get_ident()); prepared.set(); return {'rows': rows}
        with patch(MODULE+'fetch_edframe_mining_candidates', return_value=[ring('A')]), \
             patch(MODULE+'fetch_edframe_powerplay', side_effect=slow), \
             patch(MODULE+'fetch_market_imports', side_effect=lambda *a, **k: slow()):
            result = fetch_mining_refresh(QUERY, origin=ORIGIN, session_factory=Session,
                                          prepare_sites=prepare)
        self.assertNotEqual(owner[0], threading.get_ident())
        self.assertIs(result['preparedRings']['rows'], result['serverCandidates'])
        self.assertTrue(result['success'])

    def test_preparation_failure_keeps_raw_complete_domain(self):
        with patch(MODULE+'fetch_edframe_mining_candidates', return_value=[ring('A')]), \
             patch(MODULE+'fetch_edframe_powerplay', return_value=[]), \
             patch(MODULE+'fetch_market_imports', return_value=[]):
            result = fetch_mining_refresh(QUERY, origin=ORIGIN, session_factory=Session,
                                          prepare_sites=Mock(side_effect=ValueError('probe')))
        self.assertEqual(result['serverCandidates'], [ring('A')])
        self.assertEqual(result['ringPreparationError'], 'ValueError')
        self.assertNotIn('siteError', result)

    def test_cached_sites_also_prepare_before_other_domains_finish(self):
        cache = Mock()
        cache.get.side_effect = lambda kind, *a: ([ring('A')], {'cacheHit': True}) if kind == 'sites' else None
        prepare = Mock(return_value={'prepared': True})
        with patch(MODULE+'fetch_edframe_mining_candidates') as fetch, \
             patch(MODULE+'fetch_edframe_powerplay', return_value=[]), \
             patch(MODULE+'fetch_market_imports', return_value=[]):
            result = fetch_mining_refresh(QUERY, origin=ORIGIN, session_factory=Session,
                                          prepare_sites=prepare, region_cache=cache)
        fetch.assert_not_called()
        prepare.assert_called_once_with([ring('A')])
        self.assertEqual(result['preparedRings'], {'prepared': True})

    def test_superseded_preparation_is_not_published(self):
        current = threading.Event(); current.set()
        def prepare(rows): current.clear(); return {'rows': rows}
        with patch(MODULE+'fetch_edframe_mining_candidates', return_value=[ring('A')]), \
             patch(MODULE+'fetch_edframe_powerplay', return_value=[]), \
             patch(MODULE+'fetch_market_imports', return_value=[]):
            result = fetch_mining_refresh(QUERY, origin=ORIGIN, session_factory=Session,
                                          prepare_sites=prepare, is_current=current.is_set)
        self.assertNotIn('preparedRings', result)

    def test_prepared_publication_requires_exact_base_context_and_no_active_merge(self):
        for change in ('none', 'base', 'revision', 'profile', 'generation', 'path', 'reset', 'active', 'shutdown'):
            c = batch_tests.MiningBatchTests().controller()
            original = c._mining_catalog
            prepared = dict(profileKey='alpha', generation=2, path='catalog.json', resetAt='',
                            revision=1, base=original['candidates'], rows=[ring('B')],
                            candidates=[ring('A'), ring('B')], positions={}, archiveError='')
            if change == 'base': c._mining_catalog['candidates'] = list(original['candidates'])
            if change == 'revision': c._mining_catalog_revision += 1
            if change == 'profile': c.profile_context.key = 'beta'
            if change == 'generation': c._profile_generation += 1
            if change == 'path': prepared['path'] = 'other.json'
            if change == 'reset': c._mining_catalog['resetAt'] = 'reset'
            if change == 'active': c._active_mining_observation_batch = {'id': 'other'}
            if change == 'shutdown': c._shutdown_complete = True
            self.assertEqual(c._publish_prepared_regional_rings(prepared, search_refresh=True), change == 'none')
            if change == 'none':
                self.assertEqual([r['ring'] for r in c._mining_catalog['candidates']], ['A', 'B'])
                c._history_archive.archive.assert_not_called()
                c._start_network_worker.assert_not_called()
            else:
                self.assertIs(c._mining_catalog, original)

    def test_prepared_ring_notification_sees_current_markets_and_powerplay(self):
        factory = refresh_tests.MiningRefreshTests()
        c = factory.controller()
        c._mining_catalog = {'candidates': [ring('A')], 'resetAt': ''}
        c.mining_catalog_file = Path('catalog.json')
        c._mining_catalog_revision = 1
        c._pending_mining_candidates = []
        c._add_mining_system_names = Mock()
        c._save_mining_catalog = Mock()
        c._save_mining_json = Mock()
        c.mining_powerplay_observations_file = Path('unused.json')
        c._active_mining_market_request = {'id': 'request'}
        fact = {'system': 'Test', 'power': 'Aisling Duval'}
        prepared = dict(profileKey='alpha', generation=3, path='catalog.json', resetAt='',
                        revision=1, base=c._mining_catalog['candidates'], rows=[ring('B')],
                        candidates=[ring('A'), ring('B')], positions={}, archiveError='')
        seen = []
        def notification():
            if len(c._mining_catalog['candidates']) == 2:
                seen.append((c._mining_market_cache['markets'], c._mining_powerplay_observations))
        c.miningChanged.emit.side_effect = notification
        c._finish_mining_market_sync(factory.result(preparedRings=prepared,
            serverCandidates=[ring('B')], serverPowerplay=[fact]))
        self.assertTrue(seen)
        self.assertTrue(all(markets == [{'station': 'Port'}] and facts == [fact]
                            for markets, facts in seen))

    def test_early_merge_uses_same_durable_archive_path_fallback(self):
        from ed_companion.history_archive import HistoryArchive
        with TemporaryDirectory() as directory:
            c = refresh_tests.MiningRefreshTests().controller()
            c.config_dir = Path(directory)
            c._network_threads_lock = threading.Lock()
            c._history_archive = None
            c._mining_catalog = {'candidates': [ring('A')], 'resetAt': ''}
            c.mining_catalog_file = Path(directory) / 'catalog.json'
            c._start_network_worker = Mock(return_value=True)
            c._start_mining_market_refresh(QUERY, background=False)
            def fetch(*args, **kwargs):
                rows = [ring('A', source='new')]
                prepared = kwargs['prepare_sites'](rows)
                return {'success': True, 'markets': [], 'preparedRings': prepared}
            with patch('ed_companion.phase14.controller_navigation.fetch_mining_refresh', side_effect=fetch):
                worker = threading.Thread(target=c._start_network_worker.call_args.args[0])
                worker.start(); worker.join(3)
            self.assertFalse(worker.is_alive())
            archive = HistoryArchive(Path(directory) / 'data_history.sqlite3')
            self.assertEqual(archive.counts(), {'mining_catalog': 1, 'mining_observations': 1})
