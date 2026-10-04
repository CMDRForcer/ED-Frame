import unittest

from ed_companion.phase14.controller_navigation import (
    NavigationMixin,
    _merge_edframe_market_delta_page,
    _merge_edframe_station_offer_delta_page,
)


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

    def _schedule_mining_market_backup(self):
        return self._mining_market_store.backup()


class SyncStore:
    def __init__(self):
        self.events = []
        self.values = {}

    def ingest(self, rows, *, create_backup=True):
        self.events.append(("ingest", list(rows), create_backup))
        return len(rows)

    def ingest_station_offers(self, rows):
        self.events.append(("offers", list(rows)))
        return len(rows)

    def station_offer_summary(self):
        return {
            "stations": 12, "outfittingStations": 10,
            "shipyardStations": 8,
        }

    def set_metadata(self, key, value):
        self.events.append(("cursor", key, value))
        self.values[key] = value

    def count(self):
        return 321

    def record_source_result(self, source, *, success, error=""):
        self.events.append(("source", source, success, error))

    def backup(self):
        self.events.append(("backup",))
        return True


class BackupStore:
    def __init__(self, due=True):
        self.due = due
        self.calls = 0

    def backup_due(self):
        return self.due

    def backup(self):
        self.calls += 1
        return True


class BackupController:
    def __init__(self, store):
        self._mining_market_store = store
        self.started = 0

    def _start_network_worker(self, target, name):
        self.started += 1
        self.worker_name = name
        target()
        return True


class EdFrameCatalogStatusTests(unittest.TestCase):
    def test_market_backup_is_skipped_while_recent(self):
        store = BackupStore(due=False)
        controller = BackupController(store)

        result = NavigationMixin._schedule_mining_market_backup(controller)

        self.assertTrue(result)
        self.assertEqual(controller.started, 0)
        self.assertEqual(store.calls, 0)

    def test_market_backup_requests_are_coalesced_while_running(self):
        store = BackupStore(due=True)
        controller = BackupController(store)
        controller._mining_market_backup_running = True

        result = NavigationMixin._schedule_mining_market_backup(controller)

        self.assertTrue(result)
        self.assertEqual(controller.started, 0)
        self.assertEqual(store.calls, 0)

    def test_due_market_backup_runs_once_in_background(self):
        store = BackupStore(due=True)
        controller = BackupController(store)

        result = NavigationMixin._schedule_mining_market_backup(controller)

        self.assertTrue(result)
        self.assertEqual(controller.started, 1)
        self.assertEqual(controller.worker_name, "mining-market-backup")
        self.assertEqual(store.calls, 1)
        self.assertFalse(controller._mining_market_backup_running)

    def test_station_offer_page_is_merged_before_cursor_advances(self):
        store = SyncStore()
        page = _merge_edframe_station_offer_delta_page(store, {
            "rows": [{"kind": "OUTFITTING", "marketId": 42}],
            "nextCursor": "offers-2", "hasMore": False,
            "generatedAt": "2026-10-03T10:00:00Z",
        })
        self.assertEqual(store.events[0][0], "offers")
        self.assertEqual(store.events[1], (
            "cursor", "edframe_station_offer_sync_cursor", "offers-2",
        ))
        self.assertEqual(page["localSummary"]["stations"], 12)

    def test_incremental_page_is_merged_before_resume_cursor_advances(self):
        store = SyncStore()

        page = _merge_edframe_market_delta_page(store, {
            "rows": [{"commodity": "platinum"}],
            "nextCursor": "page-2", "hasMore": False,
            "generatedAt": "2026-10-03T10:00:00Z",
        })

        self.assertEqual(store.events[0][0], "ingest")
        self.assertEqual(store.events[1], (
            "cursor", "edframe_market_sync_cursor", "page-2",
        ))
        self.assertEqual(page["ingested"], 1)
        self.assertEqual(page["localCount"], 321)

    def test_completed_incremental_page_updates_visible_sync_state(self):
        controller = ControllerStub()
        store = SyncStore()
        controller._mining_market_store = store
        controller._active_edframe_catalog_sync_request = {
            "id": "sync", "generation": 7,
        }
        controller._profile_generation = 7
        controller._edframe_catalog_sync_busy = True
        controller._edframe_catalog_sync_rows = 0
        controller._mining_market_revision = 0
        controller._mining_market_cache_status = lambda: "321 retained"

        NavigationMixin._finish_edframe_catalog_sync(controller, {
            "id": "sync", "generation": 7, "success": True,
            "ingested": 1, "rowCount": 1, "localCount": 321,
            "nextCursor": "page-2", "hasMore": False,
            "generatedAt": "2026-10-03T10:00:00Z",
        })

        self.assertTrue(any(event[0] == "backup" for event in store.events))
        self.assertEqual(controller._edframe_catalog_stats["localMarkets"], 321)
        self.assertIn("Up to date", controller._edframe_catalog_sync_status)

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
                    "state_bgs_snapshots": 6,
                    "state_signals": 7,
                    "outfitting_stations": 8,
                    "shipyard_stations": 9,
                    "module_offers": 100,
                    "priced_module_offers": 75,
                    "ship_offers": 20,
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
        self.assertEqual(
            controller._edframe_catalog_stats["stateBgsSnapshots"], 6
        )
        self.assertEqual(controller._edframe_catalog_stats["stateSignals"], 7)
        self.assertEqual(
            controller._edframe_catalog_stats["outfittingStations"], 8
        )
        self.assertEqual(
            controller._edframe_catalog_stats["pricedModuleOffers"], 75
        )
        self.assertEqual(controller._edframe_catalog_stats["shipOffers"], 20)
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
