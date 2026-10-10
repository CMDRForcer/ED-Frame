"""Bounded daemon workers; interactive work never queues behind catalog imports."""
from collections import deque
import threading
import time


class BackgroundWork:
    LIMITS = {"journal": 1, "interactive": 2, "background": 1}

    def __init__(self, on_thread=None, resources=None):
        self._lock = threading.RLock()
        self._pending = {lane: deque() for lane in self.LIMITS}
        self._active = {lane: 0 for lane in self.LIMITS}
        self._closed = False
        self._on_thread = on_thread
        self._completed = 0
        self._submitted = 0
        self._resources = resources
        # Start conservatively until a worker has sampled the machine.
        self._limit = 2 if resources else 4
        self._limits = dict(self.LIMITS)
        if resources and resources.cores <= 4:
            self._limits["interactive"] = 1
        self._jobs = {}

    @staticmethod
    def lane(name):
        if name.startswith(("journal-", "initial-journal", "surface-nav", "commander-")):
            return "journal"
        if name.startswith(("mining-route-", "mining-rows-", "commodity-", "station-service",
                            "shipyard-offer-search", "frontier-", "history-export")):
            return "interactive"
        return "background"

    def submit(self, target, name, *, lane=None):
        with self._lock:
            if self._closed:
                return False
            self._submitted += 1
            self._pending[lane or self.lane(name)].append((target, name, time.monotonic()))
            self._dispatch()
            return True

    def _dispatch(self):
        for lane, limit in self._limits.items():
            # Let a requested search finish before starting another import.
            if lane == "background" and (self._active["interactive"] or self._pending["interactive"]):
                continue
            while self._pending[lane] and self._active[lane] < limit and sum(self._active.values()) < self._limit:
                target, name, queued = self._pending[lane].popleft()
                self._active[lane] += 1

                def run(target=target, lane=lane, name=name, queued=queued):
                    started, cpu = time.monotonic(), time.thread_time()
                    try:
                        if self._resources:
                            sample = self._resources.sample()
                            with self._lock:
                                constrained = (sample.get("availableMemoryMiB") is None
                                    or sample["availableMemoryMiB"] < 2048
                                    or (sample.get("cpuBusyPercent") or 0) >= 80)
                                self._limit = 2 if self._resources.cores <= 2 or constrained else 4
                        target()
                    finally:
                        with self._lock:
                            group = "journal-state" if name.startswith("journal-state-") else name
                            if group not in self._jobs and len(self._jobs) >= 64:
                                group = "other"
                            stats = self._jobs.setdefault(group, {"name": group, "runs": 0,
                                "seconds": 0, "threadCpuSeconds": 0, "waitSeconds": 0, "maxSeconds": 0})
                            duration = time.monotonic() - started
                            stats["runs"] += 1
                            stats["seconds"] += duration
                            stats["threadCpuSeconds"] += time.thread_time() - cpu
                            stats["waitSeconds"] += started - queued
                            stats["maxSeconds"] = max(stats["maxSeconds"], duration)
                            self._active[lane] -= 1
                            self._completed += 1
                            if not self._closed:
                                self._dispatch()

                thread = threading.Thread(target=run, name=name, daemon=True)
                if self._on_thread:
                    self._on_thread(thread)
                thread.start()

    def snapshot(self):
        with self._lock:
            return {"active": sum(self._active.values()),
                    "queued": sum(map(len, self._pending.values())),
                    "backgroundActive": self._active["background"],
                    "completed": self._completed, "submitted": self._submitted,
                    "threadWorkerLimit": self._limit,
                    "threadJobs": [{key: round(value, 3) if isinstance(value, float) else value
                                    for key, value in row.items()} for row in self._jobs.values()]}

    def close(self):
        """Stop launching work. Controller shutdown retains pending observations."""
        with self._lock:
            self._closed = True
            for queue in self._pending.values():
                queue.clear()


class Responsiveness:
    """Bounded, local-only event-loop measurements; no user data or telemetry."""
    def __init__(self, interval=0.1):
        self.interval = interval
        self.last = time.monotonic()
        self.samples = deque(maxlen=600)

    def tick(self):
        now = time.monotonic()
        self.samples.append((now, max(0, now - self.last - self.interval) * 1000))
        self.last = now

    def snapshot(self):
        cutoff = time.monotonic() - 60
        delays = [delay for stamp, delay in self.samples if stamp >= cutoff]
        return {"maxUiDelayMs": round(max(delays, default=0)),
                "uiStalls60s": sum(delay >= 100 for delay in delays)}
