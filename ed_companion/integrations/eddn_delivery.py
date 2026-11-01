"""Small durable upload receipts and a Journal identity check without history parsing."""

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
import time


class DeliveryReceipts:
    """Receipts are committed by the sender before Qt publishes acceptance.

    The existing JSON queue remains the durable source of message contents.
    This separate database protects acknowledgements between batched snapshots.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, closing(self._connect()) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS delivery (
                job_id TEXT PRIMARY KEY, state TEXT NOT NULL,
                attempts INTEGER NOT NULL, recorded_at TEXT NOT NULL,
                result TEXT NOT NULL)""")
            connection.execute("CREATE TABLE IF NOT EXISTS gateway_limits (name TEXT PRIMARY KEY, until_at REAL NOT NULL)")
            connection.commit()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
        except Exception:
            connection.close()
            raise
        return connection

    def record(self, job_id, state, attempts, result=None):
        at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        with self._lock, closing(self._connect()) as connection:
            connection.execute("""INSERT INTO delivery VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET state=excluded.state,
                attempts=excluded.attempts, recorded_at=excluded.recorded_at,
                result=excluded.result""", (str(job_id), str(state), int(attempts),
                    at, json.dumps(result or {}, separators=(",", ":"))))
            if state == "retry" and (result or {}).get("last_http_status") == 429:
                connection.execute("""INSERT INTO gateway_limits VALUES ('upload', ?)
                    ON CONFLICT(name) DO UPDATE SET until_at=MAX(until_at, excluded.until_at)""",
                    (float(result["next_retry_at"]),))
            connection.commit()
        return at

    def restore(self, jobs):
        with self._lock, closing(self._connect()) as connection:
            for job in jobs:
                row = connection.execute(
                    "SELECT state, attempts, recorded_at, result FROM delivery WHERE job_id=?",
                    (str(job.get("id") or ""),),
                ).fetchone()
                if not row:
                    continue
                state, attempts, at, raw = row
                job["attempts"] = max(int(job.get("attempts") or 0), attempts)
                if state == "sent":
                    job.update(status="sent", sent_at=at, receipt=json.loads(raw),
                               last_result="Gateway accepted HTTP 200")
                elif state == "sending" and job.get("status") != "sent":
                    job.update(status="sending")  # Existing restart recovery owns retries.
                elif state in {"retry", "failed"} and job.get("status") != "sent":
                    job.update(json.loads(raw), status=state)
            limit = connection.execute("SELECT until_at FROM gateway_limits WHERE name='upload'").fetchone()
            return float(limit[0]) if limit else 0.0

    def forget(self, job_ids):
        with self._lock, closing(self._connect()) as connection:
            connection.executemany("DELETE FROM delivery WHERE job_id=?",
                                   [(str(value),) for value in job_ids])
            connection.commit()

    def forget_archived(self, receipts):
        """Remove only the exact ack archived by a completed queue snapshot.

        An identically named job may already have a newer attempt/receipt.
        Compare-and-delete prevents an older archive worker erasing that ack.
        """
        with self._lock, closing(self._connect()) as connection:
            for job_id, nonce in receipts.items():
                row = connection.execute("SELECT state, result FROM delivery WHERE job_id=?", (str(job_id),)).fetchone()
                if row and row[0] == "sent" and json.loads(row[1]).get("deliveryNonce") == nonce:
                    connection.execute("DELETE FROM delivery WHERE job_id=? AND state='sent' AND result=?",
                                       (str(job_id), row[1]))
            connection.commit()


def failure_state(result, attempts, retry_enabled=True, now=None):
    terminal = bool(result.get("terminal"))
    state = {"last_error": str(result.get("message") or "Upload failed")}
    if result.get("statusCode") is not None:
        state["last_http_status"] = result["statusCode"]
    if not terminal and retry_enabled and attempts < 7:
        try:
            retry_after = max(0, int(result.get("retryAfter")))
        except (TypeError, ValueError):
            retry_after = None
        delay = (retry_after if result.get("statusCode") == 429 and retry_after is not None
                 else max(60, min(900, 60 * 2 ** max(0, attempts - 1))))
        state.update(status="retry", next_retry_at=(time.time() if now is None else now) + delay,
                     next_retry_seconds=delay)
    else:
        state.update(status="failed", terminal_error=terminal)
    return state


def journal_upload_identity(directory):
    """Read only LoadGame identity from the latest session, never all history.

    A new/incomplete part 1 pauses uploads. A continuation can use its earlier
    parts, but cannot fall back to another session or Commander.
    """
    paths = sorted(Path(directory).glob("Journal.*.log"), reverse=True)
    if not paths:
        return ""
    path = paths[0]
    while True:
        identity, part = "", 1
        with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for line in handle:
                if "LoadGame" not in line and "Fileheader" not in line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("event") == "Fileheader":
                    part = int(event.get("part") or 1)
                elif event.get("event") == "LoadGame":
                    identity = str(event.get("FID") or event.get("Commander") or "").strip()
        if identity or part <= 1:
            return identity
        prefix, suffix, extension = path.name.rsplit(".", 2)
        if not suffix.isdigit() or int(suffix) <= 1:
            return ""
        path = path.with_name(f"{prefix}.{int(suffix) - 1:02d}.{extension}")
        if not path.exists():
            return ""
