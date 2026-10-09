import multiprocessing
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from edframe_catalog.mining_pages import (
    FrozenPages, FrozenExpired, FrozenUnavailable, decode_cursor,
    MAX_ROWS, MAX_DATABASE_BYTES,
)
from unittest.mock import patch

REV = "s1-" + "a" * 64
STATIC = "b" * 64
QUERY = {"commodity": "platinum", "system": "Test"}
STAMP = "2026-10-09T00:00:00Z"


def other_worker(path, token, output):
    try:
        output.put(FrozenPages(path).page(token, query=QUERY, revision=REV,
                   projection=STATIC, offset=1, limit=1)["results"])
    except Exception as exc:
        output.put(type(exc).__name__)


class FrozenPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name, "pages.sqlite3")
        self.pages = FrozenPages(self.path)

    def create(self, rows=None, *, truncated=False, pages=None):
        pages = pages or self.pages
        with pages.build(QUERY, REV, STATIC) as build:
            if rows is None:
                rows = [{"siteIdentity": str(i), "observedAt": STAMP} for i in range(3)]
            if rows:
                pages.append(build, rows)
            pages.publish(build, references=[{"system": "Reference"}],
                          truncated=truncated, snapshot_at=STAMP)
            return build.token

    def page(self, token, **changes):
        return self.pages.page(token, **dict(query=QUERY, revision=REV,
               projection=STATIC, offset=0, limit=2, **changes))

    def test_pages_are_complete_only_at_end_and_do_not_re_date_sources(self):
        token = self.create()
        first = self.page(token)
        self.assertFalse(first["snapshotComplete"])
        self.assertEqual(first["nextOffset"], 2)
        self.assertEqual(decode_cursor(first["nextCursor"]), (token, 2))
        self.assertTrue(first["communityReferences"])
        last = self.pages.page(token, query=QUERY, revision=REV, projection=STATIC, offset=2, limit=1)
        self.assertTrue(last["snapshotComplete"])
        self.assertFalse(last["hasMore"])
        self.assertEqual(last["results"][0]["observedAt"], STAMP)
        self.assertEqual(last["snapshotAt"], STAMP)
        self.assertEqual(last["communityReferences"], [])

    def test_empty_snapshot_and_chunk_boundaries(self):
        token = self.create([])
        self.assertEqual(self.page(token)["results"], [])
        with self.pages.build({**QUERY, "new": True}, REV, STATIC) as build:
            for i in range(3):
                self.pages.append(build, [{"i": i * 2 + j} for j in range(2)])
            self.pages.publish(build, references=[], truncated=False, snapshot_at=STAMP)
            result = self.pages.page(build.token, query={**QUERY, "new": True}, revision=REV,
                                     projection=STATIC, offset=1, limit=4)
        self.assertEqual(result["results"], [{"i": i} for i in range(1, 5)])

    def test_shared_database_supports_another_process(self):
        token = self.create()
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        process = context.Process(target=other_worker, args=(str(self.path), token, queue))
        process.start()
        process.join(10)
        self.addCleanup(queue.close)
        if process.is_alive():
            process.terminate()
            process.join()
            self.fail("Worker did not finish")
        self.assertEqual(process.exitcode, 0)
        self.assertEqual(queue.get(timeout=2), [{"siteIdentity": "1", "observedAt": STAMP}])

    def test_cursor_has_no_path_or_unbounded_offset(self):
        for value in ("", "../../a", "f1." + "g" * 32 + ".1",
                      "f1." + "a" * 32 + ".100000", "f1." + "a" * 32 + ".1\n"):
            with self.assertRaises(FrozenExpired):
                decode_cursor(value)

    def test_query_revision_code_and_offset_are_fenced(self):
        token = self.create()
        for values in (dict(query={**QUERY, "commodity": "osmium"}), dict(revision="other"),
                       dict(projection="other"), dict(offset=3), dict(offset=-1), dict(limit=5001)):
            args = dict(query=QUERY, revision=REV, projection=STATIC, offset=0, limit=2)
            args.update(values)
            with self.assertRaises(FrozenExpired):
                self.pages.page(token, **args)
        self.assertEqual(self.pages.find(QUERY, REV, STATIC), token)
        self.assertIsNone(self.pages.find(QUERY, "different", STATIC))

    def test_expiry_and_clock_reversal_never_prove_unchanged(self):
        now = [1000.]
        self.pages.clock = lambda: now[0]
        token = self.create()
        for current in (1181., 999.):
            now[0] = current
            with self.assertRaises(FrozenExpired):
                self.page(token)
            self.assertIsNone(self.pages.find(QUERY, REV, STATIC))

    def test_unexpired_pages_are_not_evicted_when_full(self):
        self.pages.capacity = 1
        token = self.create()
        with self.assertRaises(FrozenUnavailable):
            with self.pages.build(QUERY, "different", STATIC):
                self.fail("Should not evict active snapshots")
        self.assertTrue(self.page(token)["results"])
        self.pages.clock = lambda: time.time() + 181
        self.create()

    def test_single_builder_partial_is_invisible_and_abort_releases_capacity(self):
        with self.pages.build(QUERY, REV, STATIC) as build:
            self.pages.append(build, [{"i": 1}])
            with self.assertRaises(FrozenExpired):
                self.page(build.token)
            with self.assertRaises(FrozenUnavailable):
                with FrozenPages(self.path).build(QUERY, REV, STATIC):
                    self.fail("Only one builder admitted")
        self.assertIsNone(self.pages.find(QUERY, REV, STATIC))
        self.create()

    def test_crashed_build_lease_is_reaped_without_eviction_of_ready_pages(self):
        token = self.create()
        with self.pages._db(write=True) as db:
            now = time.time()
            db.execute("""INSERT INTO snapshots
                (token, query_key, revision, projection, created, expires, lease_until)
                VALUES ('crash', 'query', 'r', 's', ?, ?, ?)""", (now, now + 180, now - 1))
        self.create()
        self.assertTrue(self.page(token)["results"])
        with self.pages._db() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM snapshots WHERE token='crash'").fetchone())

    def test_deadline_and_byte_budgets_abort_without_publishing(self):
        for deadline in (True, False):
            pages = FrozenPages(self.path, compressed_limit=1 if not deadline else 1000)
            with self.assertRaises(FrozenUnavailable):
                with pages.build(QUERY, REV, STATIC) as build:
                    if deadline:
                        build.deadline = time.monotonic() - 1
                    pages.append(build, [{"i": 1}])
            self.assertIsNone(pages.find(QUERY, REV, STATIC))
        with self.pages._db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots").fetchone()[0], 0)

    def test_truncation_never_claims_completeness_even_at_frozen_end(self):
        token = self.create(truncated=True)
        result = self.pages.page(token, query=QUERY, revision=REV, projection=STATIC, offset=2, limit=1)
        self.assertTrue(result["hasMore"])
        self.assertFalse(result["snapshotComplete"])
        self.assertTrue(result["snapshotTruncated"])
        self.assertEqual(result["nextOffset"], 3)

    def test_corruption_or_missing_chunk_discards_snapshot(self):
        for operation in ("UPDATE chunks SET data=x'00'", "DELETE FROM chunks",
                          "UPDATE snapshots SET metadata=x'00'",
                          "UPDATE snapshots SET row_count=2",
                          "UPDATE snapshots SET truncated=1",
                          "UPDATE chunks SET row_offset=-1"):
            token = self.create()
            with self.pages._db(write=True) as db:
                db.execute(operation)
            with self.assertRaises(FrozenExpired):
                self.page(token)

    def test_metadata_bytes_count_toward_total_raw_budget(self):
        with self.assertRaises(FrozenUnavailable):
            with self.pages.build(QUERY, REV, STATIC) as build:
                self.pages.append(build, [{"i": 1}])
                build.raw_bytes = 64 * 1024 * 1024
                self.pages.publish(build, references=[], truncated=False, snapshot_at=STAMP)
        self.assertIsNone(self.pages.find(QUERY, REV, STATIC))

    def test_sqlite_failure_is_explicit_and_does_not_serve_partial_rows(self):
        with patch("edframe_catalog.mining_pages.sqlite3.connect", side_effect=OSError("unavailable")):
            with self.assertRaises(FrozenUnavailable):
                self.pages.find(QUERY, REV, STATIC)

    def test_fifty_thousand_rows_stay_bounded_without_database_wal(self):
        with self.pages.build(QUERY, REV, STATIC) as build:
            for start in range(0, MAX_ROWS, 5000):
                self.pages.append(build, [{"i": i} for i in range(start, start + 5000)])
            with self.assertRaises(FrozenUnavailable):
                self.pages.append(build, [{"extra": True}])
            self.pages.publish(build, references=[], truncated=True, snapshot_at=STAMP)
            result = self.pages.page(build.token, query=QUERY, revision=REV,
                                     projection=STATIC, offset=49999, limit=1)
        self.assertEqual(result["results"], [{"i": 49999}])
        self.assertTrue(result["hasMore"])
        self.assertLess(self.path.stat().st_size, MAX_DATABASE_BYTES)
        self.assertFalse(Path(str(self.path) + "-wal").exists())


if __name__ == "__main__":
    unittest.main()
