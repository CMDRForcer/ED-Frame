import unittest
from unittest.mock import MagicMock, patch
from edframe_catalog.api import nearby_station_services


class StationServiceApiTests(unittest.TestCase):
    def test_radius_pad_and_distance_order_are_bounded(self):
        for pad, allowed in (("S", ["S", "M", "L"]), ("M", ["M", "L"]), ("L", ["L"])):
            conn = MagicMock()
            conn.execute.return_value.fetchall.return_value = [{"station": "one"}, {"station": "two"}]
            with patch("edframe_catalog.api.connection") as factory:
                factory.return_value.__enter__.return_value = conn
                result = nearby_station_services(0, 0, 0, "repair", landing_pad=pad, limit=1)
            sql, values = conn.execute.call_args.args
            self.assertIn("JOIN LATERAL", sql)
            self.assertIn("st.landing_pad_size = ANY(%s)", sql)
            self.assertIn('ORDER BY "distanceLy"', sql)
            self.assertIn("st.fleet_carrier IS NOT TRUE", sql)
            self.assertEqual(values[-2:], (allowed, 2))
            self.assertTrue(result["hasMore"])
            self.assertEqual(len(result["results"]), 1)

    def test_any_pad_and_carriers_are_explicit(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        with patch("edframe_catalog.api.connection") as factory:
            factory.return_value.__enter__.return_value = conn
            nearby_station_services(1, 2, 3, "refuel", exclude_fleet_carriers=False)
        sql = conn.execute.call_args.args[0]
        self.assertNotIn("landing_pad_size = ANY", sql)
        self.assertNotIn("fleet_carrier IS NOT TRUE", sql)


if __name__ == "__main__":
    unittest.main()
