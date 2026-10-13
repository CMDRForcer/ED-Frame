"""Private active-installation counts; no IP or Commander columns."""
from datetime import date, datetime, timedelta, timezone
import logging
import os
import threading
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_LOG = logging.getLogger(__name__)
RETENTION_DAYS = 90


class UsagePingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    install_id: UUID
    app_version: str = Field(min_length=1, max_length=32, strict=True)


def utc_today():
    return datetime.now(timezone.utc).date()


def excluded_ids():
    result = set()
    for value in os.environ.get("EDFRAME_USAGE_EXCLUDED_IDS", "").split(","):
        try:
            result.add(UUID(value.strip()))
        except ValueError:
            pass
    return result


def record_ping(conn, payload, today=None):
    day = today or utc_today()
    conn.execute("""INSERT INTO usage_pings (install_id, day, app_version)
        VALUES (%s, %s, %s) ON CONFLICT (install_id, day) DO NOTHING""",
        (payload.install_id, day, payload.app_version))


def usage_stats(conn, today=None):
    day = today or utc_today()
    start = day - timedelta(days=29)
    counts = conn.execute("""SELECT
        COUNT(DISTINCT CASE WHEN day = %s THEN install_id END) AS dau,
        COUNT(DISTINCT CASE WHEN day >= %s THEN install_id END) AS wau,
        COUNT(DISTINCT install_id) AS mau
        FROM usage_pings WHERE day >= %s AND day <= %s""",
        (day, day - timedelta(days=6), start, day)).fetchone()
    versions = conn.execute("""WITH ranked AS (
        SELECT install_id, app_version,
            ROW_NUMBER() OVER (PARTITION BY install_id ORDER BY day DESC) AS rank
        FROM usage_pings WHERE day >= %s AND day <= %s
        ) SELECT app_version, COUNT(*) AS installs
        FROM ranked WHERE rank = 1 GROUP BY app_version ORDER BY app_version""",
        (start, day)).fetchall()
    return {"dau": int(counts["dau"]), "wau": int(counts["wau"]),
            "mau": int(counts["mau"]),
            "by_version_30d": {row["app_version"]: int(row["installs"]) for row in versions}}


def purge_old_pings(conn, today=None):
    day = today or utc_today()
    return conn.execute("DELETE FROM usage_pings WHERE day < %s",
                        (day - timedelta(days=RETENTION_DAYS),)).rowcount


class UsageRetention:
    """Small background job managed by the existing FastAPI lifespan.

    Each worker checks the UTC date hourly; its first successful cleanup each
    day is final. Concurrent workers delete the same expired rows safely.
    No deletion of observations or changes to catalog maintenance are made.
    """
    def __init__(self, connection_factory):
        self.connection = connection_factory
        self._stop = threading.Event()
        self._thread = None
        self._last_day = None

    def run_due(self, today=None):
        day = today or utc_today()
        if day == self._last_day:
            return False
        with self.connection() as conn:
            conn.execute("SET LOCAL statement_timeout = '5s'")
            purge_old_pings(conn, day)
        self._last_day = day
        return True

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="usage-retention", daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.run_due()
            except Exception:
                _LOG.warning("Usage retention cleanup failed")
            self._stop.wait(3600)

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
