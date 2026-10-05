import json
import unittest

from edframe_catalog.projection import (
    project_markets,
    project_station_offers,
    project_station_offer_observations,
    project_stations,
    project_system,
    project_state_bgs_snapshot,
    project_state_signals,
    project_yield_observations,
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
    def test_yield_observations_are_anonymous_validated_and_deduplicated(self):
        observation = {
            "system": "Yield Test", "systemAddress": 7,
            "coordinates": [1, 2, 3], "body": "Yield Test 2",
            "bodyId": 11, "ring": "Yield Test 2 A Ring",
            "ringType": "Metallic", "reserveLevel": "PristineResources",
            "observedAt": "2026-10-03T08:00:00Z",
            "materials": [
                {"commodity": "Platinum", "proportion": 32.5},
                {"commodity": "Osmium", "proportion": 11.25},
            ],
            "commander": "must not survive",
            "journalPath": "must not survive",
        }
        rows = project_yield_observations(
            {"observations": [observation, observation]},
            "2026-10-03T08:00:01Z",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["materials"], {
            "platinum": 32.5, "osmium": 11.25,
        })
        serialized = json.dumps(rows[0])
        self.assertNotIn("must not survive", serialized)
        self.assertNotIn("commander", serialized.casefold())

    def test_yield_observations_reject_missing_materials_and_bad_time(self):
        self.assertEqual(project_yield_observations({"observations": [{
            "system": "Yield Test", "ring": "Yield Test A Ring",
            "observedAt": "2026-10-03T08:00:00Z", "materials": [],
        }]}, "2026-10-03T08:00:01Z"), [])
        self.assertEqual(project_yield_observations({"observations": [{
            "system": "Yield Test", "ring": "Yield Test A Ring",
            "observedAt": "2040-10-03T08:00:00Z",
            "materials": [{"commodity": "Platinum", "proportion": 20}],
        }]}, "2026-10-03T08:00:01Z"), [])

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

    def test_outfitting_inventory_is_complete_normalized_and_anonymous(self):
        payload = {
            "$schemaRef": "https://eddn.edcd.io/schemas/outfitting/2",
            "header": {"uploaderID": "private-name"},
            "message": {
                "timestamp": "2026-10-03T08:00:00Z",
                "systemName": "Cubeo",
                "stationName": "Chelomey Orbital",
                "marketId": 42,
                "horizons": True,
                "odyssey": True,
                "modules": ["Int_FuelScoop_Size8_Class5", "Hpt_BeamLaser"],
            },
        }
        offer = project_station_offers(payload, "2026-10-03T08:00:01Z")[0]
        station = project_stations(payload, "2026-10-03T08:00:01Z")[0]
        self.assertEqual(offer["kind"], "OUTFITTING")
        self.assertEqual(offer["market_id"], 42)
        self.assertIn("int_fuelscoop_size8_class5", offer["items"])
        self.assertNotIn("private-name", offer["items"])
        self.assertEqual(station["station_name"], "Chelomey Orbital")

    def test_outfitting_v3_retains_exact_station_module_prices(self):
        payload = {
            "$schemaRef": "https://eddn.edcd.io/schemas/outfitting/3",
            "header": {"uploaderID": "private-name"},
            "message": {
                "timestamp": "2026-10-03T08:00:00Z",
                "systemName": "Cubeo",
                "stationName": "Chelomey Orbital",
                "marketId": 42,
                "modules": [{
                    "id": 128049429,
                    "Name": "Hpt_BeamLaser_Fixed_Medium",
                    "BuyPrice": 145000,
                    "BuyMercCoinsPrice": 0,
                }],
            },
        }

        offer = project_station_offers(payload, "2026-10-03T08:00:01Z")[0]
        station = project_stations(payload, "2026-10-03T08:00:01Z")[0]

        self.assertEqual(offer["source"], "EDDN outfitting/3")
        self.assertEqual(json.loads(offer["items"]), [{
            "name": "hpt_beamlaser_fixed_medium",
            "id": 128049429,
            "buyPrice": 145000,
            "buyMercCoinsPrice": 0,
            "priceObservedAt": "2026-10-03T08:00:00Z",
            "priceSource": "EDDN outfitting/3",
        }])
        self.assertEqual(station["market_id"], 42)
        self.assertNotIn("private-name", offer["items"])

    def test_shipyard_inventory_rejects_empty_and_keeps_exact_public_ids(self):
        payload = {
            "$schemaRef": "https://eddn.edcd.io/schemas/shipyard/2",
            "message": {
                "timestamp": "2026-10-03T08:00:00Z",
                "systemName": "Cubeo", "stationName": "Chelomey Orbital",
                "marketId": 42, "ships": ["Anaconda", "CobraMkIII"],
            },
        }
        offer = project_station_offers(payload, "2026-10-03T08:00:01Z")[0]
        self.assertEqual(offer["kind"], "SHIPYARD")
        self.assertEqual(offer["items"], '["anaconda", "cobramkiii"]')
        payload["message"]["ships"] = []
        self.assertEqual(
            project_station_offers(payload, "2026-10-03T08:00:01Z"), []
        )

    def test_edframe_shipyard_observation_retains_exact_prices_anonymously(self):
        rows = project_station_offer_observations({"observations": [{
            "kind": "SHIPYARD", "marketId": 42,
            "system": "Cubeo", "station": "Chelomey Orbital",
            "observedAt": "2026-10-03T08:00:00Z",
            "ships": [{
                "id": 128049363, "name": "Anaconda", "buyPrice": 146969451,
            }],
            "commander": "must not be projected",
        }]}, "2026-10-03T08:00:01Z")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "SHIPYARD")
        self.assertEqual(rows[0]["source"], "ED-Frame Journal · Shipyard.json")
        self.assertEqual(json.loads(rows[0]["items"]), [{
            "name": "anaconda", "id": 128049363, "buyPrice": 146969451,
            "priceObservedAt": "2026-10-03T08:00:00Z",
            "priceSource": "ED-Frame Journal · Shipyard.json",
        }])
        self.assertNotIn("commander", rows[0]["items"].casefold())

    def test_edframe_outfitting_observation_retains_exact_prices_anonymously(self):
        rows = project_station_offer_observations({"observations": [{
            "kind": "OUTFITTING", "marketId": 42,
            "system": "Cubeo", "station": "Chelomey Orbital",
            "observedAt": "2026-10-03T08:00:00Z",
            "modules": [{
                "id": 128049511, "name": "Hpt_AdvancedTorpPylon_Fixed_Large",
                "buyPrice": 157960, "buyMercCoinsPrice": 0,
            }],
            "commander": "must not be projected",
        }]}, "2026-10-03T08:00:01Z")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "OUTFITTING")
        self.assertEqual(rows[0]["source"], "ED-Frame Journal · Outfitting.json")
        self.assertEqual(json.loads(rows[0]["items"]), [{
            "name": "hpt_advancedtorppylon_fixed_large",
            "id": 128049511, "buyPrice": 157960,
            "priceObservedAt": "2026-10-03T08:00:00Z",
            "priceSource": "ED-Frame Journal · Outfitting.json",
            "buyMercCoinsPrice": 0,
        }])
        self.assertNotIn("commander", rows[0]["items"].casefold())

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

    def test_state_find_projection_keeps_public_facts_without_uploader(self):
        payload = {
            "$schemaRef": "https://eddn.edcd.io/schemas/journal/1",
            "header": {"uploaderID": "private-name"},
            "message": {
                "event": "FSDJump",
                "timestamp": "2026-10-03T08:00:00Z",
                "StarSystem": "Cubeo",
                "SystemAddress": 123,
                "StarPos": [1, 2, 3],
                "SystemAllegiance": "Empire",
                "Factions": [{
                    "Name": "Cubeo Patron's Principles",
                    "Allegiance": "Empire",
                    "ActiveStates": [{"State": "$FactionState_CivilUnrest;"}],
                }],
            },
        }
        row = project_state_bgs_snapshot(payload, "2026-10-03T08:00:01Z")
        self.assertEqual(row["identity"], "address:123")
        self.assertIn('"system": "Cubeo"', row["snapshot"])
        self.assertNotIn("private-name", row["snapshot"])

    def test_state_signal_projection_rejects_expired_signals(self):
        payload = {
            "$schemaRef": "https://eddn.edcd.io/schemas/fsssignaldiscovered/1",
            "message": {
                "timestamp": "2026-10-03T08:00:00Z",
                "StarSystem": "Cubeo",
                "SystemAddress": 123,
                "StarPos": [1, 2, 3],
                "signals": [{
                    "USSType": "$USS_Type_VeryValuableSalvage;",
                    "SpawningFaction": "Faction",
                    "SpawningState": "$FactionState_Boom;",
                    "timestamp": "2026-10-03T08:00:00Z",
                    "TimeRemaining": 300,
                }],
            },
        }
        current = project_state_signals(payload, "2026-10-03T08:01:00Z")
        expired = project_state_signals(payload, "2026-10-03T08:06:00Z")
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["system_name"], "Cubeo")
        self.assertEqual(expired, [])


if __name__ == "__main__":
    unittest.main()
