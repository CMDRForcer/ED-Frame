"""One shared public statistics snapshot, refreshed outside HTTP requests."""
from __future__ import annotations

import logging
import threading

import orjson
from psycopg.types.json import Jsonb


REFRESH_SECONDS = 300
MAX_STALE_SECONDS = 1800
POLL_SECONDS = 30
_REFRESH_LOCK = 45444652417
_LOG = logging.getLogger(__name__)


class StatusUnavailable(Exception):
    """No sufficiently recent statistics snapshot is available."""


class StatusCache:
    def __init__(self, connection_factory, loader):
        self._connection = connection_factory
        self._loader = loader
        self._stop = threading.Event()
        self._thread_lock = threading.Lock()
        self._thread = None

    def get(self):
        # One tiny indexed read, regardless of total catalog size. Collector
        # state is cheap and remains live rather than lagging five minutes.
        with self._connection() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout = '2s'")
            row = conn.execute("""SELECT payload,
                    EXTRACT(EPOCH FROM (clock_timestamp() - generated_at))
                        AS age_seconds,
                    (SELECT to_jsonb(state) FROM collector_state state
                     WHERE source = 'EDDN') AS collector
                FROM catalog_status_snapshot WHERE singleton = 1""").fetchone()
        if not row or not isinstance(row["payload"], dict):
            raise StatusUnavailable("Catalog statistics are warming up")
        age = float(row["age_seconds"])
        if age < -30 or age > MAX_STALE_SECONDS:
            raise StatusUnavailable("Catalog statistics snapshot has expired")
        payload = dict(row["payload"])
        payload["collector"] = row["collector"]
        payload["cache"] = {
            "ageSeconds": max(0, int(age)),
            "refreshSeconds": REFRESH_SECONDS,
            "stale": age >= REFRESH_SECONDS,
        }
        return payload

    def refresh(self):
        # A session advisory lock coordinates all API workers and containers.
        # Closing this connection releases it even if the loader fails.
        with self._connection() as conn:
            conn.autocommit = True
            conn.execute("SET statement_timeout = '2s'")
            locked = conn.execute(
                "SELECT pg_try_advisory_lock(%s) AS acquired",
                (_REFRESH_LOCK,),
            ).fetchone()["acquired"]
            if not locked:
                return False
            row = conn.execute("""SELECT EXTRACT(EPOCH FROM
                    (clock_timestamp() - generated_at)) AS age_seconds
                FROM catalog_status_snapshot WHERE singleton = 1""").fetchone()
            if row and 0 <= float(row["age_seconds"]) < REFRESH_SECONDS:
                return False
            payload = self._loader()
            # Serialize before writing: failure leaves the previous good row.
            normalized = orjson.loads(orjson.dumps(payload))
            if not isinstance(normalized, dict) or not normalized.get("generatedAt"):
                raise ValueError("Statistics loader returned no snapshot timestamp")
            conn.execute("""INSERT INTO catalog_status_snapshot
                    (singleton, payload, generated_at)
                VALUES (1, %s, %s)
                ON CONFLICT (singleton) DO UPDATE SET
                    payload = EXCLUDED.payload,
                    generated_at = EXCLUDED.generated_at""",
                (Jsonb(normalized), normalized["generatedAt"]),
            )
            _LOG.info("Public catalog statistics snapshot refreshed")
            return True

    def start(self):
        with self._thread_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="catalog-status-refresh", daemon=True,
            )
            self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.refresh()
            except Exception:
                _LOG.warning("Statistics refresh failed; retaining previous snapshot", exc_info=True)
            self._stop.wait(POLL_SECONDS)

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
