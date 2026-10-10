"""Bounded independent route checks with worker-owned HTTP connections."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import math
import threading

import requests


LOGGER = logging.getLogger(__name__)
MAX_VERIFICATION_WORKERS = 2


def verification_market_origin(route):
    """Reuse this mine system's known coordinates, never its sale/origin system."""
    values = route.get("coordinates")
    system = str(route.get("system") or "").strip()
    if not system or not isinstance(values, (list, tuple)) or len(values) != 3:
        return None
    try:
        coordinates = [float(value) for value in values]
    except (TypeError, ValueError, OverflowError):
        return None
    if any(isinstance(value, bool) for value in values) or not all(
        math.isfinite(value) for value in coordinates
    ):
        return None
    return {"system": system, "coordinates": coordinates}


def iter_verification_jobs(jobs, execute, *, is_current=None, session_factory=None,
                           max_workers=MAX_VERIFICATION_WORKERS):
    """Run at most two independent checks, yielding each completion once.

    Each lane owns and reuses its Session; no Session is used by two threads.
    Provider fallbacks and cursor pages stay sequential within their own job.
    Check cancellation before dispatch AND every GET, join all work before
    closing connections, and leave result/progress publication to the caller.
    """
    jobs = list(jobs)
    if not jobs:
        return
    session_factory = session_factory or requests.Session
    local = threading.local()
    sessions = []
    session_lock = threading.Lock()

    def check_current():
        if is_current is not None and not is_current():
            raise RuntimeError("Mining verification superseded or shutting down")

    def run(job):
        check_current()
        if not hasattr(local, "session"):
            local.session = session_factory()
            with session_lock:
                sessions.append(local.session)

        def get(*args, **kwargs):
            check_current()
            return local.session.get(*args, **kwargs)

        kind, target = job
        return execute(kind, target, get)

    try:
        with ThreadPoolExecutor(
            max_workers=max(1, min(MAX_VERIFICATION_WORKERS, int(max_workers), len(jobs))),
            thread_name_prefix="mining-verify",
        ) as pool:
            futures = {pool.submit(run, job): (index, *job)
                       for index, job in enumerate(jobs)}
            for future in as_completed(futures):
                index, kind, target = futures[future]
                try:
                    value = future.result()
                except Exception as exc:
                    yield index, kind, target, None, exc
                else:
                    yield index, kind, target, value, None
    finally:
        for session in sessions:
            try:
                session.close()
            except Exception:
                LOGGER.exception("Mining verification connection cleanup failed")
