"""Catalog request counters. Keep only aggregate counts, never URL parameters."""
from collections import deque
import threading
import time
import requests

_lock = threading.Lock()
_recent = deque(maxlen=1024)
_total = 0
_active = 0
_errors = 0
_last = ""


def catalog_get(*args, **kwargs):
    return tracked_get(requests.get, *args, **kwargs)


def tracked_get(get, *args, **kwargs):
    global _total, _active, _errors, _last
    with _lock:
        _total += 1
        _active += 1
        _recent.append(time.monotonic())
        _last = time.strftime("%H:%M:%S")
    try:
        response = get(*args, **kwargs)
        if response.status_code >= 400:
            with _lock:
                _errors += 1
        return response
    except Exception:
        with _lock:
            _errors += 1
        raise
    finally:
        with _lock:
            _active -= 1


def catalog_session():
    session = requests.Session()
    original = session.get
    session.get = lambda *args, **kwargs: tracked_get(original, *args, **kwargs)
    return session


def snapshot():
    cutoff = time.monotonic() - 60
    with _lock:
        return {"catalogRequests": _total, "catalogRequests60s": sum(t >= cutoff for t in _recent),
                "catalogRequestsActive": _active, "catalogRequestErrors": _errors,
                "lastCatalogRequest": _last}
