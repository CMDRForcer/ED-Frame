"""Local resource samples; no platform-specific dependency or CPU affinity changes."""
import os
import threading
import time


def processor_count():
    count = getattr(os, "process_cpu_count", os.cpu_count)()
    return max(1, count or 1)


def memory_status():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        class Status(ctypes.Structure):
            _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [
                (name, ctypes.c_ulonglong) for name in
                ("total", "available", "pageTotal", "pageAvailable", "virtualTotal", "virtualAvailable", "extended")]
        value = Status()
        value.length = ctypes.sizeof(value)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
            return value.total / 1024**2, value.available / 1024**2
    elif os.path.isfile("/proc/meminfo"):
        with open("/proc/meminfo", encoding="ascii") as handle:
            values = {line.split(":")[0]: int(line.split()[1]) / 1024 for line in handle}
        return values.get("MemTotal"), values.get("MemAvailable")
    return None, None


def cpu_times():
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    idle, kernel, user = (wintypes.FILETIME() for _ in range(3))
    if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        integer = lambda value: (value.dwHighDateTime << 32) | value.dwLowDateTime
        return integer(idle), integer(kernel) + integer(user)
    return None


def worker_limit(cores, total_mb, available_mb, cpu_busy=None):
    # Leave CPU time and memory for the game/UI. Unknown resources use one child.
    if cores < 4 or total_mb is None or available_mb is None:
        return 1
    if total_mb < 8192 or available_mb < 3072 or (cpu_busy is not None and cpu_busy >= .8):
        return 1
    return 2


def io_worker_limit(cores, available_mb, cpu_busy=None):
    if cores <= 2 or available_mb is None or available_mb < 2048 or (cpu_busy is not None and cpu_busy >= .8):
        return 1
    return 2 if cores <= 4 else 3


class WorkResources:
    def __init__(self, reader=memory_status, cpu_reader=cpu_times, cores=None):
        self.cores = processor_count() if cores is None else max(1, cores)
        self.reader, self.cpu_reader = reader, cpu_reader
        self._lock = threading.Lock()
        self._at = float("-inf")
        self._previous_cpu = None
        self._snapshot = {"logicalProcessors": self.cores, "cpuWorkerLimit": 1,
                          "ioWorkerLimit": 1,
                          "availableMemoryMiB": None, "totalMemoryMiB": None, "cpuBusyPercent": None}

    def sample(self):
        # Called from worker threads, never while rebuilding a QML binding.
        with self._lock:
            now = time.monotonic()
            if now - self._at < 1:
                return dict(self._snapshot)
            self._at = now
            try:
                total, available = self.reader()
            except (OSError, ValueError, AttributeError):
                total, available = None, None
            try:
                current = self.cpu_reader()
            except (OSError, ValueError, AttributeError):
                current = None
            busy = None
            if current and self._previous_cpu:
                idle = current[0] - self._previous_cpu[0]
                elapsed = current[1] - self._previous_cpu[1]
                if elapsed > 0:
                    busy = max(0, min(1, 1 - idle / elapsed))
            self._previous_cpu = current
            self._snapshot = {"logicalProcessors": self.cores,
                "totalMemoryMiB": round(total) if total is not None else None,
                "availableMemoryMiB": round(available) if available is not None else None,
                "cpuBusyPercent": round(busy * 100) if busy is not None else None,
                "ioWorkerLimit": io_worker_limit(self.cores, available, busy),
                "cpuWorkerLimit": worker_limit(self.cores, total, available, busy)}
            return dict(self._snapshot)

    def snapshot(self):
        with self._lock:
            return dict(self._snapshot)
