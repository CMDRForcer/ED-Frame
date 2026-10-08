"""Lossless, versioned SQLite payload compression with legacy JSON reads."""
import json
import zlib

_PREFIX = b"EDFH1\0"


def pack_json(encoded):
    raw = encoded.encode("utf-8")
    if len(raw) < 512:
        return encoded
    packed = _PREFIX + zlib.compress(raw, level=1)
    return packed if len(packed) + 64 < len(raw) else encoded


def unpack_json(payload):
    if isinstance(payload, bytes) and payload.startswith(_PREFIX):
        try:
            payload = zlib.decompress(payload[len(_PREFIX):]).decode("utf-8")
        except zlib.error as exc:
            raise ValueError("Invalid compressed history JSON") from exc
    return json.loads(payload)
