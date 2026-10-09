"""Durable adoption, exact regional projections, histories and lifecycle fences."""
from contextlib import closing
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import Mock, patch

from ed_companion.navigation.catalog_json import catalog_view_value, iter_catalog_candidates
from ed_companion.navigation.mining_finder import merge_mining_candidate_batch, merge_mining_candidates
from ed_companion.navigation.mining_ring_store import RingCatalogStore, RingStoreConflict, TRANSIENT_FIELDS
from ed_companion.phase14.controller import CockpitController
from tests import test_mining_batch as batch_fixture
from tests import test_mining_startup_loading as load_fixture

NOW=datetime(2026,10,9,12,tzinfo=timezone.utc)


def ring(system="Origin", name="1 A Ring", **fields):
    return {"system":system,"ring":system+" "+name,"coordinates":[0,0,0],
            "ringType":"Metallic","reserveLevel":"Pristine",
            "sourceEvidence":"CATALOG_CANDIDATE","observedAt":NOW.isoformat(),
            "learnedAt":NOW.isoformat(),**fields}


def plain(rows):
    return [{k:catalog_view_value(v) for k,v in row.items() if k not in TRANSIENT_FIELDS} for row in rows]


class RingStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.source=self.root/"rings.json"
        self.store=RingCatalogStore(self.root/"rings.sqlite3","alpha")

    def adopt(self,rows,**root):
        self.source.write_text(json.dumps({"identityVersion":2,**root,"candidates":rows},ensure_ascii=False),encoding="utf-8")
        return self.store.adopt(self.source)

    def test_lossless_raw_adoption_metadata_order_and_original(self):
        rows=[ring(note={"unknown":[1,"Ü",{"arr":[]}]},ageSeconds=100),None,42,ring("Far",coordinates=[900,0,0])]
        view=self.adopt(rows,unknownRoot={"keep":[3,2,1]})
        before=self.source.read_bytes()
        self.assertEqual(list(view.raw_records()),rows)
        self.assertEqual(view.head["root"]["unknownRoot"],{"keep":[3,2,1]})
        self.assertEqual(len(view),2)
        self.assertEqual(plain(view),plain([rows[0],rows[3]]))
        self.assertEqual(self.source.read_bytes(),before)
        with self.store.reader() as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            self.assertEqual(db.execute("SELECT rtreecheck('spatial')").fetchone()[0],"ok")

    def test_original_legacy_identity_normalized_with_raw_versions_retained(self):
        rows=[ring(name="1 a",note="lower"),ring(name="1 A Ring",note="upper")]
        view=self.adopt(rows,identityVersion=1)
        self.assertEqual(list(view.raw_records()),rows)
        self.assertEqual(plain(view),plain(merge_mining_candidates(rows)))
        self.assertEqual(view.head["root"]["identityVersion"],2)

    def test_empty_new_profile_and_unreadable_adoption_do_not_destroy_files(self):
        view=self.store.adopt(self.source)
        self.assertEqual(len(view),0)
        self.assertFalse(self.source.exists())
        other=RingCatalogStore(self.root/"other.sqlite3","alpha")
        self.source.write_text('{"candidates":[{},',encoding="utf-8")
        before=self.source.read_bytes()
        with self.assertRaises(ValueError): other.adopt(self.source)
        self.assertFalse(other.path.exists())
        self.assertEqual(self.source.read_bytes(),before)

    def test_stream_chunks_bom_root_keys_and_trailing_content(self):
        rows=[ring(note='a\\b "ц" '+"a"*200)]
        self.source.write_text(json.dumps({"extra":[1,2],"candidates":rows}),encoding="utf-8-sig")
        root={}
        self.assertEqual(list(iter_catalog_candidates(self.source,root,chunk_size=3)),rows)
        self.assertEqual(root,{"extra":[1,2]})
        for text in ('{"candidates":[],"candidates":[]}','{"candidates":[]}x','{}'):
            self.source.write_text(text,encoding="utf-8")
            with self.assertRaises(ValueError): list(iter_catalog_candidates(self.source,{},chunk_size=2))

    def test_targeted_merge_matches_legacy_helper_and_old_view_is_unchanged(self):
        rows=[ring("Other"),ring("Origin",yieldStats=[{"commodity":"platinum","prospectorHits":2,"averageProportion":30}]),ring("Last")]
        additions=[ring(sourceEvidence="LOCAL_CONFIRMED",yieldStats=[{"commodity":"platinum","prospectorHits":1,"averageProportion":0}]),ring("New")]
        old=self.adopt(rows)
        merged,_=merge_mining_candidate_batch(rows,additions)
        new=self.store.ingest(old,additions,batch_id="one")["candidates"]
        self.assertEqual(plain(new),plain(merged))
        self.assertEqual(plain(old),plain(rows))
        self.assertEqual(list(new.raw_records()),rows)
        self.assertEqual(len(list(self.store.pending_history("mining_observations"))),2)
        self.assertEqual(len(list(self.store.pending_history("mining_catalog"))),1)

    def test_batch_replay_is_idempotent_even_after_later_commits(self):
        old=self.adopt([ring()])
        addition=ring(prospectorSampleCount=3)
        one=self.store.ingest(old,[addition],batch_id="one")["candidates"]
        two=self.store.ingest(one,[ring("New")],batch_id="two")["candidates"]
        replay=self.store.ingest(old,[addition],batch_id="one")["candidates"]
        self.assertEqual(replay.revision,two.revision)
        self.assertEqual(plain(replay),plain(two))
        with self.assertRaises(RingStoreConflict): self.store.ingest(old,[addition],batch_id="new")

    def test_reset_retains_versions_original_and_rejects_late_worker(self):
        old=self.adopt([ring(),ring("Other")])
        original=self.source.read_bytes()
        reset=self.store.reset(old)
        self.assertEqual(len(reset),0)
        self.assertEqual(plain(old),plain([ring(),ring("Other")]))
        self.assertEqual(self.source.read_bytes(),original)
        with self.assertRaises(RingStoreConflict): self.store.ingest(old,[ring("Late")])
        self.assertEqual(len(self.store.adopt(self.source)),0)
        self.assertEqual(len(list(self.store.pending_history("mining_catalog"))),2)

    def test_archive_error_has_durable_outbox_and_restart_recovers(self):
        view=self.adopt([ring(note="before")])
        archive=Mock();archive.archive.side_effect=sqlite3.OperationalError("locked")
        result=self.store.ingest(view,[ring(note="after")],archive=archive)
        self.assertEqual(result["archiveError"],"OperationalError")
        restarted=RingCatalogStore(self.store.path,"alpha")
        self.assertTrue(list(restarted.pending_history("mining_observations")))
        archive=Mock()
        self.assertEqual(restarted.flush_history(archive),"")
        self.assertEqual(list(restarted.pending_history("mining_observations")),[])
        self.assertEqual({call.args[0] for call in archive.archive.call_args_list},{"mining_observations","mining_catalog"})

    def test_profile_and_database_replacement_fences(self):
        view=self.adopt([ring()])
        with self.assertRaises(RingStoreConflict): RingCatalogStore(self.store.path,"beta").view()
        other=RingCatalogStore(self.root/"other.sqlite3","alpha").adopt(self.source)
        with self.assertRaises(RingStoreConflict): other.store.ingest(view,[ring()])

    def test_legacy_reorder_unchanged_payload_and_changed_refresh_are_lossless(self):
        rows=[ring(),ring("Other")]
        old=self.adopt(rows)
        new=self.store.ingest(old,[ring("OnlySQLite")])["candidates"]
        self.source.write_text(json.dumps({"identityVersion":2,"candidates":rows[::-1]}),encoding="utf-8")
        refreshed=self.store.adopt(self.source)
        self.assertEqual(plain(refreshed),plain(new))
        self.source.write_text('{"candidates":[',encoding="utf-8")
        with self.assertRaises(ValueError): self.store.adopt(self.source)
        self.assertEqual(plain(self.store.view()),plain(new))

    def test_region_rounding_nan_missing_current_and_unbounded_no_truncation(self):
        rows=[ring("Edge",coordinates=[250.049,0,0]),ring("Outside",coordinates=[250.051,0,0]),
              ring("Missing",coordinates=None),ring("Origin",coordinates=None),ring("NaN",coordinates=[float("nan"),0,0])]
        view=self.adopt(rows)
        self.assertEqual([r["system"] for r in view.nearby("Origin",[0,0,0],250)],["Edge","Origin","NaN"])
        self.assertEqual([r["system"] for r in view.nearby("Origin",None,250)],["Origin"])
        view.MAX_REGION_ROWS=1
        self.assertEqual(len(list(view.nearby("Origin",[0,0,0],0))),5)

    def test_overlay_moved_in_and_out_unknown_commodities_and_origin(self):
        rows=[ring("Outside",coordinates=[500,0,0]),ring("Inside",coordinates=[1,0,0])]
        view=self.adopt(rows)
        overlay=[ring("Outside",coordinates=[2,0,0],sourceEvidence="LOCAL_CONFIRMED",hotspots=[{"commodity":"newore","count":1}]),
                 ring("Inside",coordinates=[501,0,0],sourceEvidence="LOCAL_CONFIRMED"),ring("New",coordinates=[3,0,0])]
        projected=view.with_overlay(overlay)
        self.assertEqual([r["system"] for r in projected.nearby("Origin",[0,0,0],250)],["Outside","New"])
        self.assertEqual(projected.coordinates_for("Outside"),[2,0,0])
        self.assertEqual(len(projected),3)
        self.assertIn({"id":"newore"},projected.signals())
        self.assertEqual(plain(projected),plain(merge_mining_candidate_batch(rows,overlay)[0]))

    def test_overlay_merges_only_its_indexed_targets_preserving_full_order(self):
        rows=[ring(str(i),coordinates=[i,0,0]) for i in range(100)]
        additions=[ring("50",sourceEvidence="LOCAL_CONFIRMED"),ring("New")]
        view=self.adopt(rows).with_overlay(additions)
        expected=plain(merge_mining_candidate_batch(rows,additions)[0])
        sizes=[]
        def merge(existing,incoming):
            existing=list(existing);sizes.append(len(existing))
            return merge_mining_candidate_batch(existing,incoming)
        with patch("ed_companion.navigation.mining_ring_store.merge_mining_candidate_batch",side_effect=merge):
            self.assertEqual(plain(view.nearby("Origin",[0,0,0],250)),expected)
        self.assertEqual(sizes,[1])

    def test_summary_matches_original_with_overlay_and_dynamic_age(self):
        rows=[ring(),ring("Other",observedAt="2000-01-01T00:00:00Z"),
              ring("Bad",observedAt="invalid",coordinates=None),ring("Shared",name="2 A Ring"),
              ring("Whitespace",sourceEvidence=" ",evidence="LIVE_REPORTED",planetaryMiningLocationCount="0")]
        view=self.adopt(rows).with_overlay([ring("Shared",name="3 A Ring",sourceEvidence="LOCAL_CONFIRMED"),ring(sourceEvidence="LIVE_REPORTED",hotspots=[{"commodity":"platinum"}])])
        for now in (NOW,NOW+timedelta(days=400)):
            with patch("ed_companion.navigation.mining_finder.datetime") as dt:
                dt.now.return_value=now;dt.fromisoformat.side_effect=datetime.fromisoformat;dt.min=datetime.min
                expected=CockpitController._summarize_mining_rows(list(view))
            self.assertEqual(view.summary(now),expected)

    def test_reset_cutoff_applies_to_catalog_and_local_overlay(self):
        view=self.adopt([ring(learnedAt="2020-01-01"),ring("New",learnedAt="2026-10-10")],resetAt="2026-10-09")
        self.assertEqual(len(view),1)
        self.assertEqual([r["system"] for r in view],["New"])
        self.assertEqual(view.summary(NOW)["total"],1)
        self.assertEqual(view.system_names()[0],["New"])

    def test_concurrent_readers_and_writer_hold_old_revision(self):
        view=self.adopt([ring()])
        barrier=threading.Barrier(3);results=[]
        def read():
            barrier.wait();results.append(plain(view));barrier.wait()
        threads=[threading.Thread(target=read) for _ in range(2)]
        for t in threads:t.start()
        barrier.wait();self.store.ingest(view,[ring("New")]);barrier.wait()
        for t in threads:t.join(timeout=3)
        self.assertEqual(results,[plain([ring()])]*2)

    def test_source_changes_during_adoption_never_publish_partial_store(self):
        self.source.write_text(json.dumps({"identityVersion":2,"candidates":[ring()]}),encoding="utf-8")
        original=RingCatalogStore._insert
        def change(db,seq,revision,row):
            original(db,seq,revision,row)
            self.source.write_text(json.dumps({"identityVersion":2,"candidates":[ring("Changed")]}),encoding="utf-8")
        with patch.object(RingCatalogStore,"_insert",side_effect=change):
            with self.assertRaises(ValueError): self.store.adopt(self.source)
        self.assertFalse(self.store.path.exists())
        self.assertFalse(list(self.root.glob("*.adopting-*")))

    def test_failed_ingestion_rolls_back_payloads_outbox_and_revision(self):
        view=self.adopt([ring()])
        original=RingCatalogStore._insert
        def fail(db,seq,revision,row):
            original(db,seq,revision,row)
            raise sqlite3.OperationalError("disk fixture")
        with patch.object(RingCatalogStore,"_insert",side_effect=fail):
            with self.assertRaises(sqlite3.OperationalError): self.store.ingest(view,[ring("New")])
        self.assertEqual(self.store.view().revision,view.revision)
        self.assertEqual(plain(self.store.view()),plain(view))
        self.assertEqual(list(self.store.pending_history("mining_observations")),[])


class RingControllerTests(unittest.TestCase):
    setUp=RingStoreTests.setUp
    adopt=RingStoreTests.adopt
    # Run lifecycle tests against the production worker dispatch rather than
    # duplicate the domain merge implementation in the harness.
    def controller(self):
        c=batch_fixture.MiningBatchTests().controller()
        view=self.adopt([ring()])
        c.mining_catalog_file=self.source
        c._mining_catalog={**view.head["root"],"candidates":view}
        c.miningRingResetFinished=Mock()
        return c

    def test_shutdown_reclaims_committed_worker_once(self):
        c=self.controller()
        c._dispatch_mining_observation_batch([ring(prospectorSampleCount=3)])
        result,_=batch_fixture.MiningBatchTests().run_worker(c)
        c._shutdown_complete=True
        c.flushHgeObservationBatch(True)
        self.assertEqual(plain(c._mining_catalog["candidates"]),plain(result["candidates"]))
        c._finish_mining_observation_batch(result)
        self.assertIsNone(c._active_mining_observation_batch)
        self.assertEqual(c._pending_mining_candidates,[])

    def test_reset_worker_defers_ui_and_preserves_original_json(self):
        c=self.controller()
        before=self.source.read_bytes()
        c._edframe_catalog_enabled=False
        c._mining_system_names=[];c._mining_system_name_keys=[]
        c.resetMiningCatalog()
        self.assertEqual(len(c._mining_catalog["candidates"]),1)
        self.assertEqual(c._start_network_worker.call_args.args[1],"mining-ring-reset")
        c._start_network_worker.call_args.args[0]()
        result=c.miningRingResetFinished.emit.call_args.args[0]
        self.assertNotIn("error",result)
        c._finish_mining_ring_reset(result)
        self.assertEqual(len(c._mining_catalog["candidates"]),0)
        self.assertEqual(self.source.read_bytes(),before)

    def test_worker_captures_profile_store_archive_and_rejects_stale_publication(self):
        c=self.controller();original=c._mining_catalog["candidates"]
        c._dispatch_mining_observation_batch([ring("Captured")])
        c._history_archive=Mock();c.profile_context=Mock(key="replacement")
        c._profile_generation+=1
        result,_=batch_fixture.MiningBatchTests().run_worker(c)
        self.assertNotIn("error",result)
        c._history_archive.archive.assert_not_called()
        c._finish_mining_observation_batch(result)
        self.assertIs(c._mining_catalog["candidates"],original)
        self.assertEqual(len(original.store.view()),2)

    def test_no_global_ring_iteration_for_summary_and_commodity_ui(self):
        c=self.controller()
        c._state={"system":"Origin","currentPosition":[0,0,0],"localMiningEvidence":{
            "candidates":[ring("New",hotspots=[{"commodity":"futureore","count":2}])]}}
        rows=c._build_mining_rows(c._state,c._mining_catalog)
        c._mining_rows=lambda:rows
        with patch.object(type(rows),"__iter__",side_effect=AssertionError("global read")):
            self.assertEqual(CockpitController._summarize_mining_rows(rows)["total"],2)
            self.assertTrue(c._mining_commodity_catalog())

    def test_shutdown_after_reset_commit_uses_current_disk_epoch(self):
        c=self.controller()
        c.resetMiningCatalog()
        c._start_network_worker.call_args.args[0]()
        c._pending_mining_candidates=[ring("After",learnedAt="2099-01-01",observedAt="2099-01-01")]
        c._shutdown_complete=True
        c.flushHgeObservationBatch(True)
        self.assertEqual([r["system"] for r in c._mining_catalog["candidates"]],["After"])
        self.assertEqual(c._pending_mining_candidates,[])


class RingLoadTests(unittest.TestCase):
    def test_demand_load_publishes_disk_view_and_queued_observations(self):
        harness=load_fixture.MiningStartupLoadingTests();harness.setUp()
        self.addCleanup(harness.doCleanups)
        c=harness.c;c._mining_ring_storage_enabled=True
        c._pending_mining_candidates=[ring("Queued")]
        c._ensure_mining_catalog_loaded()
        harness.complete_load()
        view=c._mining_catalog["candidates"]
        self.assertTrue(hasattr(view,"nearby"))
        worker,name=harness.workers.pop(0)
        self.assertEqual(name,"mining-observation-merge")
        worker();c._finish_mining_observation_batch(c.miningObservationBatchFinished.emit.call_args.args[0])
        self.assertEqual([r["system"] for r in c._mining_catalog["candidates"]],["Test","Queued"])
        self.assertEqual(json.loads(c.mining_catalog_file.read_text()),harness.disk)


if __name__=="__main__": unittest.main()
