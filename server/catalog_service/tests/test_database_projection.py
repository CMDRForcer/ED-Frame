import unittest

from edframe_catalog.database import (
    record_state, seed_reference_catalog, upsert_batch, upsert_state_find_batch,
    upsert_station_offer_batch,
    upsert_yield_observations,
)


class RecordingConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, values):
        self.calls.append((statement, values))


class DatabaseProjectionTests(unittest.TestCase):
    def test_collector_state_records_hourly_schema_usage_and_volume(self):
        conn = RecordingConnection()
        record_state(
            conn,
            schema="commodity/3",
            received_at="2026-10-05T12:34:56Z",
            projected=412,
            message_bytes=8192,
        )
        self.assertEqual(len(conn.calls), 2)
        hourly_sql, hourly_values = conn.calls[1]
        self.assertIn("collector_schema_metrics_hourly", hourly_sql)
        self.assertIn("date_trunc('hour'", hourly_sql)
        self.assertEqual(hourly_values["used_messages"], 1)
        self.assertEqual(hourly_values["ignored_messages"], 0)
        self.assertEqual(hourly_values["projected"], 412)
        self.assertEqual(hourly_values["message_bytes"], 8192)

        ignored = RecordingConnection()
        record_state(
            ignored,
            schema="navroute/1",
            received_at="2026-10-05T12:35:00Z",
            projected=0,
            message_bytes=1024,
        )
        self.assertEqual(ignored.calls[1][1]["used_messages"], 0)
        self.assertEqual(ignored.calls[1][1]["ignored_messages"], 1)

    def test_yield_observations_create_site_sample_and_material_rows(self):
        conn = RecordingConnection()
        projected = upsert_yield_observations(conn, [{
            "sample_id": "sample", "site_identity": "site",
            "system_address": 7, "system_name": "Yield Test",
            "x": 1.0, "y": 2.0, "z": 3.0, "body_id": 11,
            "body_name": "Yield Test 2", "ring_name": "Yield Test 2 A Ring",
            "ring_type": "Metallic", "reserve_level": "PristineResources",
            "distance_to_arrival_ls": 400.0,
            "materials": {"platinum": 32.5, "osmium": 11.25},
            "observed_at": "2026-10-03T08:00:00Z",
            "received_at": "2026-10-03T08:00:01Z",
            "source": "ED-Frame Journal · ProspectedAsteroid",
        }])
        self.assertEqual(projected, 1)
        self.assertIn("mining_sites", conn.calls[0][0])
        self.assertIn("mining_yield_samples", conn.calls[1][0])
        self.assertIn("mining_yield_materials", conn.calls[2][0])
        self.assertIn("mining_yield_materials", conn.calls[3][0])

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

    def test_station_offer_kinds_use_separate_complete_inventory_tables(self):
        conn = RecordingConnection()
        base = {
            "market_id": 42, "system_name": "Cubeo",
            "station_name": "Chelomey Orbital", "horizons": True,
            "odyssey": True, "observed_at": "2026-10-03T08:00:00Z",
            "received_at": "2026-10-03T08:00:01Z",
        }
        projected = upsert_station_offer_batch(conn, [
            {**base, "kind": "OUTFITTING", "items": '["int_fuelscoop"]',
             "source": "EDDN outfitting/2"},
            {**base, "kind": "SHIPYARD", "items": '["anaconda"]',
             "source": "EDDN shipyard/2"},
        ])
        self.assertEqual(projected, 2)
        self.assertIn("station_outfitting", conn.calls[0][0])
        self.assertIn("modules", conn.calls[0][0])
        self.assertIn("jsonb_array_elements", conn.calls[0][0])
        self.assertIn("EDDN outfitting/2", conn.calls[0][0])
        self.assertIn("station_module_offers", conn.calls[1][0])
        self.assertIn("station_shipyards", conn.calls[2][0])
        self.assertIn("ships", conn.calls[2][0])
        self.assertIn("EDDN shipyard/2", conn.calls[2][0])
        self.assertIn("jsonb_array_elements", conn.calls[2][0])
        self.assertIn("station_ship_offers", conn.calls[3][0])

    def test_direct_shipyard_price_refreshes_global_reference_model(self):
        conn = RecordingConnection()
        projected = upsert_station_offer_batch(conn, [{
            "kind": "SHIPYARD", "market_id": 42,
            "system_name": "Cubeo", "station_name": "Chelomey Orbital",
            "items": '[{"name":"anaconda","id":1,"buyPrice":100000}]',
            "horizons": True, "odyssey": True,
            "observed_at": "2026-10-06T08:00:00Z",
            "received_at": "2026-10-06T08:00:01Z",
            "source": "ED-Frame Journal · Shipyard.json",
        }])
        self.assertEqual(projected, 1)
        self.assertEqual(len(conn.calls), 3)
        self.assertIn("station_ship_offers", conn.calls[1][0])
        self.assertIn("UPDATE ship_catalog", conn.calls[2][0])
        self.assertEqual(conn.calls[2][1]["market_id"], 42)

    def test_direct_carrier_metadata_is_saved_before_price_reference(self):
        conn = RecordingConnection()
        upsert_station_offer_batch(conn, [{
            "kind": "SHIPYARD", "market_id": 43,
            "system_name": "Cubeo", "station_name": "ABC-123",
            "station_type": "FleetCarrier", "fleet_carrier": True,
            "items": '[{"name":"anaconda","id":1,"buyPrice":1}]',
            "horizons": True, "odyssey": True,
            "observed_at": "2026-10-06T08:00:00Z",
            "received_at": "2026-10-06T08:00:01Z",
            "source": "ED-Frame Journal · Shipyard.json",
        }])
        self.assertIn("INSERT INTO stations", conn.calls[0][0])
        self.assertTrue(conn.calls[0][1]["fleet_carrier"])
        self.assertIn("station_shipyards", conn.calls[1][0])
        self.assertIn("station_ship_offers", conn.calls[2][0])
        self.assertIn("UPDATE ship_catalog", conn.calls[3][0])

    def test_reference_catalog_seeds_module_quality_and_ship_facts(self):
        conn = RecordingConnection()
        seed_reference_catalog(conn)
        self.assertEqual(len(conn.calls), 2)
        module_sql, module_values = conn.calls[0]
        ship_sql, ship_values = conn.calls[1]
        self.assertIn("module_catalog", module_sql)
        self.assertIn("ship_catalog", ship_sql)
        modules = __import__("json").loads(module_values[0])
        ships = __import__("json").loads(ship_values[0])
        beam = next(row for row in modules if row["symbol"] == "hpt_beamlaser_fixed_small")
        self.assertEqual((beam["display_name"], beam["module_class"], beam["rating"]),
                         ("BEAM LASER", 1, "E"))
        self.assertTrue(any(row["display_name"] == "Anaconda" for row in ships))


if __name__ == "__main__":
    unittest.main()
