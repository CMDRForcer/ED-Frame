"""Bounded JSON decoding for large public catalogs without long GIL stalls.

Decode individual records, share repeated fact strings within this load only,
and yield regularly. No process-global intern pool, dropped facts or truncation.
"""
import json
import time


SHARED_FIELDS = frozenset({
    "system", "body", "ringType", "reserveLevel", "evidence", "sourceEvidence",
    "source", "observedAt", "learnedAt", "commodity", "controllingPower",
    "power", "powerState", "powerRelationship", "yieldAggregationScope",
    "ringAssociationStatus", "systemPositionEvidence",
})


def iter_catalog_json(value):
    """Serialize record-sized chunks; never build a 225-MB temporary string."""
    options = {"ensure_ascii": False, "separators": (",", ":")}
    def array(rows):
        yield "["
        for index, row in enumerate(rows):
            if index:
                yield ","
            yield json.dumps(row, **options)
            if index % 128 == 0:
                time.sleep(0)
        yield "]"
    if isinstance(value, dict):
        yield "{"
        for index, (key, field) in enumerate(value.items()):
            if index:
                yield ","
            yield json.dumps(key, **options) + ":"
            if isinstance(field, list):
                yield from array(field)
            else:
                yield json.dumps(field, **options)
        yield "}"
    elif isinstance(value, list):
        yield from array(value)
    else:
        yield json.dumps(value, **options)


def load_catalog_json(path, default):
    """Read a JSON root object/list incrementally; retain normal JSON semantics."""
    shared = {}
    keys = {}

    def object_hook(pairs):
        result = {}
        for key, value in pairs:
            key = keys.setdefault(key, key)
            if key in SHARED_FIELDS and isinstance(value, str):
                value = shared.setdefault(value, value)
            result[key] = value
        return result

    decoder = json.JSONDecoder(object_pairs_hook=object_hook)
    with path.open("r", encoding="utf-8-sig") as handle:
        buffer = ""
        offset = 0
        exhausted = False
        records = 0

        def fill():
            nonlocal buffer, offset, exhausted
            chunk = handle.read(64 * 1024)
            buffer = buffer[offset:] + chunk
            offset = 0
            exhausted = not chunk

        def char():
            nonlocal offset
            while True:
                while offset < len(buffer) and buffer[offset].isspace():
                    offset += 1
                if offset < len(buffer):
                    return buffer[offset]
                if exhausted:
                    return ""
                fill()

        def consume(expected):
            nonlocal offset
            if char() != expected:
                raise ValueError("Invalid catalog JSON separator")
            offset += 1

        def scalar():
            nonlocal offset
            char()
            while True:
                try:
                    value, end = decoder.raw_decode(buffer, offset)
                    # A number may end at a chunk boundary but continue in the
                    # next chunk. Wait for a separator before accepting it.
                    if end == len(buffer) and not exhausted:
                        fill()
                        continue
                    offset = end
                    return value
                except json.JSONDecodeError:
                    if exhausted:
                        raise
                    fill()

        def array():
            nonlocal records
            consume("[")
            result = []
            if char() != "]":
                while True:
                    result.append(scalar())
                    records += 1
                    if records % 128 == 0:
                        time.sleep(0)  # Give Qt/control callbacks a GIL turn.
                    if char() != ",":
                        break
                    consume(",")
            consume("]")
            return result

        if char() == "[":
            result = array()
        elif char() == "{":
            consume("{")
            result = {}
            if char() != "}":
                while True:
                    key = scalar()
                    if not isinstance(key, str):
                        raise ValueError("Catalog object keys must be strings")
                    consume(":")
                    result[key] = array() if char() == "[" else scalar()
                    if char() != ",":
                        break
                    consume(",")
            consume("}")
        else:
            result = scalar()
        if char():
            raise ValueError("Trailing catalog JSON content")
        return result
