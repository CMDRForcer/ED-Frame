import unittest

from edframe_catalog.projection import (
    project_markets,
    project_stations,
    project_system,
    projected_systems,
    schema_name,
)


def commodity(name, *, sell_price=0, demand=0, status_flags=None):
    return {
        "name": name,
        "meanPrice": 100,
        "buyPrice": 90,
        "stock": 0,
        "stockBracket": 0,
        "sellPrice": sell_price,
        "demand": demand,
        "demandBracket": 0,
        "statusFlags": status_flags or [],
    }


class ProjectionTests(unittest.TestCase):
    def test_schema_name_uses_only_contract_tail(self):
        self.assertEqual(
            schema_name({
                "$schemaRef": "https://eddn.edcd.io/schemas/commodity/3",
            }),
            "commodity/3",
        )

    def test_market_projection_keeps_all_complete_commodity_rows(self):
        payload = {
            "$schemaRef": "https://eddn.edcd.io/schemas/commodity/3",
            "message": {
                "timestamp": "2026-10-03T08:00:00Z",
                "systemName": "Cubeo",
                "stationName": "Chelomey Orbital",
                "marketId": 42,
                "commodities": [
                    commodity(
                        "Platinum", sell_price=250000, demand=9000,
                        status_flags=["Rare"],
                    ),
                    commodity("Tea", sell_price=1200, demand=20),
                    commodity("Painite", sell_price=0, demand=0),
                ],
            },
        }
        rows = project_markets(payload, "2026-10-03T08:00:01Z")
        self.assertEqual(len(rows), 3)
        platinum = rows[0]
        self.assertEqual(platinum["commodity"], "platinum")
        self.assertEqual(platinum["station_name"], "Chelomey Orbital")
        self.assertEqual(platinum["sell_price"], 250000)
        self.assertEqual(platinum["mean_price"], 100)
        self.assertEqual(platinum["stock"], 0)
        self.assertEqual(platinum["demand_bracket"], 0)
        self.assertEqual(platinum["status_flags"], ["Rare"])
        self.assertEqual(rows[2]["sell_price"], 0)
        self.assertEqual(rows[2]["demand"], 0)

    def test_market_projection_rejects_incomplete_rows(self):
        payload = {
            "$schemaRef": "https://eddn.edcd.io/schemas/commodity/3",
            "message": {
                "timestamp": "2026-10-03T08:00:00Z",
                "systemName": "Cubeo",
                "stationName": "Chelomey Orbital",
                "marketId": 42,
                "commodities": [{"name": "Platinum", "sellPrice": 1}],
            },
        }
        self.assertEqual(
            project_markets(payload, "2026-10-03T08:00:01Z"), []
        )

    def test_station_projection_uses_public_commodity_metadata_only(self):
        payload = {
            "$schemaRef": "https://eddn.edcd.io/schemas/commodity/3",
            "header": {"uploaderID": "must not be projected"},
            "message": {
                "timestamp": "2026-10-03T08:00:00Z",
                "systemName": "Cubeo",
                "stationName": "Chelomey Orbital",
                "marketId": 42,
                "stationType": "Coriolis",
                "economies": [
                    {"name": "High Tech", "proportion": 0.8},
                ],
                "prohibited": ["Slaves"],
            },
        }
        rows = project_stations(payload, "2026-10-03T08:00:01Z")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["market_id"], 42)
        self.assertEqual(row["station_type"], "Coriolis")
        self.assertEqual(row["economies"], [
            {"name": "High Tech", "proportion": 0.8},
        ])
        self.assertEqual(row["prohibited"], ["Slaves"])
        self.assertIsNone(row["landing_pad_size"])
        self.assertNotIn("uploaderID", row)

    def test_docked_station_projection_uses_observed_pad_counts(self):
        payload = {
            "$schemaRef": "https://eddn.edcd.io/schemas/journal/1",
            "message": {
                "event": "Docked",
                "timestamp": "2026-10-03T08:00:00Z",
                "StarSystem": "Cubeo",
                "SystemAddress": 123,
                "StationName": "Chelomey Orbital",
                "MarketID": 42,
                "StationType": "Coriolis",
                "DistFromStarLS": 50.5,
                "LandingPads": {"Small": 4, "Medium": 4, "Large": 2},
                "StationServices": ["Market", "Outfitting"],
                "StationFaction": {"Name": "Cubeo Patron's Principles"},
                "Commander": "must not be projected",
            },
        }
        row = project_stations(payload, "2026-10-03T08:00:01Z")[0]
        self.assertEqual(row["landing_pad_size"], "L")
        self.assertEqual(row["distance_to_arrival_ls"], 50.5)
        self.assertEqual(row["services"], ["Market", "Outfitting"])
        self.assertEqual(row["controlling_faction"], "Cubeo Patron's Principles")
        self.assertNotIn("Commander", row)

    def test_station_pad_is_not_guessed_from_station_type(self):
        payload = {
            "$schemaRef": "https://eddn.edcd.io/schemas/journal/1",
            "message": {
                "event": "Docked",
                "StarSystem": "Cubeo",
                "StationName": "Small Outpost",
                "MarketID": 43,
                "StationType": "Outpost",
            },
        }
        row = project_stations(payload, "2026-10-03T08:00:01Z")[0]
        self.assertIsNone(row["landing_pad_size"])

    def test_system_projection_keeps_public_location_only(self):
        row = project_system({
            "$schemaRef": "https://eddn.edcd.io/schemas/journal/1",
            "message": {
                "event": "FSDJump",
                "timestamp": "2026-10-03T08:00:00Z",
                "StarSystem": "Cubeo",
                "SystemAddress": 123,
                "StarPos": [1, 2.5, -3],
                "Commander": "must not be projected",
            },
        })
        self.assertEqual(row["name"], "Cubeo")
        self.assertEqual((row["x"], row["y"], row["z"]), (1.0, 2.5, -3.0))
        self.assertNotIn("Commander", row)

    def test_systems_are_learned_from_all_projected_rows(self):
        rows = projected_systems(
            None,
            [{"system_name": "Cubeo", "observed_at": "2026-10-03T08:00:00Z"}],
            [{
                "system_name": "Cubeo", "system_address": 123,
                "x": 1.0, "y": 2.0, "z": 3.0,
                "observed_at": "2026-10-03T08:01:00Z",
            }],
            [{
                "system_name": "Achenar", "system_address": 456,
                "observed_at": "2026-10-03T08:02:00Z",
            }],
        )
        self.assertEqual(len(rows), 2)
        cubeo = next(row for row in rows if row["name"] == "Cubeo")
        self.assertEqual(cubeo["system_address"], 123)
        self.assertEqual((cubeo["x"], cubeo["y"], cubeo["z"]), (1.0, 2.0, 3.0))
        achenar = next(row for row in rows if row["name"] == "Achenar")
        self.assertEqual(achenar["system_address"], 456)


if __name__ == "__main__":
    unittest.main()
