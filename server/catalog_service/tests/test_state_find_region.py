import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from edframe_catalog.api import sync_state_finds


class RegionalStateFindApiTests(unittest.TestCase):
    def test_partial_coordinates_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            sync_state_finds(x=1)
        self.assertEqual(raised.exception.status_code, 422)

    def test_regional_sql_is_bounded_and_fresh_for_both_kinds(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        with patch("edframe_catalog.api.connection") as factory:
            factory.return_value.__enter__.return_value = conn
            result = sync_state_finds(x=1, y=2, z=3, max_distance=100, limit=5)
        sql, values = conn.execute.call_args.args
        self.assertIn("EXISTS", sql)
        self.assertIn("s.system_address = current_state.system_address", sql)
        self.assertIn("LOWER(s.name)", sql)
        self.assertIn("INTERVAL '24 hours'", sql)
        self.assertIn("expires_at > NOW()", sql)
        self.assertIn("<= POWER(%s, 2)", sql)
        self.assertEqual(values[-5:], (1, 2, 3, 100, 6))
        self.assertEqual(result["region"], {"origin": [1, 2, 3], "radiusLy": 100})

    def test_global_endpoint_remains_backwards_compatible(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        with patch("edframe_catalog.api.connection") as factory:
            factory.return_value.__enter__.return_value = conn
            result = sync_state_finds()
        self.assertIsNone(result["region"])
        self.assertNotIn("SELECT 1 FROM systems", conn.execute.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
