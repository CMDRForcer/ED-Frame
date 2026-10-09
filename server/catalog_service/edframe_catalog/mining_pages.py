"""Bounded, cross-worker storage for one immutable mining search.

Only public API projections are stored, never connection/transaction objects.
TTL controls page availability, NOT evidence that live data is unchanged.
Active snapshots are never evicted to admit another search. Failure leaves
the client free to use the existing fresh, bounded legacy search.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import time
import zlib

import orjson


MAX_ROWS = 50_000
CHUNK_ROWS = 5_000
BUILD_SECONDS = 20
TTL_SECONDS = 180
MAX_SNAPSHOTS = 8
MAX_COMPRESSED_BYTES = 8 * 1024 * 1024
MAX_RAW_BYTES = 64 * 1024 * 1024
MAX_CHUNK_BYTES = 8 * 1024 * 1024
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_DATABASE_BYTES = 96 * 1024 * 1024
_CURSOR = re.compile(r"f1\.([0-9a-f]{32})\.([0-9]{1,5})\Z")


class FrozenUnavailable(Exception):
    """No new snapshot can safely be built (client may fetch legacy pages)."""


class FrozenExpired(Exception):
    """Continuation cannot prove ownership/integrity; discard partial rows."""


def query_key(query):
    return hashlib.sha256(orjson.dumps(query, option=orjson.OPT_SORT_KEYS)).hexdigest()


def decode_cursor(cursor):
    match = _CURSOR.fullmatch(cursor or "")
    if not match:
        raise FrozenExpired("Invalid frozen mining cursor")
    return match[1], int(match[2])


def _pack(value, maximum):
    raw = orjson.dumps(value)
    if len(raw) > maximum:
        raise FrozenUnavailable("Mining snapshot exceeds byte budget")
    blob = zlib.compress(raw, 1)
    return blob, len(raw), hashlib.sha256(blob).hexdigest()


def _unpack(blob, raw_size, digest, maximum):
    if (not isinstance(blob, bytes) or not isinstance(raw_size, int)
            or not 0 <= raw_size <= maximum or len(blob) > MAX_COMPRESSED_BYTES
            or hashlib.sha256(blob).hexdigest() != digest):
        raise FrozenExpired("Mining snapshot checksum mismatch")
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(blob, raw_size + 1)
        if (len(raw) != raw_size or not decoder.eof or decoder.unused_data
                or decoder.unconsumed_tail):
            raise FrozenExpired("Mining snapshot size mismatch")
        return orjson.loads(raw)
    except (zlib.error, orjson.JSONDecodeError) as exc:
        raise FrozenExpired("Invalid mining snapshot contents") from exc


@dataclass
class Build:
    token: str
    deadline: float
    query_key: str
    revision: str
    projection: str
    rows: int = 0
    raw_bytes: int = 0
    compressed_bytes: int = 0

    def remaining_ms(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise FrozenUnavailable("Mining snapshot build deadline exceeded")
        return max(1, int(remaining * 1000))


class FrozenPages:
    def __init__(self, path, *, ttl=TTL_SECONDS, capacity=MAX_SNAPSHOTS,
                 compressed_limit=MAX_COMPRESSED_BYTES, clock=time.time):
        self.path = Path(path)
        self.ttl = ttl
        self.capacity = capacity
        self.compressed_limit = compressed_limit
        self.clock = clock

    @contextmanager
    def _db(self, *, write=False):
        db = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(str(self.path), timeout=.2, isolation_level=None)
            db.row_factory = sqlite3.Row
            # Rollback journal, not WAL: no pinned reader can grow an unbounded
            # WAL. FULL auto-vacuum returns freed pages after expiry/abort.
            db.execute("PRAGMA auto_vacuum=FULL")
            if db.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                raise FrozenUnavailable("Mining page cache requires bounded rollback journaling")
            if db.execute("PRAGMA auto_vacuum").fetchone()[0] != 1:
                raise FrozenUnavailable("Mining page cache requires reclaimable storage")
            db.execute("PRAGMA foreign_keys=ON")
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            db.execute(f"PRAGMA max_page_count={MAX_DATABASE_BYTES // page_size}")
            db.execute("""CREATE TABLE IF NOT EXISTS snapshots (
                token TEXT PRIMARY KEY, query_key TEXT NOT NULL,
                revision TEXT NOT NULL, projection TEXT NOT NULL,
                created REAL NOT NULL, expires REAL NOT NULL,
                lease_until REAL NOT NULL, ready INTEGER NOT NULL DEFAULT 0,
                row_count INTEGER NOT NULL DEFAULT 0, truncated INTEGER NOT NULL DEFAULT 0,
                metadata BLOB, metadata_size INTEGER, metadata_hash TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS chunks (
                token TEXT NOT NULL REFERENCES snapshots(token) ON DELETE CASCADE,
                row_offset INTEGER NOT NULL, row_count INTEGER NOT NULL,
                data BLOB NOT NULL, raw_size INTEGER NOT NULL, digest TEXT NOT NULL,
                PRIMARY KEY(token, row_offset))""")
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except (sqlite3.Error, OSError) as exc:
            if db is not None and db.in_transaction:
                db.rollback()
            raise FrozenUnavailable("Mining page cache unavailable") from exc
        finally:
            if db is not None:
                db.close()

    def _cleanup(self, db, now):
        db.execute("""DELETE FROM snapshots WHERE expires <= ? OR created > ?
            OR (ready=0 AND lease_until <= ?)""", (now, now, now))

    def find(self, query, revision, projection):
        with self._db() as db:
            row = db.execute("""SELECT token FROM snapshots
                WHERE query_key=? AND revision=? AND projection=? AND ready=1
                AND created <= ? AND expires > ? LIMIT 1""",
                (query_key(query), revision, projection, self.clock(), self.clock())).fetchone()
        return row["token"] if row else None

    @contextmanager
    def build(self, query, revision, projection):
        now = self.clock()
        build = Build(secrets.token_hex(16), time.monotonic() + BUILD_SECONDS,
                      query_key(query), revision, projection)
        with self._db(write=True) as db:
            self._cleanup(db, now)
            rows = db.execute("SELECT ready FROM snapshots").fetchall()
            if len(rows) >= self.capacity or any(not row["ready"] for row in rows):
                raise FrozenUnavailable("Mining page cache busy or full")
            db.execute("""INSERT INTO snapshots
                (token, query_key, revision, projection, created, expires, lease_until)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", (build.token, build.query_key,
                revision, projection, now, now + self.ttl, now + BUILD_SECONDS + 5))
        try:
            yield build
        finally:
            # Also handles SQL/codec/deadline failure. A worker crash is cleaned
            # up by its bounded lease; an unfinished snapshot is never served.
            try:
                with self._db(write=True) as db:
                    db.execute("DELETE FROM snapshots WHERE token=? AND ready=0", (build.token,))
            except FrozenUnavailable:
                # Cleanup must not replace the original error. The pending
                # lease remains bounded and will be reaped on next admission.
                pass

    def append(self, build, rows):
        build.remaining_ms()
        if not rows or len(rows) > CHUNK_ROWS or build.rows + len(rows) > MAX_ROWS:
            raise FrozenUnavailable("Invalid mining snapshot chunk")
        blob, size, digest = _pack({"rowOffset": build.rows, "rows": rows}, MAX_CHUNK_BYTES)
        build.raw_bytes += size
        build.compressed_bytes += len(blob)
        if (build.raw_bytes > MAX_RAW_BYTES
                or build.compressed_bytes > self.compressed_limit):
            raise FrozenUnavailable("Mining snapshot exceeds byte budget")
        with self._db(write=True) as db:
            if not db.execute("SELECT 1 FROM snapshots WHERE token=? AND ready=0",
                              (build.token,)).fetchone():
                raise FrozenUnavailable("Mining snapshot build lost")
            db.execute("INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                       (build.token, build.rows, len(rows), blob, size, digest))
        build.rows += len(rows)
        build.remaining_ms()

    def publish(self, build, *, references, truncated, snapshot_at):
        build.remaining_ms()
        blob, size, digest = _pack({"references": references, "snapshotAt": snapshot_at,
                                   "rowCount": build.rows, "truncated": bool(truncated),
                                   "queryKey": build.query_key, "revision": build.revision,
                                   "projection": build.projection},
                                   MAX_METADATA_BYTES)
        if (build.compressed_bytes + len(blob) > self.compressed_limit
                or build.raw_bytes + size > MAX_RAW_BYTES):
            raise FrozenUnavailable("Mining snapshot exceeds byte budget")
        with self._db(write=True) as db:
            changed = db.execute("""UPDATE snapshots SET ready=1, row_count=?, truncated=?,
                metadata=?, metadata_size=?, metadata_hash=? WHERE token=? AND ready=0
                AND expires > ?""", (build.rows, int(truncated), blob, size, digest,
                                      build.token, self.clock())).rowcount
            if changed != 1:
                raise FrozenUnavailable("Mining snapshot expired during build")

    def page(self, token, *, query, revision, projection, offset, limit):
        with self._db() as db:
            snapshot = db.execute("SELECT * FROM snapshots WHERE token=?", (token,)).fetchone()
            now = self.clock()
            if (not snapshot or not snapshot["ready"] or snapshot["expires"] <= now
                    or snapshot["created"] > now or snapshot["query_key"] != query_key(query)
                    or snapshot["revision"] != revision or snapshot["projection"] != projection):
                raise FrozenExpired("Mining snapshot expired or query changed")
            total = snapshot["row_count"]
            if offset < 0 or (offset >= total and (offset or total)) or not 1 <= limit <= CHUNK_ROWS:
                raise FrozenExpired("Mining snapshot page outside frozen range")
            end = min(offset + limit, total)
            chunks = db.execute("""SELECT * FROM chunks WHERE token=?
                AND row_offset < ? AND row_offset + row_count > ? ORDER BY row_offset""",
                                (token, end, offset)).fetchall()
        # Release SQLite readers before decompression/serialization.
        metadata = _unpack(snapshot["metadata"], snapshot["metadata_size"],
                           snapshot["metadata_hash"], MAX_METADATA_BYTES)
        if (not isinstance(metadata, dict) or not isinstance(metadata.get("references"), list)
                or not isinstance(metadata.get("snapshotAt"), str)
                or metadata.get("rowCount") != total
                or metadata.get("truncated") != bool(snapshot["truncated"])
                or metadata.get("queryKey") != snapshot["query_key"]
                or metadata.get("revision") != revision
                or metadata.get("projection") != projection):
            raise FrozenExpired("Invalid mining snapshot metadata")
        rows = []
        for chunk in chunks:
            contents = _unpack(chunk["data"], chunk["raw_size"], chunk["digest"], MAX_CHUNK_BYTES)
            if not isinstance(contents, dict) or contents.get("rowOffset") != chunk["row_offset"]:
                raise FrozenExpired("Mining snapshot chunk offset changed")
            values = contents.get("rows")
            if (not isinstance(values, list) or len(values) != chunk["row_count"]
                    or any(not isinstance(row, dict) for row in values)):
                raise FrozenExpired("Mining snapshot chunk length changed")
            rows.extend(values[max(0, offset - chunk["row_offset"]):end - chunk["row_offset"]])
        if len(rows) != end - offset:
            raise FrozenExpired("Mining snapshot chunk missing")
        more = end < total or bool(snapshot["truncated"])
        return {"snapshotProtocol": 1, "revision": revision, "notModified": False,
                "snapshotStatic": projection, "snapshotComplete": not more,
                "snapshotAt": metadata["snapshotAt"], "snapshotTruncated": bool(snapshot["truncated"]),
                "results": rows, "communityReferences": metadata["references"] if not offset else [],
                "hasMore": more, "nextCursor": f"f1.{token}.{end}" if more else None,
                "nextOffset": end if more else None}


def configured_pages():
    # Both Uvicorn workers share this container-local bounded cache. Not a
    # durable catalog volume and not a new cache in the Windows user profile.
    return FrozenPages(os.environ.get("EDFRAME_MINING_PAGES_PATH",
                      str(Path(tempfile.gettempdir(), "edframe-mining-pages.sqlite3"))))
