import unittest
from unittest.mock import MagicMock, patch

from edframe_catalog.mining_epochs import TABLES, trigger_sql
from edframe_catalog.mining_revision import mining_revision


QUERY = dict(commodity="platinum", system="", max_age_days=3650, x=1., y=2., z=3.,
             max_distance=250., limit=5000, include_community_overlaps=True,
             include_ring_candidates=True)
STATE = dict(schema_version=1, ready=True, generation="database-generation",
             unknown_revision=0, counters="counter-hash", age_boundary="2026-01-01",
             missing_references=0, reference_counters="reference-hash")


class MiningEpochTests(unittest.TestCase):
    def connection(self, **changes):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {**STATE, **changes}
        return conn

    def test_one_small_query_no_payload_fingerprint(self):
        conn = self.connection()
        revision = mining_revision(conn, QUERY)
        self.assertEqual(len(revision), 67)
        self.assertEqual(conn.execute.call_count, 1)
        sql, values = conn.execute.call_args.args
        self.assertEqual(sql.count("%s"), len(values))
        self.assertNotIn("xmin", sql)
        self.assertNotIn("ms.*", sql)
        self.assertNotIn("mining_yield", sql)
        self.assertNotIn("mining_revision_footprints", sql)
        self.assertIn("FROM mining_revision_cells", sql)
        self.assertIn("ORDER BY age.observed_at LIMIT 1", sql)
        self.assertNotIn("ORDER BY observed_at LIMIT 1", sql)
        self.assertEqual(values[:6], [-2, 1, -2, 1, -2, 1])

    def test_each_counter_generation_and_expiry_boundary_invalidates(self):
        original = mining_revision(self.connection(), QUERY)
        for key, value in (("generation", "restored-database"), ("unknown_revision", 1),
                           ("counters", "insert-then-delete"), ("age_boundary", None),
                           ("reference_counters", "changed-position")):
            self.assertNotEqual(mining_revision(self.connection(**{key: value}), QUERY), original)
        self.assertNotEqual(mining_revision(self.connection(), {**QUERY, "commodity": "osmium"}), original)
        with patch("edframe_catalog.mining_revision.static_revision", return_value="new projection"):
            self.assertNotEqual(mining_revision(self.connection(), QUERY), original)

    def test_not_ready_or_unknown_schema_refuses_reuse(self):
        for changes in (dict(ready=False), dict(schema_version=2), dict(missing_references=1),
                        dict(counters=None), dict(unknown_revision=None), dict(generation=None)):
            with self.assertRaises(ValueError):
                mining_revision(self.connection(**changes), QUERY)

    def test_exact_system_and_disabled_references(self):
        conn = self.connection()
        mining_revision(conn, {**QUERY, "system": " Test ", "include_community_overlaps": False})
        sql, values = conn.execute.call_args.args
        self.assertNotIn("box(", sql)
        self.assertEqual(values, ["Test", [], [], 3650])
        self.assertEqual(sql.count("%s"), len(values))

    def test_invalid_geometry_never_claims_unchanged(self):
        for field, value in (("x", float("nan")), ("y", float("inf")),
                             ("z", None), ("x", 1e15), ("max_distance", 0)):
            conn = self.connection()
            with self.assertRaises(ValueError):
                mining_revision(conn, {**QUERY, field: value})
            conn.execute.assert_not_called()

    def test_statement_triggers_cover_every_source_mutation_and_truncation(self):
        sql = trigger_sql("public")
        for table in TABLES:
            for event in ("INSERT", "UPDATE", "DELETE"):
                self.assertIn(f"AFTER {event} ON {table}", sql)
            self.assertIn(f"AFTER TRUNCATE ON {table}", sql)
        self.assertEqual(sql.count("FOR EACH STATEMENT"), 20)
        self.assertEqual(sql.count("OLD TABLE AS old_rows NEW TABLE AS new_rows"), 5)
        self.assertNotIn("FOR EACH ROW", sql)
        self.assertNotIn("DELETE FROM mining_revision", sql)
        self.assertIn("JOIN mining_revision_references", sql)
        self.assertIn("JOIN mining_sites ms ON ms.identity =", sql)
        self.assertIn("floor(x / 128)", sql)

    def test_schema_identifiers_cannot_escape_isolated_test_namespace(self):
        for schema in ("public; DROP TABLE systems", "", "pg_temp.x", '"public"'):
            with self.assertRaises(ValueError):
                trigger_sql(schema)


if __name__ == "__main__":
    unittest.main()
