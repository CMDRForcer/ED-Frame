from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ed_companion.navigation.mining_market_store import MarketCatalogStore


def _row(observed, **changes):
    row = {
        "commodity": "platinum",
        "system": "Cubeo",
        "station": "Medupe City",
        "marketId": 42,
        "landingPadSize": "L",
        "coordinates": [1, 2, 3],
        "sellPrice": 250000,
        "demand": 5000,
        "observedAt": observed.isoformat(timespec="seconds"),
        "source": "test",
    }
    row.update(changes)
    return row


class MiningMarketStoreTests(unittest.TestCase):
    def test_station_offers_merge_independent_inventories_and_survive_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "market.sqlite3")
            store = MarketCatalogStore(path)
            common = {
                "marketId": 42, "system": "Cubeo",
                "station": "Chelomey Orbital", "systemAddress": 123,
                "stationType": "Coriolis", "landingPadSize": "L",
                "distanceToArrivalLs": 50.5, "x": 1, "y": 2, "z": 3,
                "services": ["Outfitting", "Shipyard"],
                "receivedAt": "2026-10-03T08:00:01Z",
                "source": "EDDN",
            }
            store.ingest_station_offers([
                {**common, "kind": "OUTFITTING",
                 "items": ["Int_FuelScoop_Size8_Class5"],
                 "observedAt": "2026-10-03T08:00:00Z"},
                {**common, "kind": "SHIPYARD", "items": ["Anaconda"],
                 "observedAt": "2026-10-03T08:01:00Z"},
            ])
            reopened = MarketCatalogStore(path)
            self.assertEqual(reopened.station_offer_summary(), {
                "stations": 1, "outfittingStations": 1,
                "shipyardStations": 1,
            })
            module = reopened.stations_offering(
                "INT_FUELSCOOP_SIZE8_CLASS5", kind="OUTFITTING"
            )[0]
            ship = reopened.stations_offering("anaconda", kind="SHIPYARD")[0]
            self.assertEqual(module["station"], "Chelomey Orbital")
            self.assertEqual(module["coordinates"], [1.0, 2.0, 3.0])
            self.assertEqual(ship["system"], "Cubeo")

    def test_older_or_invalid_station_offer_does_not_replace_inventory(self):
        with TemporaryDirectory() as directory:
            store = MarketCatalogStore(Path(directory, "market.sqlite3"))
            base = {
                "kind": "OUTFITTING", "marketId": 42,
                "system": "Cubeo", "station": "Chelomey Orbital",
                "source": "EDDN",
            }
            self.assertEqual(store.ingest_station_offers([
                {**base, "items": ["new-module"],
                 "observedAt": "2026-10-03T08:00:00Z"},
                {**base, "items": [],
                 "observedAt": "2026-10-03T09:00:00Z"},
                {**base, "items": ["old-module"],
                 "observedAt": "2026-10-03T07:00:00Z"},
            ]), 2)
            self.assertEqual(len(store.stations_offering(
                "new-module", kind="OUTFITTING"
            )), 1)
            self.assertEqual(store.stations_offering(
                "old-module", kind="OUTFITTING"
            ), [])

    def test_incremental_server_cursor_survives_restart_and_reset_clears_it(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "market.sqlite3"
            store = MarketCatalogStore(path)
            store.set_metadata("edframe_market_sync_cursor", "page-17")

            reopened = MarketCatalogStore(path)
            self.assertEqual(
                reopened.metadata("edframe_market_sync_cursor"), "page-17"
            )

            reopened.reset()
            self.assertEqual(
                reopened.metadata("edframe_market_sync_cursor"), ""
            )

    def test_complete_station_metadata_survives_restart_and_sparse_refresh(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "market.sqlite3")
            now = datetime.now(timezone.utc)
            rich = _row(
                now - timedelta(minutes=1), stationType="Coriolis",
                systemAddress=1234, distanceToArrivalLs=321.5,
                meanPrice=180000, buyPrice=0, stock=12, stockBracket=1,
                statusFlags=["Docked"], receivedAt=now.isoformat(),
                services=["Commodities"], economies=["Industrial"],
                primaryEconomy="Industrial", government="Democracy",
                controllingFaction="Test", fleetCarrier=False,
                carrierDockingAccess="all", prohibited=["Slaves"],
            )
            store = MarketCatalogStore(path)
            store.ingest([rich])
            store.ingest([_row(
                now, sellPrice=300000, landingPadSize="", coordinates=[],
            )])

            result = MarketCatalogStore(path).nearby(
                "Platinum", origin_system="Cubeo",
            )[0]
            self.assertEqual(result["sellPrice"], 300000)
            self.assertEqual(result["stationType"], "Coriolis")
            self.assertEqual(result["landingPadSize"], "L")
            self.assertEqual(result["services"], ["Commodities"])
            self.assertEqual(result["economies"], ["Industrial"])
            self.assertEqual(result["meanPrice"], 180000)
            self.assertFalse(result["fleetCarrier"])
            self.assertEqual(result["prohibited"], ["Slaves"])

    def test_version_three_catalog_adds_station_columns_without_losing_rows(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "market.sqlite3")
            observed = datetime.now(timezone.utc)
            connection = sqlite3.connect(path)
            try:
                connection.execute("""
                    CREATE TABLE market_current (
                        market_key TEXT PRIMARY KEY, commodity TEXT NOT NULL,
                        system_key TEXT NOT NULL, system TEXT NOT NULL,
                        station TEXT NOT NULL, market_id INTEGER NOT NULL,
                        system_address INTEGER NOT NULL DEFAULT 0,
                        station_type TEXT NOT NULL DEFAULT '',
                        landing_pad_size TEXT NOT NULL DEFAULT '',
                        distance_to_arrival REAL, x REAL, y REAL, z REAL,
                        sell_price INTEGER NOT NULL, demand INTEGER NOT NULL,
                        demand_infinite INTEGER NOT NULL DEFAULT 0,
                        demand_bracket INTEGER NOT NULL DEFAULT 0,
                        observed_at TEXT NOT NULL, observed_epoch REAL NOT NULL,
                        fetched_at TEXT NOT NULL, fetched_epoch REAL NOT NULL,
                        source TEXT NOT NULL DEFAULT '',
                        source_url TEXT NOT NULL DEFAULT ''
                    )
                """)
                connection.execute("""
                    INSERT INTO market_current VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?
                    )
                """, (
                    "platinum\x1fmarket:42", "platinum", "cubeo", "Cubeo",
                    "Medupe City", 42, 1234, "Coriolis", "L", 321.5,
                    1, 2, 3, 250000, 5000, 0, 3,
                    observed.isoformat(), observed.timestamp(),
                    observed.isoformat(), observed.timestamp(), "legacy", "",
                ))
                connection.execute("PRAGMA user_version=3")
                connection.commit()
            finally:
                connection.close()

            store = MarketCatalogStore(path)
            result = store.nearby("Platinum", origin_system="Cubeo")[0]
            self.assertEqual(store.count(), 1)
            self.assertEqual(result["stationType"], "Coriolis")
            self.assertEqual(result["landingPadSize"], "L")
            self.assertIsNone(result["meanPrice"])
            self.assertIsNone(result["fleetCarrier"])

    def test_empty_first_start_is_valid_and_queryable(self):
        with TemporaryDirectory() as directory:
            store = MarketCatalogStore(Path(directory, "market.sqlite3"))

            self.assertTrue(store.integrity_check())
            self.assertEqual(store.count(), 0)
            self.assertEqual(store.history_count(), 0)
            self.assertEqual(store.nearby("Platinum", origin_system="Cubeo"), [])

    def test_all_commodities_returns_concrete_rows_without_fake_warm_target(self):
        with TemporaryDirectory() as directory:
            now = datetime.now(timezone.utc)
            store = MarketCatalogStore(Path(directory, "market.sqlite3"))
            store.ingest([
                _row(now, commodity="platinum"),
                _row(now, commodity="painite", marketId=43),
            ])

            rows = store.nearby(
                "ALL COMMODITIES", origin_system="Cubeo",
            )
            stored = store.remember_warm_target({
                "startSystem": "Cubeo", "commodity": "ALL COMMODITIES",
            })

            self.assertEqual(
                {row["commodity"] for row in rows},
                {"platinum", "painite"},
            )
            self.assertFalse(stored)
            self.assertEqual(store.warm_targets(), [])

    def test_local_external_order_metadata_and_restart_matrix(self):
        now = datetime.now(timezone.utc)
        for newer_source in ("local", "external"):
            for reverse_order in (False, True):
                for restart_before_read in (False, True):
                    with self.subTest(
                        newer_source=newer_source,
                        reverse_order=reverse_order,
                        restart_before_read=restart_before_read,
                    ), TemporaryDirectory() as directory:
                        path = Path(directory, "market.sqlite3")
                        store = MarketCatalogStore(path)
                        local_is_newer = newer_source == "local"
                        local = _row(
                            now if local_is_newer else now - timedelta(minutes=1),
                            sellPrice=300000 if local_is_newer else 200000,
                            landingPadSize="", coordinates=[],
                            source="Local Journal Market.json",
                        )
                        external = _row(
                            now if not local_is_newer else now - timedelta(minutes=1),
                            sellPrice=310000 if not local_is_newer else 210000,
                            stationType="Coriolis", source="Ardent API",
                        )
                        rows = [local, external]
                        if reverse_order:
                            rows.reverse()
                        for row in rows:
                            store.ingest([row])
                        if restart_before_read:
                            store = MarketCatalogStore(path)

                        result = store.nearby(
                            "Platinum", origin_system="Cubeo",
                            origin_coordinates=[1, 2, 3], max_distance=10,
                        )

                        self.assertEqual(store.count(), 1)
                        self.assertEqual(
                            result[0]["sellPrice"],
                            300000 if local_is_newer else 310000,
                        )
                        self.assertEqual(result[0]["landingPadSize"], "L")
                        self.assertEqual(result[0]["stationType"], "Coriolis")
                        self.assertEqual(result[0]["coordinates"], [1.0, 2.0, 3.0])

    def test_newest_observation_wins_and_missing_metadata_is_preserved(self):
        with TemporaryDirectory() as directory:
            now = datetime.now(timezone.utc)
            store = MarketCatalogStore(Path(directory, "market.sqlite3"))
            store.ingest([_row(
                now - timedelta(minutes=5), landingPadSize="", coordinates=[],
            )])
            store.ingest([_row(
                now, sellPrice=300000, landingPadSize="", coordinates=[],
            )])
            store.ingest([_row(
                now - timedelta(minutes=10), sellPrice=1,
                stationType="Coriolis",
            )])

            rows = store.nearby(
                "Platinum", origin_system="Cubeo",
                origin_coordinates=[1, 2, 3], max_distance=10,
            )

            self.assertEqual(store.count(), 1)
            self.assertEqual(store.history_count(), 3)
            self.assertEqual(rows[0]["sellPrice"], 300000)
            self.assertEqual(rows[0]["landingPadSize"], "L")
            self.assertEqual(rows[0]["coordinates"], [1.0, 2.0, 3.0])
            self.assertEqual(rows[0]["stationType"], "Coriolis")

    def test_expired_current_and_history_rows_are_pruned(self):
        with TemporaryDirectory() as directory:
            now = datetime.now(timezone.utc)
            store = MarketCatalogStore(Path(directory, "market.sqlite3"))
            store.ingest([
                _row(
                    now - timedelta(days=91), station="Expired", marketId=1,
                ),
                _row(
                    now - timedelta(days=31), station="History expired",
                    marketId=2,
                ),
                _row(now, station="Current", marketId=3),
            ], fetched_at=now)

            self.assertEqual(store.count(), 2)
            self.assertEqual(store.history_count(), 1)

    def test_current_and_history_hard_limits_are_enforced(self):
        with TemporaryDirectory() as directory, patch(
            "ed_companion.navigation.mining_market_store.MAX_CURRENT_ROWS", 2,
        ), patch(
            "ed_companion.navigation.mining_market_store.MAX_HISTORY_ROWS", 2,
        ):
            now = datetime.now(timezone.utc)
            store = MarketCatalogStore(Path(directory, "market.sqlite3"))
            store.ingest([
                _row(
                    now + timedelta(seconds=index), marketId=index + 1,
                    station=f"Port {index}",
                )
                for index in range(4)
            ])

            self.assertEqual(store.count(), 2)
            self.assertEqual(store.history_count(), 2)

    def test_provider_failure_records_status_without_removing_markets(self):
        with TemporaryDirectory() as directory:
            now = datetime.now(timezone.utc)
            store = MarketCatalogStore(Path(directory, "market.sqlite3"))
            store.ingest([_row(now)])
            store.record_source_result(
                "EDDN market indexes", success=False,
                error="offline", next_retry_at="2026-10-02T10:02:00+00:00",
            )

            status = store.source_status("EDDN market indexes")
            self.assertEqual(store.count(), 1)
            self.assertEqual(status["consecutive_failures"], 1)
            self.assertEqual(status["last_error"], "offline")

            store.record_source_result("EDDN market indexes", success=True)
            status = store.source_status("EDDN market indexes")
            self.assertEqual(status["consecutive_failures"], 0)
            self.assertEqual(status["last_error"], "")

    def test_market_id_prevents_duplicates_after_station_rename(self):
        with TemporaryDirectory() as directory:
            now = datetime.now(timezone.utc)
            store = MarketCatalogStore(Path(directory, "market.sqlite3"))
            store.ingest([_row(now - timedelta(minutes=1))])
            store.ingest([_row(
                now, station="Renamed Port", sellPrice=275000,
            )])

            self.assertEqual(store.count(), 1)
            rows = store.nearby("Platinum", origin_system="Cubeo")
            self.assertEqual(rows[0]["station"], "Renamed Port")
            self.assertEqual(rows[0]["sellPrice"], 275000)

    def test_duplicate_observation_is_idempotent_and_invalid_rows_are_ignored(self):
        with TemporaryDirectory() as directory:
            now = datetime.now(timezone.utc)
            store = MarketCatalogStore(Path(directory, "market.sqlite3"))
            observation = _row(now)

            store.ingest([observation, observation, {}, {
                **observation, "system": "",
            }])
            store.ingest([observation])

            self.assertEqual(store.count(), 1)
            self.assertEqual(store.history_count(), 1)

    def test_corrupt_database_is_restored_from_last_good_backup(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "market.sqlite3")
            now = datetime.now(timezone.utc)
            store = MarketCatalogStore(path)
            store.ingest([_row(now)])
            self.assertTrue(store.backup_path.is_file())
            path.write_bytes(b"not a sqlite database")

            self.assertEqual(store.count(), 1)
            path.write_bytes(b"not a sqlite database again")

            recovered = MarketCatalogStore(path)

            self.assertTrue(recovered.integrity_check())
            self.assertEqual(recovered.count(), 1)
            self.assertTrue(list(Path(directory).glob("*.corrupt-*")))

    def test_corrupt_database_without_backup_rebuilds_empty(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "market.sqlite3")
            path.write_bytes(b"not a sqlite database")

            rebuilt = MarketCatalogStore(path)

            self.assertTrue(rebuilt.integrity_check())
            self.assertEqual(rebuilt.count(), 0)

    def test_reset_clears_primary_backup_status_and_allows_rebuild(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "market.sqlite3")
            now = datetime.now(timezone.utc)
            store = MarketCatalogStore(path)
            store.ingest([_row(now)])
            store.record_source_result(
                "EDDN market indexes", success=False, error="offline",
            )
            store.remember_warm_target({
                "startSystem": "Cubeo", "commodity": "Platinum",
            })

            self.assertTrue(store.reset())
            self.assertEqual(store.count(), 0)
            self.assertEqual(store.history_count(), 0)
            self.assertEqual(store.warm_targets(), [])
            self.assertEqual(store.source_status("EDDN market indexes"), {})
            self.assertEqual(store.metadata("legacy_migrated"), "1")

            path.write_bytes(b"corrupt after reset")
            self.assertEqual(store.count(), 0)
            store.ingest([_row(now + timedelta(minutes=1))])
            self.assertEqual(store.count(), 1)

    def test_catalogs_are_isolated_by_profile_path(self):
        with TemporaryDirectory() as directory:
            now = datetime.now(timezone.utc)
            first = MarketCatalogStore(Path(directory, "one", "market.sqlite3"))
            second = MarketCatalogStore(Path(directory, "two", "market.sqlite3"))
            first.ingest([_row(now)])

            self.assertEqual(first.count(), 1)
            self.assertEqual(second.count(), 0)

    def test_warm_targets_persist_prioritize_user_intent_and_track_success(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "market.sqlite3")
            now = datetime.now(timezone.utc)
            store = MarketCatalogStore(path)
            store.remember_warm_target({
                "startSystem": "Cubeo", "commodity": "Painite",
                "nearbyLy": 100, "maxMarketAgeHours": 1,
            }, priority=10, used=False, now=now)
            store.remember_warm_target({
                "startSystem": "Cubeo", "commodity": "Platinum",
                "nearbyLy": 250, "minDemand": 5000,
                "maxMarketAgeHours": 1, "landingPad": "LARGE",
            }, priority=100, used=True, now=now)

            target = store.next_warm_target(now=now)
            self.assertEqual(target["commodity"], "platinum")
            self.assertEqual(target["nearbyLy"], 250)
            store.mark_warm_target(target["key"], success=True, now=now)
            self.assertEqual(
                store.next_warm_target(now=now)["commodity"], "painite"
            )

            reopened = MarketCatalogStore(path)
            self.assertEqual(len(reopened.warm_targets()), 2)
            self.assertEqual(reopened.warm_summary(now=now)["fresh"], 1)

    def test_existing_catalog_migrates_to_warm_queue_schema_in_place(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "market.sqlite3")
            store = MarketCatalogStore(path)
            store.ingest([_row(datetime.now(timezone.utc))])
            connection = sqlite3.connect(path)
            try:
                connection.execute("DROP TABLE warm_targets")
                connection.execute("PRAGMA user_version=2")
                connection.commit()
            finally:
                connection.close()

            migrated = MarketCatalogStore(path)
            migrated.remember_warm_target({
                "startSystem": "Cubeo", "commodity": "Platinum",
            })

            self.assertEqual(migrated.count(), 1)
            self.assertEqual(len(migrated.warm_targets()), 1)

    def test_warm_target_retry_and_hard_limit_are_enforced(self):
        with TemporaryDirectory() as directory, patch(
            "ed_companion.navigation.mining_market_store.MAX_WARM_TARGETS", 2,
        ):
            now = datetime.now(timezone.utc)
            store = MarketCatalogStore(Path(directory, "market.sqlite3"))
            for index, commodity in enumerate(("gold", "silver", "platinum")):
                store.remember_warm_target({
                    "startSystem": "Cubeo", "commodity": commodity,
                }, priority=index, used=True, now=now + timedelta(seconds=index))

            self.assertEqual(len(store.warm_targets()), 2)
            target = store.next_warm_target(now=now + timedelta(seconds=3))
            self.assertEqual(target["commodity"], "platinum")
            store.mark_warm_target(
                target["key"], success=False, error="offline",
                retry_seconds=120, now=now,
            )
            next_target = store.next_warm_target(now=now + timedelta(seconds=1))
            self.assertEqual(next_target["commodity"], "silver")
            self.assertEqual(store.warm_summary(now=now)["failed"], 1)


if __name__ == "__main__":
    unittest.main()
