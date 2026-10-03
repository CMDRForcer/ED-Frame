import unittest

from ed_companion.phase14.controller_navigation import NavigationMixin


class Emitter:
    def emit(self):
        pass


class ControllerStub:
    connectionChanged = Emitter()
    miningChanged = Emitter()

    def __init__(self):
        self._active_edframe_catalog_request = {"id": "request"}
        self._edframe_catalog_enabled = True
        self._edframe_catalog_busy = True
        self._edframe_catalog_stats = {}
        self._edframe_catalog_log = []
        self._mining_market_store = None

    def _append_edframe_catalog_log(self, text):
        self._edframe_catalog_log.append(text)

    def _save_ui_config(self):
        pass


class EdFrameCatalogStatusTests(unittest.TestCase):
    def test_new_station_and_completeness_metrics_are_retained(self):
        controller = ControllerStub()
        NavigationMixin._finish_edframe_catalog_status(controller, {
            "id": "request",
            "success": True,
            "status": {
                "generatedAt": "2026-10-03T08:00:00Z",
                "counts": {
                    "systems": 10,
                    "stations": 20,
                    "markets": 30,
                    "sites": 40,
                    "commodities": 50,
                },
                "completeness": {
                    "marketDetailPercent": 99.5,
                    "stationTypePercent": 80,
                    "stationLandingPadPercent": 70,
                    "stationServicesPercent": 60,
                },
                "collector": {
                    "messages_total": 123,
                    "errors_total": 2,
                },
            },
        })

        self.assertEqual(controller._edframe_catalog_stats["stations"], 20)
        self.assertEqual(
            controller._edframe_catalog_stats["marketDetailPercent"], 99.5
        )
        self.assertEqual(
            controller._edframe_catalog_stats["stationLandingPadPercent"], 70
        )
        self.assertEqual(controller._edframe_catalog_stats["collectorMessages"], 123)
        self.assertEqual(controller._edframe_catalog_stats["collectorErrors"], 2)
        self.assertIn("20 stations", controller._edframe_catalog_status)

    def test_old_server_does_not_report_missing_station_catalog_as_zero(self):
        controller = ControllerStub()
        NavigationMixin._finish_edframe_catalog_status(controller, {
            "id": "request",
            "success": True,
            "status": {
                "counts": {"systems": 10, "markets": 30, "sites": 40},
                "completeness": {},
                "collector": {},
            },
        })

        self.assertEqual(controller._edframe_catalog_stats["stations"], -1)
        self.assertEqual(
            controller._edframe_catalog_stats["stationLandingPadPercent"], -1
        )
        self.assertIn(
            "station catalog pending server update",
            controller._edframe_catalog_status,
        )
        self.assertNotIn("0 stations", controller._edframe_catalog_status)


if __name__ == "__main__":
    unittest.main()
