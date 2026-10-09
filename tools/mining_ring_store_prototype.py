"""Opt-in immutable ring-store experiment; not used by the application.

Build only a new test database from a frozen public JSON copy. Preserve all
candidate payloads, order and root metadata; never prune or compress facts.
Readers bind to an explicit synthetic profile/generation. No ingestion, live
profile migration, reset, history maintenance or server changes are implemented.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass, asdict
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import uuid

from ed_companion.navigation.catalog_json import CatalogDictFactory, SHARED_FIELDS

FORMAT_VERSION = 1


@dataclass(frozen=True)
class StoreScope:
    profile: str
    generation: str


def file_digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def valid_position(value):
    # Match the current controller, including its legacy nonfinite semantics.
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _snapshot_decoder():
    """Use the production JSON loader's representation for selected rows.

    Pools are local to this one read and released when its generator closes.
    Facts remain independent replacement-only records; no global interning.
    """
    factory, keys, shared = CatalogDictFactory(), {}, {}
    def array_snapshot(value):
        return tuple(array_snapshot(item) if isinstance(item, list) else item for item in value)
    def object_hook(pairs):
        result = factory.new_dict(key for key, _value in pairs)
        for key, value in pairs:
            key = keys.setdefault(key, key)
            if key in SHARED_FIELDS and isinstance(value, str):
                value = shared.setdefault(value, value)
            if isinstance(value, list):
                value = array_snapshot(value)
            result[key] = value
        return result
    return json.JSONDecoder(object_pairs_hook=object_hook)


class _JSONReader:
    """Stream root candidates instead of retaining the complete JSON array."""
    def __init__(self, handle, chunk_size):
        self.handle = handle
        self.chunk_size = chunk_size
        self.buffer = ""
        self.offset = 0
        self.eof = False
        self.decoder = json.JSONDecoder()

    def fill(self):
        chunk = self.handle.read(self.chunk_size)
        self.buffer = self.buffer[self.offset:] + chunk
        self.offset = 0
        self.eof = not chunk

    def char(self):
        while True:
            while self.offset < len(self.buffer) and self.buffer[self.offset].isspace():
                self.offset += 1
            if self.offset < len(self.buffer):
                return self.buffer[self.offset]
            if self.eof:
                return ""
            self.fill()

    def consume(self, expected):
        if self.char() != expected:
            raise ValueError("Invalid catalog JSON separator")
        self.offset += 1

    def scalar(self):
        self.char()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.offset)
                # A numeric token can continue across a read boundary.
                if not self.eof and (end == len(self.buffer)
                        or self.buffer[end] not in " \t\r\n,]}:"):
                    self.fill()
                    continue
                self.offset = end
                return value
            except json.JSONDecodeError:
                if self.eof:
                    raise
                self.fill()

    def array(self):
        self.consume("[")
        if self.char() != "]":
            while True:
                yield self.scalar()
                if self.char() != ",":
                    break
                self.consume(",")
        self.consume("]")


def iter_catalog(path, metadata, *, chunk_size=64 * 1024):
    """Yield every candidate, preserving even non-dict legacy entries.

The experiment explicitly rejects duplicate root keys or a non-array candidate
field, instead of silently producing a different root than the JSON loader.
Metadata is available after fully consuming the iterator.
"""
    if chunk_size <= 0:
        raise ValueError("Positive JSON chunk size required")
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        reader = _JSONReader(handle, chunk_size)
        if reader.char() != "{":
            raise ValueError("A catalog root object is required")
        reader.consume("{")
        keys = set()
        if reader.char() != "}":
            while True:
                key = reader.scalar()
                if not isinstance(key, str) or key in keys:
                    raise ValueError("Unique string catalog keys required")
                keys.add(key)
                reader.consume(":")
                if key == "candidates":
                    yield from reader.array()
                else:
                    metadata[key] = reader.scalar()
                if reader.char() != ",":
                    break
                reader.consume(",")
        reader.consume("}")
        if reader.char() or "candidates" not in keys:
            raise ValueError("Complete catalog with candidates array required")


def build_store(source, destination, scope, *, checkpoint=None):
    """Atomic, no-clobber build from an explicit frozen test input only."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or destination.exists():
        raise FileExistsError("Use a new isolated database path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + ".building-" + uuid.uuid4().hex)
    source_hash = file_digest(source)
    metadata, pending, spatial = {}, [], []
    count = indexed = exceptional = 0
    try:
        with closing(sqlite3.connect(staging)) as connection, connection:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA cache_size=-4096")
            connection.execute("PRAGMA temp_store=FILE")
            connection.executescript("""
                CREATE TABLE records (
                    seq INTEGER PRIMARY KEY, system_key TEXT NOT NULL,
                    exceptional INTEGER NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX records_system ON records(system_key);
                CREATE INDEX records_exceptional ON records(seq) WHERE exceptional=1;
                CREATE VIRTUAL TABLE spatial USING rtree(seq,x0,x1,y0,y1,z0,z1);
                CREATE TABLE metadata (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
            """)
            connection.execute("BEGIN IMMEDIATE")
            def flush():
                connection.executemany("INSERT INTO records VALUES (?,?,?,?)", pending)
                connection.executemany("INSERT INTO spatial VALUES (?,?,?,?,?,?,?)", spatial)
                pending.clear()
                spatial.clear()
            for seq, row in enumerate(iter_catalog(source, metadata)):
                system = str(row.get("system") or "").strip().casefold() if isinstance(row, dict) else ""
                position = valid_position(row.get("coordinates")) if isinstance(row, dict) else None
                usable = position is not None and all(math.isfinite(v) and abs(v) < 3e38 for v in position)
                fallback = int(position is not None and not usable)
                pending.append((seq, system, fallback, encode(row)))
                if usable:
                    x, y, z = position
                    spatial.append((seq, x, x, y, y, z, z))
                    indexed += 1
                exceptional += fallback
                count += 1
                if len(pending) >= 512:
                    flush()
                    if checkpoint is not None:
                        checkpoint(count)
            flush()
            if file_digest(source) != source_hash:
                raise ValueError("Frozen source changed during import")
            manifest = {"format": FORMAT_VERSION, "scope": asdict(scope),
                        "sourceSha256": source_hash, "count": count,
                        "indexed": indexed, "exceptional": exceptional,
                        "complete": True}
            connection.executemany("INSERT INTO metadata VALUES (?,?)", (
                ("root", encode(metadata)), ("manifest", encode(manifest)),
            ))
        # Windows rename and POSIX hard-link creation refuse existing targets.
        # The staging database is closed and has no WAL sidecar.
        if os.name == "nt":
            os.rename(staging, destination)
        else:
            os.link(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return {**manifest, "bytes": destination.stat().st_size}


class PrototypeRingStore:
    """Read-only immutable scope-bound store with a 4-MiB SQLite page cache."""
    def __init__(self, path, scope):
        self.path = Path(path).resolve()
        self.scope = scope

    @contextmanager
    def _reader(self):
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA cache_size=-4096")
            connection.execute("PRAGMA mmap_size=0")
            connection.execute("PRAGMA temp_store=FILE")
            connection.execute("BEGIN")
            row = connection.execute("SELECT payload FROM metadata WHERE key='manifest'").fetchone()
            manifest = json.loads(row[0]) if row else {}
            if (manifest.get("format") != FORMAT_VERSION or manifest.get("complete") is not True
                    or manifest.get("scope") != asdict(self.scope)):
                raise ValueError("Ring store format/profile/generation mismatch")
            yield connection
        finally:
            connection.close()

    def metadata(self):
        with self._reader() as connection:
            return {key: json.loads(payload) for key, payload in
                    connection.execute("SELECT key,payload FROM metadata")}

    def iter_all(self):
        with self._reader() as connection:
            for payload, in connection.execute("SELECT payload FROM records ORDER BY seq"):
                yield json.loads(payload)

    def nearby(self, origin_system, origin, radius, *, snapshot_arrays=False):
        """Preserve source order and current rounded inclusive selection.

        Nonfinite legacy coordinates require a small fallback scan; nonfinite
        origins require a full scan to match the existing geometry semantics.
        There is no row limit or retention period. Callers apply dynamic filters
        and freshness to these original payloads using existing domain code.
        """
        radius = float(radius)
        if not math.isfinite(radius):
            raise ValueError("Finite radius required")
        position = valid_position(origin)
        system = str(origin_system or "").casefold()
        with self._reader() as connection:
            parameters = ()
            if radius <= 0 or (position is not None and not all(math.isfinite(v) for v in position)):
                statement = "SELECT payload FROM records ORDER BY seq"
            elif position is None:
                statement = "SELECT payload FROM records WHERE system_key=? ORDER BY seq"
                parameters = (system,)
            else:
                # RTree rounds bounds outwards to float32. Overlap tests plus
                # this conservative box cannot lose a rounded-in boundary row.
                margin = radius + 0.1
                statement = """SELECT payload FROM records WHERE seq IN (
                    SELECT seq FROM records WHERE system_key=?
                    UNION SELECT seq FROM records WHERE exceptional=1
                    UNION SELECT seq FROM spatial WHERE
                      x0<=? AND x1>=? AND y0<=? AND y1>=? AND z0<=? AND z1>=?
                ) ORDER BY seq"""
                parameters = (system, position[0]+margin, position[0]-margin,
                              position[1]+margin, position[1]-margin,
                              position[2]+margin, position[2]-margin)
            decoder = _snapshot_decoder() if snapshot_arrays else json.JSONDecoder()
            rows = (decoder.decode(payload) for payload, in connection.execute(statement, parameters))
            rows = (row for row in rows if isinstance(row, dict))
            if radius <= 0:
                yield from rows
            else:
                for row in rows:
                    coordinates = valid_position(row.get("coordinates"))
                    if str(row.get("system") or "").strip().casefold() == system:
                        distance = 0.0
                    elif position is not None and coordinates is not None:
                        distance = round(math.sqrt(sum((a-b)**2 for a, b in zip(position, coordinates))), 1)
                    else:
                        distance = None
                    if distance is not None and not float(distance) > radius:
                        yield row
