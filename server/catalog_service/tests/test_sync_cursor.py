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
    _resolved_ship_offer,
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

    def test_ship_price_resolution_keeps_observed_price_authoritative(self):
        result = _resolved_ship_offer(
            {"name": "anaconda", "buyPrice": 85000},
            reference_price=100000, reference_samples=4,
            evidence=[{"price": 85000, "reference": 100000}],
        )
        self.assertEqual(result["buyPrice"], 85000)
        self.assertEqual(result["priceType"], "OBSERVED")

    def test_ship_price_resolution_infers_station_discount(self):
        result = _resolved_ship_offer(
            {"name": "python"}, reference_price=60000000,
            reference_samples=3,
            evidence=[
                {"price": 85000, "reference": 100000},
                {"price": 127500, "reference": 150000},
            ],
        )
        self.assertEqual(result["buyPrice"], 51000000)
        self.assertEqual(result["discountBps"], 1500)
        self.assertEqual(result["priceType"], "INFERRED")
        self.assertEqual(result["priceConfidence"], "CONFIRMED")

    def test_ship_reference_is_not_presented_as_a_station_price(self):
        result = _resolved_ship_offer(
            {"name": "python"}, reference_price=60000000,
            reference_samples=1, evidence=[],
        )
        self.assertNotIn("buyPrice", result)
        self.assertEqual(result["referencePrice"], 60000000)
        self.assertEqual(result["priceType"], "UNKNOWN")
        self.assertEqual(result["priceConfidence"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
