import unittest

from edframe_catalog.database import upsert_batch, upsert_state_find_batch


class RecordingConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, values):
        self.calls.append((statement, values))


class DatabaseProjectionTests(unittest.TestCase):
    def test_station_and_market_rows_are_serialized_for_jsonb(self):
        conn = RecordingConnection()
        projected = upsert_batch(
            conn,
            systems=[],
            stations=[{
                "market_id": 42,
                "system_name": "Cubeo",
                "station_name": "Chelomey Orbital",
                "system_address": 123,
                "station_type": "Coriolis",
                "landing_pad_size": "L",
                "distance_to_arrival_ls": 50.5,
                "services": ["Market"],
                "economies": [{"name": "High Tech"}],
                "primary_economy": "High Tech",
                "government": "Patronage",
                "controlling_faction": "Cubeo Patron's Principles",
                "fleet_carrier": False,
                "carrier_docking_access": None,
                "prohibited": ["Slaves"],
                "observed_at": "2026-10-03T08:00:00Z",
                "received_at": "2026-10-03T08:00:01Z",
                "source": "EDDN journal/1:Docked",
            }],
            markets=[{
                "market_id": 42,
                "commodity": "platinum",
                "station_name": "Chelomey Orbital",
                "system_name": "Cubeo",
                "mean_price": 100,
                "buy_price": 90,
                "stock": 0,
                "stock_bracket": 0,
                "sell_price": 250000,
                "demand": 9000,
                "demand_bracket": 3,
                "status_flags": ["Rare"],
                "observed_at": "2026-10-03T08:00:00Z",
                "received_at": "2026-10-03T08:00:01Z",
            }],
            sites=[],
        )

        self.assertEqual(projected, 2)
        station_values = conn.calls[0][1]
        self.assertEqual(station_values["services"], '["Market"]')
        self.assertEqual(
            station_values["economies"], '[{"name": "High Tech"}]'
        )
        self.assertEqual(station_values["prohibited"], '["Slaves"]')
        market_values = conn.calls[1][1]
        self.assertEqual(market_values["status_flags"], '["Rare"]')

    def test_state_find_rows_are_upserted_separately(self):
        conn = RecordingConnection()
        projected = upsert_state_find_batch(
            conn,
            snapshots=[{
                "identity": "address:123", "system_address": 123,
                "system_name": "Cubeo",
                "observed_at": "2026-10-03T08:00:00Z",
                "received_at": "2026-10-03T08:00:01Z",
                "snapshot": '{"system":"Cubeo","observations":[]}',
            }],
            signals=[{
                "identity": "signal", "system_address": 123,
                "system_name": "Cubeo",
                "observed_at": "2026-10-03T08:00:00Z",
                "received_at": "2026-10-03T08:00:01Z",
                "expires_at": "2026-10-03T08:05:00Z",
                "observation": '{"system":"Cubeo"}',
            }],
        )
        self.assertEqual(projected, 2)
        self.assertIn("state_bgs_snapshots", conn.calls[0][0])
        self.assertIn("state_signals", conn.calls[1][0])


if __name__ == "__main__":
    unittest.main()
