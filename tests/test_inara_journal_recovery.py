import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from ed_companion.integrations.inara import _minor_reputation_data
from ed_companion.phase14.controller import CockpitController
from ed_companion.phase14.state import ProfileContext


class _Signal:
    def __init__(self, callback=None):
        self.callback = callback

    def emit(self, *_args):
        if self.callback:
            self.callback(*_args)


class InaraJournalRecoveryTests(unittest.TestCase):
    def test_minor_reputation_omits_only_neutral_factions(self):
        rows = _minor_reputation_data({
            "Factions": [
                {"Name": "Neutral", "MyReputation": 0.0},
                {"Name": "Near neutral positive", "MyReputation": 3.6},
                {"Name": "Near neutral negative", "MyReputation": -0.335},
                {"Name": "Positive boundary", "MyReputation": 4.0},
                {"Name": "Negative boundary", "MyReputation": -4.0},
                {"Name": "Friendly", "MyReputation": 91.846703},
            ],
        })

        self.assertEqual(
            [row["minorfactionName"] for row in rows],
            ["Positive boundary", "Negative boundary", "Friendly"],
        )
        self.assertAlmostEqual(rows[0]["minorfactionReputation"], 0.04)
        self.assertAlmostEqual(rows[1]["minorfactionReputation"], -0.04)
        self.assertAlmostEqual(rows[2]["minorfactionReputation"], 0.91846703)

    def _journals(self, root, count=7):
        paths = []
        newest = datetime.now(timezone.utc).replace(
            hour=10, minute=0, second=0, microsecond=0,
        )

        def timestamp(start, seconds):
            return (
                start + timedelta(seconds=seconds)
            ).isoformat(timespec="seconds").replace("+00:00", "Z")

        for index in range(count):
            path = root / f"Journal.{index + 1:02d}.log"
            session_start = newest - timedelta(days=count - index - 1)
            events = [
                {
                    "timestamp": timestamp(session_start, 0),
                    "event": "Fileheader", "gameversion": "4.2.0.0",
                    "build": "r0",
                },
                {
                    "timestamp": timestamp(session_start, 1),
                    "event": "LoadGame", "Commander": "Recovery Test",
                    "FID": "F-RECOVERY", "Horizons": True, "Odyssey": True,
                },
                {
                    "timestamp": timestamp(session_start, 2),
                    "event": "FSDJump", "StarSystem": f"Recovery {index}",
                    "StarPos": [float(index), 2.0, 3.0],
                    "SystemAddress": 1000 + index,
                },
            ]
            path.write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )
            paths.append(path)
        return paths

    def _controller(self, root, cache=None):
        profile = root / "profile-recovery"
        profile.mkdir(exist_ok=True)
        controller = CockpitController.__new__(CockpitController)
        controller.profile_context = ProfileContext(
            "F-RECOVERY", "recovery", profile, str(root)
        )
        controller._inara_cache = cache or {
            "initialized": True,
            "journal_root": str(root),
            "fingerprints": [],
        }
        controller._inara_config = {
            "consent": True, "auto_sync": True,
            "api_key": "test-key", "commander_name": "Recovery Test",
        }
        controller._inara_pending_events = []
        controller._inara_pending_fingerprints = []
        controller._inara_inflight_fingerprints = []
        controller._inara_recovery_candidate_file = ""
        controller._inara_pending_since = 0.0
        controller._inara_failure_count = 0
        controller._inara_scan_token = 0
        controller._inara_scan_in_flight = False
        controller._inara_scan_dirty = False
        controller._inara_scan_requested_signature = None
        controller._inara_scan_completed_signature = None
        controller._sync_eddn_profile = lambda: True
        controller._save_inara_config = mock.Mock()
        controller._save_inara_journal_cache = mock.Mock()
        controller.connectionChanged = _Signal()
        return controller

    def test_restart_recovers_pending_events_from_more_than_five_journals(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._journals(root, 7)
            controller = self._controller(root)

            with mock.patch(
                "ed_companion.phase14.controller_inara.journal_paths_for_profile",
                return_value=paths,
            ):
                self.assertTrue(controller._scan_inara_journal())

            recovered_systems = {
                event.get("eventData", {}).get("starsystemName")
                for event in controller._inara_pending_events
                if event.get("eventName") == "addCommanderTravelFSDJump"
            }
            self.assertEqual(
                recovered_systems,
                {f"Recovery {index}" for index in range(7)},
            )

    def test_confirmed_boundary_reads_only_boundary_and_newer_journals(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._journals(root, 7)
            controller = self._controller(root, {
                "initialized": True,
                "journal_root": str(root),
                "fingerprints": [],
                "journal_recovery_file": paths[5].name,
            })

            with mock.patch(
                "ed_companion.phase14.controller_inara.journal_paths_for_profile",
                return_value=paths,
            ):
                self.assertTrue(controller._scan_inara_journal())

            recovered_systems = {
                event.get("eventData", {}).get("starsystemName")
                for event in controller._inara_pending_events
                if event.get("eventName") == "addCommanderTravelFSDJump"
            }
            self.assertEqual(recovered_systems, {"Recovery 5", "Recovery 6"})

    def test_periodic_scan_prepares_cached_history_in_worker(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._journals(root, 2)
            controller = self._controller(root)
            controller._journal_state_ready = True
            controller._profile_generation = 1
            controller._inara_scan_token = 0
            controller._inara_scan_in_flight = False
            controller._inara_scan_dirty = False
            controller.inaraJournalScanReady = _Signal(
                controller._finish_inara_journal_scan
            )
            controller._start_network_worker = (
                lambda target, _name: (target(), True)[1]
            )
            events = []
            for path in paths:
                events.extend(
                    json.loads(line)
                    for line in path.read_text(encoding="utf-8").splitlines()
                )

            with (
                mock.patch(
                    "ed_companion.phase14.controller_inara.journal_paths_for_profile",
                    return_value=paths,
                ),
                mock.patch(
                    "ed_companion.phase14.controller_inara.profiled_journal_events",
                    return_value=events,
                ),
            ):
                self.assertTrue(controller._queue_inara_journal_scan())

            recovered_systems = {
                event.get("eventData", {}).get("starsystemName")
                for event in controller._inara_pending_events
                if event.get("eventName") == "addCommanderTravelFSDJump"
            }
            self.assertEqual(recovered_systems, {"Recovery 0", "Recovery 1"})
            self.assertFalse(controller._inara_scan_in_flight)

    def test_periodic_scan_reuses_only_cached_recovery_boundary(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._journals(root, 3)
            controller = self._controller(root, {
                "initialized": True,
                "journal_root": str(root),
                "fingerprints": [],
                "journal_recovery_file": paths[2].name,
            })
            controller._journal_state_ready = True
            controller._profile_generation = 1
            controller._inara_scan_token = 0
            controller._inara_scan_in_flight = False
            controller._inara_scan_dirty = False
            controller.inaraJournalScanReady = _Signal(
                controller._finish_inara_journal_scan
            )
            controller._start_network_worker = (
                lambda target, _name: (target(), True)[1]
            )
            latest_events = [
                json.loads(line)
                for line in paths[2].read_text(encoding="utf-8").splitlines()
            ]

            with (
                mock.patch(
                    "ed_companion.phase14.controller_inara.journal_paths_for_profile",
                    return_value=paths,
                ),
                mock.patch(
                    "ed_companion.phase14.controller_inara.profiled_journal_events",
                    return_value=latest_events,
                ) as cached_events,
            ):
                controller._queue_inara_journal_scan()

            cached_events.assert_called_once_with(paths[2].name)
            recovered_systems = {
                event.get("eventData", {}).get("starsystemName")
                for event in controller._inara_pending_events
                if event.get("eventName") == "addCommanderTravelFSDJump"
            }
            self.assertEqual(recovered_systems, {"Recovery 2"})

    def test_periodic_scan_coalesces_duplicate_unchanged_requests(self):
        with TemporaryDirectory() as directory:
            controller = self._controller(Path(directory))
            controller._journal_state_ready = True
            controller._profile_generation = 1
            workers = []
            controller._start_network_worker = (
                lambda target, _name: workers.append(target) or True
            )
            controller.inaraJournalScanReady = _Signal(
                controller._finish_inara_journal_scan
            )
            controller._prepare_inara_journal_scan = mock.Mock(return_value={
                "detected": {}, "prepared": [], "fingerprints": [],
                "hasCommunityGoal": False, "lastPath": "Journal.01.log",
                "recoveryComplete": True,
                "journalRoot": controller.profile_context.journal_root,
            })

            with mock.patch(
                "ed_companion.phase14.controller_inara.journal_change_signature",
                return_value=("journal", (("Journal.01.log", 100, 1),)),
            ):
                self.assertTrue(controller._queue_inara_journal_scan())
                self.assertFalse(controller._queue_inara_journal_scan())
                workers[0]()

            self.assertEqual(len(workers), 1)
            self.assertEqual(
                controller._prepare_inara_journal_scan.call_count, 1
            )
            self.assertFalse(controller._inara_scan_in_flight)

    def test_periodic_scan_runs_again_when_journal_changes_in_flight(self):
        with TemporaryDirectory() as directory:
            controller = self._controller(Path(directory))
            controller._journal_state_ready = True
            controller._profile_generation = 1
            workers = []
            controller._start_network_worker = (
                lambda target, _name: workers.append(target) or True
            )
            controller.inaraJournalScanReady = _Signal(
                controller._finish_inara_journal_scan
            )
            controller._prepare_inara_journal_scan = mock.Mock(return_value={
                "detected": {}, "prepared": [], "fingerprints": [],
                "hasCommunityGoal": False, "lastPath": "Journal.01.log",
                "recoveryComplete": True,
                "journalRoot": controller.profile_context.journal_root,
            })
            signature = [
                "journal", (("Journal.01.log", 100, 1),)
            ]

            with mock.patch(
                "ed_companion.phase14.controller_inara.journal_change_signature",
                side_effect=lambda: tuple(signature),
            ):
                self.assertTrue(controller._queue_inara_journal_scan())
                signature[1] = (("Journal.01.log", 200, 2),)
                self.assertFalse(controller._queue_inara_journal_scan())
                workers[0]()

            self.assertEqual(len(workers), 2)
            self.assertTrue(controller._inara_scan_in_flight)


if __name__ == "__main__":
    unittest.main()
