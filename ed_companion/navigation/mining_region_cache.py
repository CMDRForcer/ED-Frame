"""Bounded, process-local reuse of complete regional reads, not live proof.

Only network workers serialize/decompress entries. No user files are changed.
Retrieval reuse never changes observation timestamps or extends source freshness.
"""

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import threading
import time
import zlib

from .mining_commodities import mining_commodity_id
from .mining_finder import EDFRAME_CATALOG_SITES_URL
from .mining_powerplay import EDFRAME_POWERPLAY_URL
from .mining_powerplay_policy import POWERPLAY_LAST_KNOWN_HOURS


MAX_STORED_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_ROWS = 50_000
REUSE_SECONDS = {"sites": 300, "powerplay": 60}
ROWS_PER_BLOCK = 128


@dataclass(frozen=True)
class _Region:
    started: float
    expires: float
    coverage: bytes
    blocks: tuple[bytes, ...]
    size: int


class MiningRegionCache:
    def __init__(self, *, clock=time.monotonic, wall_clock=time.time,
                 max_bytes=MAX_STORED_BYTES, max_entries=4):
        self._clock = clock
        self._wall_clock = wall_clock
        self._max_bytes = max(0, min(MAX_STORED_BYTES, max_bytes))
        self._max_entries = max(0, min(4, max_entries))
        self._entries = OrderedDict()
        self._lock = threading.Lock()

    def now(self):
        return self._clock()

    @staticmethod
    def _key(kind, query, origin):
        if kind not in REUSE_SECONDS:
            raise ValueError("Unknown regional domain")
        coordinates = tuple(float(value) for value in origin["coordinates"])
        radius = float(query["nearbyLy"])
        if (len(coordinates) != 3 or not 0 < radius <= 2000
                or not all(math.isfinite(value) for value in (*coordinates, radius))):
            raise ValueError("Invalid regional scope")
        url = EDFRAME_CATALOG_SITES_URL if kind == "sites" else EDFRAME_POWERPLAY_URL
        return (url, coordinates, radius,
                mining_commodity_id(query["commodity"]) if kind == "sites" else "",
                str(query.get('_powerplayPower') or '').casefold() if kind == 'powerplay' else '',
                query.get('_powerplayGoal', '') if kind == 'powerplay' else '')

    def get(self, kind, query, origin):
        try:
            key = self._key(kind, query, origin)
            with self._lock:
                entry = self._entries.get(key)
                now = self.now()
                if not entry:
                    return None
                if not entry.started <= now < entry.expires:
                    del self._entries[key]
                    return None
                self._entries.move_to_end(key)
            rows, expanded = [], len(entry.coverage)
            coverage = json.loads(entry.coverage)
            # Keep JSON's GIL-held C calls small. A complete 50k-row document
            # would add a new event-loop stall even on a network worker.
            for packed in entry.blocks:
                decoder = zlib.decompressobj()
                raw = decoder.decompress(packed, MAX_EXPANDED_BYTES - expanded + 1)
                expanded += len(raw)
                if expanded > MAX_EXPANDED_BYTES or not decoder.eof or decoder.unused_data:
                    return None
                rows.extend(json.loads(raw))
            now = self.now()
            if (not entry.started <= now < entry.expires or not isinstance(coverage, dict)
                    or (kind == "powerplay" and self._powerplay_lifetime(rows) <= 0)):
                return None
            # This is recent retrieval reuse, NOT a new server confirmation.
            coverage.pop("notModified", None)
            coverage.update(cacheHit=True, cacheAgeSeconds=round(now - entry.started, 1))
            return rows, coverage
        except (KeyError, ValueError, TypeError, zlib.error):
            return None  # Losing an optimization must never lose the fresh path.

    def put(self, kind, query, origin, rows, coverage, *, started_at, is_current=None):
        if (not isinstance(coverage, dict) or coverage.get("complete") is not True
                or coverage.get("bounded") is not False
                or coverage.get("consistent") is False or coverage.get("partialError")
                or not isinstance(rows, list) or len(rows) > MAX_ROWS
                or any(not isinstance(row, dict) or not row.get("system")
                       or not row.get("ring" if kind == "sites" else "power") for row in rows)):
            return False
        try:
            key = self._key(kind, query, origin)
            now = self.now()
            expires = started_at + REUSE_SECONDS[kind]
            if kind == "powerplay":
                # Retain dated history; the planner re-evaluates current versus
                # last-known status at its own clock on every query.
                expires = min(expires, now + self._powerplay_lifetime(rows))
            if not started_at <= now < expires or (is_current is not None and not is_current()):
                return False
            clean_coverage = {key: value for key, value in coverage.items()
                              if key not in ("_snapshot", "cacheHit", "cacheAgeSeconds")}
            metadata = json.dumps(clean_coverage, separators=(",", ":"), allow_nan=False).encode()
            expanded = size = len(metadata)
            if not self._max_entries or size > self._max_bytes or expanded > MAX_EXPANDED_BYTES:
                return False
            blocks = []
            for offset in range(0, len(rows), ROWS_PER_BLOCK):
                if is_current is not None and not is_current():
                    return False
                raw = json.dumps(rows[offset:offset + ROWS_PER_BLOCK], ensure_ascii=False,
                                 separators=(",", ":"), allow_nan=False).encode()
                expanded += len(raw)
                if expanded > MAX_EXPANDED_BYTES:
                    return False
                packed = zlib.compress(raw, level=1)
                size += len(packed)
                if size > self._max_bytes:
                    return False
                blocks.append(packed)
            with self._lock:
                now = self.now()
                if (not started_at <= now < expires
                        or (is_current is not None and not is_current())):
                    return False
                for old_key, old in list(self._entries.items()):
                    if old.expires <= now:
                        del self._entries[old_key]
                self._entries[key] = _Region(started_at, expires, metadata, tuple(blocks), size)
                self._entries.move_to_end(key)
                while (len(self._entries) > self._max_entries
                       or sum(entry.size for entry in self._entries.values()) > self._max_bytes):
                    self._entries.popitem(last=False)
            return True
        except (KeyError, ValueError, TypeError, OverflowError, zlib.error):
            return False

    def _powerplay_lifetime(self, rows):
        remaining = REUSE_SECONDS["powerplay"]
        now = self._wall_clock()
        for row in rows:
            stamp = datetime.fromisoformat(str(row["observedAt"]).replace("Z", "+00:00"))
            stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
            age = now - stamp.timestamp()
            limit = POWERPLAY_LAST_KNOWN_HOURS * 3600
            if not -300 <= age < limit:
                return 0
            remaining = min(remaining, limit - age)
        return remaining

    @property
    def stored_bytes(self):
        with self._lock:
            return sum(entry.size for entry in self._entries.values())

    @property
    def entry_count(self):
        with self._lock:
            return len(self._entries)
