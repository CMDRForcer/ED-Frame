import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from edframe_catalog import api
from edframe_catalog.mining_revision import mining_content_revision as mining_revision, static_revision
from edframe_catalog.mining_pages import FrozenPages


REV = "s1-" + "a" * 64
QUERY = dict(commodity="platinum", system="", max_age_days=3650, x=1., y=2., z=3.,
             max_distance=250., limit=1000, include_community_overlaps=True,
             include_ring_candidates=True)
PARTS = {k: k for k in ("membership", "sites", "samples", "materials", "metadata", "positions")}


@patch.object(api, "MINING_SNAPSHOT_PROTOCOL_ENABLED", True)
class MiningRevisionTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.pages = FrozenPages(Path(directory.name, "pages.sqlite3"))
        selected = patch.object(api, "configured_pages", return_value=self.pages)
        selected.start()
        self.addCleanup(selected.stop)

    def test_uninstalled_markers_never_trigger_content_fallback(self):
        with patch.object(api, "connection") as connection, \
                patch.object(api, "mining_revision", side_effect=ValueError("not ready")):
            conn = connection.return_value.__enter__.return_value
            with self.assertRaises(HTTPException) as raised:
                api.search_sites(**QUERY, offset=0, snapshot_protocol=1, known_revision=REV)
        self.assertEqual(raised.exception.status_code, 503)
        conn.execute.assert_called_once_with("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")

    def connection(self):
        conn = MagicMock()
        conn.parts = dict(PARTS)
        conn.scope_names = ["regional", "regional", "boundary"]
        def read(sql, values):
            data = {"membership": conn.parts["membership"], "names": conn.scope_names} \
                if " AS names" in sql else {k: v for k, v in conn.parts.items() if k != "membership"}
            cursor = MagicMock()
            cursor.fetchone.return_value = data
            return cursor
        conn.execute.side_effect = read
        return conn

    def test_each_domain_deletion_membership_and_query_invalidate_revision(self):
        conn = self.connection()
        with patch("edframe_catalog.mining_revision.static_revision", return_value="static"):
            original = mining_revision(conn, QUERY)
            for key in PARTS:
                conn.parts = {**PARTS, key: "changed"}
                self.assertNotEqual(mining_revision(conn, QUERY), original, key)
            conn.parts = dict(PARTS)
            self.assertNotEqual(mining_revision(conn, {**QUERY, "commodity": "osmium"}), original)
        with patch("edframe_catalog.mining_revision.static_revision", return_value="new references"):
            self.assertNotEqual(mining_revision(conn, QUERY), original)

    def test_digest_sql_covers_both_yield_tables_and_same_system_fallback_metadata(self):
        conn = self.connection()
        mining_revision(conn, QUERY)
        scope_sql, scope_values = conn.execute.call_args_list[0].args
        sql, values = conn.execute.call_args_list[1].args
        for query_sql, params in ((scope_sql, scope_values), (sql, values)):
            self.assertEqual(query_sql.count("%s"), len(params))
        for name in ("mining_sites", "mining_yield_samples", "mining_yield_materials", "xmin",
                     "ring_reference_metadata", "systems"):
            self.assertIn(name, sql)
        self.assertIn("NOW()", scope_sql)
        self.assertIn("POWER(ms.x", scope_sql)
        self.assertEqual(scope_values, [3650, 1., 2., 3., 250.])
        self.assertNotIn("commodity", scope_sql)  # No eligibility round-trip gap.
        self.assertNotIn("max_distance", sql)  # Same-system fallback outside sphere.
        self.assertNotIn("ARRAY(SELECT", sql)
        self.assertTrue(values[-1])
        self.assertEqual(values[0], values[1])
        self.assertTrue(set(values[2]).issubset(values[0]))
        self.assertEqual(values[0], sorted(set(values[0])))
        self.assertTrue({"regional", "boundary"}.issubset(values[0]))
        self.assertEqual(len(static_revision()), 64)

    def test_small_region_uses_conservative_index_but_broad_region_does_not(self):
        for radius, spatial in ((50., True), (100., True), (100.01, False), (500., False)):
            conn = self.connection()
            mining_revision(conn, {**QUERY, "max_distance": radius})
            sql, values = conn.execute.call_args_list[0].args
            self.assertEqual("point(ms.x, ms.y)" in sql, spatial)
            self.assertIn("<= POWER(%s, 2)", sql)  # Exact inclusive sphere in BOTH plans.
            self.assertEqual(sql.count("%s"), len(values))
            self.assertEqual(values[:5], [3650, 1., 2., 3., radius])

    def test_empty_region_still_protects_reference_positions_and_dependencies(self):
        conn = self.connection()
        conn.scope_names = []
        mining_revision(conn, QUERY)
        _, values = conn.execute.call_args_list[1].args
        self.assertEqual(values[0], values[2])
        self.assertTrue(values[2])
        conn.execute.reset_mock()
        mining_revision(conn, {**QUERY, "include_community_overlaps": False})
        self.assertEqual(conn.execute.call_args_list[1].args[1], ([], [], []))

    def test_bad_region_summary_never_queries_dependencies_or_issues_revision(self):
        for data in ({}, {"membership": "m", "names": None},
                     {"membership": "m", "names": [None]}):
            conn = MagicMock()
            conn.execute.return_value.fetchone.return_value = data
            with self.assertRaises(ValueError):
                mining_revision(conn, QUERY)
            self.assertEqual(conn.execute.call_count, 1)

    def test_bad_dependency_summary_never_issues_revision(self):
        conn = self.connection()
        conn.parts.pop("materials")
        with self.assertRaises(ValueError):
            mining_revision(conn, QUERY)

    def test_no_unknown_revision_is_accepted(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {}
        with self.assertRaises(ValueError):
            mining_revision(conn, QUERY)

    def test_unchanged_response_does_not_query_or_serialize_ring_pages(self):
        with patch.object(api, "connection") as connection, \
                patch.object(api, "mining_revision", return_value=REV) as version:
            conn = connection.return_value.__enter__.return_value
            result = api.search_sites(**QUERY, offset=0, snapshot_protocol=1, known_revision=REV)
        conn.execute.assert_called_once_with("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        self.assertIs(version.call_args.args[0], conn)
        self.assertTrue(result["notModified"])
        self.assertEqual(result["revision"], REV)
        self.assertFalse(result["hasMore"])
        self.assertEqual(result["results"], [])

    def test_old_unfrozen_cursor_restarts_without_live_database_read(self):
        with patch.object(api, "connection") as connection, \
                patch.object(api, "mining_revision", return_value=REV):
            conn = connection.return_value.__enter__.return_value
            with self.assertRaises(HTTPException) as raised:
                api.search_sites(**QUERY, offset=1000, snapshot_protocol=1, snapshot_revision="old",
                                 snapshot_static=static_revision())
        self.assertEqual(raised.exception.status_code, 409)
        conn.execute.assert_not_called()

    def test_new_snapshot_uses_same_read_transaction_and_marks_version(self):
        with patch.object(api, "connection") as connection, \
                patch.object(api, "mining_revision", return_value=REV), \
                patch.object(api, "overlap_site_identities", return_value=[]), \
                patch.object(api, "community_reference_candidates", return_value=[]):
            conn = connection.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value.fetchmany.return_value = []
            conn.execute.return_value.fetchone.return_value = {"stamp": "2026-10-09T00:00:00Z"}
            result = api.search_sites(**QUERY, offset=0, snapshot_protocol=1, known_revision="old")
        self.assertEqual(conn.execute.call_args_list[0].args,
                         ("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",))
        self.assertEqual(result["revision"], REV)
        self.assertEqual(result["snapshotProtocol"], 1)
        self.assertFalse(result["notModified"])
        self.assertTrue(result["snapshotComplete"])

    def test_all_continuations_are_frozen_and_never_query_live_data(self):
        rows = [{"siteIdentity": str(i), "observedAt": "2026-10-07T00:00:00Z",
                 "system": "Test", "ring": "Test " + str(i) + " Ring",
                 "ringType": "Metallic", "reserveLevel": "Pristine"} for i in range(3)]
        with patch.object(api, "connection") as connection, \
                patch.object(api, "mining_revision", return_value=REV) as version, \
                patch.object(api, "overlap_site_identities", return_value=[]), \
                patch.object(api, "community_reference_candidates", return_value=[]):
            conn = connection.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value.fetchmany.side_effect = [rows, []]
            conn.execute.return_value.fetchone.return_value = {"stamp": "2026-10-09T00:00:00Z"}
            first = api.search_sites(**{**QUERY, "limit": 2}, offset=0, snapshot_protocol=1)
            version.assert_called_once()
            connection.reset_mock()
            version.reset_mock()
            result = api.search_sites(**{**QUERY, "limit": 2}, offset=2, snapshot_protocol=1,
                snapshot_revision=REV, snapshot_static=first["snapshotStatic"], cursor=first["nextCursor"])
        connection.assert_not_called()
        version.assert_not_called()
        self.assertEqual(result["results"], rows[2:])
        self.assertFalse(result["hasMore"])
        self.assertTrue(result["snapshotComplete"])
        self.assertEqual(first["snapshotAt"], result["snapshotAt"])

    def test_cache_publish_happens_only_after_pg_transaction_closes(self):
        with patch.object(api, "connection") as connection, \
                patch.object(api, "mining_revision", return_value=REV), \
                patch.object(api, "overlap_site_identities", return_value=[]), \
                patch.object(api, "community_reference_candidates", return_value=[]):
            conn = connection.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value.fetchmany.return_value = []
            conn.execute.return_value.fetchone.return_value = {"stamp": "2026-10-09T00:00:00Z"}
            publish = self.pages.publish
            def checked_publish(*args, **kwargs):
                connection.return_value.__exit__.assert_called_once()
                publish(*args, **kwargs)
            with patch.object(self.pages, "publish", side_effect=checked_publish):
                api.search_sites(**QUERY, offset=0, snapshot_protocol=1)

    def test_existing_ready_snapshot_reuses_rows_only_after_live_revision_check(self):
        with self.pages.build(QUERY, REV, static_revision()) as build:
            self.pages.publish(build, references=[], truncated=False, snapshot_at="2026-10-09T00:00:00Z")
        with patch.object(api, "connection") as connection, \
                patch.object(api, "mining_revision", return_value=REV) as version:
            result = api.search_sites(**QUERY, offset=0, snapshot_protocol=1)
        version.assert_called_once()
        connection.return_value.__enter__.return_value.cursor.assert_not_called()
        self.assertTrue(result["snapshotComplete"])

    def test_rolling_projection_change_rejects_page_without_database_digest(self):
        with patch.object(api, "connection"), patch.object(api, "mining_revision") as version:
            with self.assertRaises(HTTPException) as raised:
                api.search_sites(**QUERY, offset=1000, snapshot_protocol=1,
                                 snapshot_revision=REV, snapshot_static="old code")
        self.assertEqual(raised.exception.status_code, 409)
        version.assert_not_called()

    def test_invalid_unbounded_or_unversioned_continuations_rejected(self):
        for kwargs in (dict(snapshot_protocol=1),
                       dict(system="Test", offset=0, snapshot_protocol=1, cursor="c"),
                       dict(system="Test", offset=20, snapshot_protocol=1, known_revision=REV),
                       dict(system="Test", offset=20, snapshot_protocol=1)):
            with self.assertRaises(HTTPException) as raised:
                api.search_sites(**kwargs)
            self.assertEqual(raised.exception.status_code, 400)


class MiningRevisionGateTests(unittest.TestCase):
    def test_disabled_initial_protocol_uses_fresh_paging_without_revision_work(self):
        with patch.object(api, "MINING_SNAPSHOT_PROTOCOL_ENABLED", False), \
                patch.object(api, "connection") as connection, \
                patch.object(api, "mining_revision") as revision:
            conn = connection.return_value.__enter__.return_value
            conn.execute.return_value.fetchall.return_value = []
            result = api.search_sites(system="Test", offset=0, snapshot_protocol=1, known_revision=REV)
        revision.assert_not_called()
        self.assertNotIn("snapshotProtocol", result)
        self.assertNotIn("notModified", result)
        self.assertIn("results", result)
        self.assertFalse(result["hasMore"])
        self.assertEqual(conn.execute.call_count, 1)

    def test_disabled_continuation_cannot_force_expensive_proofs_or_client_restart(self):
        with patch.object(api, "MINING_SNAPSHOT_PROTOCOL_ENABLED", False), \
                patch.object(api, "connection") as connection, \
                patch.object(api, "mining_revision") as revision:
            conn = connection.return_value.__enter__.return_value
            conn.execute.return_value.fetchall.return_value = []
            result = api.search_sites(system="Test", offset=20, snapshot_protocol=1)
        revision.assert_not_called()
        self.assertNotIn("snapshotProtocol", result)
        self.assertEqual(conn.execute.call_args.args[1][-1], 20)


if __name__ == "__main__":
    unittest.main()
