"""Qt-facing getters must not wait for Journal parsing or history writes."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sqlite3
import threading
import time
import unittest
from unittest.mock import Mock, patch

from ed_companion.navigation.hge_batch import prepare_hge_batch
from ed_companion.phase14.commander_projection import prepare_commander_projection, FINANCE_PERIODS
from ed_companion.phase14.controller import CockpitController
from ed_companion.phase14.dashboard_views import (
    build_commander_cards, build_finance_history, build_finance_summary, filter_finance_history,
)
from ed_companion.phase14.state import ProfileContext, read_journal_tail_records

CMDR = "ed_companion.phase14.controller_commander."
JOURNAL = "ed_companion.phase14.controller_journal_health."


def controller():
    c = CockpitController.__new__(CockpitController)
    c._network_threads_lock = threading.Lock()
    c._start_network_worker = Mock(return_value=True)
    c._profile_generation = 3
    c.profile_context = ProfileContext("test-fid", "alpha", Path("profile-alpha"), "journal")
    c._state_revision = 2
    c._state = {"commanderOverview": {"credits": {"known": True, "value": 2000,
                "timestamp": "2026-10-08T09:00:00Z"}}}
    c._derived_cache = {}
    c._journal_state_ready = True
    c._commander_credit_snapshots = []
    c._commander_finance_period = "all"
    c._shutdown_complete = False
    c._journal_auto = True
    c._renderer_active = "software"
    c.timer = Mock()
    c.timer.isActive.return_value = True
    for name in ("commanderProjectionReady", "commanderCardsChanged", "journalLocationReady",
                 "journalHealthReady", "journalHealthChanged", "connectionChanged",
                 "hgeObservationBatchFinished", "hgeChanged", "stateChanged"):
        setattr(c, name, Mock())
    return c


def run_worker(test, c, signal_name):
    target = c._start_network_worker.call_args.args[0]
    errors = []
    def run():
        try:
            target()
        except BaseException as exc:
            errors.append(exc)
    worker = threading.Thread(target=run)
    worker.start()
    worker.join(3)
    test.assertFalse(worker.is_alive())
    test.assertEqual(errors, [])
    return getattr(c, signal_name).emit.call_args.args[0], worker.ident


def signal(system="Test", **changes):
    return {"system": system, "signal_timestamp": datetime.now(timezone.utc).isoformat(),
            "evidence_kind": "LOCAL_JOURNAL", "time_remaining": 3600, **changes}


class CommanderProjectionResponsivenessTests(unittest.TestCase):
    def test_all_periods_and_cards_match_original_calculations_exactly(self):
        events = [
            {"event": "LoadGame", "timestamp": "2026-10-06T08:00:00Z", "Credits": 500},
            {"event": "Statistics", "timestamp": "2026-10-07T08:00:00Z",
             "Bank_Account": {"Current_Wealth": 50000}},
            {"event": "LoadGame", "timestamp": "2026-10-08T08:00:00Z", "Credits": 1000,
             "Ship": "adder", "ShipName": "Test"},
            {"event": "Docked", "StarSystem": "Test", "StationName": "Port"},
        ]
        c = controller()
        overview = c._state["commanderOverview"]
        snapshots = [{"timestamp": "2026-10-08T08:30:00Z", "credits": 1500}]
        prepared = prepare_commander_projection(overview, events, snapshots)
        self.assertEqual(prepared["cards"], build_commander_cards(overview, events))
        original = build_finance_history(events, current_credits=overview["credits"], credit_snapshots=snapshots)
        for period in FINANCE_PERIODS:
            with self.subTest(period=period):
                rows = filter_finance_history(original, period, events)
                self.assertEqual(prepared["histories"][period], rows)
                self.assertEqual(prepared["summaries"][period], build_finance_summary(rows))

    def test_getters_coalesce_and_never_touch_journal_on_calling_thread(self):
        c = controller()
        threads = []
        with patch(CMDR + "profiled_journal_events", side_effect=lambda: threads.append(threading.get_ident()) or []):
            c._commander_cards()
            self.assertEqual(c._commander_finance_history(), [])
            self.assertFalse(c._commander_finance_summary()["known"])
            self.assertEqual(threads, [])
            self.assertEqual(c._start_network_worker.call_count, 1)
            result, worker_id = run_worker(self, c, "commanderProjectionReady")
        self.assertEqual(threads, [worker_id])
        c._finish_commander_projection(result)
        self.assertEqual(c._commander_finance_history(), result["histories"]["all"])
        for period in FINANCE_PERIODS:
            c._commander_finance_period = period
            self.assertEqual(c._commander_finance_history(), result["histories"][period])
            self.assertEqual(c._commander_finance_summary(), result["summaries"][period])
        self.assertEqual(c._start_network_worker.call_count, 1)

    def test_state_changed_during_worker_requests_one_fresh_projection(self):
        c = controller()
        c._commander_ui_snapshot()
        with patch(CMDR + "profiled_journal_events", return_value=[]):
            result, _ = run_worker(self, c, "commanderProjectionReady")
        c._state_revision += 1
        c._finish_commander_projection(result)
        self.assertEqual(c._start_network_worker.call_count, 2)
        self.assertEqual(c._commander_ui_snapshot(), {})
        self.assertEqual(c._start_network_worker.call_count, 2)

    def test_profile_change_never_exposes_other_commanders_cached_cards(self):
        c = controller()
        c._commander_projection = {"key": c._commander_projection_key(), "cards": {"secret": True}}
        self.assertIn("cards", c._commander_ui_snapshot())
        c._profile_generation += 1
        self.assertEqual(c._commander_ui_snapshot(), {})

    def test_worker_error_does_not_start_a_binding_retry_loop(self):
        c = controller()
        c._commander_ui_snapshot()
        with self.assertLogs("ed_companion.phase14.controller_commander", level="ERROR"), patch(
                CMDR + "profiled_journal_events", side_effect=OSError("test")):
            result, _ = run_worker(self, c, "commanderProjectionReady")
        c._finish_commander_projection(result)
        for _ in range(5):
            c._commander_cards()
        self.assertEqual(c._start_network_worker.call_count, 1)
        c._state_revision += 1
        c._commander_cards()
        self.assertEqual(c._start_network_worker.call_count, 2)

    def test_startup_does_not_parse_journal_before_state_is_ready(self):
        c = controller()
        c._journal_state_ready = False
        c._commander_cards()
        with patch(CMDR + "profiled_journal_events") as read:
            result, _ = run_worker(self, c, "commanderProjectionReady")
        read.assert_not_called()
        c._finish_commander_projection(result)
        self.assertTrue(c._commander_finance_summary()["known"])

    def test_rejected_dispatch_preserves_last_complete_same_profile_snapshot(self):
        c = controller()
        c._commander_projection = {"key": c._commander_projection_key(), "cards": {"test": True}}
        c._state_revision += 1
        c._start_network_worker.return_value = False
        self.assertEqual(c._commander_cards(), {"test": True})
        self.assertIsNone(c._active_commander_projection)
        c._commander_cards()
        self.assertEqual(c._start_network_worker.call_count, 1)


class LiveSignalResponsivenessTests(unittest.TestCase):
    def controller(self):
        c = controller()
        c._hge_sightings = [signal("Old")]
        c.hge_cache_file = Path("hge.json")
        c._history_archive = Mock()
        c._archive_history = Mock(return_value=True)
        c._save_hge_cache = Mock()
        c._selected_material = {}
        c._pending_bgs_snapshots = []
        c._pending_hge_observations = []
        c._pending_mining_candidates = []
        c._next_hge_expiry_epoch = time.time() + 3000
        return c

    def prepare(self, existing, additions=(), snapshots=(), archive=None, limit=10000):
        return prepare_hge_batch(existing, list(snapshots), list(additions), limit=limit,
                                 archive=archive or Mock(),
                                 displaced_rows=CockpitController._hge_displaced_history_rows,
                                 next_expiry=CockpitController._hge_next_expiry_epoch)

    def test_worker_owns_archive_and_gui_completion_only_publishes(self):
        c = self.controller()
        thread_ids = []
        c._history_archive.archive.side_effect = lambda *_args: thread_ids.append(threading.get_ident())
        before = c._hge_sightings
        c._dispatch_hge_observation_batch([], [signal("New")])
        self.assertIs(c._hge_sightings, before)
        c._history_archive.archive.assert_not_called()
        result, worker_id = run_worker(self, c, "hgeObservationBatchFinished")
        self.assertEqual(set(thread_ids), {worker_id})
        c._history_archive.reset_mock()
        c._finish_hge_observation_batch(result)
        self.assertEqual([row["system"] for row in c._hge_sightings], ["Old", "New"])
        c._history_archive.archive.assert_not_called()
        c._archive_history.assert_not_called()
        c._save_hge_cache.assert_called_once_with(already_partitioned=True)

    def test_retention_and_overflow_are_archived_before_removal(self):
        expired = signal("Expired", signal_timestamp=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat())
        rows = [expired, signal("A"), signal("B")]
        archive = Mock()
        result = self.prepare(rows, archive=archive, limit=1)
        self.assertEqual(result["sightings"], rows[-1:])
        self.assertEqual(result["stats"]["expiredRemoved"], 2)
        archive.archive.assert_called_once_with("hge_observations", rows[:2])
        self.assertEqual(len(rows), 3)

    def test_failed_retirement_keeps_all_rows(self):
        rows = [signal("A"), signal("B")]
        archive = Mock()
        archive.archive.side_effect = sqlite3.OperationalError("locked")
        result = self.prepare(rows, archive=archive, limit=1)
        self.assertEqual(result["sightings"], rows)
        self.assertEqual(result["stats"]["expiredRemoved"], 0)
        self.assertEqual(result["archiveError"], "OperationalError")

    def test_failed_input_archive_requeues_without_publishing(self):
        c = self.controller()
        added = signal("New")
        c._history_archive.archive.side_effect = sqlite3.OperationalError("locked")
        c._dispatch_hge_observation_batch([], [added])
        result, _ = run_worker(self, c, "hgeObservationBatchFinished")
        c._finish_hge_observation_batch(result)
        self.assertEqual(c._pending_hge_observations, [added])
        c._save_hge_cache.assert_not_called()

    def test_server_completion_rebases_local_inputs_instead_of_overwriting(self):
        c = self.controller()
        c._dispatch_hge_observation_batch([], [signal("Journal")])
        result, _ = run_worker(self, c, "hgeObservationBatchFinished")
        c._hge_sightings = [*c._hge_sightings, signal("Server")]
        c._finish_hge_observation_batch(result)
        result, _ = run_worker(self, c, "hgeObservationBatchFinished")
        c._finish_hge_observation_batch(result)
        self.assertEqual([r["system"] for r in c._hge_sightings], ["Old", "Server", "Journal"])

    def test_new_inputs_coalesce_while_busy_and_then_publish_without_loss(self):
        c = self.controller()
        c._dispatch_hge_observation_batch([], [signal("B")])
        c._dispatch_hge_observation_batch([], [signal("C")])
        self.assertEqual(c._start_network_worker.call_count, 1)
        result, _ = run_worker(self, c, "hgeObservationBatchFinished")
        c._finish_hge_observation_batch(result)
        self.assertEqual(c._start_network_worker.call_count, 2)
        result, _ = run_worker(self, c, "hgeObservationBatchFinished")
        c._finish_hge_observation_batch(result)
        self.assertEqual([r["system"] for r in c._hge_sightings], ["Old", "B", "C"])

    def test_profile_generation_key_and_path_fences_keep_old_inputs_in_original_archive(self):
        for change in ("generation", "key", "path"):
            c = self.controller()
            added = signal("New")
            c._dispatch_hge_observation_batch([], [added])
            result, _ = run_worker(self, c, "hgeObservationBatchFinished")
            if change == "generation":
                c._profile_generation += 1
            elif change == "key":
                c.profile_context = Mock(key="beta")
            else:
                c.hge_cache_file = Path("other.json")
            before = c._hge_sightings
            c._finish_hge_observation_batch(result)
            self.assertIs(c._hge_sightings, before)
            c._history_archive.archive.assert_any_call("hge_observations", [added])
            c._save_hge_cache.assert_not_called()

    def test_late_old_completion_cannot_clear_new_worker(self):
        c = self.controller()
        c._dispatch_hge_observation_batch([], [signal("Old Profile")])
        old, _ = run_worker(self, c, "hgeObservationBatchFinished")
        c._profile_generation += 1
        c._dispatch_hge_observation_batch([], [signal("New Profile")])
        active = c._active_hge_observation_batch
        c._finish_hge_observation_batch(old)
        self.assertIs(c._active_hge_observation_batch, active)

    def test_rejected_dispatch_retains_inputs(self):
        c = self.controller()
        c._start_network_worker.return_value = False
        added = signal("New")
        c._dispatch_hge_observation_batch([], [added])
        self.assertEqual(c._pending_hge_observations, [added])
        self.assertIsNone(c._active_hge_observation_batch)

    def test_shutdown_reclaims_unpublished_batch_and_ignores_late_completion(self):
        c = self.controller()
        c._dispatch_hge_observation_batch([], [signal("B")])
        result, _ = run_worker(self, c, "hgeObservationBatchFinished")
        c._pending_hge_observations = [signal("C")]
        c._shutdown_complete = True
        c.flushHgeObservationBatch(True)
        before = c._hge_sightings
        self.assertEqual([r["system"] for r in before], ["Old", "B", "C"])
        c._finish_hge_observation_batch(result)
        self.assertIs(c._hge_sightings, before)

    def test_manual_refresh_counts_are_published_after_worker_completion(self):
        c = self.controller()
        c._state_find_refresh_batch_pending = True
        c._state_find_refresh_batch_totals = {}
        c._dispatch_hge_observation_batch([], [signal("B")])
        c._dispatch_hge_observation_batch([], [signal("C")])
        result, _ = run_worker(self, c, "hgeObservationBatchFinished")
        c._finish_hge_observation_batch(result)
        self.assertTrue(c._state_find_refresh_batch_pending)
        result, _ = run_worker(self, c, "hgeObservationBatchFinished")
        c._finish_hge_observation_batch(result)
        self.assertFalse(c._state_find_refresh_batch_pending)
        self.assertEqual(c._last_state_find_refresh_stats["signalsMerged"], 2)

    def test_profile_handover_waits_nonblocking_for_original_profile_pending_work(self):
        for pending in ("_active_hge_observation_batch", "_active_mining_observation_batch",
                        "_pending_bgs_snapshots", "_pending_hge_observations",
                        "_pending_mining_candidates", "_pending_mining_powerplay_observations"):
            with self.subTest(pending=pending):
                c = self.controller()
                c._eddn_busy = False
                c.flushHgeObservationBatch = Mock()
                setattr(c, pending, [signal("Uncommitted")])
                original = c.profile_context
                other = ProfileContext("other", "beta", Path("profile-beta"), "journal")
                self.assertFalse(c._switch_profile_context(other))
                self.assertIs(c.profile_context, original)
                c.flushHgeObservationBatch.assert_called_once_with(True)


class JournalWorkerResponsivenessTests(unittest.TestCase):
    def test_location_getter_uses_only_metadata_and_worker_resolves_full_profile(self):
        c = controller()
        c._poll_exobiology_distance_check = Mock()
        c._scan_eddn_journal = Mock()
        location = {"system": "New", "currentPosition": [1, 2, 3], "currentSystemAddress": 42}
        with patch(JOURNAL + "journal_change_signature", return_value=("journal", ())), patch(
                JOURNAL + "resolve_profile_context", return_value=c.profile_context) as resolve, patch(
                JOURNAL + "latest_profile_location", return_value=location) as read, patch(
                JOURNAL + "journal_paths_for_profile", return_value=[Path("journal/Journal.01.log")]) as paths:
            self.assertEqual(c._live_profile_location(), {})
            c._live_profile_location()
            resolve.assert_not_called(); read.assert_not_called(); paths.assert_not_called()
            self.assertEqual(c._start_network_worker.call_count, 1)
            result, _ = run_worker(self, c, "journalLocationReady")
            c._finish_journal_location(result)
            self.assertEqual(c._live_profile_location(), location)
            self.assertEqual(c._state["system"], "New")
            self.assertEqual(c._state_revision, 3)
            self.assertEqual(c._start_network_worker.call_count, 1)

    def test_new_stamp_returns_unknown_not_stale_system_and_rejects_delayed_result(self):
        c = controller()
        c._poll_exobiology_distance_check = Mock()
        c._scan_eddn_journal = Mock()
        stamp = [1]
        with patch(JOURNAL + "journal_change_signature", side_effect=lambda: tuple(stamp)), patch(
                JOURNAL + "resolve_profile_context", return_value=c.profile_context), patch(
                JOURNAL + "latest_profile_location", return_value={"currentSystemAddress": 42}), patch(
                JOURNAL + "journal_paths_for_profile", return_value=[]):
            c._live_profile_location()
            result, _ = run_worker(self, c, "journalLocationReady")
            stamp[0] = 2
            c._finish_journal_location(result)
            self.assertEqual(c._live_profile_location(), {})
            self.assertEqual(c._start_network_worker.call_count, 2)
            c._poll_exobiology_distance_check.assert_not_called()

    def test_changed_profile_requests_coherent_state_refresh_not_foreign_location(self):
        c = controller()
        c.refresh = Mock()
        c._poll_exobiology_distance_check = Mock()
        c._scan_eddn_journal = Mock()
        other = ProfileContext("other", "beta", Path("profile-beta"), "journal")
        with patch(JOURNAL + "journal_change_signature", return_value=(1,)), patch(
                JOURNAL + "resolve_profile_context", return_value=other), patch(
                JOURNAL + "latest_profile_location", return_value={"system": "Foreign"}), patch(
                JOURNAL + "journal_paths_for_profile", return_value=[]):
            c._live_profile_location()
            result, _ = run_worker(self, c, "journalLocationReady")
            c._finish_journal_location(result)
            c.refresh.assert_called_once()
            self.assertEqual(c._live_profile_location(), {})
            self.assertNotIn("system", c._state)

    def test_error_clears_active_location_and_suppresses_identical_retry_loop(self):
        c = controller()
        with patch(JOURNAL + "journal_change_signature", return_value=(1,)), patch(
                JOURNAL + "resolve_profile_context", side_effect=OSError("test")), self.assertLogs(
                "ed_companion.phase14.controller_journal_health", level="ERROR"):
            c._live_profile_location()
            result, _ = run_worker(self, c, "journalLocationReady")
            c._finish_journal_location(result)
            c._live_profile_location()
            self.assertIsNone(c._active_journal_location)
            self.assertEqual(c._start_network_worker.call_count, 1)

    def test_health_getter_dispatches_io_once_then_returns_cached_age(self):
        c = controller()
        with TemporaryDirectory() as directory, patch(JOURNAL + "journal_dir", return_value=Path(directory)):
            path = Path(directory) / "Journal.01.log"
            path.write_text(json.dumps({"event": "FSDJump"}) + "\n", encoding="utf-8")
            original = c._read_journal_health
            ids = []
            c._read_journal_health = lambda *args: ids.append(threading.get_ident()) or original(*args)
            self.assertEqual(c._journal_health()["status"], "CHECKING")
            c._journal_health()
            self.assertEqual(ids, [])
            result, worker_id = run_worker(self, c, "journalHealthReady")
            c._finish_journal_health(result)
            self.assertEqual(c._journal_health()["status"], "LIVE")
            self.assertEqual(ids, [worker_id])
            self.assertEqual(c._start_network_worker.call_count, 1)
            c._journal_health_cache["data"]["_modifiedAt"] = time.time() - 30
            self.assertEqual(c._journal_health()["status"], "READY")
            self.assertNotIn("_modifiedAt", c._journal_health())

    def test_health_io_failure_completes_and_allows_later_poll(self):
        c = controller()
        c._read_journal_health = Mock(side_effect=OSError("test"))
        with patch(JOURNAL + "journal_dir", return_value=Path("journal")), self.assertLogs(
                "ed_companion.phase14.controller_journal_health", level="ERROR"):
            c._journal_health()
            result, _ = run_worker(self, c, "journalHealthReady")
            c._finish_journal_health(result)
            self.assertIsNone(c._active_journal_health)
            self.assertEqual(c._journal_health()["status"], "ERROR")
            c._journal_health_requested_at -= 2
            c._journal_health()
            self.assertEqual(c._start_network_worker.call_count, 2)

    def test_stale_health_completion_does_not_publish_after_root_or_profile_change(self):
        for change in ("root", "profile"):
            c = controller()
            c._read_journal_health = Mock(return_value={"parserOk": False})
            root = [Path("journal")]
            with patch(JOURNAL + "journal_dir", side_effect=lambda: root[0]):
                c._journal_health()
                result, _ = run_worker(self, c, "journalHealthReady")
                if change == "root":
                    root[0] = Path("other")
                else:
                    c._profile_generation += 1
                c._finish_journal_health(result)
                c.journalHealthChanged.emit.assert_not_called()

    def test_tail_read_budget_never_commits_partial_or_unread_lines(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "Journal.01.log"
            path.write_text('bad-json\n' + json.dumps({"event": "One"}) + '\n{"event":', encoding="utf-8")
            offset, first = read_journal_tail_records(path, 0, limit=1)
            self.assertEqual(len(first), 1)
            self.assertIsNone(first[0][2])
            next_offset, second = read_journal_tail_records(path, offset, limit=1)
            self.assertEqual(second[0][2]["event"], "One")
            final_offset, partial = read_journal_tail_records(path, next_offset, limit=1)
            self.assertEqual(partial, [])
            self.assertEqual(final_offset, next_offset)
            self.assertLess(final_offset, path.stat().st_size)


if __name__ == "__main__":
    unittest.main()
