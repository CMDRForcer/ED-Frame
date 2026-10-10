from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch

from ed_companion.compute_work import ComputeWork, ComputeStopped
from ed_companion.cpu_tasks import journal_projection, commander_projection, powerplay_merge
from ed_companion.work_resources import WorkResources, worker_limit, io_worker_limit


class ControlledPool:
    """Control completion rather than rely on machine speed in scheduling tests."""
    def __init__(self, **kwargs):
        self.calls = []
        self._processes = {}
        self.closed = False

    def submit(self, fn, args, kwargs):
        # The service sends run_task(function, arguments, keyword_arguments).
        raise AssertionError("Use submit with the service's four arguments")

    def shutdown(self, **kwargs):
        self.closed = True


class QueuePool(ControlledPool):
    def submit(self, wrapper, function, args, kwargs):
        future = Future()
        self.calls.append((function, args, kwargs, future))
        return future

    def finish(self, index):
        function, args, kwargs, future = self.calls[index]
        future.set_result((function(*args, **kwargs), {"pid": 123, "seconds": .01, "cpuSeconds": .01}))


def resources(cores=8, total=16384, available=12000):
    return WorkResources(cores=cores, reader=lambda: (total, available), cpu_reader=lambda: None)


def await_condition(check, timeout=2):
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() >= deadline:
            raise AssertionError("Timed out waiting for controlled worker")
        time.sleep(.005)


class ComputePolicyTests(unittest.TestCase):
    def test_small_unknown_low_memory_and_busy_machines_use_one_worker(self):
        for cores, total, available, busy in ((1, 16384, 12000, None), (2, 8192, 5000, None),
                (28, 4096, 3000, None), (28, 32768, 2000, None), (28, None, None, None),
                (28, 32768, 18000, .9)):
            self.assertEqual(worker_limit(cores, total, available, busy), 1)
        self.assertEqual(worker_limit(4, 8192, 4096), 2)
        self.assertEqual(worker_limit(28, 32768, 18000, .3), 2)
        for cores, available, busy in ((1, 12000, None), (2, 5000, None), (28, 1000, None),
                                       (28, None, None), (28, 18000, .9)):
            self.assertEqual(io_worker_limit(cores, available, busy), 1)
        self.assertEqual(io_worker_limit(4, 4096), 2)
        self.assertEqual(io_worker_limit(28, 18000, .3), 3)

    def test_two_jobs_overlap_and_journal_overtakes_waiting_background_job(self):
        pool = QueuePool()
        service = ComputeWork(resources(), executor_factory=lambda **kw: pool)
        self.addCleanup(service.close)
        results = []
        threads = []
        def launch(name, priority):
            thread = threading.Thread(target=lambda: results.append(service.compute(name, str, name, priority=priority)))
            threads.append(thread)
            thread.start()
        launch("first", 1)
        launch("second", 1)
        await_condition(lambda: len(pool.calls) == 2)
        launch("background", 0)
        await_condition(lambda: service.snapshot()["computeQueued"] == 1)
        launch("journal", 3)
        await_condition(lambda: service.snapshot()["computeQueued"] == 2)
        pool.finish(0)
        await_condition(lambda: len(pool.calls) == 3)
        self.assertEqual(pool.calls[2][1], ("journal",))
        pool.finish(1)
        await_condition(lambda: len(pool.calls) == 4)
        pool.finish(2)
        pool.finish(3)
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertCountEqual(results, ("first", "second", "background", "journal"))

    def test_memory_pressure_serializes_jobs_and_low_memory_fallback_stays_off_ui(self):
        pool = QueuePool()
        service = ComputeWork(resources(total=8192, available=3400), executor_factory=lambda **kw: pool)
        self.addCleanup(service.close)
        first = threading.Thread(target=lambda: service.compute("large", str, "large", memory_mb=2300))
        first.start()
        await_condition(lambda: len(pool.calls) == 1)
        result = []
        second = threading.Thread(target=lambda: result.append(service.compute("second", str, "ok", memory_mb=1024)))
        second.start()
        await_condition(lambda: service.snapshot()["computeQueued"] == 1)
        self.assertEqual(len(pool.calls), 1)
        pool.finish(0)
        await_condition(lambda: len(pool.calls) == 2)
        pool.finish(1)
        first.join(2)
        second.join(2)
        self.assertEqual(result, ["ok"])
        low = ComputeWork(resources(cores=2, total=4096, available=600))
        self.addCleanup(low.close)
        thread_id = []
        thread = threading.Thread(target=lambda: low.compute("fallback", str, "unused", memory_mb=1024,
            fallback=lambda: thread_id.append(threading.get_ident())))
        thread.start()
        thread.join(2)
        self.assertNotEqual(thread_id, [threading.get_ident()])
        self.assertEqual(low.snapshot()["computeFallbacks"], 1)
        self.assertIsNone(low._pool)

    def test_failed_spawn_falls_back_and_next_task_can_recover(self):
        def broken(**kwargs):
            raise OSError("spawn unavailable")
        service = ComputeWork(resources(), executor_factory=broken)
        self.addCleanup(service.close)
        self.assertEqual(service.compute("recover", str, "x", fallback=lambda: "retained"), "retained")
        self.assertEqual(service.snapshot()["computeFallbacks"], 1)
        pool = QueuePool()
        service._factory = lambda **kw: pool
        done = []
        thread = threading.Thread(target=lambda: done.append(service.compute("recovered", str, "yes")))
        thread.start()
        await_condition(lambda: len(pool.calls) == 1)
        pool.finish(0)
        thread.join(2)
        self.assertEqual(done, ["yes"])

    def test_late_failure_of_old_pool_does_not_terminate_replacement_pool(self):
        old, fresh = QueuePool(), QueuePool()
        pools = iter((old, fresh))
        service = ComputeWork(resources(), executor_factory=lambda **kw: next(pools))
        self.addCleanup(service.close)
        fallback_entered, finish_fallback = threading.Event(), threading.Event()
        self.addCleanup(finish_fallback.set)
        done = []
        def fallback():
            fallback_entered.set()
            finish_fallback.wait(2)
            return "fallback"
        first = threading.Thread(target=lambda: done.append(service.compute("old-first", str, "x", fallback=fallback)))
        second = threading.Thread(target=lambda: done.append(service.compute("old-second", str, "y", fallback=lambda: "second")))
        first.start()
        second.start()
        await_condition(lambda: len(old.calls) == 2)
        old.calls[0][3].set_exception(BrokenProcessPool("old failed"))
        self.assertTrue(fallback_entered.wait(2))
        finish_fallback.set()
        first.join(2)
        third = threading.Thread(target=lambda: done.append(service.compute("fresh", str, "fresh")))
        third.start()
        await_condition(lambda: len(fresh.calls) == 1)
        old.calls[1][3].set_exception(BrokenProcessPool("old also failed"))
        second.join(2)
        self.assertFalse(fresh.closed)
        self.assertIs(service._pool, fresh)
        fresh.finish(0)
        third.join(2)
        self.assertCountEqual(done, ["fallback", "second", "fresh"])

    def test_task_error_is_not_silently_retried(self):
        pool = QueuePool()
        service = ComputeWork(resources(), executor_factory=lambda **kw: pool)
        self.addCleanup(service.close)
        errors = []
        def run():
            try:
                service.compute("invalid", str, "x", fallback=lambda: self.fail("Unexpected retry"))
            except ValueError as exc:
                errors.append(str(exc))
        thread = threading.Thread(target=run)
        thread.start()
        await_condition(lambda: len(pool.calls) == 1)
        pool.calls[0][3].set_exception(ValueError("invalid evidence"))
        thread.join(2)
        self.assertEqual(errors, ["invalid evidence"])
        self.assertEqual(service.snapshot()["computeFallbacks"], 0)
        self.assertIs(service._pool, pool)

    def test_close_wakes_queued_job_and_idle_pool_is_released(self):
        pool = QueuePool()
        service = ComputeWork(resources(cores=2), executor_factory=lambda **kw: pool, idle_seconds=0)
        errors = []
        def run(name):
            try:
                service.compute(name, str, name)
            except ComputeStopped:
                errors.append(name)
        first = threading.Thread(target=run, args=("first",))
        first.start()
        await_condition(lambda: len(pool.calls) == 1)
        second = threading.Thread(target=run, args=("queued",))
        second.start()
        await_condition(lambda: service.snapshot()["computeQueued"] == 1)
        service.close()
        pool.finish(0)
        first.join(2)
        second.join(2)
        self.assertIn("queued", errors)
        self.assertTrue(pool.closed)
        with self.assertRaises(ComputeStopped):
            service.compute("late", str, "late")
        idle = ComputeWork(resources(), executor_factory=lambda **kw: pool, idle_seconds=0)
        idle._pool = pool
        idle.trim_idle()
        self.assertIsNone(idle._pool)
        idle.close()

    def test_real_spawn_preserves_journal_commander_and_powerplay_results(self):
        service = ComputeWork(resources())
        self.addCleanup(service.close)
        events = [{"event": "LoadGame", "timestamp": "2026-10-10T00:00:00Z", "Credits": 1000},
                  {"event": "Location", "StarSystem": "Origin", "StarPos": [0, 0, 0]},
                  {"event": "Powerplay", "Power": "Aisling Duval", "Rank": 5}]
        rows = [{"system": "Origin", "power": "Aisling Duval", "observedAt": "2026-10-10T00:00:00Z"}]
        overview = {"credits": {"known": True, "value": 1000, "timestamp": "2026-10-10T00:00:00Z"}}
        jobs = [("journal", journal_projection, (events,)),
                ("commander", commander_projection, (overview, events, [])),
                ("powerplay", powerplay_merge, ([], rows, 20000))]
        for name, function, args in jobs:
            self.assertEqual(service.compute(name, function, *args), function(*args))
        for job in service.snapshot()["computeJobs"]:
            self.assertNotEqual(job["lastPid"], os.getpid())

    def test_large_state_projection_matches_original_and_remains_profile_scoped(self):
        from ed_companion.phase14.state import build_state, clear_journal_event_cache
        service = ComputeWork(resources())
        self.addCleanup(service.close)
        self.addCleanup(clear_journal_event_cache)
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 10, 10, 12, tzinfo=timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        with TemporaryDirectory() as folder:
            root = Path(folder)
            journal = root / "journal"
            journal.mkdir()
            events = [{"event": "LoadGame", "FID": "F-SYNTHETIC-ALPHA", "Commander": "Fixture Alpha",
                       "timestamp": "2026-10-10T00:00:00Z", "Ship": "Adder", "ShipID": 1, "Credits": 1000},
                      {"event": "Location", "StarSystem": "Fixture", "StarPos": [0, 0, 0]},
                      {"event": "Powerplay", "Power": "Aisling Duval", "Rank": 5}]
            events += [{"event": "Music", "MusicTrack": "Supercruise", "timestamp": "2026-10-10T00:01:00Z"}] * 20000
            events += [{"event": "LoadGame", "FID": "F-SYNTHETIC-BRAVO", "Commander": "Fixture Bravo",
                        "timestamp": "2026-10-10T00:02:00Z", "Ship": "CobraMkIII", "ShipID": 2, "Credits": 2000}]
            (journal / "Journal.2026-10-10T000000.01.log").write_text(
                "\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
            with patch.dict(os.environ, {"LOCALAPPDATA": str(root), "ED_FRAME_JOURNAL_DIR": str(journal),
                                        "ED_FRAME_PROFILE_FID": "F-SYNTHETIC-ALPHA"}), \
                 patch("ed_companion.phase14.state_logbook.datetime", Clock):
                clear_journal_event_cache()
                baseline = build_state(Path(__file__).resolve().parents[1])
                actual = build_state(Path(__file__).resolve().parents[1], compute=service)
                self.assertEqual(actual, baseline)
                cached = build_state(Path(__file__).resolve().parents[1], compute=service)
                self.assertEqual(cached, actual)
                self.assertEqual(service.snapshot()["computeJobs"][0]["runs"], 1)
                small = ComputeWork(resources(cores=2, total=4096, available=2500))
                self.addCleanup(small.close)
                self.assertEqual(build_state(Path(__file__).resolve().parents[1], compute=small), baseline)
                self.assertEqual(small.snapshot()["computeJobs"], [])
                os.environ["ED_FRAME_PROFILE_FID"] = "F-SYNTHETIC-BRAVO"
                bravo = build_state(Path(__file__).resolve().parents[1], compute=service)
                self.assertNotEqual(bravo["commanderOverview"], actual["commanderOverview"])


class ResourceSamplingTests(unittest.TestCase):
    def test_cached_resource_snapshot_and_cpu_pressure_limit(self):
        ticks = iter(((100, 1000), (110, 2000), (1000, 3000)))
        machine = WorkResources(cores=28, reader=lambda: (32768, 20000), cpu_reader=lambda: next(ticks))
        with patch("ed_companion.work_resources.time.monotonic", side_effect=(0, .1, 2, 4)):
            self.assertEqual(machine.sample()["cpuWorkerLimit"], 2)
            self.assertEqual(machine.sample()["cpuBusyPercent"], None)
            busy = machine.sample()
            self.assertEqual(busy["cpuBusyPercent"], 99)
            self.assertEqual(busy["cpuWorkerLimit"], 1)
            idle = machine.sample()
            self.assertEqual(idle["cpuWorkerLimit"], 2)
        self.assertEqual(machine.snapshot(), idle)

    def test_failed_resource_read_uses_conservative_limit(self):
        def unavailable():
            raise OSError("measurement unavailable")
        machine = WorkResources(cores=28, reader=unavailable, cpu_reader=unavailable)
        self.assertEqual(machine.sample()["cpuWorkerLimit"], 1)
        self.assertIsNone(machine.snapshot()["availableMemoryMiB"])


if __name__ == "__main__":
    unittest.main()
