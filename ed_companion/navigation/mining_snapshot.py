"""Bounded, profile-local complete snapshots; never a freshness override."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import zlib


MAX_SNAPSHOTS = 8
MAX_STORED_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 128 * 1024 * 1024
PROJECTION_VERSION = 1  # Bump when the cached candidate projection changes.


def valid_revision(value):
    return isinstance(value, str) and re.fullmatch(r"s1-[0-9a-f]{64}", value) is not None


def snapshot_key(url, params):
    scope = {key: value for key, value in params.items() if key not in
             ("offset", "cursor", "snapshot_protocol", "known_revision", "snapshot_revision", "snapshot_static")}
    if "system" in scope:
        scope["system"] = scope["system"].strip().casefold()
    raw = json.dumps({"server": url, "projection": PROJECTION_VERSION, "scope": scope}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


class MiningSnapshotStore:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5)
        try:
            with conn:
                conn.execute("CREATE TABLE IF NOT EXISTS snapshots ("
                             "key TEXT PRIMARY KEY, revision TEXT NOT NULL, payload BLOB NOT NULL, "
                             "checksum TEXT NOT NULL, touched INTEGER NOT NULL)")
                yield conn
        finally:
            conn.close()

    def revision(self, key):
        """Read only the small hint; rows must still validate before reuse.

        A changed region never needs to allocate/decompress its old payload.
        Missing/corrupt payloads after confirmation take the fresh paging path.
        """
        if not self.path.is_file():
            return None
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT revision FROM snapshots WHERE key=?", (key,)).fetchone()
            return row[0] if row and valid_revision(row[0]) else None
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            return None

    def load(self, key, *, expected_revision=None):
        if not self.path.is_file():
            return None
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT revision, payload, checksum FROM snapshots WHERE key=?",
                                   (key,)).fetchone()
            if (not row or not valid_revision(row[0]) or len(row[1]) > MAX_STORED_BYTES
                    or (expected_revision is not None and row[0] != expected_revision)):
                return None
            decoder = zlib.decompressobj()
            raw = decoder.decompress(row[1], MAX_EXPANDED_BYTES + 1)
            if len(raw) > MAX_EXPANDED_BYTES or not decoder.eof or decoder.unused_data:
                return None
            if hashlib.sha256(raw).hexdigest() != row[2]:
                return None
            candidates = json.loads(raw)
            if not isinstance(candidates, list) or any(
                    not isinstance(r, dict) or not r.get("system") or not r.get("ring")
                    for r in candidates):
                return None
            return {"revision": row[0], "candidates": candidates}
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError, zlib.error):
            # A corrupt/missing snapshot loses an optimization, never coverage.
            return None

    def save(self, snapshot):
        rows = snapshot.get("candidates")
        if (not valid_revision(snapshot.get("revision")) or snapshot.get("complete") is not True
                or not isinstance(rows, list) or any(not isinstance(r, dict)
                or not r.get("system") or not r.get("ring") for r in rows)):
            raise ValueError("A complete versioned mining snapshot is required")
        raw = json.dumps(snapshot["candidates"], ensure_ascii=False, separators=(",", ":")).encode()
        packed = zlib.compress(raw, level=3)
        if len(raw) > MAX_EXPANDED_BYTES or len(packed) > MAX_STORED_BYTES:
            return False
        with self._connect() as conn:
            touched = conn.execute("SELECT COALESCE(MAX(touched), 0)+1 FROM snapshots").fetchone()[0]
            conn.execute("INSERT OR REPLACE INTO snapshots VALUES (?, ?, ?, ?, ?)",
                         (snapshot["key"], snapshot["revision"], packed,
                          hashlib.sha256(raw).hexdigest(), touched))
            rows = conn.execute("SELECT key, length(payload) FROM snapshots ORDER BY touched DESC").fetchall()
            total = 0
            for index, (key, size) in enumerate(rows):
                total += size
                if index >= MAX_SNAPSHOTS or total > MAX_STORED_BYTES:
                    conn.execute("DELETE FROM snapshots WHERE key=?", (key,))
        return True

    def reset(self):
        if self.path.is_file():
            try:
                with self._connect() as conn:
                    conn.execute("DELETE FROM snapshots")
            except sqlite3.DatabaseError:
                # Explicit profile reset must not be blocked by a corrupt
                # disposable proof cache. Never delete the retained catalog.
                self.path.unlink(missing_ok=True)
