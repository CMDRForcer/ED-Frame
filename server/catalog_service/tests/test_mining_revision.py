import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from edframe_catalog import api
from edframe_catalog.mining_revision import mining_revision, static_revision


REV = "s1-" + "a" * 64
QUERY = dict(commodity="platinum", system="", max_age_days=3650, x=1., y=2., z=3.,
             max_distance=250., limit=1000, include_community_overlaps=True,
             include_ring_candidates=True)
PARTS = {k: k for k in ("membership", "sites", "samples", "materials", "metadata", "positions")}


class MiningRevisionTests(unittest.TestCase):
    def test_each_domain_deletion_membership_and_query_invalidate_revision(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = PARTS
        with patch("edframe_catalog.mining_revision.static_revision", return_value="static"):
            original = mining_revision(conn, QUERY)
            for key in PARTS:
                conn.execute.return_value.fetchone.return_value = {**PARTS, key: "changed"}
                self.assertNotEqual(mining_revision(conn, QUERY), original, key)
            conn.execute.return_value.fetchone.return_value = PARTS
            self.assertNotEqual(mining_revision(conn, {**QUERY, "commodity": "osmium"}), original)
        with patch("edframe_catalog.mining_revision.static_revision", return_value="new references"):
            self.assertNotEqual(mining_revision(conn, QUERY), original)

    def test_digest_sql_covers_both_yield_tables_and_same_system_fallback_metadata(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = PARTS
        mining_revision(conn, QUERY)
        sql, values = conn.execute.call_args.args
        self.assertEqual(sql.count("%s"), len(values))
        for name in ("mining_sites", "mining_yield_samples", "mining_yield_materials", "xmin",
                     "ring_reference_metadata", "systems", "NOW()", "SELECT system FROM scope"):
            self.assertIn(name, sql)
        self.assertEqual(values[:5], [3650, 1., 2., 3., 250.])
        self.assertTrue(values[-1])
        self.assertEqual(values[-1], values[-2])
        self.assertEqual(len(static_revision()), 64)

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

    def test_final_page_change_is_not_marked_complete(self):
        with patch.object(api, "connection") as connection, \
                patch.object(api, "mining_revision", return_value=REV):
            conn = connection.return_value.__enter__.return_value
            with self.assertRaises(HTTPException) as raised:
                api.search_sites(**QUERY, offset=1000, snapshot_protocol=1, snapshot_revision="old",
                                 snapshot_static=static_revision())
        self.assertEqual(raised.exception.status_code, 409)
        self.assertFalse(any("UPDATE" in str(c.args[0]) for c in conn.execute.call_args_list))

    def test_new_snapshot_uses_same_read_transaction_and_marks_version(self):
        with patch.object(api, "connection") as connection, \
                patch.object(api, "mining_revision", return_value=REV), \
                patch.object(api, "overlap_site_identities", return_value=[]), \
                patch.object(api, "community_reference_candidates", return_value=[]):
            conn = connection.return_value.__enter__.return_value
            conn.execute.return_value.fetchall.return_value = []
            result = api.search_sites(**QUERY, offset=0, snapshot_protocol=1, known_revision="old")
        self.assertEqual(conn.execute.call_args_list[0].args,
                         ("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",))
        self.assertEqual(result["revision"], REV)
        self.assertEqual(result["snapshotProtocol"], 1)
        self.assertFalse(result["notModified"])
        self.assertTrue(result["snapshotComplete"])

    def test_intermediate_pages_are_provisional_and_do_not_repeat_content_digest(self):
        rows = [{"siteIdentity": str(i), "observedAt": "2026-10-07T00:00:00Z",
                 "system": "Test", "ring": "Test " + str(i) + " Ring",
                 "ringType": "Metallic", "reserveLevel": "Pristine"} for i in range(3)]
        with patch.object(api, "connection") as connection, \
                patch.object(api, "mining_revision") as version, \
                patch.object(api, "overlap_site_identities", return_value=[]):
            conn = connection.return_value.__enter__.return_value
            conn.execute.return_value.fetchall.return_value = rows
            result = api.search_sites(**{**QUERY, "limit": 2}, offset=2, snapshot_protocol=1,
                                      snapshot_revision=REV, snapshot_static=static_revision())
        version.assert_not_called()
        self.assertTrue(result["hasMore"])
        self.assertFalse(result["snapshotComplete"])

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


if __name__ == "__main__":
    unittest.main()
