from datetime import datetime, timezone
import unittest

from ed_companion.navigation.mining_market import (
    EDDATA_MARKET_SOURCE,
    MiningMarketError,
    fetch_edframe_catalog_status,
    fetch_edframe_market_delta,
    fetch_edframe_station_offer_delta,
    fetch_edframe_system_coordinates,
    fetch_edsm_system_coordinates,
    fetch_market_imports,
    latest_market_rows,
    merge_market_catalog,
    nearby_catalog_markets,
    project_local_market_snapshot,
    project_edframe_catalog_markets,
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
    def test_incremental_sync_is_anonymous_bounded_and_resumable(self):
        calls = []

        def get(url, **kwargs):
            calls.append((url, kwargs))
            return _Response({
                "generatedAt": "2026-10-03T10:00:00Z",
                "nextCursor": "cursor-2",
                "hasMore": True,
                "results": [{
                    "marketId": 42, "commodity": "platinum",
                    "station": "Safe Port", "system": "HIP 1",
                    "sellPrice": 260000, "demand": 9000,
                    "observedAt": "2026-10-03T10:00:00Z",
                }],
            })

        page = fetch_edframe_market_delta(
            cursor="cursor-1", get=get, limit=250,
        )

        self.assertEqual(page["nextCursor"], "cursor-2")
        self.assertTrue(page["hasMore"])
        self.assertEqual(page["rows"][0]["commodity"], "platinum")
        url, kwargs = calls[0]
        self.assertTrue(url.endswith("/v1/sync/markets"))
        self.assertEqual(kwargs["params"]["cursor"], "cursor-1")
        self.assertEqual(kwargs["params"]["limit"], 250)
        self.assertIn("platinum", kwargs["params"]["commodities"])
        self.assertNotIn("commander", str((url, kwargs)).casefold())

    def test_incremental_sync_rejects_a_non_advancing_cursor(self):
        def get(_url, **_kwargs):
            return _Response({
                "nextCursor": "same", "hasMore": True, "results": [{
                    "marketId": 42, "commodity": "platinum",
                    "station": "Safe Port", "system": "HIP 1",
                    "sellPrice": 260000, "demand": 9000,
                    "observedAt": "2026-10-03T10:00:00Z",
                }],
            })

        with self.assertRaises(MiningMarketError):
            fetch_edframe_market_delta(cursor="same", get=get)

    def test_station_offer_sync_is_anonymous_bounded_and_resumable(self):
        calls = []

        def get(url, **kwargs):
            calls.append((url, kwargs))
            return _Response({
                "generatedAt": "2026-10-03T10:00:00Z",
                "nextCursor": "offers-2", "hasMore": True,
                "results": [{
                    "kind": "OUTFITTING", "marketId": 42,
                    "system": "Cubeo", "station": "Chelomey Orbital",
                    "items": ["int_fuelscoop_size8_class5"],
                    "observedAt": "2026-10-03T09:00:00Z",
                }],
            })

        page = fetch_edframe_station_offer_delta(
            cursor="offers-1", get=get, limit=250,
        )
        self.assertEqual(page["nextCursor"], "offers-2")
        self.assertTrue(page["hasMore"])
        url, kwargs = calls[0]
        self.assertTrue(url.endswith("/v1/sync/station-offers"))
        self.assertEqual(kwargs["params"], {
            "cursor": "offers-1", "limit": 250,
        })
        self.assertNotIn("commander", str((url, kwargs)).casefold())

    def test_central_catalog_status_projects_public_counts(self):
        calls = []

        def get(url, **kwargs):
            calls.append((url, kwargs))
            return _Response({
                "generatedAt": "2026-10-03T10:00:00Z",
                "counts": {"systems": 10, "markets": 20, "sites": 30},
            })

        status = fetch_edframe_catalog_status(get=get)
        self.assertEqual(status["counts"]["markets"], 20)
        self.assertTrue(calls[0][0].endswith("/v1/status"))

    def test_central_catalog_resolves_exact_system_coordinates(self):
        calls = []

        def get(url, **kwargs):
            calls.append((url, kwargs))
            return _Response({"results": [{
                "name": "Cubeo", "x": 1, "y": 2.5, "z": -3,
            }]})

        origin = fetch_edframe_system_coordinates("cubeo", get=get)
        self.assertEqual(origin["system"], "Cubeo")
        self.assertEqual(origin["coordinates"], [1.0, 2.5, -3.0])
        self.assertEqual(calls[0][1]["params"], {"q": "cubeo", "limit": 5})

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

    def test_projects_central_catalog_without_inventing_station_metadata(self):
        rows = project_edframe_catalog_markets({"results": [{
            "marketId": 42, "commodity": "platinum",
            "station": "Safe Port", "system": "HIP 1",
            "sellPrice": 260000, "demand": 9000,
            "observedAt": "2026-10-03T10:00:00Z",
            "x": 1, "y": 2, "z": 3,
        }]}, "Platinum")
        self.assertEqual(rows[0]["coordinates"], [1.0, 2.0, 3.0])
        self.assertEqual(rows[0]["landingPadSize"], "")
        self.assertIsNone(rows[0]["meanPrice"])
        self.assertIsNone(rows[0]["stock"])
        self.assertIn("ED-Frame live catalog", rows[0]["source"])

    def test_projects_complete_central_station_and_market_metadata(self):
        rows = project_edframe_catalog_markets({"results": [{
            "marketId": 42, "commodity": "platinum",
            "station": "Safe Port", "system": "HIP 1",
            "systemAddress": 1234, "stationType": "Coriolis",
            "landingPadSize": "L", "distanceToArrivalLs": 321.5,
            "x": 1, "y": 2, "z": 3, "meanPrice": 180000,
            "buyPrice": 0, "sellPrice": 260000, "stock": 12,
            "stockBracket": 1, "demand": 0, "demandBracket": 3,
            "statusFlags": ["Docked"], "services": ["Commodities"],
            "economies": ["Industrial"], "primaryEconomy": "Industrial",
            "government": "Democracy", "controllingFaction": "Test",
            "fleetCarrier": False, "carrierDockingAccess": "all",
            "prohibited": ["Slaves"],
            "observedAt": "2026-10-03T10:00:00Z",
            "receivedAt": "2026-10-03T10:00:01Z",
        }]}, "Platinum")

        self.assertEqual(rows[0]["systemAddress"], 1234)
        self.assertEqual(rows[0]["landingPadSize"], "L")
        self.assertEqual(rows[0]["distanceToArrivalLs"], 321.5)
        self.assertEqual(rows[0]["services"], ["Commodities"])
        self.assertEqual(rows[0]["primaryEconomy"], "Industrial")
        self.assertFalse(rows[0]["fleetCarrier"])
        self.assertTrue(rows[0]["demandInfinite"])

    def test_central_market_query_applies_pad_and_carrier_filters(self):
        calls = []

        def get(url, **kwargs):
            calls.append((url, kwargs))
            if url.endswith("/v1/systems/suggest"):
                return _Response({"results": [{
                    "name": "Cubeo", "x": 1, "y": 2, "z": 3,
                }]})
            if url.endswith("/v1/markets/search"):
                return _Response({"results": []})
            return _Response([])

        fetch_market_imports(
            "Cubeo", "Platinum", max_distance=250, max_days_ago=1,
            landing_pad="LARGE", get=get,
        )
        _, kwargs = next(
            call for call in calls if call[0].endswith("/v1/markets/search")
        )
        self.assertEqual(kwargs["params"]["landing_pad"], "L")
        self.assertTrue(kwargs["params"]["exclude_fleet_carriers"])

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
        url, kwargs = next(
            call for call in calls if "api.ardent-insight.com" in call[0]
        )
        self.assertIn("HIP%206703", url)
        self.assertIn("/platinum/nearby/imports", url)
        self.assertEqual(kwargs["params"]["fleetCarriers"], "false")
        self.assertEqual(kwargs["params"]["maxDistance"], 250)
        self.assertNotIn("commander", str((url, kwargs)).casefold())

    def test_fetch_falls_back_when_primary_index_is_unavailable(self):
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            if "vps-20b25c36" in url:
                return _Response(None, RuntimeError("catalog down"))
            if "api.ardent-insight.com" in url:
                return _Response(None, RuntimeError("primary down"))
            return _Response([])

        self.assertEqual(fetch_market_imports(
            "Sol", "Gold", max_distance=100, max_days_ago=1, get=get,
        ), [])
        self.assertTrue(any("api.ardent-insight.com" in url for url in calls))
        self.assertTrue(any("api.eddata.dev" in url for url in calls))

    def test_disabled_central_catalog_is_not_contacted(self):
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            return _Response([])

        self.assertEqual(fetch_market_imports(
            "Sol", "Gold", max_distance=100, max_days_ago=1, get=get,
            include_edframe=False,
        ), [])
        self.assertFalse(any("vps-20b25c36" in url for url in calls))
        self.assertTrue(any("api.ardent-insight.com" in url for url in calls))

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

    def test_newer_central_price_keeps_older_verified_pad_metadata(self):
        enriched = {
            "commodity": "platinum", "station": "Port A", "system": "A",
            "sellPrice": 100000, "observedAt": "2026-10-01T10:00:00Z",
            "landingPadSize": "L", "distanceToArrivalLs": 500,
        }
        central = {
            **enriched, "sellPrice": 250000,
            "observedAt": "2026-10-03T10:00:00Z",
            "landingPadSize": "", "distanceToArrivalLs": None,
        }
        row = latest_market_rows([enriched], [central])[0]
        self.assertEqual(row["sellPrice"], 250000)
        self.assertEqual(row["landingPadSize"], "L")
        self.assertEqual(row["distanceToArrivalLs"], 500)

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
