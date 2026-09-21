"""Profile-bound, lossless history storage for large runtime datasets."""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


LOGGER = logging.getLogger(__name__)


_CORRUPTION_MARKERS = (
    "malformed", "not a database", "file is not a database",
    "file is encrypted or is not a database",
)


def _is_corruption_error(exc: BaseException) -> bool:
    return isinstance(exc, sqlite3.DatabaseError) and any(
        marker in str(exc).lower() for marker in _CORRUPTION_MARKERS
    )


def _recoverable(method):
    """Quarantine a corrupt database and retry once instead of crashing.

    This is a cache of displaced runtime records (EDDN uploads, mining
    sync, credit snapshots, ...), never the source of truth - Journal
    files and the profile's JSON stores are. A repeated hard process
    kill (or third-party file-lock interference from antivirus/OneDrive,
    the same kind already seen corrupting other saves on Windows) can
    still leave this file with genuinely malformed pages even under
    WAL + synchronous=FULL. Losing the cached history to a fresh,
    empty database is a minor inconvenience; crashing the whole app on
    every future launch, as an unhandled ``sqlite3.DatabaseError`` from
    inside ``__init__`` used to, is not.
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except sqlite3.DatabaseError as exc:
            if not _is_corruption_error(exc):
                raise
            self._quarantine_and_reset()
            return method(self, *args, **kwargs)
    return wrapper


class HistoryArchive:
    """Keep displaced records queryable without loading them at app startup."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._counts_cache = None
        try:
            self._ensure_schema()
        except sqlite3.DatabaseError as exc:
            if not _is_corruption_error(exc):
                raise
            self._quarantine_and_reset()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
        except Exception:
            # A failure here (e.g. corruption) must not leak the raw
            # connection - on Windows an open sqlite3 handle blocks the
            # rename _quarantine_and_reset() is about to perform on this
            # very file.
            connection.close()
            raise
        return connection

    def _quarantine_and_reset(self) -> None:
        """Move a corrupt database aside (never delete) and start fresh.

        Mirrors how persistence.py protects the JSON stores: keep the
        broken file as a recovery copy under a timestamped name, then
        rebuild an empty, working schema in its place.
        """
        with self._lock:
            LOGGER.error(
                "History database corrupt, quarantining and starting fresh: %s",
                self.path,
            )
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            for suffix in ("", "-wal", "-shm"):
                candidate = self.path.with_name(self.path.name + suffix)
                if not candidate.exists():
                    continue
                try:
                    candidate.replace(
                        candidate.with_name(f"{candidate.name}.corrupt-{stamp}")
                    )
                except OSError:
                    pass
            self._counts_cache = None
            self._ensure_schema()

    def _ensure_schema(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, closing(self._connect()) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    category TEXT NOT NULL,
                    record_key TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    archived_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (category, record_key)
                )
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS history_category_observed
                ON history(category, observed_at)
            """)
            connection.commit()

    @staticmethod
    def _encoded(record):
        return json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    @staticmethod
    def _record_key(record, encoded, key_field):
        explicit = str(record.get(key_field) or "") if key_field else ""
        return explicit or hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @_recoverable
    def archive(self, category, records: Iterable[dict], key_field=""):
        """Archive every valid record in one durable transaction."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = []
        occurrences = {}
        for record in records or []:
            if not isinstance(record, dict):
                continue
            encoded = self._encoded(record)
            record_key = self._record_key(record, encoded, key_field)
            if not key_field:
                occurrence = occurrences.get(record_key, 0)
                occurrences[record_key] = occurrence + 1
                if occurrence:
                    record_key = f"{record_key}:{occurrence}"
            observed = str(
                record.get("sent_at") or record.get("signal_timestamp")
                or record.get("received_at") or record.get("observedAt")
                or record.get("created") or ""
            )
            rows.append((
                str(category), record_key,
                observed, now, encoded,
            ))
        if not rows:
            return 0
        with self._lock, closing(self._connect()) as connection:
            connection.executemany("""
                INSERT INTO history(
                    category, record_key, observed_at, archived_at, payload
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(category, record_key) DO UPDATE SET
                    observed_at=excluded.observed_at,
                    archived_at=excluded.archived_at,
                    payload=excluded.payload
            """, rows)
            connection.commit()
        self._counts_cache = None
        return len(rows)

    def checkpoint(self) -> None:
        """Merge any pending WAL content back into the main file and shrink
        it to its actual size.

        In WAL mode, SQLite normally reclaims this itself once the last
        open connection on the database closes - but ``archive()`` runs
        from several different threads (EDDN, mining sync, credit
        snapshots, ...) opening and closing their own short-lived
        connections, so there is rarely a moment with truly zero
        connections open to trigger that. A non-graceful exit (a forced
        process kill, a crash, a power loss) skips it entirely. Call this
        once after construction - cheap when there is nothing pending,
        and it is what actually reclaims the file's size when there is.
        """
        try:
            with self._lock, closing(self._connect()) as connection:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.DatabaseError as exc:
            if _is_corruption_error(exc):
                self._quarantine_and_reset()
        except sqlite3.Error:
            pass

    @_recoverable
    def count(self, category=None):
        with self._lock, closing(self._connect()) as connection:
            if category is None:
                row = connection.execute("SELECT COUNT(*) FROM history").fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) FROM history WHERE category=?", (category,)
                ).fetchone()
        return int(row[0] if row else 0)

    @_recoverable
    def counts(self):
        with self._lock:
            if self._counts_cache is not None:
                return dict(self._counts_cache)
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute("""
                SELECT category, COUNT(*) FROM history GROUP BY category
                ORDER BY category
            """).fetchall()
            self._counts_cache = {
                str(category): int(count) for category, count in rows
            }
            return dict(self._counts_cache)

    @_recoverable
    def records(self, category, limit=0):
        """Return one category in chronological order, optionally tail-limited."""
        with self._lock, closing(self._connect()) as connection:
            if limit and int(limit) > 0:
                rows = connection.execute("""
                    SELECT payload FROM (
                        SELECT payload, observed_at, record_key
                        FROM history WHERE category=?
                        ORDER BY observed_at DESC, record_key DESC LIMIT ?
                    ) ORDER BY observed_at, record_key
                """, (str(category), int(limit))).fetchall()
            else:
                rows = connection.execute("""
                    SELECT payload FROM history WHERE category=?
                    ORDER BY observed_at, record_key
                """, (str(category),)).fetchall()
        result = []
        for (payload,) in rows:
            try:
                record = json.loads(payload)
            except (TypeError, ValueError):
                continue
            if isinstance(record, dict):
                result.append(record)
        return result

    @_recoverable
    def clear(self, category):
        with self._lock, closing(self._connect()) as connection:
            cursor = connection.execute(
                "DELETE FROM history WHERE category=?", (str(category),)
            )
            connection.commit()
        self._counts_cache = None
        return max(0, int(cursor.rowcount or 0))

    @_recoverable
    def export_json(self, path, active=None):
        """Create a complete, portable JSON export without loading it all in RAM."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with self._lock, closing(self._connect()) as connection, temporary.open(
            "w", encoding="utf-8", newline="\n"
        ) as handle:
            handle.write('{\n  "format": "EDOPS_HISTORY_V1",\n  "records": [\n')
            first = True
            for category, observed_at, archived_at, payload in connection.execute("""
                SELECT category, observed_at, archived_at, payload
                FROM history ORDER BY category, observed_at, record_key
            """):
                if not first:
                    handle.write(",\n")
                first = False
                envelope = {
                    "category": category,
                    "observedAt": observed_at,
                    "archivedAt": archived_at,
                    "data": json.loads(payload),
                }
                handle.write("    " + json.dumps(envelope, ensure_ascii=False))
            for category, records in (active or {}).items():
                for record in records or []:
                    if not isinstance(record, dict):
                        continue
                    if not first:
                        handle.write(",\n")
                    first = False
                    envelope = {
                        "category": category,
                        "observedAt": str(
                            record.get("sent_at")
                            or record.get("signal_timestamp")
                            or record.get("received_at")
                            or record.get("observedAt") or ""
                        ),
                        "archivedAt": "",
                        "active": True,
                        "data": record,
                    }
                    handle.write("    " + json.dumps(envelope, ensure_ascii=False))
            handle.write("\n  ]\n}\n")
            handle.flush()
        temporary.replace(destination)
        return destination
