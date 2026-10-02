"""Durable, profile-local market catalog for the Mining Finder."""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .mining_commodities import mining_commodity_id


LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION = 2
CURRENT_RETENTION_DAYS = 90
HISTORY_RETENTION_DAYS = 30
MAX_CURRENT_ROWS = 20_000
MAX_HISTORY_ROWS = 100_000

_CORRUPTION_MARKERS = (
    "malformed", "not a database", "file is not a database",
    "file is encrypted or is not a database", "integrity check failed",
)


def _is_corruption_error(exc: BaseException) -> bool:
    return isinstance(exc, sqlite3.DatabaseError) and any(
        marker in str(exc).casefold() for marker in _CORRUPTION_MARKERS
    )


def _timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _market_key(row: dict[str, Any]) -> str:
    commodity = mining_commodity_id(row.get("commodity") or row.get("name"))
    system = str(row.get("system") or "").strip().casefold()
    station = str(row.get("station") or "").strip().casefold()
    market_id = _integer(row.get("marketId"))
    if commodity and market_id > 0:
        return "\x1f".join((commodity, f"market:{market_id}"))
    return "\x1f".join((commodity, system, station)) if all(
        (commodity, system, station)
    ) else ""


class MarketCatalogStore:
    """SQLite market knowledge with stale-while-revalidate semantics."""

    def __init__(self, path: Any):
        self.path = Path(path)
        self.backup_path = self.path.with_name(
            self.path.stem + ".backup" + self.path.suffix
        )
        self._lock = threading.RLock()
        try:
            self._ensure_schema()
            self.integrity_check()
        except sqlite3.DatabaseError as exc:
            if not _is_corruption_error(exc):
                raise
            self._recover()

    def _connect(self, path: Path | None = None):
        connection = sqlite3.connect(path or self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=15000")
        except Exception:
            connection.close()
            raise
        return connection

    def _ensure_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, closing(self._connect()) as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS market_current (
                    market_key TEXT PRIMARY KEY,
                    commodity TEXT NOT NULL,
                    system_key TEXT NOT NULL,
                    system TEXT NOT NULL,
                    station TEXT NOT NULL,
                    market_id INTEGER NOT NULL DEFAULT 0,
                    system_address INTEGER NOT NULL DEFAULT 0,
                    station_type TEXT NOT NULL DEFAULT '',
                    landing_pad_size TEXT NOT NULL DEFAULT '',
                    distance_to_arrival REAL,
                    x REAL,
                    y REAL,
                    z REAL,
                    sell_price INTEGER NOT NULL DEFAULT 0,
                    demand INTEGER NOT NULL DEFAULT 0,
                    demand_infinite INTEGER NOT NULL DEFAULT 0,
                    demand_bracket INTEGER NOT NULL DEFAULT 0,
                    observed_at TEXT NOT NULL,
                    observed_epoch REAL NOT NULL,
                    fetched_at TEXT NOT NULL,
                    fetched_epoch REAL NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS market_current_lookup
                ON market_current(commodity, observed_epoch, system_key);
                CREATE INDEX IF NOT EXISTS market_current_coordinates
                ON market_current(commodity, x, y, z);

                CREATE TABLE IF NOT EXISTS market_history (
                    market_key TEXT NOT NULL,
                    observed_epoch REAL NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    fetched_epoch REAL NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY(market_key, observed_epoch, source)
                );
                CREATE INDEX IF NOT EXISTS market_history_observed
                ON market_history(observed_epoch);

                CREATE TABLE IF NOT EXISTS source_status (
                    source TEXT PRIMARY KEY,
                    last_success_at TEXT NOT NULL DEFAULT '',
                    last_failure_at TEXT NOT NULL DEFAULT '',
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS catalog_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT ''
                );
            """)
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            connection.commit()

    def _quarantine(self, path: Path) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        for suffix in ("", "-wal", "-shm"):
            candidate = path.with_name(path.name + suffix)
            if not candidate.exists():
                continue
            try:
                candidate.replace(candidate.with_name(
                    f"{candidate.name}.corrupt-{stamp}"
                ))
            except OSError:
                pass

    def _recover(self) -> None:
        with self._lock:
            LOGGER.error(
                "Mining market database corrupt; attempting backup recovery: %s",
                self.path,
            )
            self._quarantine(self.path)
            restored = False
            if self.backup_path.is_file():
                try:
                    shutil.copy2(self.backup_path, self.path)
                    self._ensure_schema()
                    self.integrity_check()
                    restored = True
                except (OSError, sqlite3.DatabaseError):
                    self._quarantine(self.path)
                    self._quarantine(self.backup_path)
            if not restored:
                self._ensure_schema()

    def integrity_check(self) -> bool:
        with self._lock, closing(self._connect()) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
            if not result or str(result[0]).casefold() != "ok":
                raise sqlite3.DatabaseError("integrity check failed")
        return True

    def _read_rows(self, statement: str, parameters: Any = ()):
        for attempt in range(2):
            try:
                with self._lock, closing(self._connect()) as connection:
                    return connection.execute(
                        statement, parameters
                    ).fetchall()
            except sqlite3.DatabaseError as exc:
                if attempt or not _is_corruption_error(exc):
                    raise
                self._recover()
        return []

    @staticmethod
    def _prepared(row: dict[str, Any], fetched: datetime):
        key = _market_key(row)
        observed = _timestamp(row.get("observedAt"))
        system = str(row.get("system") or "").strip()
        station = str(row.get("station") or "").strip()
        if not key or not system or not station or observed is None:
            return None
        commodity = mining_commodity_id(row.get("commodity") or row.get("name"))
        system_key = system.casefold()
        coordinates = row.get("coordinates")
        coordinates = (
            [_number(value) for value in coordinates]
            if isinstance(coordinates, (list, tuple)) and len(coordinates) == 3
            else [None, None, None]
        )
        if not all(value is not None for value in coordinates):
            coordinates = [None, None, None]
        payload = json.dumps(
            row, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        return (
            key, commodity, system_key,
            system, station,
            _integer(row.get("marketId")),
            _integer(row.get("systemAddress")),
            str(row.get("stationType") or "").strip(),
            str(row.get("landingPadSize") or "").strip().upper(),
            _number(row.get("distanceToArrivalLs")),
            *coordinates,
            max(0, _integer(row.get("sellPrice"))),
            max(0, _integer(row.get("demand"))),
            int(bool(row.get("demandInfinite"))),
            max(0, _integer(row.get("demandBracket"))),
            observed.isoformat(timespec="seconds"), observed.timestamp(),
            fetched.isoformat(timespec="seconds"), fetched.timestamp(),
            str(row.get("source") or "").strip(),
            str(row.get("sourceUrl") or "").strip(),
            payload,
        )

    def ingest(
        self, observations: Iterable[dict[str, Any]], *, fetched_at: Any = None,
        create_backup: bool = True,
    ) -> int:
        fetched = _timestamp(fetched_at) or datetime.now(timezone.utc)
        prepared = [
            value for row in observations or []
            if isinstance(row, dict)
            and (value := self._prepared(row, fetched)) is not None
        ]
        if not prepared:
            return 0
        try:
            count = self._ingest_prepared(prepared, fetched)
        except sqlite3.DatabaseError as exc:
            if not _is_corruption_error(exc):
                raise
            self._recover()
            count = self._ingest_prepared(prepared, fetched)
        if create_backup:
            self.backup()
        return count

    def _ingest_prepared(self, prepared, now: datetime) -> int:
        current_cutoff = (now - timedelta(
            days=CURRENT_RETENTION_DAYS
        )).timestamp()
        history_cutoff = (now - timedelta(
            days=HISTORY_RETENTION_DAYS
        )).timestamp()
        current_rows = [row[:-1] for row in prepared]
        history_rows = [
            (row[0], row[18], row[21], row[20], row[-1]) for row in prepared
        ]
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany("""
                INSERT OR IGNORE INTO market_history(
                    market_key, observed_epoch, source, fetched_epoch, payload
                ) VALUES (?, ?, ?, ?, ?)
            """, history_rows)
            connection.executemany("""
                INSERT INTO market_current(
                    market_key, commodity, system_key, system, station,
                    market_id, system_address, station_type, landing_pad_size,
                    distance_to_arrival, x, y, z, sell_price, demand,
                    demand_infinite, demand_bracket, observed_at, observed_epoch,
                    fetched_at, fetched_epoch, source, source_url
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                ON CONFLICT(market_key) DO UPDATE SET
                    system=CASE WHEN excluded.observed_epoch >=
                        market_current.observed_epoch THEN excluded.system
                        ELSE market_current.system END,
                    system_key=CASE WHEN excluded.observed_epoch >=
                        market_current.observed_epoch THEN excluded.system_key
                        ELSE market_current.system_key END,
                    station=CASE WHEN excluded.observed_epoch >=
                        market_current.observed_epoch THEN excluded.station
                        ELSE market_current.station END,
                    market_id=CASE WHEN market_current.market_id <= 0
                        AND excluded.market_id > 0 THEN excluded.market_id
                        ELSE market_current.market_id END,
                    system_address=CASE WHEN excluded.system_address > 0
                        AND (market_current.system_address <= 0 OR
                            excluded.observed_epoch >=
                            market_current.observed_epoch)
                        THEN excluded.system_address
                        ELSE market_current.system_address END,
                    station_type=CASE WHEN excluded.station_type <> ''
                        AND (market_current.station_type = '' OR
                            excluded.observed_epoch >=
                            market_current.observed_epoch)
                        THEN excluded.station_type
                        ELSE market_current.station_type END,
                    landing_pad_size=CASE WHEN excluded.landing_pad_size <> ''
                        AND (market_current.landing_pad_size = '' OR
                            excluded.observed_epoch >=
                            market_current.observed_epoch)
                        THEN excluded.landing_pad_size
                        ELSE market_current.landing_pad_size END,
                    distance_to_arrival=CASE
                        WHEN excluded.distance_to_arrival IS NOT NULL
                        AND (market_current.distance_to_arrival IS NULL OR
                            excluded.observed_epoch >=
                            market_current.observed_epoch)
                        THEN excluded.distance_to_arrival
                        ELSE market_current.distance_to_arrival END,
                    x=CASE WHEN excluded.observed_epoch >=
                        market_current.observed_epoch AND excluded.x IS NOT NULL
                        THEN excluded.x
                        ELSE COALESCE(market_current.x, excluded.x) END,
                    y=CASE WHEN excluded.observed_epoch >=
                        market_current.observed_epoch AND excluded.y IS NOT NULL
                        THEN excluded.y
                        ELSE COALESCE(market_current.y, excluded.y) END,
                    z=CASE WHEN excluded.observed_epoch >=
                        market_current.observed_epoch AND excluded.z IS NOT NULL
                        THEN excluded.z
                        ELSE COALESCE(market_current.z, excluded.z) END,
                    sell_price=CASE WHEN excluded.observed_epoch >=
                        market_current.observed_epoch THEN excluded.sell_price
                        ELSE market_current.sell_price END,
                    demand=CASE WHEN excluded.observed_epoch >=
                        market_current.observed_epoch THEN excluded.demand
                        ELSE market_current.demand END,
                    demand_infinite=CASE WHEN excluded.observed_epoch >=
                        market_current.observed_epoch
                        THEN excluded.demand_infinite
                        ELSE market_current.demand_infinite END,
                    demand_bracket=CASE WHEN excluded.observed_epoch >=
                        market_current.observed_epoch
                        THEN excluded.demand_bracket
                        ELSE market_current.demand_bracket END,
                    observed_at=CASE WHEN excluded.observed_epoch >=
                        market_current.observed_epoch THEN excluded.observed_at
                        ELSE market_current.observed_at END,
                    observed_epoch=MAX(
                        excluded.observed_epoch, market_current.observed_epoch
                    ),
                    fetched_at=CASE WHEN excluded.observed_epoch >=
                        market_current.observed_epoch THEN excluded.fetched_at
                        ELSE market_current.fetched_at END,
                    fetched_epoch=CASE WHEN excluded.observed_epoch >=
                        market_current.observed_epoch THEN excluded.fetched_epoch
                        ELSE market_current.fetched_epoch END,
                    source=CASE WHEN excluded.observed_epoch >=
                        market_current.observed_epoch THEN excluded.source
                        ELSE market_current.source END,
                    source_url=CASE WHEN market_current.source_url = ''
                        AND excluded.source_url <> '' THEN excluded.source_url
                        ELSE market_current.source_url END
            """, current_rows)
            connection.execute(
                "DELETE FROM market_history WHERE observed_epoch < ?",
                (history_cutoff,),
            )
            connection.execute("""
                DELETE FROM market_history WHERE rowid IN (
                    SELECT rowid FROM market_history
                    ORDER BY observed_epoch DESC LIMIT -1 OFFSET ?
                )
            """, (MAX_HISTORY_ROWS,))
            connection.execute(
                "DELETE FROM market_current WHERE observed_epoch < ?",
                (current_cutoff,),
            )
            connection.execute("""
                DELETE FROM market_current WHERE market_key IN (
                    SELECT market_key FROM market_current
                    ORDER BY observed_epoch DESC LIMIT -1 OFFSET ?
                )
            """, (MAX_CURRENT_ROWS,))
            connection.commit()
        return len(prepared)

    @staticmethod
    def _project(row: sqlite3.Row) -> dict[str, Any]:
        coordinates = (
            [row["x"], row["y"], row["z"]]
            if all(row[key] is not None for key in ("x", "y", "z")) else []
        )
        return {
            "commodity": row["commodity"],
            "marketId": row["market_id"],
            "station": row["station"],
            "system": row["system"],
            "systemAddress": row["system_address"],
            "stationType": row["station_type"],
            "landingPadSize": row["landing_pad_size"],
            "distanceToArrivalLs": row["distance_to_arrival"],
            "coordinates": coordinates,
            "sellPrice": row["sell_price"],
            "demand": row["demand"],
            "demandInfinite": bool(row["demand_infinite"]),
            "demandBracket": row["demand_bracket"],
            "observedAt": row["observed_at"],
            "source": row["source"],
            "sourceUrl": row["source_url"],
            "meritEligible": None,
        }

    def nearby(
        self, commodity: str, *, origin_system: str = "",
        origin_coordinates: Any = None, max_distance: int = 0,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        commodity_id = mining_commodity_id(commodity)
        origin_key = str(origin_system or "").strip().casefold()
        coordinates = (
            [_number(value) for value in origin_coordinates]
            if isinstance(origin_coordinates, (list, tuple))
            and len(origin_coordinates) == 3 else []
        )
        known = len(coordinates) == 3 and all(
            value is not None for value in coordinates
        )
        radius = max(0.0, float(max_distance or 0))
        cutoff = (now - timedelta(days=CURRENT_RETENTION_DAYS)).timestamp()
        parameters: list[Any] = [commodity_id, cutoff]
        where = "commodity = ? AND observed_epoch >= ?"
        if known and radius > 0:
            where += " AND (system_key = ? OR (x BETWEEN ? AND ? AND y BETWEEN ? AND ? AND z BETWEEN ? AND ?))"
            parameters.extend([
                origin_key,
                coordinates[0] - radius, coordinates[0] + radius,
                coordinates[1] - radius, coordinates[1] + radius,
                coordinates[2] - radius, coordinates[2] + radius,
            ])
        elif not known:
            where += " AND system_key = ?"
            parameters.append(origin_key)
        rows = self._read_rows(
            f"SELECT * FROM market_current WHERE {where} "
            "ORDER BY observed_epoch DESC",
            parameters,
        )
        result = []
        for row in rows:
            if known and radius > 0 and row["system_key"] != origin_key:
                if any(row[key] is None for key in ("x", "y", "z")):
                    continue
                distance = math.sqrt(
                    (row["x"] - coordinates[0]) ** 2
                    + (row["y"] - coordinates[1]) ** 2
                    + (row["z"] - coordinates[2]) ** 2
                )
                if distance > radius:
                    continue
            result.append(self._project(row))
        return result

    def count(self) -> int:
        return int(self._read_rows(
            "SELECT COUNT(*) FROM market_current"
        )[0][0])

    def history_count(self) -> int:
        return int(self._read_rows(
            "SELECT COUNT(*) FROM market_history"
        )[0][0])

    def record_source_result(
        self, source: str, *, success: bool, error: str = "",
        next_retry_at: str = "",
    ) -> None:
        try:
            self._record_source_result(
                source, success=success, error=error,
                next_retry_at=next_retry_at,
            )
        except sqlite3.DatabaseError as exc:
            if not _is_corruption_error(exc):
                raise
            self._recover()
            self._record_source_result(
                source, success=success, error=error,
                next_retry_at=next_retry_at,
            )

    def _record_source_result(
        self, source: str, *, success: bool, error: str,
        next_retry_at: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock, closing(self._connect()) as connection:
            connection.execute("""
                INSERT INTO source_status(
                    source, last_success_at, last_failure_at,
                    consecutive_failures, next_retry_at, last_error
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    last_success_at=CASE WHEN ?
                        THEN excluded.last_success_at
                        ELSE source_status.last_success_at END,
                    last_failure_at=CASE WHEN ?
                        THEN source_status.last_failure_at
                        ELSE excluded.last_failure_at END,
                    consecutive_failures=CASE WHEN ? THEN 0
                        ELSE source_status.consecutive_failures + 1 END,
                    next_retry_at=excluded.next_retry_at,
                    last_error=CASE WHEN ? THEN '' ELSE excluded.last_error END
            """, (
                str(source), now if success else "", "" if success else now,
                0 if success else 1, str(next_retry_at or ""), str(error or ""),
                success, success, success, success,
            ))
            connection.commit()

    def source_status(self, source: str) -> dict[str, Any]:
        rows = self._read_rows(
            "SELECT * FROM source_status WHERE source = ?", (str(source),)
        )
        row = rows[0] if rows else None
        return dict(row) if row else {}

    def metadata(self, key: str, default: str = "") -> str:
        rows = self._read_rows(
            "SELECT value FROM catalog_meta WHERE key = ?", (str(key),)
        )
        return str(rows[0][0]) if rows else str(default)

    def set_metadata(self, key: str, value: str) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO catalog_meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(key), str(value)),
            )
            connection.commit()

    def reset(self) -> bool:
        """Create a genuinely empty catalog that cannot restore old rows."""
        with self._lock:
            targets = [
                self.path,
                self.path.with_name(self.path.name + "-wal"),
                self.path.with_name(self.path.name + "-shm"),
                self.backup_path,
                self.backup_path.with_name(self.backup_path.name + "-wal"),
                self.backup_path.with_name(self.backup_path.name + "-shm"),
                self.backup_path.with_name(self.backup_path.name + ".tmp"),
            ]
            for target in targets:
                target.unlink(missing_ok=True)
            self._ensure_schema()
            self.set_metadata("legacy_migrated", "1")
            return self.backup()

    def backup(self) -> bool:
        temporary = self.backup_path.with_name(self.backup_path.name + ".tmp")
        self.backup_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._lock, closing(self._connect()) as source, closing(
                sqlite3.connect(temporary, timeout=15)
            ) as target:
                source.backup(target)
                target.commit()
            os.replace(temporary, self.backup_path)
            return True
        except (OSError, sqlite3.DatabaseError):
            LOGGER.warning("Mining market database backup failed: %s", self.path)
            return False
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
