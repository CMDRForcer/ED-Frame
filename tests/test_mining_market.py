from datetime import datetime, timezone
import unittest

from ed_companion.navigation.mining_market import (
    EDDATA_MARKET_SOURCE,
    MiningMarketError,
    fetch_edsm_system_coordinates,
    fetch_market_imports,
    latest_market_rows,
    merge_market_catalog,
    nearby_catalog_markets,
    project_local_market_snapshot,
    project_market_imports,
)


class _Response:
    def __init__(self, payload, error=None):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error
        return None

    def json(self):
        return self.payload


class MiningMarketTests(unittest.TestCase):
    def test_edsm_resolves_free_text_origin_without_commander_identity(self):
        calls = []

        def get(url, **kwargs):
            calls.append((url, kwargs))
            return _Response({
                "name": "Cubeo",
                "coords": {"x": 128.25, "y": 42.5, "z": -72.0},
            })

        origin = fetch_edsm_system_coordinates("cubeo", get=get)

        self.assertEqual(origin["system"], "Cubeo")
        self.assertEqual(origin["coordinates"], [128.25, 42.5, -72.0])
        url, kwargs = calls[0]
        self.assertEqual(url, "https://www.edsm.net/api-v1/system")
        self.assertEqual(kwargs["params"], {
            "systemName": "cubeo", "showCoordinates": 1,
        })
        self.assertNotIn("commander", str((url, kwargs)).casefold())

    def test_projects_station_sell_offer_as_commander_sale_price(self):
        rows = project_market_imports([{
            "commodityName": "platinum",
            "marketId": 42,
            "stationName": "Safe Port",
            "stationType": "Coriolis",
            "systemName": "HIP 1",
            "systemAddress": 1234,
            "systemX": 1,
            "systemY": 2,
            "systemZ": 3,
            "maxLandingPadSize": "L",
            "distanceToArrival": 321.5,
            "buyPrice": 0,
            "sellPrice": 250000,
            "demand": 8000,
            "demandBracket": 3,
            "updatedAt": "2026-10-01T10:00:00Z",
        }], "Platinum")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sellPrice"], 250000)
        self.assertEqual(rows[0]["demand"], 8000)
        self.assertEqual(rows[0]["source"], EDDATA_MARKET_SOURCE)
        self.assertEqual(rows[0]["systemAddress"], 1234)
        self.assertIsNone(rows[0]["meritEligible"])

    def test_positive_demand_bracket_marks_zero_as_infinite(self):
        row = {
            "commodityName": "platinum", "marketId": 42,
            "stationName": "Safe Port", "systemName": "HIP 1",
            "sellPrice": 250000, "demand": 0, "demandBracket": 3,
            "updatedAt": "2026-10-01T10:00:00Z",
        }
        self.assertTrue(project_market_imports([row], "Platinum")[0]["demandInfinite"])

    def test_local_market_snapshot_keeps_only_sellable_mining_commodities(self):
        rows = project_local_market_snapshot({
            "timestamp": "2026-10-02T10:00:00Z",
            "StarSystem": "Cubeo",
            "StationName": "Medupe City",
            "MarketID": 42,
            "Items": [{
                "Name": "$Platinum_Name;", "SellPrice": 250000,
                "Demand": 0, "DemandBracket": 3,
            }, {
                "Name": "$FoodCartridges_Name;", "SellPrice": 100,
                "Demand": 500, "DemandBracket": 1,
            }, {
                "Name": "$Gold_Name;", "SellPrice": 0,
                "Demand": 0, "DemandBracket": 0,
            }],
        }, coordinates=[1, 2, 3])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["commodity"], "platinum")
        self.assertEqual(rows[0]["coordinates"], [1.0, 2.0, 3.0])
        self.assertTrue(rows[0]["demandInfinite"])
        self.assertEqual(rows[0]["source"], "Local Journal Market.json")

    def test_rejects_structured_service_failure(self):
        with self.assertRaises(MiningMarketError):
            project_market_imports({
                "status": "unavailable", "message": "maintenance",
            }, "Platinum")

    def test_fetch_sends_no_commander_identity_and_uses_bounded_query(self):
        calls = []

        def get(url, **kwargs):
            calls.append((url, kwargs))
            return _Response([])

        self.assertEqual(fetch_market_imports(
            "HIP 6703", "Platinum", max_distance=250,
            max_days_ago=1, get=get,
        ), [])
        url, kwargs = calls[0]
        self.assertIn("HIP%206703", url)
        self.assertIn("/platinum/nearby/imports", url)
        self.assertEqual(kwargs["params"]["fleetCarriers"], "false")
        self.assertEqual(kwargs["params"]["maxDistance"], 250)
        self.assertNotIn("commander", str((url, kwargs)).casefold())

    def test_fetch_falls_back_when_primary_index_is_unavailable(self):
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            if len(calls) == 1:
                return _Response(None, RuntimeError("primary down"))
            return _Response([])

        self.assertEqual(fetch_market_imports(
            "Sol", "Gold", max_distance=100, max_days_ago=1, get=get,
        ), [])
        self.assertIn("api.ardent-insight.com", calls[0])
        self.assertIn("api.eddata.dev", calls[1])

    def test_catalog_accumulates_markets_and_newer_observation_wins(self):
        old = {
            "commodity": "platinum", "station": "Port A", "system": "A",
            "sellPrice": 100000, "observedAt": "2026-09-25T10:00:00Z",
            "coordinates": [0, 0, 0],
        }
        newer = {
            **old, "sellPrice": 250000,
            "observedAt": "2026-10-01T10:00:00Z",
        }
        other = {
            "commodity": "platinum", "station": "Port B", "system": "B",
            "sellPrice": 200000, "observedAt": "2026-10-01T09:00:00Z",
            "coordinates": [3, 4, 0],
        }

        catalog = merge_market_catalog(
            {"markets": [old]}, [newer, other],
            now=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )

        self.assertEqual(len(catalog["markets"]), 2)
        rows = latest_market_rows(catalog["markets"], [old])
        port_a = next(row for row in rows if row["station"] == "Port A")
        self.assertEqual(port_a["sellPrice"], 250000)

    def test_catalog_prunes_expired_rows_and_selects_search_radius(self):
        catalog = merge_market_catalog(
            {}, [{
                "commodity": "platinum", "station": "Local", "system": "A",
                "sellPrice": 100000, "observedAt": "2026-10-01T10:00:00Z",
                "coordinates": [0, 0, 0],
            }, {
                "commodity": "platinum", "station": "Near", "system": "B",
                "sellPrice": 200000, "observedAt": "2026-10-01T10:00:00Z",
                "coordinates": [3, 4, 0],
            }, {
                "commodity": "platinum", "station": "Far", "system": "C",
                "sellPrice": 300000, "observedAt": "2026-10-01T10:00:00Z",
                "coordinates": [30, 0, 0],
            }, {
                "commodity": "platinum", "station": "Expired", "system": "D",
                "sellPrice": 400000, "observedAt": "2026-08-01T10:00:00Z",
                "coordinates": [1, 0, 0],
            }], now=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )

        rows = nearby_catalog_markets(
            catalog, "Platinum", origin_system="A",
            origin_coordinates=[0, 0, 0], max_distance=10,
        )

        self.assertEqual({row["station"] for row in rows}, {"Local", "Near"})


if __name__ == "__main__":
    unittest.main()
