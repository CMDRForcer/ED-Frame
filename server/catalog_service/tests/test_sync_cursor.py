import unittest
from datetime import datetime, timezone

from fastapi import HTTPException

from edframe_catalog.api import (
    _decode_market_cursor,
    _decode_offer_cursor,
    _decode_state_cursor,
    _encode_market_cursor,
    _encode_offer_cursor,
    _encode_state_cursor,
)


class SyncCursorTests(unittest.TestCase):
    def test_market_cursor_round_trip_is_stable_and_opaque(self):
        stamp = datetime(2026, 10, 3, 10, 20, 30, tzinfo=timezone.utc)
        cursor = _encode_market_cursor(stamp, 42, "platinum")

        self.assertNotIn("platinum", cursor)
        self.assertEqual(
            _decode_market_cursor(cursor), (stamp, 42, "platinum")
        )

    def test_empty_cursor_starts_from_epoch(self):
        stamp, market_id, commodity = _decode_market_cursor("")
        self.assertEqual(stamp, datetime(1970, 1, 1, tzinfo=timezone.utc))
        self.assertEqual((market_id, commodity), (0, ""))

    def test_invalid_cursor_is_a_bounded_client_error(self):
        with self.assertRaises(HTTPException) as raised:
            _decode_market_cursor("not-a-cursor")
        self.assertEqual(raised.exception.status_code, 400)

    def test_state_cursor_round_trip_is_stable_and_opaque(self):
        stamp = datetime(2026, 10, 3, 10, 20, 30, tzinfo=timezone.utc)
        cursor = _encode_state_cursor(stamp, "SIGNAL", "secret-identity")
        self.assertNotIn("secret-identity", cursor)
        self.assertEqual(
            _decode_state_cursor(cursor),
            (stamp, "SIGNAL", "secret-identity"),
        )

    def test_station_offer_cursor_round_trip_is_stable_and_opaque(self):
        stamp = datetime(2026, 10, 3, 10, 20, 30, tzinfo=timezone.utc)
        cursor = _encode_offer_cursor(stamp, "OUTFITTING", 42)
        self.assertNotIn("OUTFITTING", cursor)
        self.assertEqual(
            _decode_offer_cursor(cursor), (stamp, "OUTFITTING", 42)
        )


if __name__ == "__main__":
    unittest.main()
