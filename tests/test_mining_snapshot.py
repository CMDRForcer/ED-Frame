"""Complete conditional snapshots, bounded storage and race/fallback safety."""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import requests
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import Mock, patch

from ed_companion.navigation.mining_finder import fetch_edframe_mining_candidates
from ed_companion.navigation.mining_snapshot import MiningSnapshotStore, snapshot_key
from tests import test_mining_refresh as refresh_tests
from tests.test_mining_refresh import QUERY, ORIGIN, MODULE, Session
from ed_companion.navigation.mining_refresh import fetch_mining_refresh


REV = "s1-" + "a" * 64
NEW = "s1-" + "b" * 64
STAMP = "2026-09-01T12:00:00Z"


def site(ring="A", proportion=25):
    return dict(system="Test", ring="Test " + ring + " Ring", x=1, y=2, z=3,
                observedAt=STAMP, receivedAt=STAMP, evidence="LIVE_REPORTED",
                hotspots=[dict(commodity="platinum", count=1)],
                prospectorSampleCount=10,
                yieldStats=[dict(commodity="platinum", averageProportion=proportion,
                                proportionSamples=10, proportionTotal=proportion * 10,
                                prospectorHits=10, lastObservedAt=STAMP)])


def page(rows=None, revision=REV, **extra):
    return dict(results=rows or [], snapshotProtocol=1, revision=revision,
                snapshotStatic="c" * 64, snapshotComplete=True,
                notModified=False, hasMore=False, communityReferences=[], **extra)


class Getter:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        data = next(self.responses)
        if data == 409:
            return Mock(status_code=409)
        return Mock(status_code=200, json=Mock(return_value=data))


class SnapshotClock(datetime):
    @classmethod
    def now(cls, tz=None):
        fixed = cls(2026, 10, 10, 12, tzinfo=timezone.utc)
        return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)


@patch('ed_companion.navigation.mining_finder.datetime', SnapshotClock)
class MiningSnapshotTests(unittest.TestCase):
    def fetch(self, get, **kwargs):
        return fetch_edframe_mining_candidates("Test", get, commodity="platinum",
                                               origin=[0, 0, 0], max_distance=250, **kwargs)

    def test_full_then_restart_uses_one_conditional_request_without_changing_observation_age(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "sites.sqlite3")
            store = MiningSnapshotStore(path)
            coverage = {}
            original = self.fetch(Getter(page([site()])), snapshot_store=store, diagnostics=coverage)
            store.save(coverage["_snapshot"])
            get = Getter({**page(), "notModified": True})
            checked = {}
            reused = self.fetch(get, snapshot_store=MiningSnapshotStore(path), diagnostics=checked)
            self.assertEqual(reused, original)
            self.assertEqual(reused[0]["observedAt"], STAMP)
            self.assertEqual(reused[0]["learnedAt"], STAMP)
            self.assertTrue(checked["notModified"])
            self.assertEqual(checked["pages"], 1)
            self.assertFalse(checked["bounded"])
            self.assertEqual(get.calls[0][1]["params"]["known_revision"], REV)
            self.assertNotIn("_snapshot", checked)  # no redundant cache write

    def test_changed_yield_hotspot_and_overlap_are_not_replaced_by_cached_rows(self):
        with TemporaryDirectory() as directory:
            store = MiningSnapshotStore(Path(directory, "sites.sqlite3"))
            coverage = {}
            self.fetch(Getter(page([site()])), snapshot_store=store, diagnostics=coverage)
            store.save(coverage["_snapshot"])
            updated = site(proportion=40)
            updated["hotspots"][0]["count"] = 2
            updated["communityOverlapReports"] = [{"status": "COMMUNITY_REPORTED_UNDATED"}]
            checked = {}
            rows = self.fetch(Getter(page([updated], NEW)), snapshot_store=store, diagnostics=checked)
            self.assertEqual(rows[0]["yieldStats"][0]["averageProportion"], 40)
            self.assertEqual(rows[0]["hotspots"][0]["count"], 2)
            self.assertTrue(rows[0]["communityOverlapReports"])
            self.assertEqual(checked["_snapshot"]["revision"], NEW)

    def test_paging_continues_exact_revision_and_saves_only_after_final_page(self):
        first = {**page([site("A")]), "hasMore": True, "nextOffset": 1000, "nextCursor": "cursor"}
        get = Getter(first, page([site("B")]))
        coverage = {}
        self.assertEqual(len(self.fetch(get, diagnostics=coverage)), 2)
        self.assertEqual(get.calls[1][1]["params"]["snapshot_revision"], REV)
        self.assertEqual(get.calls[1][1]["params"]["cursor"], "cursor")
        self.assertTrue(coverage["_snapshot"]["complete"])

    def test_opaque_frozen_cursors_keep_one_projection_and_original_observation_times(self):
        token = "f1." + "d" * 32
        responses = [{**page([site("A")]), "hasMore": True, "snapshotComplete": False,
                      "snapshotAt": "2026-10-09T12:00:00Z", "nextOffset": 5000,
                      "nextCursor": token + ".5000"},
                     {**page([site("B")]), "hasMore": True, "snapshotComplete": False,
                      "snapshotAt": "2026-10-09T12:00:00Z", "nextOffset": 10000,
                      "nextCursor": token + ".10000"}, page([site("C")])]
        get = Getter(*responses)
        coverage = {}
        rows = self.fetch(get, diagnostics=coverage)
        self.assertEqual([row["ring"] for row in rows], ["Test A Ring", "Test B Ring", "Test C Ring"])
        self.assertEqual(get.calls[1][1]["params"]["cursor"], token + ".5000")
        self.assertEqual(get.calls[2][1]["params"]["snapshot_revision"], REV)
        self.assertTrue(coverage["_snapshot"]["complete"])
        self.assertTrue(all(row["observedAt"] == STAMP and row["learnedAt"] == STAMP for row in rows))

    def test_frozen_capacity_limit_does_not_save_a_complete_local_snapshot(self):
        responses = [{**page([site(str(i))]), "hasMore": True, "snapshotComplete": False,
                      "snapshotTruncated": True, "nextOffset": (i + 1) * 5000,
                      "nextCursor": "f1." + "d" * 32 + "." + str((i + 1) * 5000)}
                     for i in range(10)]
        get = Getter(*responses)
        coverage = {}
        self.assertEqual(len(self.fetch(get, diagnostics=coverage)), 10)
        self.assertEqual(len(get.calls), 10)
        self.assertTrue(coverage["bounded"])
        self.assertNotIn("_snapshot", coverage)

    def test_page_race_restarts_once_and_discards_mixed_partial_records(self):
        first = {**page([site("Old")]), "hasMore": True, "nextOffset": 1000}
        for changed in (409, page([site("Bad")], NEW), {"results": [], "hasMore": False}):
            get = Getter(first, changed, page([site("New")], NEW))
            coverage = {}
            rows = self.fetch(get, diagnostics=coverage)
            self.assertEqual([r["ring"] for r in rows], ["Test New Ring"])
            self.assertEqual(get.calls[2][1]["params"]["offset"], 0)
            self.assertNotIn("snapshot_revision", get.calls[2][1]["params"])
            self.assertEqual(coverage["revision"], NEW)

    def test_continuously_changing_pages_keep_fresh_provisional_results_without_completeness_proof(self):
        first = {**page([site()]), "hasMore": True, "nextOffset": 1000}
        coverage = {}
        rows = self.fetch(Getter(first, 409, first, 409,
                                 {"results": [site("Latest")], "hasMore": False}), diagnostics=coverage)
        self.assertEqual(rows[0]["ring"], "Test Latest Ring")
        self.assertTrue(coverage["bounded"])
        self.assertFalse(coverage["consistent"])
        self.assertNotIn("_snapshot", coverage)

    def test_page_cap_keeps_partial_results_bounded_and_never_cacheable(self):
        get = Getter(*[{**page([site(str(i))]), "hasMore": True, "nextOffset": (i + 1) * 1000}
                       for i in range(50)])
        coverage = {}
        self.assertEqual(len(self.fetch(get, diagnostics=coverage)), 50)
        self.assertTrue(coverage["bounded"])
        self.assertNotIn("_snapshot", coverage)

    def test_legacy_paged_and_unpaged_servers_never_issue_version_proof(self):
        for response in ({"results": [site()], "hasMore": False}, {"results": [site()]}):
            coverage = {}
            self.assertEqual(len(self.fetch(Getter(response), diagnostics=coverage)), 1)
            self.assertNotIn("revision", coverage)
            self.assertNotIn("_snapshot", coverage)

    def test_missing_partial_or_malformed_snapshot_never_accepts_not_modified(self):
        for response in ({**page(), "notModified": True},
                         {**page([site()]), "revision": "invalid"},
                         {**page([site()]), "hasMore": None},
                         {**page([site()]), "snapshotComplete": False},
                         page([{"system": "Test"}])):
            with self.assertRaises(ValueError):
                self.fetch(Getter(response))

    def test_failed_revision_service_falls_back_to_fresh_unversioned_paging(self):
        for failure in (requests.Timeout("slow revision"), Mock(status_code=503)):
            legacy = Mock(status_code=200, json=Mock(return_value={"results": [site()], "hasMore": False}))
            get = Mock(side_effect=[failure, legacy])
            coverage = {}
            self.assertEqual(len(self.fetch(get, diagnostics=coverage)), 1)
            self.assertIn("snapshot_protocol", get.call_args_list[0].kwargs["params"])
            self.assertNotIn("snapshot_protocol", get.call_args_list[1].kwargs["params"])
            self.assertNotIn("_snapshot", coverage)

    def test_large_radius_keeps_original_paging_without_expensive_revision_probe(self):
        get = Getter({"results": [site()], "hasMore": False})
        rows = fetch_edframe_mining_candidates("Test", get, origin=[0, 0, 0], max_distance=1000)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("snapshot_protocol", get.calls[0][1]["params"])

    def test_corruption_reset_and_profile_isolation_force_full_fetch(self):
        with TemporaryDirectory() as directory:
            store = MiningSnapshotStore(Path(directory, "alpha.sqlite3"))
            coverage = {}
            self.fetch(Getter(page([site()])), diagnostics=coverage)
            snapshot = coverage["_snapshot"]
            store.save(snapshot)
            self.assertIsNone(MiningSnapshotStore(Path(directory, "beta.sqlite3")).load(snapshot["key"]))
            with closing(sqlite3.connect(store.path)) as conn, conn:
                conn.execute("UPDATE snapshots SET checksum='corrupt'")
            get = Getter(page([site()], NEW))
            self.fetch(get, snapshot_store=store)
            # The small header is only a hint. A changed full response never
            # uses the corrupt cached payload and needs no pre-HTTP expansion.
            self.assertEqual(get.calls[0][1]["params"]["known_revision"], REV)
            store.save(snapshot)
            store.reset()
            self.assertIsNone(store.load(snapshot["key"]))

    def test_query_scope_server_and_projection_bind_cache(self):
        base = dict(x=0, y=0, z=0, max_distance=250, commodity="platinum", limit=1000)
        key = snapshot_key("https://server", base)
        for change in (dict(x=1), dict(max_distance=500), dict(commodity="osmium"), dict(limit=200)):
            self.assertNotEqual(key, snapshot_key("https://server", {**base, **change}))
        self.assertNotEqual(key, snapshot_key("https://other", base))
        self.assertEqual(key, snapshot_key("https://server", {**base, "cursor": "c", "offset": 2}))

    def test_changed_response_never_loads_or_decompresses_old_rows(self):
        with TemporaryDirectory() as directory:
            store = MiningSnapshotStore(Path(directory, "sites.sqlite3"))
            coverage = {}
            self.fetch(Getter(page([site()])), diagnostics=coverage)
            store.save(coverage["_snapshot"])
            with patch.object(store, "load", wraps=store.load) as load:
                rows = self.fetch(Getter(page([site(proportion=40)], NEW)), snapshot_store=store)
            load.assert_not_called()
            self.assertEqual(rows[0]["yieldStats"][0]["averageProportion"], 40)

    def test_corrupt_payload_after_unchanged_hint_retries_fresh_and_keeps_age(self):
        with TemporaryDirectory() as directory:
            store = MiningSnapshotStore(Path(directory, "sites.sqlite3"))
            coverage = {}
            original = self.fetch(Getter(page([site()])), diagnostics=coverage)
            store.save(coverage["_snapshot"])
            with closing(sqlite3.connect(store.path)) as conn, conn:
                conn.execute("UPDATE snapshots SET checksum='bad'")
            get = Getter({**page(), "notModified": True}, page([site()], NEW))
            checked = {}
            rows = self.fetch(get, snapshot_store=store, diagnostics=checked)
            self.assertEqual(rows, original)
            self.assertEqual(len(get.calls), 2)
            self.assertNotIn("known_revision", get.calls[1][1]["params"])
            self.assertEqual(get.calls[1][1]["params"]["snapshot_protocol"], 1)
            self.assertNotIn("notModified", checked)
            store.save(checked["_snapshot"])
            self.assertEqual(store.revision(checked["_snapshot"]["key"]), NEW)

    def test_replaced_cache_during_request_cannot_return_different_revision_rows(self):
        with TemporaryDirectory() as directory:
            store = MiningSnapshotStore(Path(directory, "sites.sqlite3"))
            coverage = {}
            self.fetch(Getter(page([site()])), diagnostics=coverage)
            snapshot = coverage["_snapshot"]
            store.save(snapshot)
            get = Getter({**page(), "notModified": True}, page([site(proportion=40)], NEW))
            def replace(url, **kwargs):
                if len(get.calls) == 0:
                    store.save({**snapshot, "revision": NEW, "candidates": [{"system": "Wrong", "ring": "Wrong"}]})
                return get(url, **kwargs)
            rows = self.fetch(replace, snapshot_store=store)
            self.assertEqual(rows[0]["system"], "Test")
            self.assertEqual(rows[0]["yieldStats"][0]["averageProportion"], 40)
            self.assertEqual(len(get.calls), 2)

    def test_missing_hint_and_expected_revision_mismatch_are_never_row_proof(self):
        with TemporaryDirectory() as directory:
            store = MiningSnapshotStore(Path(directory, "sites.sqlite3"))
            self.assertIsNone(store.revision("missing"))
            snapshot = dict(key="test", revision=REV, candidates=[{"system": "Test", "ring": "Test"}], complete=True)
            store.save(snapshot)
            self.assertEqual(store.revision("test"), REV)
            self.assertIsNone(store.load("test", expected_revision=NEW))
            self.assertIsNotNone(store.load("test", expected_revision=REV))
            with closing(sqlite3.connect(store.path)) as conn, conn:
                conn.execute("UPDATE snapshots SET revision='bad'")
            self.assertIsNone(store.revision("test"))

    def test_storage_is_bounded_and_partial_snapshots_cannot_be_saved(self):
        with TemporaryDirectory() as directory:
            store = MiningSnapshotStore(Path(directory, "sites.sqlite3"))
            snapshot = dict(key="old", revision=REV, candidates=[], complete=True)
            with self.assertRaises(ValueError):
                store.save({**snapshot, "complete": False})
            for index in range(10):
                store.save({**snapshot, "key": str(index)})
            with closing(sqlite3.connect(store.path)) as conn, conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 8)
            self.assertIsNone(store.load("0"))
            self.assertIsNotNone(store.load("9"))

    def test_corrupt_disposable_cache_cannot_block_explicit_profile_reset(self):
        with TemporaryDirectory() as directory:
            store = MiningSnapshotStore(Path(directory, "sites.sqlite3"))
            store.save(dict(key="test", revision=REV, candidates=[], complete=True))
            with patch.object(store, "_connect", side_effect=sqlite3.DatabaseError("bad cache")):
                store.reset()
            self.assertFalse(store.path.exists())

    def test_reused_diagnostics_cannot_carry_an_old_completeness_proof(self):
        coverage = {}
        self.fetch(Getter(page([site()])), diagnostics=coverage)
        self.assertIn("_snapshot", coverage)
        self.fetch(Getter({"results": [site()], "hasMore": False}), diagnostics=coverage)
        self.assertNotIn("_snapshot", coverage)
        self.assertNotIn("revision", coverage)

    def test_material_domain_still_fetches_when_sites_are_not_modified(self):
        def unchanged(*_args, **kwargs):
            kwargs["diagnostics"].update(count=1, bounded=False, pages=1, notModified=True)
            return [site()]
        with patch(MODULE + "fetch_edframe_mining_candidates", side_effect=unchanged) as rings, \
                patch(MODULE + "fetch_edframe_powerplay", return_value=[{"fresh": True}]) as powerplay, \
                patch(MODULE + "fetch_market_imports", return_value=[{"fresh": True}]) as markets:
            result = fetch_mining_refresh(QUERY, origin=ORIGIN, session_factory=Session,
                                          snapshot_path="not-created.sqlite3")
        self.assertIsInstance(rings.call_args.kwargs["snapshot_store"], MiningSnapshotStore)
        powerplay.assert_called_once()
        markets.assert_called_once()
        self.assertEqual(result["markets"], [{"fresh": True}])
        self.assertTrue(result["siteCoverage"]["notModified"])

    def test_worker_persists_ring_success_even_when_market_fails_and_stale_result_never_writes(self):
        helper = refresh_tests.MiningRefreshTests()
        controller = helper.controller()
        controller._active_mining_market_request = {"id": "request"}
        snapshot = dict(key="test", revision=REV, candidates=[], complete=True)
        with patch("ed_companion.phase14.controller_navigation.MiningSnapshotStore") as store:
            result = helper.result(success=False, siteSnapshot=snapshot, siteSnapshotPath="profile-sites.sqlite3")
            controller._persist_mining_market_result(result, controller._mining_market_store, threading.Lock())
            store.return_value.save.assert_called_once_with(snapshot)
            store.reset_mock()
            for change in (dict(id="old"), dict(profileKey="beta"), dict(generation=4), dict(path="other.json")):
                result = helper.result(siteSnapshot=snapshot, siteSnapshotPath="old-sites.sqlite3", **change)
                controller._persist_mining_market_result(result, controller._mining_market_store, threading.Lock())
            store.assert_not_called()


if __name__ == "__main__":
    unittest.main()
