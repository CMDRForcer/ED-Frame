import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from ed_companion.navigation.station_services import fetch_station_services, describe_station_services
from ed_companion.navigation.mining_market import MiningMarketError
from ed_companion.phase14.controller_station_services import StationServicesMixin


class StationServiceTests(unittest.TestCase):
    def payload(self):
        return {"region": {"origin": [0, 0, 0], "radiusLy": 100}, "hasMore": False,
                "results": [{"marketId": 1, "system": "Here", "station": "Hub",
                             "services": ["repair"], "distanceLy": 5,
                             "landingPadSize": "L", "fleetCarrier": False}]}

    def get(self, payload):
        response = Mock()
        response.json.return_value = payload
        return Mock(return_value=response)

    def test_medium_ship_can_use_large_pad(self):
        get = self.get(self.payload())
        result = fetch_station_services(origin=[0, 0, 0], service="repair", pad="M", get=get)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(get.call_args.kwargs["params"]["landing_pad"], "M")

    def test_filters_invalid_service_distance_pad_and_carrier(self):
        payload = self.payload()
        base = payload["results"][0]
        payload["results"] = [
            {**base, "services": ["refuel"]}, {**base, "distanceLy": 101},
            {**base, "distanceLy": float("nan")}, {**base, "landingPadSize": "S"},
            {**base, "fleetCarrier": True},
        ]
        result = fetch_station_services(origin=[0, 0, 0], service="repair", pad="M",
                                        get=self.get(payload))
        self.assertEqual(result["results"], [])

    def test_unknown_pad_not_treated_as_compatible(self):
        payload = self.payload()
        payload["results"][0]["landingPadSize"] = None
        self.assertEqual(fetch_station_services(origin=[0, 0, 0], service="repair", pad="S",
                                               get=self.get(payload))["results"], [])

    def test_region_confirmation_required(self):
        payload = self.payload()
        payload["region"] = None
        with self.assertRaises(MiningMarketError):
            fetch_station_services(origin=[0, 0, 0], service="repair", get=self.get(payload))

    def test_invalid_position_sends_nothing(self):
        get = Mock()
        with self.assertRaises(MiningMarketError):
            fetch_station_services(origin=[], service="repair", get=get)
        get.assert_not_called()

    def test_age_is_metadata_age_not_guessed_zero(self):
        rows = [{"system": "Here", "observedAt": "2026-10-07T08:00:00Z"},
                {"system": "Elsewhere", "observedAt": "bad"}]
        result = describe_station_services(rows, now=datetime(2026, 10, 7, 10, tzinfo=timezone.utc))
        self.assertEqual(result[0]["ageHours"], 2)
        self.assertIsNone(result[1]["ageHours"])

    def test_missing_rank_is_not_invented(self):
        row = {"system": "Sol"}
        result = describe_station_services([row], permit_rules={
            "sol": {"name": "Sol permit", "rule": {"type": "rank", "field": "federation", "minimum": 4}}
        })
        self.assertNotEqual(result[0]["accessStatus"], "CONFIRMED")

    def shell(self):
        region = {"origin": [0., 0., 0.], "radiusLy": 100.}
        return SimpleNamespace(
            _station_services_request={"id": "job", "region": region, "system": "Here", "service": "repair"},
            _state={"currentPosition": [0, 0, 0]}, _profile_generation=4,
            _edframe_catalog_enabled=True, _station_services_rows=[{"station": "Old"}],
            stationServicesChanged=Mock(), stationServicesFinished=Mock(),
            _start_network_worker=Mock(return_value=True), stationServiceBusy=False,
        )

    def test_failed_search_retains_previous_rows(self):
        controller = self.shell()
        StationServicesMixin._finish_station_services(controller, {
            "id": "job", "generation": 4, "success": False, "error": "HTTP 503",
        })
        self.assertEqual(controller._station_services_rows, [{"station": "Old"}])
        self.assertIn("HTTP 503", controller._station_services_status)

    def test_profile_and_location_changes_reject_result(self):
        for profile in (True, False):
            controller = self.shell()
            if profile:
                controller._profile_generation = 5
            else:
                controller._state["currentPosition"] = [1, 2, 3]
            StationServicesMixin._finish_station_services(controller, {
                "id": "job", "generation": 4, "success": True, "payload": self.payload(),
            })
            self.assertNotEqual(controller._station_services_rows, self.payload()["results"])

    def test_success_retains_bounded_warning(self):
        controller = self.shell()
        payload = self.payload()
        payload["hasMore"] = True
        StationServicesMixin._finish_station_services(controller, {
            "id": "job", "generation": 4, "success": True, "payload": payload,
        })
        self.assertEqual(controller._station_services_rows_generation, 4)
        self.assertIn("first 100", controller._station_services_status)

    def test_disabled_server_sends_nothing(self):
        controller = self.shell()
        controller._edframe_catalog_enabled = False
        StationServicesMixin.searchStationServices(controller, "repair", 100, "ANY", True)
        controller._start_network_worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
