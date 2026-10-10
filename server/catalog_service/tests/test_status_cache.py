import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from edframe_catalog import api
from edframe_catalog.status_cache import StatusCache, StatusUnavailable


class StatusCacheTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.factory = MagicMock()
        self.factory.return_value.__enter__.return_value = self.conn
        self.loader = MagicMock()
        self.cache = StatusCache(self.factory, self.loader)
        self.payload = {
            "generatedAt": "2026-10-10T10:00:00Z",
            "counts": {"markets": 123},
            "completeness": {}, "collector24h": {},
            "collector": {"messages_total": 1},
        }

    def row(self, age):
        return {"payload": self.payload, "age_seconds": age,
                "collector": {"messages_total": 2}}

    def test_repeated_requests_never_recompute_and_keep_snapshot_time(self):
        self.conn.execute.return_value.fetchone.return_value = self.row(42)
        for _ in range(10):
            result = self.cache.get()
            self.assertEqual(result["generatedAt"], self.payload["generatedAt"])
            self.assertEqual(result["counts"], self.payload["counts"])
            self.assertEqual(result["collector"]["messages_total"], 2)
            self.assertEqual(result["cache"]["ageSeconds"], 42)
            self.assertFalse(result["cache"]["stale"])
        self.loader.assert_not_called()
        self.assertEqual(self.payload["collector"]["messages_total"], 1)
        self.assertNotIn("cache", self.payload)

    def test_stale_snapshot_can_be_served_while_refresh_is_running(self):
        self.conn.execute.return_value.fetchone.return_value = self.row(301)
        result = self.cache.get()
        self.assertTrue(result["cache"]["stale"])
        self.assertEqual(result["generatedAt"], "2026-10-10T10:00:00Z")
        self.loader.assert_not_called()

    def test_missing_expired_or_future_snapshot_never_triggers_blocking_scan(self):
        for row in (None, self.row(1801), self.row(-31)):
            with self.subTest(row=row):
                self.conn.execute.return_value.fetchone.return_value = row
                with self.assertRaises(StatusUnavailable):
                    self.cache.get()
                self.loader.assert_not_called()

    def test_another_worker_holding_lock_prevents_duplicate_refresh(self):
        self.conn.execute.return_value.fetchone.return_value = {"acquired": False}
        self.assertFalse(self.cache.refresh())
        self.loader.assert_not_called()

    def test_worker_rechecks_freshness_after_acquiring_shared_lock(self):
        self.conn.execute.return_value.fetchone.side_effect = [
            {"acquired": True}, {"age_seconds": 42},
        ]
        self.assertFalse(self.cache.refresh())
        self.loader.assert_not_called()

    def test_failed_refresh_does_not_overwrite_last_good_snapshot(self):
        self.conn.execute.return_value.fetchone.side_effect = [
            {"acquired": True}, {"age_seconds": 301},
        ]
        self.loader.side_effect = RuntimeError("database temporarily busy")
        with self.assertRaises(RuntimeError):
            self.cache.refresh()
        writes = [call for call in self.conn.execute.call_args_list
                  if "INSERT INTO" in str(call.args[0])]
        self.assertEqual(writes, [])

    def test_successful_refresh_publishes_complete_snapshot_with_original_time(self):
        self.conn.execute.return_value.fetchone.side_effect = [
            {"acquired": True}, None,
        ]
        self.loader.return_value = self.payload
        self.assertTrue(self.cache.refresh())
        self.loader.assert_called_once_with()
        statement, params = self.conn.execute.call_args.args
        self.assertIn("ON CONFLICT", statement)
        self.assertEqual(params[0].obj, self.payload)
        self.assertEqual(params[1], self.payload["generatedAt"])

    def test_api_returns_retryable_warmup_without_loading_statistics(self):
        with patch.object(api, "_status_cache") as cache:
            cache.get.side_effect = StatusUnavailable("warming up")
            with self.assertRaises(HTTPException) as raised:
                api.status()
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.headers["Retry-After"], "5")


if __name__ == "__main__":
    unittest.main()
