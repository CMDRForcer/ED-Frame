import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from edframe_catalog import api
from edframe_catalog.market_sync import market_sync_query


class MarketSyncTests(unittest.TestCase):
    def execute_page(self, rows, *, cursor=None, commodities=None, limit=2):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = rows
        conn.__enter__.return_value = conn
        with patch.object(api, "connection", return_value=conn):
            response = api.sync_markets(cursor, commodities, limit)
        return response, conn.execute.call_args.args

    def test_filter_is_normalized_and_bound_as_values(self):
        response, (query, params) = self.execute_page(
            [], commodities=" Platinum, GOLD, platinum , ",
        )
        self.assertEqual(params["commodities"], ["gold", "platinum"])
        self.assertNotIn("platinum", query)
        self.assertEqual(params["batch_size"], 3)
        self.assertEqual(response["results"], [])

    def test_extra_row_sets_has_more_but_cursor_uses_last_visible_row(self):
        stamp = datetime(2026, 10, 12, tzinfo=timezone.utc)
        rows = [
            {"syncAt": stamp, "marketId": 42, "commodity": symbol}
            for symbol in ("gold", "platinum", "silver")
        ]
        response, _ = self.execute_page(rows)
        self.assertEqual(response["results"], rows[:2])
        self.assertTrue(response["hasMore"])
        self.assertEqual(
            api._decode_market_cursor(response["nextCursor"]),
            (stamp, 42, "platinum"),
        )

    def test_empty_page_preserves_existing_cursor(self):
        stamp = datetime(2026, 10, 12, tzinfo=timezone.utc)
        cursor = api._encode_market_cursor(stamp, 42, "platinum")
        response, (_, params) = self.execute_page([], cursor=cursor)
        self.assertEqual(response["nextCursor"], cursor)
        self.assertFalse(response["hasMore"])
        self.assertEqual(
            (params["cursor_at"], params["cursor_market_id"],
             params["cursor_commodity"]), (stamp, 42, "platinum"),
        )

    def test_too_many_commodities_does_not_open_database(self):
        with patch.object(api, "connection") as conn:
            with self.assertRaises(HTTPException) as raised:
                api.sync_markets(None, ",".join(f"symbol{i}" for i in range(101)), 500)
        self.assertEqual(raised.exception.status_code, 400)
        conn.assert_not_called()

    def test_unfiltered_page_has_no_commodity_restriction(self):
        stamp = datetime(1970, 1, 1, tzinfo=timezone.utc)
        query, params = market_sync_query(stamp, 0, "", [], 1001)
        self.assertNotIn("= ANY", query)
        self.assertEqual(params["batch_size"], 1001)


if __name__ == "__main__":
    unittest.main()
