import unittest

from ed_companion.navigation.mining_market import (
    EDDATA_MARKET_SOURCE,
    MiningMarketError,
    fetch_market_imports,
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


if __name__ == "__main__":
    unittest.main()
