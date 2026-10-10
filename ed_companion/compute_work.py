"""Shared, memory-aware CPU service. Only pure/read-only tasks belong here."""
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
import multiprocessing
import os
import pickle
import threading
import time

from .work_resources import WorkResources


class ComputeStopped(RuntimeError):
    pass


def run_task(function, args, kwargs):
    started, cpu = time.monotonic(), time.process_time()
    result = function(*args, **kwargs)
    return result, {"pid": os.getpid(), "seconds": time.monotonic() - started,
                    "cpuSeconds": time.process_time() - cpu}


class ComputeWork:
    def __init__(self, resources=None, executor_factory=ProcessPoolExecutor, idle_seconds=30):
        self.resources = resources or WorkResources()
        self._factory = executor_factory
        self._condition = threading.Condition()
        self._pool = None
        self._closed = False
        self._active = {}
        self._waiting = []
        self._sequence = 0
        self._last_used = time.monotonic()
        self._idle_seconds = idle_seconds
        self._stats = {}
        self._fallbacks = 0

    def compute(self, name, function, *args, memory_mb=512, priority=1, fallback=None, **kwargs):
        queued_at = time.monotonic()
        with self._condition:
            if self._closed:
                raise ComputeStopped("Compute service stopped")
            self._sequence += 1
            ticket = (priority, -self._sequence)
            self._waiting.append(ticket)
        admitted = False
        use_fallback = False
        try:
            while not admitted:
                sample = self.resources.sample()
                with self._condition:
                    if self._closed:
                        raise ComputeStopped("Compute service stopped")
                    first = ticket == max(self._waiting)
                    available = sample.get("availableMemoryMiB")
                    reserve = max(512, (sample.get("totalMemoryMiB") or 5120) * .1)
                    reserved = sum(self._active.values())
                    fits = available is None or available - reserved - reserve >= memory_mb
                    if first and not self._active and not fits and fallback is not None:
                        self._waiting.remove(ticket)
                        self._active[ticket] = 0
                        admitted, use_fallback = True, True
                    elif first and len(self._active) < sample["cpuWorkerLimit"] and (fits or not self._active):
                        self._waiting.remove(ticket)
                        self._active[ticket] = memory_mb
                        admitted = True
                    else:
                        self._condition.wait(.25)
            if use_fallback:
                return self._fallback(name, fallback, queued_at)
            pool = None
            try:
                with self._condition:
                    if self._closed:
                        raise ComputeStopped("Compute service stopped")
                    if self._pool is None:
                        self._pool = self._factory(max_workers=1 if self.resources.cores < 4 else 2,
                            mp_context=multiprocessing.get_context("spawn"))
                    pool = self._pool
                    future = pool.submit(run_task, function, args, kwargs)
                value, stats = future.result()
                with self._condition:
                    self._record(name, stats, time.monotonic() - queued_at - stats["seconds"])
                return value
            except (BrokenProcessPool, OSError, pickle.PicklingError) as exc:
                with self._condition:
                    if self._closed:
                        raise ComputeStopped("Compute service stopped") from exc
                    # Dispose a failed pool; later jobs can build a fresh one.
                    damaged = pool if self._pool is pool else None
                    if self._pool is pool:
                        self._pool = None
                self._dispose(damaged)
                if fallback is None:
                    raise
                return self._fallback(name, fallback, queued_at)
        finally:
            with self._condition:
                if ticket in self._waiting:
                    self._waiting.remove(ticket)
                self._active.pop(ticket, None)
                self._last_used = time.monotonic()
                self._condition.notify_all()

    def _fallback(self, name, fallback, queued_at):
        # Run on the calling background thread, never on Qt's thread.
        started, cpu = time.monotonic(), time.thread_time()
        with self._condition:
            if self._closed:
                raise ComputeStopped("Compute service stopped")
            self._fallbacks += 1
        value = fallback()
        with self._condition:
            self._record(name, {"pid": os.getpid(), "seconds": time.monotonic() - started,
                               "cpuSeconds": time.thread_time() - cpu}, started - queued_at)
        return value

    def _record(self, name, stats, wait):
        previous = self._stats.get(name, {})
        self._stats[name] = {"name": name, "runs": previous.get("runs", 0) + 1,
            "seconds": round(previous.get("seconds", 0) + stats["seconds"], 3),
            "cpuSeconds": round(previous.get("cpuSeconds", 0) + stats["cpuSeconds"], 3),
            "maxSeconds": round(max(previous.get("maxSeconds", 0), stats["seconds"]), 3),
            "waitSeconds": round(previous.get("waitSeconds", 0) + max(0, wait), 3), "lastPid": stats["pid"]}

    def snapshot(self):
        resources = self.resources.snapshot()
        with self._condition:
            return {**resources, "computeActive": len(self._active), "computeQueued": len(self._waiting),
                    "computeFallbacks": self._fallbacks, "computeJobs": list(self._stats.values())}

    def trim_idle(self):
        with self._condition:
            if self._active or self._waiting or time.monotonic() - self._last_used < self._idle_seconds:
                return
            pool, self._pool = self._pool, None
        self._dispose(pool)

    @staticmethod
    def _dispose(pool):
        if pool:
            for process in list((pool._processes or {}).values()):
                process.terminate()
            pool.shutdown(wait=False, cancel_futures=True)

    def close(self):
        with self._condition:
            self._closed = True
            pool, self._pool = self._pool, None
            self._condition.notify_all()
        self._dispose(pool)
