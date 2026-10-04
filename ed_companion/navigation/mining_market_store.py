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

SCHEMA_VERSION = 5
CURRENT_RETENTION_DAYS = 90
HISTORY_RETENTION_DAYS = 30
MAX_CURRENT_ROWS = 150_000
MAX_HISTORY_ROWS = 500_000
MAX_WARM_TARGETS = 96
# The catalog is a rebuildable cache and the primary SQLite file already uses
# WAL + synchronous=FULL.  A daily recovery snapshot is ample protection and
# avoids copying more than a gigabyte during ordinary short app sessions.
BACKUP_INTERVAL_SECONDS = 24 * 3600
OPEN_INTEGRITY_CHECK_MAX_BYTES = 64 * 1024 * 1024

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


def _json_list(value: Any) -> str:
    return json.dumps(
        value if isinstance(value, list) else [],
        ensure_ascii=False, separators=(",", ":"),
    )


def _loaded_list(value: Any) -> list[Any]:
    try:
        result = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return result if isinstance(result, list) else []


def _tri_bool(value: Any) -> int:
    return int(value) if isinstance(value, bool) else -1


def _optional_nonnegative(value: Any) -> int:
    return max(0, _integer(value)) if value not in (None, "") else -1


def _module_offer(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        name = value.strip().casefold()
        return {"name": name} if name else None
    if not isinstance(value, dict):
        return None
    name = str(value.get("name") or value.get("Name") or "").strip().casefold()
    if not name:
        return None
    result: dict[str, Any] = {"name": name}
    for source_key, target_key in (
        ("id", "id"),
        ("BuyPrice", "buyPrice"),
        ("buyPrice", "buyPrice"),
        ("BuyMercCoinsPrice", "buyMercCoinsPrice"),
        ("buyMercCoinsPrice", "buyMercCoinsPrice"),
    ):
        if target_key in result:
            continue
        number = _optional_nonnegative(value.get(source_key))
        if number >= 0:
            result[target_key] = number
    for key in ("priceObservedAt", "priceSource"):
        text = str(value.get(key) or "").strip()
        if text:
            result[key] = text
    return result


def _normalize_offer_items(value: Any, kind: str) -> list[Any]:
    if not isinstance(value, list):
        return []
    if kind != "OUTFITTING":
        return sorted({
            str(item).strip().casefold()
            for item in value if isinstance(item, str) and item.strip()
        })
    by_name: dict[str, str | dict[str, Any]] = {}
    for item in value:
        offer = _module_offer(item)
        if not offer:
            continue
        name = offer["name"]
        current = by_name.get(name)
        if len(offer) > 1 or current is None:
            by_name[name] = offer if len(offer) > 1 else name
    return [by_name[name] for name in sorted(by_name)]


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
            # A full quick_check touches the complete database.  That is a
            # useful eager guard for small/local catalogs, but it made a
            # healthy 1+ GB synchronized catalog saturate the disk on every
            # launch.  Normal reads remain corruption-aware and recover from
            # the last good backup if a damaged page is actually encountered.
            if (
                not self.path.is_file()
                or self.path.stat().st_size <= OPEN_INTEGRITY_CHECK_MAX_BYTES
            ):
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
                    source_url TEXT NOT NULL DEFAULT '',
                    mean_price INTEGER NOT NULL DEFAULT -1,
                    buy_price INTEGER NOT NULL DEFAULT -1,
                    stock INTEGER NOT NULL DEFAULT -1,
                    stock_bracket INTEGER NOT NULL DEFAULT -1,
                    status_flags_json TEXT NOT NULL DEFAULT '[]',
                    received_at TEXT NOT NULL DEFAULT '',
                    services_json TEXT NOT NULL DEFAULT '[]',
                    economies_json TEXT NOT NULL DEFAULT '[]',
                    primary_economy TEXT NOT NULL DEFAULT '',
                    government TEXT NOT NULL DEFAULT '',
                    controlling_faction TEXT NOT NULL DEFAULT '',
                    fleet_carrier INTEGER NOT NULL DEFAULT -1,
                    carrier_docking_access TEXT NOT NULL DEFAULT '',
                    prohibited_json TEXT NOT NULL DEFAULT '[]'
                );
                CREATE INDEX IF NOT EXISTS market_current_lookup
                ON market_current(commodity, observed_epoch, system_key);
                CREATE INDEX IF NOT EXISTS market_current_coordinates
                ON market_current(commodity, x, y, z);

                CREATE TABLE IF NOT EXISTS station_offers (
                    market_id INTEGER PRIMARY KEY,
                    system TEXT NOT NULL DEFAULT '',
                    station TEXT NOT NULL DEFAULT '',
                    system_address INTEGER NOT NULL DEFAULT 0,
                    station_type TEXT NOT NULL DEFAULT '',
                    landing_pad_size TEXT NOT NULL DEFAULT '',
                    distance_to_arrival REAL,
                    x REAL,
                    y REAL,
                    z REAL,
                    services_json TEXT NOT NULL DEFAULT '[]',
                    modules_json TEXT NOT NULL DEFAULT '[]',
                    ships_json TEXT NOT NULL DEFAULT '[]',
                    outfitting_observed_at TEXT NOT NULL DEFAULT '',
                    outfitting_observed_epoch REAL NOT NULL DEFAULT 0,
                    shipyard_observed_at TEXT NOT NULL DEFAULT '',
                    shipyard_observed_epoch REAL NOT NULL DEFAULT 0,
                    received_at TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS station_offers_system
                ON station_offers(system COLLATE NOCASE, station COLLATE NOCASE);

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

                CREATE TABLE IF NOT EXISTS warm_targets (
                    target_key TEXT PRIMARY KEY,
                    start_system TEXT NOT NULL,
                    commodity TEXT NOT NULL,
                    nearby_ly INTEGER NOT NULL DEFAULT 250,
                    min_demand INTEGER NOT NULL DEFAULT 0,
                    max_market_age_hours INTEGER NOT NULL DEFAULT 1,
                    landing_pad TEXT NOT NULL DEFAULT 'ANY',
                    priority INTEGER NOT NULL DEFAULT 0,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    last_requested_at TEXT NOT NULL DEFAULT '',
                    last_requested_epoch REAL NOT NULL DEFAULT 0,
                    last_success_at TEXT NOT NULL DEFAULT '',
                    last_success_epoch REAL NOT NULL DEFAULT 0,
                    last_failure_at TEXT NOT NULL DEFAULT '',
                    last_failure_epoch REAL NOT NULL DEFAULT 0,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT NOT NULL DEFAULT '',
                    next_retry_epoch REAL NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS warm_targets_due
                ON warm_targets(enabled, priority, last_success_epoch,
                                next_retry_epoch);
            """)
            columns = {
                str(row[1]) for row in connection.execute(
                    "PRAGMA table_info(market_current)"
                )
            }
            migrations = {
                "mean_price": "INTEGER NOT NULL DEFAULT -1",
                "buy_price": "INTEGER NOT NULL DEFAULT -1",
                "stock": "INTEGER NOT NULL DEFAULT -1",
                "stock_bracket": "INTEGER NOT NULL DEFAULT -1",
                "status_flags_json": "TEXT NOT NULL DEFAULT '[]'",
                "received_at": "TEXT NOT NULL DEFAULT ''",
                "services_json": "TEXT NOT NULL DEFAULT '[]'",
                "economies_json": "TEXT NOT NULL DEFAULT '[]'",
                "primary_economy": "TEXT NOT NULL DEFAULT ''",
                "government": "TEXT NOT NULL DEFAULT ''",
                "controlling_faction": "TEXT NOT NULL DEFAULT ''",
                "fleet_carrier": "INTEGER NOT NULL DEFAULT -1",
                "carrier_docking_access": "TEXT NOT NULL DEFAULT ''",
                "prohibited_json": "TEXT NOT NULL DEFAULT '[]'",
            }
            for name, declaration in migrations.items():
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE market_current ADD COLUMN "
                        f"{name} {declaration}"
                    )
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
            _optional_nonnegative(row.get("meanPrice")),
            _optional_nonnegative(row.get("buyPrice")),
            _optional_nonnegative(row.get("stock")),
            _optional_nonnegative(row.get("stockBracket")),
            _json_list(row.get("statusFlags")),
            str(row.get("receivedAt") or "").strip(),
            _json_list(row.get("services")),
            _json_list(row.get("economies")),
            str(row.get("primaryEconomy") or "").strip(),
            str(row.get("government") or "").strip(),
            str(row.get("controllingFaction") or "").strip(),
            _tri_bool(row.get("fleetCarrier")),
            str(row.get("carrierDockingAccess") or "").strip(),
            _json_list(row.get("prohibited")),
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
                    fetched_at, fetched_epoch, source, source_url,
                    mean_price, buy_price, stock, stock_bracket,
                    status_flags_json, received_at, services_json,
                    economies_json, primary_economy, government,
                    controlling_faction, fleet_carrier,
                    carrier_docking_access, prohibited_json
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                        ELSE market_current.source_url END,
                    mean_price=CASE WHEN excluded.mean_price >= 0 AND
                        (market_current.mean_price < 0 OR excluded.observed_epoch >=
                        market_current.observed_epoch) THEN excluded.mean_price
                        ELSE market_current.mean_price END,
                    buy_price=CASE WHEN excluded.buy_price >= 0 AND
                        (market_current.buy_price < 0 OR excluded.observed_epoch >=
                        market_current.observed_epoch) THEN excluded.buy_price
                        ELSE market_current.buy_price END,
                    stock=CASE WHEN excluded.stock >= 0 AND
                        (market_current.stock < 0 OR excluded.observed_epoch >=
                        market_current.observed_epoch) THEN excluded.stock
                        ELSE market_current.stock END,
                    stock_bracket=CASE WHEN excluded.stock_bracket >= 0 AND
                        (market_current.stock_bracket < 0 OR excluded.observed_epoch >=
                        market_current.observed_epoch) THEN excluded.stock_bracket
                        ELSE market_current.stock_bracket END,
                    status_flags_json=CASE
                        WHEN excluded.status_flags_json <> '[]'
                        AND (market_current.status_flags_json = '[]' OR
                            excluded.observed_epoch >= market_current.observed_epoch)
                        THEN excluded.status_flags_json
                        ELSE market_current.status_flags_json END,
                    received_at=CASE WHEN excluded.received_at <> ''
                        AND excluded.observed_epoch >= market_current.observed_epoch
                        THEN excluded.received_at
                        ELSE market_current.received_at END,
                    services_json=CASE WHEN excluded.services_json <> '[]'
                        AND (market_current.services_json = '[]' OR
                            excluded.observed_epoch >= market_current.observed_epoch)
                        THEN excluded.services_json
                        ELSE market_current.services_json END,
                    economies_json=CASE WHEN excluded.economies_json <> '[]'
                        AND (market_current.economies_json = '[]' OR
                            excluded.observed_epoch >= market_current.observed_epoch)
                        THEN excluded.economies_json
                        ELSE market_current.economies_json END,
                    primary_economy=CASE WHEN excluded.primary_economy <> ''
                        AND (market_current.primary_economy = '' OR
                            excluded.observed_epoch >= market_current.observed_epoch)
                        THEN excluded.primary_economy
                        ELSE market_current.primary_economy END,
                    government=CASE WHEN excluded.government <> ''
                        AND (market_current.government = '' OR
                            excluded.observed_epoch >= market_current.observed_epoch)
                        THEN excluded.government
                        ELSE market_current.government END,
                    controlling_faction=CASE
                        WHEN excluded.controlling_faction <> ''
                        AND (market_current.controlling_faction = '' OR
                            excluded.observed_epoch >= market_current.observed_epoch)
                        THEN excluded.controlling_faction
                        ELSE market_current.controlling_faction END,
                    fleet_carrier=CASE WHEN excluded.fleet_carrier >= 0
                        AND (market_current.fleet_carrier < 0 OR
                            excluded.observed_epoch >= market_current.observed_epoch)
                        THEN excluded.fleet_carrier
                        ELSE market_current.fleet_carrier END,
                    carrier_docking_access=CASE
                        WHEN excluded.carrier_docking_access <> ''
                        AND (market_current.carrier_docking_access = '' OR
                            excluded.observed_epoch >= market_current.observed_epoch)
                        THEN excluded.carrier_docking_access
                        ELSE market_current.carrier_docking_access END,
                    prohibited_json=CASE WHEN excluded.prohibited_json <> '[]'
                        AND (market_current.prohibited_json = '[]' OR
                            excluded.observed_epoch >= market_current.observed_epoch)
                        THEN excluded.prohibited_json
                        ELSE market_current.prohibited_json END
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
            "meanPrice": None if row["mean_price"] < 0 else row["mean_price"],
            "buyPrice": None if row["buy_price"] < 0 else row["buy_price"],
            "stock": None if row["stock"] < 0 else row["stock"],
            "stockBracket": (
                None if row["stock_bracket"] < 0 else row["stock_bracket"]
            ),
            "statusFlags": _loaded_list(row["status_flags_json"]),
            "receivedAt": row["received_at"],
            "services": _loaded_list(row["services_json"]),
            "economies": _loaded_list(row["economies_json"]),
            "primaryEconomy": row["primary_economy"],
            "government": row["government"],
            "controllingFaction": row["controlling_faction"],
            "fleetCarrier": (
                None if row["fleet_carrier"] < 0
                else bool(row["fleet_carrier"])
            ),
            "carrierDockingAccess": row["carrier_docking_access"],
            "prohibited": _loaded_list(row["prohibited_json"]),
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
        all_commodities = commodity_id in {"", "allcommodities"}
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
        parameters: list[Any] = [cutoff] if all_commodities else [
            commodity_id, cutoff,
        ]
        where = "observed_epoch >= ?" if all_commodities else (
            "commodity = ? AND observed_epoch >= ?"
        )
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

    def ingest_station_offers(self, observations: Iterable[dict[str, Any]]) -> int:
        """Merge complete station inventories without crossing their timestamps."""
        prepared = []
        for row in observations or []:
            if not isinstance(row, dict):
                continue
            kind = str(row.get("kind") or "").strip().upper()
            market_id = _integer(row.get("marketId"))
            system = str(row.get("system") or "").strip()
            station = str(row.get("station") or "").strip()
            observed = _timestamp(row.get("observedAt"))
            items = _normalize_offer_items(row.get("items"), kind)
            if (
                kind not in {"OUTFITTING", "SHIPYARD"}
                or market_id <= 0 or not system or not station
                or observed is None or not items
            ):
                continue
            coordinates = [
                _number(row.get(axis)) for axis in ("x", "y", "z")
            ]
            if not all(value is not None for value in coordinates):
                coordinates = [None, None, None]
            modules = items if kind == "OUTFITTING" else []
            ships = items if kind == "SHIPYARD" else []
            prepared.append((
                market_id, system, station,
                _integer(row.get("systemAddress")),
                str(row.get("stationType") or "").strip(),
                str(row.get("landingPadSize") or "").strip().upper(),
                _number(row.get("distanceToArrivalLs")), *coordinates,
                _json_list(row.get("services")), _json_list(modules),
                _json_list(ships),
                observed.isoformat(timespec="seconds") if modules else "",
                observed.timestamp() if modules else 0,
                observed.isoformat(timespec="seconds") if ships else "",
                observed.timestamp() if ships else 0,
                str(row.get("receivedAt") or "").strip(),
                str(row.get("source") or "").strip(),
            ))
        if not prepared:
            return 0
        statement = """
            INSERT INTO station_offers(
                market_id, system, station, system_address, station_type,
                landing_pad_size, distance_to_arrival, x, y, z, services_json,
                modules_json, ships_json, outfitting_observed_at,
                outfitting_observed_epoch, shipyard_observed_at,
                shipyard_observed_epoch, received_at, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_id) DO UPDATE SET
                system=CASE WHEN excluded.system <> '' THEN excluded.system
                    ELSE station_offers.system END,
                station=CASE WHEN excluded.station <> '' THEN excluded.station
                    ELSE station_offers.station END,
                system_address=CASE WHEN excluded.system_address > 0
                    THEN excluded.system_address ELSE station_offers.system_address END,
                station_type=CASE WHEN excluded.station_type <> ''
                    THEN excluded.station_type ELSE station_offers.station_type END,
                landing_pad_size=CASE WHEN excluded.landing_pad_size <> ''
                    THEN excluded.landing_pad_size
                    ELSE station_offers.landing_pad_size END,
                distance_to_arrival=COALESCE(
                    excluded.distance_to_arrival, station_offers.distance_to_arrival),
                x=COALESCE(excluded.x, station_offers.x),
                y=COALESCE(excluded.y, station_offers.y),
                z=COALESCE(excluded.z, station_offers.z),
                services_json=CASE WHEN excluded.services_json <> '[]'
                    THEN excluded.services_json ELSE station_offers.services_json END,
                modules_json=CASE
                    WHEN excluded.outfitting_observed_epoch >=
                         station_offers.outfitting_observed_epoch
                         AND excluded.outfitting_observed_epoch > 0
                    THEN excluded.modules_json ELSE station_offers.modules_json END,
                outfitting_observed_at=CASE
                    WHEN excluded.outfitting_observed_epoch >=
                         station_offers.outfitting_observed_epoch
                         AND excluded.outfitting_observed_epoch > 0
                    THEN excluded.outfitting_observed_at
                    ELSE station_offers.outfitting_observed_at END,
                outfitting_observed_epoch=MAX(
                    excluded.outfitting_observed_epoch,
                    station_offers.outfitting_observed_epoch),
                ships_json=CASE
                    WHEN excluded.shipyard_observed_epoch >=
                         station_offers.shipyard_observed_epoch
                         AND excluded.shipyard_observed_epoch > 0
                    THEN excluded.ships_json ELSE station_offers.ships_json END,
                shipyard_observed_at=CASE
                    WHEN excluded.shipyard_observed_epoch >=
                         station_offers.shipyard_observed_epoch
                         AND excluded.shipyard_observed_epoch > 0
                    THEN excluded.shipyard_observed_at
                    ELSE station_offers.shipyard_observed_at END,
                shipyard_observed_epoch=MAX(
                    excluded.shipyard_observed_epoch,
                    station_offers.shipyard_observed_epoch),
                received_at=CASE WHEN excluded.received_at <> ''
                    THEN excluded.received_at ELSE station_offers.received_at END,
                source=CASE WHEN excluded.source <> '' THEN excluded.source
                    ELSE station_offers.source END
        """
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(statement, prepared)
            connection.commit()
        return len(prepared)

    def station_offer_summary(self) -> dict[str, int]:
        row = self._read_rows("""
            SELECT COUNT(*) AS stations,
                   SUM(CASE WHEN modules_json <> '[]' THEN 1 ELSE 0 END)
                       AS outfitting_stations,
                   SUM(CASE WHEN ships_json <> '[]' THEN 1 ELSE 0 END)
                       AS shipyard_stations
            FROM station_offers
        """)[0]
        return {
            "stations": int(row["stations"] or 0),
            "outfittingStations": int(row["outfitting_stations"] or 0),
            "shipyardStations": int(row["shipyard_stations"] or 0),
        }

    def stations_offering(self, item: str, *, kind: str) -> list[dict[str, Any]]:
        """Return exact locally retained module or ship matches."""
        wanted = str(item or "").strip().casefold()
        column = "modules_json" if str(kind).upper() == "OUTFITTING" else (
            "ships_json" if str(kind).upper() == "SHIPYARD" else ""
        )
        if not wanted or not column:
            return []
        result = []
        for row in self._read_rows(
            f"SELECT * FROM station_offers WHERE {column} <> '[]'"
        ):
            stored_items = _loaded_list(row[column])
            matched_offer = None
            if column == "modules_json":
                matched_offer = next((
                    offer for offer in map(_module_offer, stored_items)
                    if offer and offer["name"] == wanted
                ), None)
                matches = matched_offer is not None
            else:
                matches = wanted in {
                    str(value).strip().casefold() for value in stored_items
                    if isinstance(value, str)
                }
            if not matches:
                continue
            result.append({
                "marketId": row["market_id"], "system": row["system"],
                "station": row["station"],
                "systemAddress": row["system_address"],
                "stationType": row["station_type"],
                "landingPadSize": row["landing_pad_size"],
                "distanceToArrivalLs": row["distance_to_arrival"],
                "coordinates": (
                    [row["x"], row["y"], row["z"]]
                    if all(row[key] is not None for key in ("x", "y", "z"))
                    else []
                ),
                "services": _loaded_list(row["services_json"]),
                "moduleOffer": matched_offer,
                "moduleId": (
                    matched_offer.get("id") if matched_offer else None
                ),
                "buyPrice": (
                    matched_offer.get("buyPrice") if matched_offer else None
                ),
                "buyMercCoinsPrice": (
                    matched_offer.get("buyMercCoinsPrice")
                    if matched_offer else None
                ),
                "priceObservedAt": (
                    matched_offer.get("priceObservedAt")
                    if matched_offer else None
                ),
                "priceSource": (
                    matched_offer.get("priceSource")
                    if matched_offer else None
                ),
                "observedAt": row[
                    "outfitting_observed_at" if column == "modules_json"
                    else "shipyard_observed_at"
                ],
                "source": row["source"],
            })
        return result

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

    @staticmethod
    def _warm_target(query: Any) -> tuple[str, dict[str, Any]]:
        source = query if isinstance(query, dict) else {}
        system = str(source.get("startSystem") or "").strip()
        commodity = mining_commodity_id(source.get("commodity"))
        key = "\x1f".join((system.casefold(), commodity))
        if not system or not commodity or commodity == "allcommodities":
            return "", {}
        return key, {
            "startSystem": system,
            "commodity": commodity,
            "nearbyLy": max(1, min(1000, _integer(
                source.get("nearbyLy"), 250
            ))),
            "minDemand": max(0, _integer(source.get("minDemand"))),
            "maxMarketAgeHours": max(1, min(336, _integer(
                source.get("maxMarketAgeHours"), 1
            ))),
            "landingPad": str(
                source.get("landingPad") or "ANY"
            ).strip().upper(),
        }

    def remember_warm_target(
        self, query: Any, *, priority: int = 100, used: bool = True,
        now: datetime | None = None,
    ) -> bool:
        """Persist one bounded, anonymous background market lookup target."""
        return bool(self.remember_warm_targets(
            [(query, priority, used)], now=now,
        ))

    def remember_warm_targets(
        self, targets: Iterable[tuple[Any, int, bool]], *,
        now: datetime | None = None,
    ) -> int:
        """Persist several warm targets in one short SQLite transaction."""
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        stamp = now.isoformat(timespec="seconds")
        epoch = now.timestamp()
        prepared = []
        for query, priority, used in targets:
            key, target = self._warm_target(query)
            if not key:
                continue
            prepared.append((
                key, target["startSystem"], target["commodity"],
                target["nearbyLy"], target["minDemand"],
                target["maxMarketAgeHours"], target["landingPad"],
                int(priority), int(bool(used)), stamp if used else "",
                epoch if used else 0,
            ))
        if not prepared:
            return 0
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                "DELETE FROM warm_targets WHERE commodity = 'allcommodities'"
            )
            connection.executemany("""
                INSERT INTO warm_targets(
                    target_key, start_system, commodity, nearby_ly,
                    min_demand, max_market_age_hours, landing_pad, priority,
                    use_count, last_requested_at, last_requested_epoch
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(target_key) DO UPDATE SET
                    start_system=excluded.start_system,
                    nearby_ly=excluded.nearby_ly,
                    min_demand=excluded.min_demand,
                    max_market_age_hours=excluded.max_market_age_hours,
                    landing_pad=excluded.landing_pad,
                    priority=MAX(warm_targets.priority, excluded.priority),
                    use_count=warm_targets.use_count + excluded.use_count,
                    last_requested_at=CASE WHEN excluded.use_count > 0
                        THEN excluded.last_requested_at
                        ELSE warm_targets.last_requested_at END,
                    last_requested_epoch=CASE WHEN excluded.use_count > 0
                        THEN excluded.last_requested_epoch
                        ELSE warm_targets.last_requested_epoch END,
                    enabled=1
            """, prepared)
            connection.execute("""
                DELETE FROM warm_targets WHERE target_key IN (
                    SELECT target_key FROM warm_targets
                    ORDER BY priority DESC, use_count DESC,
                             last_requested_epoch DESC
                    LIMIT -1 OFFSET ?
                )
            """, (MAX_WARM_TARGETS,))
            connection.commit()
        return len(prepared)

    @staticmethod
    def _project_warm_target(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "key": row["target_key"],
            "startSystem": row["start_system"],
            "commodity": row["commodity"],
            "nearbyLy": row["nearby_ly"],
            "minDemand": row["min_demand"],
            "maxMarketAgeHours": row["max_market_age_hours"],
            "landingPad": row["landing_pad"],
            "priority": row["priority"],
            "useCount": row["use_count"],
            "lastSuccessAt": row["last_success_at"],
            "consecutiveFailures": row["consecutive_failures"],
            "nextRetryAt": row["next_retry_at"],
        }

    def warm_targets(self) -> list[dict[str, Any]]:
        rows = self._read_rows("""
            SELECT * FROM warm_targets WHERE enabled = 1
            ORDER BY priority DESC, use_count DESC, last_requested_epoch DESC
        """)
        return [self._project_warm_target(row) for row in rows]

    def next_warm_target(
        self, *, now: datetime | None = None,
        default_fresh_seconds: int = 3600,
    ) -> dict[str, Any]:
        """Return the highest-value stale target whose retry delay elapsed."""
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        epoch = now.timestamp()
        rows = self._read_rows("""
            SELECT * FROM warm_targets
            WHERE enabled = 1 AND commodity <> 'allcommodities'
                  AND next_retry_epoch <= ?
            ORDER BY priority DESC, use_count DESC,
                     last_success_epoch ASC, last_requested_epoch DESC
        """, (epoch,))
        for row in rows:
            requested_freshness = max(
                1800, min(21600, int(row["max_market_age_hours"]) * 3600)
            )
            freshness = max(
                1800, min(requested_freshness, int(default_fresh_seconds))
            )
            if float(row["last_success_epoch"] or 0) <= epoch - freshness:
                return self._project_warm_target(row)
        return {}

    def mark_warm_target(
        self, key: str, *, success: bool, error: str = "",
        retry_seconds: int = 0, now: datetime | None = None,
    ) -> None:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        stamp = now.isoformat(timespec="seconds")
        epoch = now.timestamp()
        retry_at = now + timedelta(seconds=max(0, int(retry_seconds)))
        with self._lock, closing(self._connect()) as connection:
            connection.execute("""
                UPDATE warm_targets SET
                    last_success_at=CASE WHEN ? THEN ? ELSE last_success_at END,
                    last_success_epoch=CASE WHEN ? THEN ?
                        ELSE last_success_epoch END,
                    last_failure_at=CASE WHEN ? THEN last_failure_at ELSE ? END,
                    last_failure_epoch=CASE WHEN ? THEN last_failure_epoch
                        ELSE ? END,
                    consecutive_failures=CASE WHEN ? THEN 0
                        ELSE consecutive_failures + 1 END,
                    next_retry_at=CASE WHEN ? THEN '' ELSE ? END,
                    next_retry_epoch=CASE WHEN ? THEN 0 ELSE ? END,
                    last_error=CASE WHEN ? THEN '' ELSE ? END
                WHERE target_key = ?
            """, (
                success, stamp, success, epoch,
                success, stamp, success, epoch,
                success,
                success, retry_at.isoformat(timespec="seconds"),
                success, retry_at.timestamp(),
                success, str(error or ""), str(key or ""),
            ))
            connection.commit()

    def warm_summary(self, *, now: datetime | None = None) -> dict[str, int]:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        rows = self._read_rows("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN last_success_epoch > ? THEN 1 ELSE 0 END)
                       AS fresh,
                   SUM(CASE WHEN consecutive_failures > 0 THEN 1 ELSE 0 END)
                       AS failed
            FROM warm_targets WHERE enabled = 1
        """, (now.timestamp() - 3600,))
        row = rows[0]
        return {
            "total": int(row["total"] or 0),
            "fresh": int(row["fresh"] or 0),
            "failed": int(row["failed"] or 0),
        }

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

    def backup_due(self, interval_seconds: int = BACKUP_INTERVAL_SECONDS) -> bool:
        """Return whether the recovery snapshot is old enough to refresh."""
        if not self.backup_path.is_file():
            return True
        try:
            age = datetime.now(timezone.utc).timestamp() - (
                self.backup_path.stat().st_mtime
            )
        except OSError:
            return True
        return age >= max(0, int(interval_seconds or 0))

    def checkpoint(self) -> bool:
        """Durably merge WAL content without copying the complete catalog."""
        try:
            with self._lock, closing(self._connect()) as connection:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            return True
        except (OSError, sqlite3.DatabaseError):
            LOGGER.warning(
                "Mining market database checkpoint failed: %s", self.path,
            )
            return False

    def backup(self) -> bool:
        temporary = self.backup_path.with_name(self.backup_path.name + ".tmp")
        self.backup_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # A killed prior backup may leave a very large partial target.
            # Start with a clean snapshot and do not hold the store's Python
            # lock for the whole copy: SQLite's online backup API provides the
            # consistent snapshot while readers and writers remain usable.
            temporary.unlink(missing_ok=True)
            with closing(self._connect()) as source, closing(
                sqlite3.connect(temporary, timeout=15)
            ) as target:
                source.backup(target, pages=4096, sleep=0.01)
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
