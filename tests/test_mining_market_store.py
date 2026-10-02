from datetime import datetime, timedelta, timezone
from pathlib import Path
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
    def test_empty_first_start_is_valid_and_queryable(self):
        with TemporaryDirectory() as directory:
            store = MarketCatalogStore(Path(directory, "market.sqlite3"))

            self.assertTrue(store.integrity_check())
            self.assertEqual(store.count(), 0)
            self.assertEqual(store.history_count(), 0)
            self.assertEqual(store.nearby("Platinum", origin_system="Cubeo"), [])

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

            self.assertTrue(store.reset())
            self.assertEqual(store.count(), 0)
            self.assertEqual(store.history_count(), 0)
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


if __name__ == "__main__":
    unittest.main()
