from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import Mock, patch

from ed_companion.background_work import BackgroundWork, Responsiveness
from ed_companion.work_resources import WorkResources
from ed_companion.network_activity import tracked_get, snapshot
from ed_companion.navigation.mining_market_store import MarketCatalogStore
from ed_companion.navigation.mining_ring_store import RingCatalogStore
from ed_companion.navigation.mining_process import MiningProcess
from ed_companion.phase14.controller import CockpitController
from ed_companion.phase14.controller_navigation import NavigationMixin
from ed_companion.phase14.controller_eddn import EddnMixin


class BackgroundWorkTests(unittest.TestCase):
    def test_local_inventory_counts_are_read_off_ui_and_fenced_on_completion(self):
        owner = CockpitController.__new__(CockpitController)
        owner._background_work = Mock()
        owner._profile_generation = 1
        owner._edframe_catalog_stats = {}
        store = Mock()
        store.station_offer_summary.return_value = {"stations": 12, "outfittingStations": 10, "shipyardStations": 4}
        store.count.return_value = 123
        owner._mining_market_store = store
        owner.localCatalogSummaryReady = Mock()
        owner.connectionChanged = Mock()
        owner._start_network_worker = Mock(return_value=True)
        owner._request_local_catalog_summary()
        owner._request_local_catalog_summary()
        store.station_offer_summary.assert_not_called()
        owner._start_network_worker.assert_called_once()
        thread = threading.Thread(target=owner._start_network_worker.call_args.args[0])
        thread.start()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        payload = owner.localCatalogSummaryReady.emit.call_args.args[0]
        owner._finish_local_catalog_summary(payload)
        self.assertEqual(owner._edframe_catalog_stats["localOfferStations"], 12)
        self.assertEqual(owner._edframe_catalog_stats["localMarkets"], 123)
        owner.connectionChanged.emit.assert_called_once()
        owner._edframe_catalog_stats = {"localOfferStations": 99}
        owner._finish_local_catalog_summary(payload)
        self.assertEqual(owner._edframe_catalog_stats, {"localOfferStations": 99})
        owner._edframe_catalog_stats = {}
        owner._profile_generation = 2
        owner._finish_local_catalog_summary(payload)
        self.assertEqual(owner._edframe_catalog_stats, {})

    def test_small_pc_keeps_two_slots_and_publishes_local_job_costs(self):
        machine = WorkResources(cores=2, reader=lambda: (4096, 2500), cpu_reader=lambda: None)
        work = BackgroundWork(resources=machine)
        self.addCleanup(work.close)
        entered, release, interactive, queued = (threading.Event() for _ in range(4))
        self.addCleanup(release.set)
        work.submit(lambda: (entered.set(), release.wait(2)), "journal-state-123")
        self.assertTrue(entered.wait(1))
        work.submit(lambda: (interactive.set(), release.wait(2)), "mining-route-plan")
        self.assertTrue(interactive.wait(1))
        work.submit(queued.set, "catalog-sync")
        self.assertFalse(queued.wait(.05))
        self.assertEqual(work.snapshot()["threadWorkerLimit"], 2)
        self.assertEqual(work.snapshot()["active"], 2)
        release.set()
        self.assertTrue(queued.wait(1))
        self.assertTrue(any(row["name"] == "journal-state" and row["runs"] == 1
                            for row in work.snapshot()["threadJobs"]))

    def test_imports_are_serial_and_interactive_work_overtakes_waiting_import(self):
        started, release, foreground, second = (threading.Event() for _ in range(4))
        work = BackgroundWork()
        self.addCleanup(work.close)
        self.addCleanup(release.set)
        work.submit(lambda: (started.set(), release.wait(2)), "edframe-catalog-sync")
        self.assertTrue(started.wait(1))
        work.submit(second.set, "edframe-station-offer-sync")
        work.submit(foreground.set, "mining-route-plan")
        self.assertTrue(foreground.wait(1))
        self.assertFalse(second.is_set())
        self.assertEqual(work.snapshot()["backgroundActive"], 1)
        release.set()
        self.assertTrue(second.wait(1))

    def test_close_does_not_launch_queued_network_jobs(self):
        started, release, queued = (threading.Event() for _ in range(3))
        work = BackgroundWork()
        self.addCleanup(release.set)
        work.submit(lambda: (started.set(), release.wait(2)), "catalog-one")
        self.assertTrue(started.wait(1))
        work.submit(queued.set, "catalog-two")
        work.close()
        release.set()
        self.assertFalse(work.submit(queued.set, "catalog-three"))
        self.assertFalse(queued.wait(.1))

    def test_catalog_checks_coalesce_without_blocking_manual_actions(self):
        owner = CockpitController.__new__(CockpitController)
        owner._edframe_catalog_enabled = True
        owner.syncEdFrameCatalog = Mock()
        owner.syncEdFrameStationOffers = Mock()
        owner.syncEdFrameStateFinds = Mock()
        with patch('ed_companion.phase14.controller_navigation.time.monotonic', return_value=1000), \
             patch('ed_companion.phase14.controller_navigation.QTimer.singleShot') as later:
            owner._queue_background_catalog_sync()
            owner._queue_background_catalog_sync()
            self.assertEqual(later.call_count, 3)
            self.assertEqual([call.args[0] for call in later.call_args_list], [0, 2000, 4000])
        owner._edframe_catalog_enabled = False
        with patch('ed_companion.phase14.controller_navigation.QTimer.singleShot') as later:
            owner._queue_background_catalog_sync()
            later.assert_not_called()

    def test_live_batches_keep_all_domains_and_original_evidence(self):
        owner = CockpitController.__new__(CockpitController)
        owner._eddn_relay_batches = queue.SimpleQueue()
        for name in ('_pending_bgs_snapshots', '_pending_hge_observations',
                     '_pending_mining_candidates', '_pending_mining_powerplay_observations'):
            setattr(owner, name, [])
        evidence = {'observedAt': '2026-10-09T11:00:00Z', 'system': 'Origin'}
        for _ in range(20):
            owner._eddn_relay_batches.put([[evidence], [evidence], [evidence], [evidence]])
        owner._drain_eddn_batches()
        self.assertEqual(len(owner._pending_mining_candidates), 16)
        owner._drain_eddn_batches(force=True)
        self.assertEqual(len(owner._pending_bgs_snapshots), 20)
        self.assertEqual(owner._pending_mining_powerplay_observations[-1], evidence)

    def test_network_counters_are_local_aggregates_and_include_failures(self):
        before = snapshot()
        response = Mock(status_code=200)
        self.assertIs(tracked_get(Mock(return_value=response), 'https://example.test/private?secret=x'), response)
        with self.assertRaises(RuntimeError):
            tracked_get(Mock(side_effect=RuntimeError('offline')), 'https://example.test')
        after = snapshot()
        self.assertEqual(after['catalogRequests'] - before['catalogRequests'], 2)
        self.assertEqual(after['catalogRequestErrors'] - before['catalogRequestErrors'], 1)
        self.assertEqual(after['catalogRequestsActive'], before['catalogRequestsActive'])
        self.assertNotIn('secret', json.dumps(after))

    def test_market_revisions_are_published_once_per_ui_batch(self):
        owner = CockpitController.__new__(CockpitController)
        owner._background_work = BackgroundWork()
        self.addCleanup(owner._background_work.close)
        owner._responsiveness = Responsiveness()
        owner._background_activity = {}
        owner._mining_market_public_revision = 0
        owner._mining_market_revision = 6
        owner.catalogSyncTimer = Mock()
        owner.catalogSyncTimer.remainingTime.return_value = 600000
        owner.miningChanged = Mock()
        owner.backgroundActivityChanged = Mock()
        owner._publish_background_activity()
        owner._publish_background_activity()
        self.assertEqual(owner._mining_market_public_revision, 6)
        owner.miningChanged.emit.assert_called_once()

    def test_verification_waits_for_work_without_a_stale_cache_lock(self):
        owner = CockpitController.__new__(CockpitController)
        owner._mining_plan_deferred = True
        owner._mining_plan_requested_args = ('new-query',)
        owner._mining_plan_cache_key = ('old-data',)
        owner._mining_plan_inputs_pending = Mock(return_value=True)
        owner._mining_plan_key = Mock(return_value=('new-data',))
        self.assertTrue(owner._mining_plan_is_busy())
        # Once inputs finish, the controller resumes the deferred plan itself.
        # A dirty cache without a running worker must not lock the UI forever.
        owner._mining_plan_inputs_pending.return_value = False
        self.assertFalse(owner._mining_plan_is_busy())
        owner._active_mining_plan = 'new-query-worker'
        self.assertTrue(owner._mining_plan_is_busy())
        owner._active_mining_plan = None
        self.assertFalse(owner._mining_plan_is_busy())

    def test_exit_retains_latest_powerplay_when_queued_writer_is_cancelled(self):
        from tests.test_shutdown_thread_join import ShutdownWaitsForInFlightRefreshTests
        with TemporaryDirectory() as folder:
            owner = ShutdownWaitsForInFlightRefreshTests._controller()
            owner.mining_powerplay_observations_file = Path(folder) / 'powerplay.json'
            owner._mining_powerplay_observations = [{'system': 'Origin',
                'observedAt': '2026-10-09T11:00:00Z', 'controllingPower': ''}]
            owner.shutdown()
            self.assertEqual(json.loads(owner.mining_powerplay_observations_file.read_text(encoding='utf-8')),
                             owner._mining_powerplay_observations)


class MiningProcessTests(unittest.TestCase):
    def test_spawned_plan_matches_same_clock_thread_and_does_not_change_databases(self):
        now = datetime.now(timezone.utc)
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'rings.json'
            source.write_text(json.dumps({'identityVersion': 2, 'candidates': [{
                'system': 'Origin', 'ring': 'Origin 1 A Ring', 'coordinates': [0, 0, 0],
                'ringType': 'Metallic', 'reserveLevel': 'Pristine',
                'sourceEvidence': 'CATALOG_CANDIDATE', 'observedAt': now.isoformat(),
                'learnedAt': now.isoformat(), 'hotspots': [{'commodity': 'platinum', 'count': 1}],
            }]}), encoding='utf-8')
            rings = RingCatalogStore(root / 'rings.sqlite3', 'alpha').adopt(source)
            markets = MarketCatalogStore(root / 'markets.sqlite3')
            markets.ingest([{'system': 'Origin', 'station': 'Port', 'commodity': 'platinum',
                'coordinates': [0, 0, 0], 'sellPrice': 250000, 'demand': 10000,
                'observedAt': now.isoformat(), 'landingPadSize': 'L'}], create_backup=False)
            attributes = {'_state': {'system': 'Origin', 'currentPosition': [0, 0, 0]},
                          '_mining_market_cache': {}, '_mining_powerplay_catalog': {},
                          '_mining_powerplay_observations': [], '_mining_market_verification_states': {}}
            args = ('Origin', 'Platinum', 250, 'ALL RESERVES', 'ANY RING', True,
                    'LASER', 'PRICE', 0, 0, 24, 100, False, False, False, False,
                    'L', '', 'REINFORCE', 'ANY', 'ANY')
            payload = {'rings': {'path': str(rings.store.path), 'profile': 'alpha',
                                'head': rings.head, 'overlay': (), 'signals': rings.signals()},
                       'markets': str(markets.path), 'attributes': attributes, 'scope': 'alpha',
                       'args': args, 'clock': now.isoformat()}
            # Exercise real Windows spawn, including the controller's descriptor conversion.
            process = MiningProcess()
            try:
                routes, diagnostic_args, diagnostics, stats = process.compute(payload)
                self.assertNotEqual(stats['miningWorkerPid'], os.getpid())
                self.assertTrue(routes)
                from ed_companion.navigation.mining_process import plan_in_process
                baseline = plan_in_process(payload)
                self.assertEqual((routes, diagnostic_args, diagnostics), baseline[:3])
                newer = rings.store.ingest(rings, [{**next(iter(rings)), 'system': 'New'}], batch_id='new')
                self.assertEqual(rings.revision, payload['rings']['head']['revision'])
                repeated = process.compute(payload)
                self.assertEqual(routes, repeated[0])
                self.assertEqual(len(newer['candidates']), 2)
            finally:
                process.close()

    def test_closed_worker_refuses_new_plan(self):
        process = MiningProcess()
        process.close()
        with self.assertRaises(RuntimeError):
            process.compute({})
