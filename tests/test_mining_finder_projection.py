import json
import time
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from ed_companion.navigation.mining_finder import (
    fetch_edframe_mining_candidates,
    fetch_spansh_system_dump,
    is_belt_candidate,
    merge_mining_candidate_batch,
    merge_mining_candidates,
    mining_candidate_positions,
    mining_candidate_freshness,
    project_local_mining_evidence,
    project_local_yield_observations,
    project_edframe_mining_candidates,
    project_spansh_mining_candidates,
    project_eddn_mining_candidates,
    send_edframe_yield_observations,
    yield_observation_key,
)
from ed_companion.navigation.mining_market_store import MarketCatalogStore
from ed_companion.phase14.controller import CockpitController, _eddn_relay_relevant


FIXTURE = json.loads(Path(__file__).with_name("fixtures").joinpath(
    "mining_finder_observations.json"
).read_text(encoding="utf-8"))


class MiningFinderProjectionTests(unittest.TestCase):
    def test_yield_sharing_runs_off_thread_and_persists_receipt(self):
        with TemporaryDirectory() as directory:
            controller = CockpitController.__new__(CockpitController)
            controller._edframe_yield_sharing_enabled = True
            controller._edframe_yield_upload_busy = False
            controller._shutdown_complete = False
            controller._profile_generation = 4
            controller.profile_context = Mock(key="alpha")
            controller.edframe_yield_receipts_file = (
                Path(directory) / "yield-receipts.json"
            )
            controller._edframe_yield_uploaded = set()
            controller._edframe_catalog_log = []
            controller.connectionChanged = Mock()
            controller.edFrameYieldUploadFinished = Mock()
            controller._state = {"localMiningEvidence": {
                "candidates": [{
                    "system": "Yield Test", "systemAddress": 7,
                    "coordinates": [1, 2, 3],
                    "ring": "Yield Test 2 A Ring", "bodyId": 11,
                }],
                "prospectorSamples": [{
                    "system": "Yield Test", "systemAddress": 7,
                    "ring": "Yield Test 2 A Ring", "bodyId": 11,
                    "observedAt": "2026-10-03T08:01:00Z",
                    "boundToRing": True,
                    "materials": [{
                        "commodity": "platinum", "proportion": 32.5,
                    }],
                }],
            }}
            workers = []
            controller._start_network_worker = (
                lambda target, _name: workers.append(target) or True
            )

            controller._maybe_share_mining_yields()

            self.assertTrue(controller._edframe_yield_upload_busy)
            self.assertEqual(len(workers), 1)
            with patch(
                "ed_companion.phase14.controller_navigation."
                "send_edframe_yield_observations",
                return_value={"accepted": 1, "rejected": 0},
            ) as send:
                workers[0]()
            sent = send.call_args.args[0]
            self.assertEqual(sent[0]["materials"][0]["commodity"], "platinum")
            result = controller.edFrameYieldUploadFinished.emit.call_args.args[0]
            with patch(
                "ed_companion.phase14.controller_navigation.QTimer.singleShot"
            ):
                controller._finish_edframe_yield_upload(result)
            receipt = json.loads(
                controller.edframe_yield_receipts_file.read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(len(receipt["uploaded"]), 1)
            self.assertIn("Shared 1", controller._edframe_yield_upload_status)

    def test_yield_upload_projection_is_commodity_neutral_and_private(self):
        local = project_local_mining_evidence([{
            "event": "Location", "StarSystem": "Yield Test",
            "SystemAddress": 7, "StarPos": [1, 2, 3],
        }, {
            "event": "SupercruiseExit", "timestamp": "2026-10-03T08:00:00Z",
            "StarSystem": "Yield Test", "SystemAddress": 7,
            "Body": "Yield Test 2 A Ring", "BodyID": 11,
            "BodyType": "PlanetaryRing",
        }, {
            "event": "ProspectedAsteroid", "timestamp": "2026-10-03T08:01:00Z",
            "Materials": [
                {"Name": "Platinum", "Proportion": 32.5},
                {"Name": "Osmium", "Proportion": 11.25},
            ],
            "Commander": "must not upload", "Cargo": ["private"],
        }])
        rows = project_local_yield_observations(local)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            [item["commodity"] for item in rows[0]["materials"]],
            ["osmium", "platinum"],
        )
        serialized = json.dumps(rows)
        self.assertNotIn("must not upload", serialized)
        self.assertNotIn("Cargo", serialized)
        self.assertEqual(
            yield_observation_key(rows[0]), yield_observation_key(rows[0])
        )

    def test_yield_sender_posts_only_one_bounded_public_batch(self):
        response = Mock()
        response.json.return_value = {"accepted": 1, "rejected": 0}
        post = Mock(return_value=response)
        payload = {"system": "Test", "ring": "Test A Ring"}
        result = send_edframe_yield_observations([payload], post)
        self.assertEqual(result["accepted"], 1)
        post.assert_called_once()
        self.assertEqual(
            post.call_args.kwargs["json"], {"observations": [payload]}
        )
        response.raise_for_status.assert_called_once()

    def test_more_resources_reads_all_retained_commodity_markets(self):
        controller = CockpitController.__new__(CockpitController)
        controller._mining_find_page = Mock(return_value=[])
        controller._mining_market_rows_for_query = Mock(return_value=[])
        controller._mining_powerplay_catalog = {}

        with patch(
            "ed_companion.phase14.controller_navigation.plan_mining_routes",
            return_value=[],
        ):
            controller.miningPlanRoutes(
                "Cubeo", "Platinum", 100, "ALL RESERVES", "ANY RING",
                True, "LASER", "BEST YIELD", 0, 0, 24, 30,
                False, False, True, False, "LARGE", "Aisling Duval",
                "REINFORCE", "ANY", "ANY",
            )

        query = controller._mining_market_rows_for_query.call_args.args[0]
        self.assertEqual(query["commodity"], "allcommodities")

    def test_belt_recognition_covers_explicit_and_legacy_names(self):
        self.assertTrue(is_belt_candidate({"miningSiteType": "BELT"}))
        self.assertTrue(is_belt_candidate({
            "ring": "Cubeo A Belt Cluster 2",
        }))
        self.assertTrue(is_belt_candidate({"ring": "Arcadian A Belt"}))
        self.assertFalse(is_belt_candidate({"ring": "Cubeo 4 A Ring"}))

    def test_route_verification_deduplicates_top_thirty_systems(self):
        controller = CockpitController.__new__(CockpitController)
        controller._mining_verification_busy = False
        controller._mining_verification_cache = {}
        controller._profile_generation = 3
        controller.profile_context = Mock(key="alpha")
        controller.mining_catalog_file = Path("mining.json")
        controller._known_mining_origin = Mock(return_value={
            "coordinates": [1, 2, 3],
        })
        workers = []
        controller._start_network_worker = (
            lambda target, _name: workers.append(target) or True
        )
        controller.miningVerificationChanged = Mock()
        controller.miningVerificationProgress = Mock()
        controller.miningVerificationFinished = Mock()
        controller.miningChanged = Mock()
        routes = [{
            "system": f"System {index // 2}",
            "systemAddress": index // 2 + 1,
            "ring": f"Ring {index}",
        } for index in range(40)]

        controller.verifyMiningRoutes(routes, "Origin")

        request = controller._active_mining_verification_request
        self.assertEqual(request["total"], 15)
        self.assertEqual(len(request["targets"]), 15)
        self.assertEqual(len(workers), 1)
        self.assertTrue(controller._mining_verification_busy)
        with patch(
            "ed_companion.phase14.controller_navigation.fetch_spansh_system_dump",
            return_value=FIXTURE["spansh_dump"],
        ) as fetch:
            workers[0]()
        result = controller.miningVerificationFinished.emit.call_args.args[0]
        self.assertEqual(fetch.call_count, 15)
        self.assertEqual(len(result["succeeded"]), 15)
        self.assertEqual(result["failed"], [])
        self.assertEqual(
            controller.miningVerificationProgress.emit.call_count, 15
        )

    def test_recent_spansh_route_is_not_fetched_again(self):
        controller = CockpitController.__new__(CockpitController)
        controller._mining_verification_busy = False
        controller._mining_verification_cache = {}
        controller.miningVerificationChanged = Mock()
        controller._start_network_worker = Mock()
        learned_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        controller.verifyMiningRoutes([{
            "system": "Current", "systemAddress": 42,
            "ring": "Current A Ring", "learnedAt": learned_at,
            "observations": [{"source": "Spansh dump catalog"}],
        }], "Origin")

        controller._start_network_worker.assert_not_called()
        self.assertEqual(controller._mining_verification_completed, 1)
        self.assertIn("1/1 systems verified", controller._mining_verification_status)

    def test_powerplay_verification_checks_top_pending_same_system_market(self):
        controller = CockpitController.__new__(CockpitController)
        controller._mining_verification_busy = False
        controller._mining_verification_cache = {}
        controller._mining_powerplay_market_verification_cache = {}
        controller._profile_generation = 3
        controller.profile_context = Mock(key="alpha")
        controller.mining_catalog_file = Path("mining.json")
        controller._known_mining_origin = Mock(return_value={})
        workers = []
        controller._start_network_worker = (
            lambda target, _name: workers.append(target) or True
        )
        controller.miningVerificationChanged = Mock()
        controller.miningVerificationProgress = Mock()
        controller.miningVerificationFinished = Mock()

        controller.verifyMiningRoutes([{
            "system": "Cubeo", "optimization": "POWERPLAY MERITS",
            "sameSystemSaleRequired": True, "marketKnown": False,
        }], "Origin", "Platinum", 1, 5000, "LARGE")

        targets = controller._active_mining_verification_request[
            "marketTargets"
        ]
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["system"], "Cubeo")
        self.assertEqual(targets[0]["commodity"], "platinum")
        self.assertEqual(targets[0]["key"], "cubeo\x1fplatinum")
        with patch(
            "ed_companion.phase14.controller_navigation.fetch_market_imports",
            return_value=[{
                "commodity": "platinum", "system": "Cubeo",
                "station": "Chelomey Orbital", "sellPrice": 200000,
                "demand": 10000,
            }],
        ) as fetch:
            workers[0]()

        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.kwargs["landing_pad"], "LARGE")
        result = controller.miningVerificationFinished.emit.call_args.args[0]
        self.assertEqual(result["marketSucceeded"], ["cubeo\x1fplatinum"])
        self.assertEqual(result["markets"][0]["station"], "Chelomey Orbital")
        self.assertEqual(result["marketOutcomes"][0]["state"], "FOUND")

    def test_market_verification_budget_marks_remaining_targets_queued(self):
        controller = CockpitController.__new__(CockpitController)
        controller._mining_verification_busy = False
        controller._mining_verification_cache = {}
        controller._mining_powerplay_market_verification_cache = {}
        controller._profile_generation = 3
        controller.profile_context = Mock(key="alpha")
        controller.mining_catalog_file = Path("mining.json")
        controller._known_mining_origin = Mock(return_value={})
        controller._start_network_worker = Mock(return_value=True)
        controller.miningVerificationChanged = Mock()
        controller.miningVerificationProgress = Mock()
        controller.miningVerificationFinished = Mock()
        controller.miningChanged = Mock()
        routes = [{
            "system": f"Pending {index}", "systemAddress": index + 1,
            "optimization": "POWERPLAY MERITS",
            "sameSystemSaleRequired": True,
            "marketMatchesFilters": False,
            "marketStatus": "NO_MARKET_DATA",
            "selectedCommodity": "platinum",
            "pendingReason": "No local market data",
        } for index in range(8)]

        controller.verifyMiningRoutes(
            routes, "Origin", "Platinum", 1, 5000, "LARGE",
        )

        request = controller._active_mining_verification_request
        self.assertEqual(len(request["marketTargets"]), 6)
        self.assertEqual(
            request["powerplayTargets"], request["targets"],
        )
        states = controller._mining_market_verification_states
        self.assertEqual(
            sum(item["state"] == "CHECKING" for item in states.values()), 6,
        )
        self.assertEqual(
            sum(item["state"] == "QUEUED" for item in states.values()), 2,
        )
        controller._start_network_worker.assert_called_once()

    def test_route_projection_exposes_queued_market_lookup(self):
        controller = CockpitController.__new__(CockpitController)
        controller._mining_find_page = Mock(return_value=[])
        controller._mining_market_rows_for_query = Mock(return_value=[])
        controller._mining_powerplay_catalog = {}
        controller._mining_powerplay_observations = []
        controller._mining_market_verification_states = {
            "cubeo\x1fplatinum": {"state": "QUEUED"},
        }
        projected = [{
            "system": "Cubeo", "selectedCommodity": "platinum",
            "sameSystemSaleRequired": True,
            "marketStatus": "NO_MARKET_DATA",
            "powerplayVerificationState": "NO_MARKET_DATA",
        }]
        with patch(
            "ed_companion.phase14.controller_navigation.plan_mining_routes",
            return_value=projected,
        ):
            rows = controller.miningPlanRoutes(
                "Cubeo", "Platinum", 100, "ALL RESERVES", "ANY RING",
                True, "LASER", "POWERPLAY MERITS", 5000, 500000, 1, 30,
                False, False, False, False, "LARGE", "Aisling Duval",
                "REINFORCE", "ANY", "ANY",
            )

        self.assertEqual(rows[0]["verificationStatus"], "NOT_YET_CHECKED")
        self.assertIn("six-target budget", rows[0]["pendingReason"])

    def test_empty_market_response_is_logged_and_recorded_as_no_data(self):
        controller = CockpitController.__new__(CockpitController)
        controller._mining_verification_busy = False
        controller._mining_verification_cache = {}
        controller._mining_powerplay_market_verification_cache = {}
        controller._profile_generation = 3
        controller.profile_context = Mock(key="alpha")
        controller.mining_catalog_file = Path("mining.json")
        controller._known_mining_origin = Mock(return_value={})
        workers = []
        controller._start_network_worker = (
            lambda target, _name: workers.append(target) or True
        )
        controller.miningVerificationChanged = Mock()
        controller.miningVerificationProgress = Mock()
        controller.miningVerificationFinished = Mock()
        controller.miningChanged = Mock()
        controller._debug_mode = True
        controller._write_log = Mock()

        controller.verifyMiningRoutes([{
            "system": "Empty", "optimization": "POWERPLAY MERITS",
            "sameSystemSaleRequired": True,
            "marketMatchesFilters": False,
            "marketStatus": "NO_MARKET_DATA",
            "selectedCommodity": "platinum",
            "pendingReason": "No local market data",
        }], "Origin", "Platinum", 1, 5000, "LARGE")
        with patch(
            "ed_companion.phase14.controller_navigation.fetch_market_imports",
            return_value=[],
        ):
            workers[0]()

        result = controller.miningVerificationFinished.emit.call_args.args[0]
        self.assertEqual(result["marketOutcomes"], [{
            "key": "empty\x1fplatinum", "state": "NO_DATA",
            "reason": (
                "Server returned no market data for this system and commodity"
            ),
        }])
        log = controller._write_log.call_args.args[0]
        self.assertIn('"responseStatus": "NO_DATA"', log)
        self.assertIn('"filterResult": "NO_MARKET_DATA"', log)

    def test_powerplay_market_check_is_persisted_without_replacing_ui_cache(self):
        with TemporaryDirectory() as directory:
            controller = CockpitController.__new__(CockpitController)
            controller.profile_context = Mock(key="alpha")
            controller._profile_generation = 3
            controller.mining_catalog_file = Path("mining.json")
            controller._active_mining_verification_request = {"id": "check"}
            controller._mining_verification_busy = True
            controller._mining_verification_cache = {}
            controller._mining_powerplay_market_verification_cache = {}
            controller._mining_market_cache = {"markets": [
                {"station": "Visible Search Result"},
            ]}
            visible_cache = controller._mining_market_cache
            controller._mining_market_store = MarketCatalogStore(
                Path(directory, "markets.sqlite3")
            )
            controller._mining_market_revision = 0
            controller._schedule_mining_market_backup = Mock(return_value=True)
            controller._pending_mining_verification = None
            controller.miningVerificationChanged = Mock()
            controller.miningChanged = Mock()
            controller.stateChanged = Mock()

            controller._finish_mining_verification({
                "id": "check", "profileKey": "alpha", "generation": 3,
                "path": "mining.json", "total": 1,
                "candidates": [], "succeeded": [], "failed": [],
                "marketSucceeded": ["cubeo\x1fplatinum"],
                "marketFailed": [],
                "markets": [{
                    "commodity": "platinum", "marketId": 42,
                    "system": "Cubeo", "station": "Chelomey Orbital",
                    "sellPrice": 200000, "demand": 10000,
                    "observedAt": datetime.now(timezone.utc).isoformat(),
                }],
            })

            self.assertIs(controller._mining_market_cache, visible_cache)
            self.assertEqual(controller._mining_market_store.count(), 1)
            self.assertEqual(controller._mining_market_revision, 1)
            controller._schedule_mining_market_backup.assert_called_once()

    def test_mining_catalog_load_is_deferred_and_profile_scoped(self):
        with TemporaryDirectory() as directory:
            controller = CockpitController.__new__(CockpitController)
            controller._profile_generation = 4
            controller.profile_context = Mock(key="alpha")
            controller.mining_catalog_file = Path(directory) / "mining.json"
            controller.mining_catalog_file.write_text(
                json.dumps({"candidates": [{
                    "system": "Alpha", "ring": "Alpha A Ring",
                }]}),
                encoding="utf-8",
            )
            workers = []
            controller._start_network_worker = (
                lambda target, _name: workers.append(target) or True
            )
            controller.miningCatalogLoaded = Mock()

            self.assertTrue(controller._start_mining_catalog_load())
            controller.miningCatalogLoaded.emit.assert_not_called()
            workers[0]()
            payload = controller.miningCatalogLoaded.emit.call_args.args[0]

            self.assertEqual(payload[:4], (
                1, 4, "alpha", str(controller.mining_catalog_file),
            ))
            self.assertEqual(payload[4]["candidates"][0]["ring"], "Alpha A Ring")
            self.assertEqual(payload[6], ["Alpha"])
            self.assertEqual(payload[7], ["alpha"])

    def test_mining_system_suggestions_are_prefix_ranked_and_keep_free_input(self):
        controller = CockpitController.__new__(CockpitController)
        controller._state = {"system": "HIP 6703"}
        names, keys = controller._mining_system_name_index([
            {"system": "HIP 100"},
            {"system": "HIP 6703"},
            {"system": "HIP 200"},
            {"system": "Shinrarta Dezhra"},
            {"system": "hip 100"},
        ])
        controller._mining_system_names = names
        controller._mining_system_name_keys = keys

        self.assertEqual(
            controller.miningSystemSuggestions("hip", 3),
            ["HIP 6703", "HIP 100", "HIP 200"],
        )
        self.assertEqual(
            controller.miningSystemSuggestions("shin", 8),
            ["Shinrarta Dezhra"],
        )
        self.assertEqual(
            controller.miningSystemSuggestions("freely typed system", 8), []
        )

    def test_filter_rejects_distant_rows_before_hotspot_projection_and_caches(self):
        controller = CockpitController.__new__(CockpitController)
        controller._mining_rows_cache_key = ("stable",)
        controller._mining_rows = Mock(return_value=[{
            "system": f"Far {index}", "ring": f"Far {index} A Ring",
            "distanceLy": 5000.0, "evidence": "LIVE_REPORTED",
            "reserveLevel": "PristineResources",
            "hotspots": [{"commodity": "osmium", "count": 1}],
        } for index in range(5000)])

        with patch(
            "ed_companion.phase14.controller_navigation.mining_commodity_id",
            wraps=__import__(
                "ed_companion.phase14.controller", fromlist=["mining_commodity_id"]
            ).mining_commodity_id,
        ) as commodity_id:
            first = controller.miningFindPageForMethod(
                "OSMIUM", 100, "ALL EVIDENCE", "ALL RESERVES", "LASER"
            )
            calls_after_first = commodity_id.call_count
            second = controller.miningFindPageForMethod(
                "OSMIUM", 100, "ALL EVIDENCE", "ALL RESERVES", "LASER"
            )

        self.assertEqual(first, [])
        self.assertIs(second, first)
        self.assertEqual(calls_after_first, 1)
        self.assertEqual(commodity_id.call_count, 2)

    def test_large_mining_view_is_built_off_the_ui_thread(self):
        controller = CockpitController.__new__(CockpitController)
        controller._state = {
            "system": "Origin", "currentPosition": [0, 0, 0],
            "localMiningEvidence": {},
        }
        controller._mining_catalog = {"candidates": [{
            "system": "Nearby", "ring": "Nearby A Ring",
            "coordinates": [1, 2, 3], "hotspots": [],
            "evidence": "CATALOG_CANDIDATE",
        }]}
        controller._profile_generation = 2
        controller.profile_context = Mock(key="alpha")
        controller._network_threads_lock = object()
        controller._mining_rows_cache_key = None
        controller._mining_rows_cache = []
        controller._mining_rows_build_token = 0
        controller._mining_rows_build_in_flight = False
        controller._mining_rows_build_dirty = False
        workers = []
        controller._start_network_worker = (
            lambda target, _name: workers.append(target) or True
        )
        controller.miningRowsReady = Mock()
        controller.miningChanged = Mock()

        self.assertEqual(controller._mining_rows(), [])
        self.assertEqual(len(workers), 1)
        workers[0]()
        payload = controller.miningRowsReady.emit.call_args.args[0]
        controller._finish_mining_rows_build(payload)

        self.assertEqual(controller._mining_rows()[0]["system"], "Nearby")
        controller.miningChanged.emit.assert_called_once_with()

    def test_live_mining_observations_are_retained_until_batched(self):
        controller = CockpitController.__new__(CockpitController)
        pending = [{"ring": "Pending A Ring"}]
        controller._pending_bgs_snapshots = []
        controller._pending_hge_observations = []
        controller._pending_mining_candidates = pending
        controller._last_mining_batch_monotonic = time.monotonic()
        controller._next_hge_expiry_epoch = time.time() + 3600
        controller._shutdown_complete = False

        controller.flushHgeObservationBatch()

        self.assertIs(controller._pending_mining_candidates, pending)

    def test_bgs_snapshots_are_retained_until_batched(self):
        controller = CockpitController.__new__(CockpitController)
        pending = [{"system": "Pending", "observations": []}]
        controller._pending_bgs_snapshots = pending
        controller._pending_hge_observations = []
        controller._pending_mining_candidates = []
        controller._last_bgs_batch_monotonic = time.monotonic()
        controller._last_mining_batch_monotonic = time.monotonic()
        controller._next_hge_expiry_epoch = time.time() + 3600
        controller._shutdown_complete = False

        controller.flushHgeObservationBatch()

        self.assertIs(controller._pending_bgs_snapshots, pending)

    def test_leaving_mining_page_retains_shared_source_view_for_return(self):
        controller = CockpitController.__new__(CockpitController)
        controller._last_page = 12
        controller._mining_rows_build_token = 4
        controller._mining_rows_build_in_flight = True
        controller._mining_rows_build_dirty = True
        controller._mining_rows_cache_key = ("large",)
        controller._mining_rows_cache = [{"system": "Cached"}]
        controller._mining_find_cache_key = ("filtered",)
        controller._mining_find_cache = [{"system": "Cached"}]
        controller._save_ui_config = Mock(return_value=True)

        controller.setLastPage(0)

        self.assertEqual(controller._mining_rows_build_token, 4)
        self.assertEqual(controller._mining_rows_cache, [{"system": "Cached"}])
        self.assertEqual(controller._mining_find_cache, [])
        self.assertEqual(controller._mining_rows_cache_key, ("large",))

    def test_mining_catalog_save_is_deferred_and_only_latest_snapshot_wins(self):
        with TemporaryDirectory() as directory:
            controller = CockpitController.__new__(CockpitController)
            controller.mining_catalog_file = Path(directory) / "mining.json"
            controller._shutdown_complete = False
            controller._mining_catalog = {"candidates": [{"ring": "Old"}]}
            workers = []
            controller._start_network_worker = (
                lambda target, _name: workers.append(target) or True
            )

            controller._save_mining_catalog()
            controller._mining_catalog = {"candidates": [{"ring": "Latest"}]}
            controller._save_mining_catalog()

            self.assertFalse(controller.mining_catalog_file.exists())
            workers[0]()
            self.assertFalse(controller.mining_catalog_file.exists())
            workers[1]()
            saved = json.loads(
                controller.mining_catalog_file.read_text(encoding="utf-8")
            )

        self.assertEqual(saved["candidates"][0]["ring"], "Latest")

    def test_incremental_mining_merge_matches_full_merge_without_dropping_rows(self):
        now = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
        base = [
            {"systemAddress": 1, "bodyId": 1, "ring": "A Ring",
             "evidence": "CATALOG_CANDIDATE", "observedAt": "2026-09-04T10:00:00Z",
             "hotspots": [{"commodity": "platinum", "count": 1}]},
            {"systemAddress": 2, "bodyId": 2, "ring": "B Ring",
             "evidence": "LIVE_REPORTED", "observedAt": "2026-09-05T10:00:00Z",
             "hotspots": []},
        ]
        additions = [
            {"systemAddress": 1, "bodyId": 1, "ring": "A Ring",
             "evidence": "LIVE_REPORTED", "observedAt": "2026-09-05T11:00:00Z",
             "hotspots": [{"commodity": "painite", "count": 1}]},
            {"systemAddress": 3, "bodyId": 3, "ring": "C Ring",
             "evidence": "LIVE_REPORTED", "observedAt": "2026-09-05T11:00:00Z",
             "hotspots": []},
        ]
        prepared = merge_mining_candidates(base, now=now)

        incremental, displaced = merge_mining_candidate_batch(
            prepared, additions, now=now
        )
        expected = merge_mining_candidates([*base, *additions], now=now)

        self.assertEqual(
            sorted(incremental, key=lambda row: row["ring"]),
            sorted(expected, key=lambda row: row["ring"]),
        )
        self.assertEqual([row["ring"] for row in displaced], ["A Ring"])

    def test_incremental_mining_merge_reuses_catalog_identity_index(self):
        base = [{
            "systemAddress": index,
            "bodyId": index,
            "ring": f"Ring {index}",
            "evidence": "CATALOG_CANDIDATE",
        } for index in range(2000)]
        positions = mining_candidate_positions(base)
        additions = [
            {"systemAddress": 1200, "bodyId": 1200, "ring": "Ring 1200",
             "evidence": "LIVE_REPORTED"},
            {"systemAddress": 3000, "bodyId": 3000, "ring": "Ring 3000",
             "evidence": "LIVE_REPORTED"},
        ]

        with patch(
            "ed_companion.navigation.mining_finder._candidate_identity",
            wraps=__import__(
                "ed_companion.navigation.mining_finder",
                fromlist=["_candidate_identity"],
            )._candidate_identity,
        ) as identity:
            merged, displaced = merge_mining_candidate_batch(
                base, additions, positions=positions,
            )

        self.assertLess(identity.call_count, 20)
        self.assertEqual(len(merged), 2001)
        self.assertEqual(displaced[0]["ring"], "Ring 1200")
        self.assertEqual(positions[("address", 3000, "ring 3000")], 2000)

    def test_equivalent_ring_names_and_missing_body_id_merge_globally(self):
        merged = merge_mining_candidates([{
            "system": "Delkar", "systemAddress": 42, "bodyId": 7,
            "ring": "Delkar 7 a", "ringType": "Metallic",
            "evidence": "CATALOG_CANDIDATE",
            "observedAt": "2026-09-04T10:00:00Z",
        }, {
            "system": "Delkar", "systemAddress": 42,
            "ring": "  DELKAR   7 A Ring  ",
            "reserveLevel": "PristineResources",
            "evidence": "LIVE_REPORTED",
            "observedAt": "2026-09-05T10:00:00Z",
        }], now=datetime(2026, 9, 5, 12, tzinfo=timezone.utc))

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["ringType"], "Metallic")
        self.assertEqual(merged[0]["reserveLevel"], "PristineResources")
        self.assertEqual(merged[0]["sourceCount"], 2)

    def test_generic_ring_names_on_different_bodies_stay_separate(self):
        merged = merge_mining_candidates([{
            "system": "Generic", "systemAddress": 91,
            "body": "Generic 2", "bodyId": 2, "ring": "A Ring",
            "evidence": "CATALOG_CANDIDATE",
        }, {
            "system": "Generic", "systemAddress": 91,
            "body": "Generic 3", "bodyId": 3, "ring": "A Ring",
            "evidence": "CATALOG_CANDIDATE",
        }])

        self.assertEqual(len(merged), 2)

    def test_relay_prefilter_keeps_every_consumed_schema_and_event(self):
        self.assertTrue(_eddn_relay_relevant({
            "$schemaRef": "https://eddn.edcd.io/schemas/fsssignaldiscovered/1",
            "message": {},
        }))
        self.assertTrue(_eddn_relay_relevant({
            "$schemaRef": "https://eddn.edcd.io/schemas/fssbodysignals/1",
            "message": {},
        }))
        for event in (
            "FSDJump", "Location", "CarrierJump", "Scan", "SAASignalsFound",
        ):
            self.assertTrue(_eddn_relay_relevant({
                "$schemaRef": "https://eddn.edcd.io/schemas/journal/1",
                "message": {"event": event},
            }))
        self.assertFalse(_eddn_relay_relevant({
            "$schemaRef": "https://eddn.edcd.io/schemas/journal/1",
            "message": {"event": "Docked"},
        }))
        self.assertFalse(_eddn_relay_relevant({
            "$schemaRef": "https://eddn.edcd.io/schemas/commodity/3",
            "message": {},
        }))

    def test_reset_removes_only_the_active_profile_mining_catalog(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            mining_file = root / "mining_finder_catalog.json"
            queue_file = root / "community_upload_queue.json"
            market_cache_file = root / "mining_market_cache.json"
            market_legacy_file = root / "mining_market_catalog.json"
            market_database_file = root / "mining_market_catalog.sqlite3"
            mining_file.write_text(
                json.dumps({"candidates": [{"ring": "Old ring"}]}),
                encoding="utf-8",
            )
            queue_file.write_text('[{"status": "queued"}]', encoding="utf-8")
            market_cache_file.write_text(
                json.dumps({"markets": [{"station": "Old port"}]}),
                encoding="utf-8",
            )
            market_legacy_file.write_text(
                json.dumps({"markets": [{"station": "Legacy port"}]}),
                encoding="utf-8",
            )
            controller = CockpitController.__new__(CockpitController)
            controller.mining_catalog_file = mining_file
            controller.mining_market_cache_file = market_cache_file
            controller.mining_market_catalog_legacy_file = market_legacy_file
            controller._mining_market_store = MarketCatalogStore(
                market_database_file
            )
            observed_at = datetime.now(timezone.utc)
            controller._mining_market_store.ingest([{
                "commodity": "platinum", "station": "Old port",
                "system": "Cubeo", "marketId": 42,
                "sellPrice": 250000, "demand": 5000,
                "observedAt": observed_at.isoformat(),
            }])
            controller._mining_market_cache = {"markets": [{
                "station": "Old port",
            }]}
            controller._mining_catalog = {"candidates": [{"ring": "Old ring"}]}
            controller._active_mining_request = {"id": "old"}
            controller._mining_sync_busy = True
            controller._pending_mining_candidates = [{"ring": "Pending"}]
            controller.miningChanged = Mock()
            controller.stateChanged = Mock()
            controller.connectionChanged = Mock()

            controller.resetMiningCatalog()

            self.assertEqual(
                json.loads(mining_file.read_text(encoding="utf-8"))["candidates"],
                [],
            )
            self.assertEqual(
                queue_file.read_text(encoding="utf-8"), '[{"status": "queued"}]'
            )
            self.assertEqual(controller._pending_mining_candidates, [])
            self.assertTrue(controller._mining_catalog["resetAt"])
            self.assertIsNone(controller._mining_rows_cache_key)
            self.assertEqual(controller._mining_market_store.count(), 0)
            self.assertEqual(
                json.loads(market_cache_file.read_text(encoding="utf-8")), {}
            )
            self.assertFalse(market_legacy_file.exists())
            self.assertEqual(
                controller._mining_market_store.metadata("legacy_migrated"),
                "1",
            )

            controller._mining_market_store.ingest([{
                "commodity": "platinum", "station": "New port",
                "system": "Cubeo", "marketId": 43,
                "sellPrice": 275000, "demand": 6000,
                "observedAt": (observed_at + timedelta(minutes=1)).isoformat(),
            }])
            self.assertEqual(controller._mining_market_store.count(), 1)

    def test_reset_cutoff_hides_old_projected_journal_results(self):
        controller = CockpitController.__new__(CockpitController)
        controller._state = {
            "system": "Test", "localMiningEvidence": {"candidates": [{
                "system": "Old", "ring": "Old A Ring",
                "observedAt": "2026-09-01T10:00:00Z",
                "evidence": "LOCAL_CONFIRMED", "hotspots": [],
            }, {
                "system": "New", "ring": "New A Ring",
                "observedAt": "2026-09-07T10:00:00Z",
                "evidence": "LOCAL_CONFIRMED", "hotspots": [],
            }]},
        }
        controller._mining_catalog = {
            "resetAt": "2026-09-06T10:00:00+00:00", "candidates": [],
        }

        rows = controller.miningFindPageForMethod(
            "ALL COMMODITIES", 0, "ALL EVIDENCE", "ALL RESERVES", "LASER"
        )

        self.assertEqual([row["system"] for row in rows], ["New"])

    def test_reset_cutoff_hides_old_catalog_but_accepts_newly_learned_rows(self):
        controller = CockpitController.__new__(CockpitController)
        controller._state = {"system": "Test", "localMiningEvidence": {}}
        controller._mining_catalog = {
            "resetAt": "2026-09-06T10:00:00+00:00", "candidates": [{
                "system": "Old", "ring": "Old A Ring",
                "learnedAt": "2026-09-06T09:00:00+00:00",
                "evidence": "LIVE_REPORTED", "hotspots": [],
            }, {
                "system": "New", "ring": "New A Ring",
                "learnedAt": "2026-09-06T11:00:00+00:00",
                "evidence": "LIVE_REPORTED", "hotspots": [],
            }],
        }

        rows = controller.miningFindPageForMethod(
            "ALL COMMODITIES", 0, "ALL EVIDENCE", "ALL RESERVES", "LASER"
        )

        self.assertEqual([row["system"] for row in rows], ["New"])

    def test_laser_readiness_uses_installed_modules_and_cargo_capacity(self):
        controller = CockpitController.__new__(CockpitController)
        controller._state = {
            "moduleSlots": [
                {"moduleId": "intdronecontrol_prospector_size3_class5"},
                {"moduleId": "intdronecontrol_collection_size5_class5"},
                {"moduleId": "intrefinery_size4_class5"},
            ],
            "selectedShipStats": {"cargoCapacity": 128},
        }

        result = controller.miningLoadoutReadiness("LASER")

        self.assertTrue(result["ready"])
        self.assertEqual(result["status"], "READY")

    def test_catalog_summary_reports_field_completeness_without_claiming_galaxy_coverage(self):
        controller = CockpitController.__new__(CockpitController)
        controller._mining_rows = Mock(return_value=[{
            "system": "Complete",
            "ring": "Complete A Ring",
            "coordinates": [1, 2, 3],
            "ringTypeName": "Metallic",
            "reserveName": "Pristine",
            "hotspots": [{"commodity": "platinum"}],
            "evidence": "LIVE_REPORTED",
            "observedAt": "2026-10-02T10:00:00Z",
            "stale": False,
        }, {
            "system": "Partial",
            "ring": "Partial A Ring",
            "ringTypeName": "Unknown",
            "reserveName": "Unknown",
            "hotspots": [],
            "evidence": "STALE",
            "observedAt": "2026-09-01T10:00:00Z",
            "stale": True,
        }])
        controller._mining_market_revision = 4
        controller._mining_market_store = Mock()
        controller._mining_market_store.count.return_value = 3
        controller._mining_powerplay_catalog = {
            "systems": [{"system": "One"}, {"system": "Two"}],
        }

        summary = controller._mining_cache_summary()

        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["systems"], 2)
        self.assertEqual(summary["marketTotal"], 3)
        self.assertEqual(summary["powerplayTotal"], 2)
        self.assertEqual(summary["recordCompleteness"], 67)
        self.assertEqual(summary["coordinatesPercent"], 50)
        self.assertEqual(summary["resourceEvidencePercent"], 50)
        self.assertEqual(summary["currentPercent"], 50)

    def test_method_readiness_does_not_claim_missing_modules(self):
        controller = CockpitController.__new__(CockpitController)
        controller._state = {
            "moduleSlots": [], "selectedShipStats": {"cargoCapacity": 0},
            "vehicleState": {"vehicles": []},
        }

        for method in ("LASER", "CORE", "SUBSURFACE", "RHINO SURFACE"):
            with self.subTest(method=method):
                self.assertFalse(controller.miningLoadoutReadiness(method)["ready"])

    def test_mining_multi_limpet_fulfils_prospector_and_collector_roles(self):
        controller = CockpitController.__new__(CockpitController)
        controller._state = {
            "moduleSlots": [
                {"moduleId": "int_multidronecontrolminingmkii_size5_class1"},
                {"moduleId": "intrefinery_size3_class5"},
            ],
            "selectedShipStats": {"cargoCapacity": 164},
        }

        result = controller.miningLoadoutReadiness("LASER")

        self.assertTrue(result["ready"])
        self.assertIn("✓ Prospector", result["summary"])
        self.assertIn("✓ Collector", result["summary"])

    def test_non_mining_dss_categories_are_not_commodity_filters(self):
        controller = CockpitController.__new__(CockpitController)
        controller._state = {"system": "Test", "localMiningEvidence": {}}
        controller._mining_catalog = {"candidates": [{
            "system": "Test", "ring": "Test A Ring",
            "evidence": "LIVE_REPORTED",
            "observedAt": "2026-09-04T10:00:00Z",
            "hotspots": [
                {"commodity": "$saa_signaltype_biological;", "count": 1},
                {"commodity": "planetarymininglocation", "count": 1},
                {"commodity": "monazite", "count": 1},
            ],
        }]}

        filters = controller._mining_commodity_filters()
        self.assertIn("Monazite", filters)
        self.assertIn("Water", filters)
        self.assertIn("Thortveitite", filters)
        self.assertNotIn("Biological", filters)
        self.assertNotIn("Planetarymininglocation", filters)
        self.assertEqual(controller._mining_rows()[0]["hotspotNames"], "Monazite")

    def test_eddn_scan_and_hotspots_merge_without_private_fields(self):
        common = {
            "$schemaRef": "https://eddn.edcd.io/schemas/journal/1",
        }
        scan = {**common, "message": {
            "event": "Scan", "timestamp": "2026-09-04T10:00:00Z",
            "StarSystem": "Public System", "SystemAddress": 42,
            "StarPos": [1, 2, 3], "BodyName": "Public System 1",
            "BodyID": 1, "ReserveLevel": "PristineResources",
            "Rings": [{"Name": "Public System 1 A Ring",
                       "RingClass": "eRingClass_Metallic"}],
            "Commander": "PRIVATE", "FuturePrivateField": {"secret": "PRIVATE"},
        }}
        signals = {**common, "message": {
            "event": "SAASignalsFound", "timestamp": "2026-09-04T10:01:00Z",
            "StarSystem": "Public System", "SystemAddress": 42,
            "StarPos": [1, 2, 3], "BodyName": "Public System 1 A Ring",
            "BodyID": 1, "Signals": [
                {"Type": "$Platinum_Name;", "Count": 2,
                 "FuturePrivateField": "PRIVATE"}
            ], "FID": "PRIVATE",
        }}

        rows = merge_mining_candidates([
            *project_eddn_mining_candidates(scan),
            *project_eddn_mining_candidates(signals),
        ], now=datetime(2026, 9, 4, 10, 2, tzinfo=timezone.utc))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["evidence"], "LIVE_REPORTED")
        self.assertEqual(rows[0]["hotspots"], [
            {"commodity": "platinum", "count": 2}
        ])
        self.assertNotIn("PRIVATE", json.dumps(rows))

    def test_eddn_fss_body_signals_project_rhino_destination(self):
        rows = project_eddn_mining_candidates({
            "$schemaRef": "https://eddn.edcd.io/schemas/fssbodysignals/1",
            "message": {
                "event": "FSSBodySignals",
                "timestamp": "2026-09-05T10:00:00Z",
                "StarSystem": "Rhino Test", "SystemAddress": 42,
                "StarPos": [1, 2, 3], "BodyName": "Rhino Test 2 b",
                "BodyID": 8, "Signals": [{
                    "Type": "$PlanetaryMiningLocation_Name;", "Count": 17,
                }],
            },
        })

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["planetaryMiningLocationCount"], 17)
        self.assertEqual(rows[0]["hotspots"], [])

    def test_spansh_fetch_sends_only_public_system_address(self):
        calls = []

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"system": {"id64": 42, "bodies": []}}

        def get(url, **kwargs):
            calls.append((url, kwargs))
            return Response()

        payload = fetch_spansh_system_dump(42, get)

        self.assertEqual(payload["system"]["id64"], 42)
        self.assertEqual(calls, [(
            "https://spansh.co.uk/api/dump/42", {"timeout": 20}
        )])

    def test_central_catalog_fetch_sends_only_public_search_fields(self):
        calls = []

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"results": []}

        def get(url, **kwargs):
            calls.append((url, kwargs))
            return Response()

        self.assertEqual(fetch_edframe_mining_candidates(
            "Cubeo", get, commodity="Platinum", origin=[0, 0, 0],
        ), [])
        self.assertEqual(calls[0][1]["params"], {
            "system": "Cubeo", "limit": 200, "commodity": "platinum", "offset": 0,
            "snapshot_protocol": 1,
            "max_age_days": 3650,
            "include_community_overlaps": True,
            "include_ring_candidates": True,
        })
        self.assertNotIn("commander", json.dumps(calls).casefold())

    def test_controller_filters_the_same_projected_state_without_journal_io(self):
        controller = CockpitController.__new__(CockpitController)
        controller._state = {
            "system": "Test System",
            "localMiningEvidence": {"candidates": [{
                "system": "Test System", "systemAddress": 7,
                "ring": "Test A Ring", "hotspots": [
                    {"commodity": "platinum", "count": 2}
                ], "evidence": "LOCAL_CONFIRMED",
                "observedAt": "2026-09-04T10:00:00Z", "source": "test",
            }]},
        }
        controller._mining_catalog = {"candidates": []}

        rows = controller.miningFindPage(
            "Platinum", 25, "ALL EVIDENCE", "ALL RESERVES"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["distanceLy"], 0.0)
        self.assertEqual(rows[0]["hotspotNames"], "Platinum")

    def test_custom_start_system_recalculates_candidate_distances(self):
        controller = CockpitController.__new__(CockpitController)
        controller._state = {
            "system": "Journal System", "currentPosition": [100, 100, 100]
        }
        controller._mining_rows_cache_key = ("custom-origin",)
        controller._system_coordinate_index = Mock(return_value={})
        common = {
            "observedAt": datetime.now(timezone.utc).isoformat(),
            "reserveLevel": "PristineResources",
            "evidence": "LIVE_REPORTED",
            "ringTypeName": "Metallic",
            "hotspots": [{"commodity": "platinum", "count": 1}],
        }
        controller._mining_rows = Mock(return_value=[
            {**common, "system": "Origin", "ring": "Origin A Ring",
             "coordinates": [0, 0, 0], "distanceLy": 999},
            {**common, "system": "Near", "ring": "Near A Ring",
             "coordinates": [3, 4, 0], "distanceLy": 999},
            {**common, "system": "Far", "ring": "Far A Ring",
             "coordinates": [30, 0, 0], "distanceLy": 1},
        ])

        rows = controller._mining_find_page(
            "Platinum", 15, "ALL EVIDENCE", "ALL RESERVES", "LASER",
            "Origin",
        )

        self.assertEqual([row["system"] for row in rows], ["Origin", "Near"])
        self.assertEqual([row["distanceLy"] for row in rows], [0.0, 5.0])
        self.assertTrue(all(row["routeOriginKnown"] for row in rows))

    def test_unknown_custom_start_system_waits_for_coordinates(self):
        controller = CockpitController.__new__(CockpitController)
        controller._state = {"system": "Journal System"}
        controller._mining_rows_cache_key = ("unknown-origin",)
        controller._system_coordinate_index = Mock(return_value={})
        controller._mining_rows = Mock(return_value=[{
            "system": "Candidate", "ring": "Candidate A Ring",
            "coordinates": [30, 0, 0], "distanceLy": 1,
            "observedAt": datetime.now(timezone.utc).isoformat(),
            "reserveLevel": "PristineResources",
            "evidence": "LIVE_REPORTED", "ringTypeName": "Metallic",
            "hotspots": [{"commodity": "platinum", "count": 1}],
        }])

        rows = controller._mining_find_page(
            "Platinum", 15, "ALL EVIDENCE", "ALL RESERVES", "LASER",
            "Completely Unknown",
        )

        self.assertEqual(rows, [])

    def test_cached_edsm_origin_resolves_free_text_route_distances(self):
        controller = CockpitController.__new__(CockpitController)
        controller._state = {"system": "Journal System"}
        controller._mining_market_cache = {
            "origin": {"system": "Cubeo", "coordinates": [10, 20, 30]},
        }
        controller._mining_rows_cache_key = ("cached-origin",)
        controller._system_coordinate_index = Mock(return_value={})
        controller._mining_rows = Mock(return_value=[{
            "system": "Candidate", "ring": "Candidate A Ring",
            "coordinates": [13, 24, 30], "distanceLy": 999,
            "observedAt": datetime.now(timezone.utc).isoformat(),
            "reserveLevel": "PristineResources",
            "evidence": "LIVE_REPORTED", "ringTypeName": "Metallic",
            "hotspots": [{"commodity": "platinum", "count": 1}],
        }])

        rows = controller._mining_find_page(
            "Platinum", 15, "ALL EVIDENCE", "ALL RESERVES", "LASER",
            "cubeo",
        )

        self.assertEqual(rows[0]["distanceLy"], 5.0)
        self.assertTrue(rows[0]["routeOriginKnown"])

    def test_accumulated_market_catalog_is_reused_for_a_new_query(self):
        controller = CockpitController.__new__(CockpitController)
        controller._mining_market_cache = {
            "query": {"startSystem": "old"}, "markets": [],
        }
        controller._mining_market_catalog = {"markets": [{
            "commodity": "platinum", "station": "Remembered Port",
            "system": "Near", "coordinates": [3, 4, 0],
            "sellPrice": 250000, "demand": 9000,
            "observedAt": datetime.now(timezone.utc).isoformat(),
        }]}
        controller._known_mining_origin = Mock(return_value={
            "system": "Origin", "coordinates": [0, 0, 0],
        })

        rows = controller._mining_market_rows_for_query({
            "startSystem": "origin", "commodity": "platinum",
            "nearbyLy": 10, "minDemand": 5000,
            "maxMarketAgeHours": 1, "landingPad": "ANY",
        })

        self.assertEqual([row["station"] for row in rows], ["Remembered Port"])

    def test_sqlite_market_catalog_is_reused_for_a_new_query(self):
        with TemporaryDirectory() as directory:
            controller = CockpitController.__new__(CockpitController)
            controller._mining_market_cache = {
                "query": {"startSystem": "old"}, "markets": [],
            }
            controller._mining_market_store = MarketCatalogStore(
                Path(directory, "markets.sqlite3")
            )
            controller._mining_market_store.ingest([{
                "commodity": "platinum", "station": "Remembered Port",
                "system": "Near", "coordinates": [3, 4, 0],
                "sellPrice": 250000, "demand": 9000,
                "observedAt": datetime.now(timezone.utc).isoformat(),
            }])
            controller._known_mining_origin = Mock(return_value={
                "system": "Origin", "coordinates": [0, 0, 0],
            })

            rows = controller._mining_market_rows_for_query({
                "startSystem": "origin", "commodity": "platinum",
                "nearbyLy": 10, "minDemand": 5000,
                "maxMarketAgeHours": 1, "landingPad": "ANY",
            })

            self.assertEqual(
                [row["station"] for row in rows], ["Remembered Port"]
            )

    def test_legacy_market_json_is_migrated_without_deletion(self):
        with TemporaryDirectory() as directory:
            controller = CockpitController.__new__(CockpitController)
            controller.mining_market_catalog_file = Path(
                directory, "markets.sqlite3"
            )
            controller.mining_market_catalog_legacy_file = Path(
                directory, "markets.json"
            )
            controller.mining_market_catalog_legacy_file.write_text(
                "legacy remains", encoding="utf-8"
            )
            observation = {
                "commodity": "platinum", "station": "Legacy Port",
                "system": "Cubeo", "coordinates": [1, 2, 3],
                "sellPrice": 250000, "demand": 9000,
                "observedAt": datetime.now(timezone.utc).isoformat(),
            }
            controller._mining_market_cache = {"markets": []}
            controller._read_local_json = Mock(return_value={
                "markets": [observation],
            })

            store = controller._open_mining_market_store()

            self.assertEqual(store.count(), 1)
            self.assertEqual(store.metadata("legacy_migrated"), "1")
            self.assertEqual(
                controller.mining_market_catalog_legacy_file.read_text(
                    encoding="utf-8"
                ),
                "legacy remains",
            )
            controller._read_local_json.reset_mock()
            reopened = controller._open_mining_market_store()
            self.assertEqual(reopened.count(), 1)
            controller._read_local_json.assert_not_called()

    def test_market_lookup_failure_keeps_catalog_and_uses_staged_retry(self):
        controller = CockpitController.__new__(CockpitController)
        controller.profile_context = Mock(key="alpha")
        controller._profile_generation = 3
        controller.mining_market_cache_file = Path("market-cache.json")
        controller._remember_mining_origin = Mock(return_value=False)
        controller._mining_market_failure_count = 0
        controller._shutdown_complete = False
        controller._mining_market_retry_timer = Mock()
        controller._mining_market_store = Mock()
        controller.miningChanged = Mock()
        controller.stateChanged = Mock()
        result = {
            "id": "request", "profileKey": "alpha", "generation": 3,
            "path": "market-cache.json", "success": False,
            "error": "offline",
        }
        for expected_delay in (120, 300, 900, 1800, 1800):
            controller._active_mining_market_request = {"id": "request"}
            result["failureCount"] = controller._mining_market_failure_count
            controller._persist_mining_market_result(
                result, controller._mining_market_store, threading.Lock(),
            )
            controller._finish_mining_market_sync(result)
            controller._mining_market_retry_timer.start.assert_called_with(
                expected_delay * 1000
            )

        self.assertEqual(controller._mining_market_failure_count, 5)
        self.assertEqual(controller._mining_market_store.count.call_count, 0)
        self.assertEqual(
            controller._mining_market_store.record_source_result.call_count, 5
        )

    def test_local_market_snapshot_is_retained_without_eddn_upload(self):
        with TemporaryDirectory() as directory:
            controller = CockpitController.__new__(CockpitController)
            controller._state = {
                "system": "Cubeo", "currentPosition": [1, 2, 3],
            }
            controller._mining_market_store = MarketCatalogStore(
                Path(directory, "markets.sqlite3")
            )
            controller._mining_market_revision = 0
            controller._schedule_mining_market_backup = Mock(return_value=True)
            controller.miningChanged = Mock()

            imported = controller._ingest_local_mining_market_snapshot({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "StarSystem": "Cubeo", "StationName": "Medupe City",
                "MarketID": 42,
                "Items": [{
                    "Name": "$Platinum_Name;", "SellPrice": 250000,
                    "Demand": 5000, "DemandBracket": 3,
                }],
            })

            self.assertEqual(imported, 1)
            self.assertEqual(controller._mining_market_store.count(), 1)
            controller._schedule_mining_market_backup.assert_called_once()
            controller.miningChanged.emit.assert_called_once()

    def test_local_market_file_is_scanned_without_eddn_profile(self):
        controller = CockpitController.__new__(CockpitController)
        controller._scan_local_mining_market_file = Mock()
        controller._sync_eddn_profile = Mock(return_value=False)

        controller._scan_eddn_journal()

        controller._scan_local_mining_market_file.assert_called_once()
        controller._sync_eddn_profile.assert_called_once()

    def test_market_catalog_auto_refresh_reuses_the_last_query(self):
        controller = CockpitController.__new__(CockpitController)
        controller._mining_market_busy = False
        controller._shutdown_complete = False
        controller._mining_market_cache = {"query": {
            "startSystem": "cubeo", "commodity": "platinum",
            "nearbyLy": 250, "minDemand": 5000,
            "maxMarketAgeHours": 1, "landingPad": "LARGE",
        }}
        controller.refreshMiningMarkets = Mock()

        controller._maybe_auto_refresh_mining_markets()

        controller.refreshMiningMarkets.assert_called_once_with(
            "cubeo", "platinum", 250, 5000, 1, "LARGE",
        )

    def test_all_commodities_warms_concrete_markets_not_fake_commodity(self):
        with TemporaryDirectory() as directory:
            controller = CockpitController.__new__(CockpitController)
            controller._mining_market_store = MarketCatalogStore(
                Path(directory, "markets.sqlite3")
            )
            controller._mining_market_busy = False
            controller._known_mining_origin = Mock(return_value={
                "system": "Cubeo", "coordinates": [1, 2, 3],
            })
            controller._start_mining_market_refresh = Mock(return_value=True)
            controller.miningChanged = Mock()

            controller.refreshMiningMarkets(
                "Cubeo", "ALL COMMODITIES", 250, 5000, 1, "LARGE",
            )

            request = controller._start_mining_market_refresh.call_args.args[0]
            self.assertNotEqual(request["commodity"], "allcommodities")
            self.assertIn(
                request["commodity"], {
                    "platinum", "painite", "osmium", "monazite",
                    "musgravite", "alexandrite", "lowtemperaturediamond",
                    "opal", "tritium", "palladium", "gold", "silver",
                },
            )
            controller._start_mining_market_refresh.assert_called_once_with(
                request, background=True,
            )

    def test_all_commodities_resolves_unknown_origin_before_planning(self):
        with TemporaryDirectory() as directory:
            controller = CockpitController.__new__(CockpitController)
            controller._mining_market_store = MarketCatalogStore(
                Path(directory, "markets.sqlite3")
            )
            controller._mining_market_busy = False
            controller._known_mining_origin = Mock(return_value={})
            controller._start_mining_market_refresh = Mock(return_value=True)
            controller.miningChanged = Mock()

            controller.refreshMiningMarkets(
                "Cubeo", "ALL COMMODITIES", 250, 5000, 1, "LARGE",
            )

            request = controller._start_mining_market_refresh.call_args.args[0]
            self.assertEqual(request["startSystem"], "cubeo")
            self.assertEqual(request["commodity"], "platinum")
            controller._start_mining_market_refresh.assert_called_once_with(
                request, background=False,
            )

    def test_warm_queue_seeds_defaults_but_keeps_explicit_search_first(self):
        with TemporaryDirectory() as directory:
            controller = CockpitController.__new__(CockpitController)
            controller._mining_market_store = MarketCatalogStore(
                Path(directory, "markets.sqlite3")
            )
            query = {
                "startSystem": "cubeo", "commodity": "platinum",
                "nearbyLy": 250, "minDemand": 5000,
                "maxMarketAgeHours": 1, "landingPad": "LARGE",
            }

            controller._remember_mining_warm_targets(query)

            targets = controller._mining_market_store.warm_targets()
            self.assertEqual(len(targets), 12)
            self.assertEqual(targets[0]["commodity"], "platinum")
            self.assertEqual(targets[0]["priority"], 100)
            self.assertEqual(targets[0]["useCount"], 1)

    def test_user_market_lookup_queues_behind_background_warmup(self):
        with TemporaryDirectory() as directory:
            controller = CockpitController.__new__(CockpitController)
            controller._mining_market_store = MarketCatalogStore(
                Path(directory, "markets.sqlite3")
            )
            controller._mining_market_busy = True
            controller._mining_market_background = True
            controller._start_mining_market_refresh = Mock()
            controller.miningChanged = Mock()

            controller.refreshMiningMarkets(
                "Cubeo", "Platinum", 250, 5000, 1, "LARGE"
            )

            self.assertEqual(
                controller._pending_mining_market_query["commodity"],
                "platinum",
            )
            controller._start_mining_market_refresh.assert_not_called()
            self.assertTrue(
                CockpitController.miningMarketSyncBusy.fget(controller)
            )
            controller._mining_market_busy = False
            self.assertTrue(controller._launch_pending_mining_market_refresh())
            controller._start_mining_market_refresh.assert_called_once_with(
                {
                    "startSystem": "cubeo", "commodity": "platinum",
                    "nearbyLy": 250, "minDemand": 5000,
                    "maxMarketAgeHours": 1, "landingPad": "LARGE",
                },
                background=False,
            )

    def test_background_warm_result_does_not_replace_visible_query(self):
        with TemporaryDirectory() as directory:
            controller = CockpitController.__new__(CockpitController)
            controller.profile_context = Mock(key="alpha")
            controller._profile_generation = 3
            controller.mining_market_cache_file = Path("market-cache.json")
            controller._mining_market_cache = {
                "query": {"startSystem": "cubeo", "commodity": "platinum"},
                "markets": [{"station": "Visible Port"}],
            }
            visible_cache = controller._mining_market_cache
            controller._remember_mining_origin = Mock(return_value=False)
            controller._mining_market_store = MarketCatalogStore(
                Path(directory, "markets.sqlite3")
            )
            warm_query = {
                "startSystem": "cubeo", "commodity": "painite",
                "nearbyLy": 250, "minDemand": 0,
                "maxMarketAgeHours": 1, "landingPad": "ANY",
            }
            controller._mining_market_store.remember_warm_target(warm_query)
            controller._active_mining_market_request = {
                "id": "warm", "profileKey": "alpha", "generation": 3,
                "path": "market-cache.json", "query": warm_query,
                "background": True, "warmKey": "cubeo\x1fpainite",
            }
            controller._mining_market_busy = True
            controller._mining_market_background = True
            controller._mining_market_revision = 0
            controller._mining_market_failure_count = 0
            controller._shutdown_complete = False
            controller._mining_market_retry_timer = Mock()
            controller._schedule_mining_market_backup = Mock(return_value=True)
            controller._persist_json = Mock()
            controller.miningChanged = Mock()
            controller.stateChanged = Mock()

            result = {
                "id": "warm", "profileKey": "alpha", "generation": 3,
                "path": "market-cache.json", "success": True,
                "background": True, "warmKey": "cubeo\x1fpainite",
                "query": warm_query, "origin": {},
                "providerStatus": {
                    "ED-Frame": "OK (1 rows)",
                    "Ardent": "OK (1 rows)",
                    "EDData": "NOT NEEDED",
                },
                "markets": [{
                    "commodity": "painite", "station": "Warm Port",
                    "system": "Cubeo", "marketId": 9,
                    "sellPrice": 200000, "demand": 5000,
                    "observedAt": datetime.now(timezone.utc).isoformat(),
                }],
            }
            controller._persist_mining_market_result(
                result, controller._mining_market_store, threading.Lock(),
            )
            controller._finish_mining_market_sync(result)

            self.assertIs(controller._mining_market_cache, visible_cache)
            self.assertEqual(controller._mining_market_store.count(), 1)
            self.assertTrue(
                controller._mining_market_store.warm_targets()[0][
                    "lastSuccessAt"
                ]
            )
            controller._persist_json.assert_not_called()
            controller._mining_market_retry_timer.start.assert_called_with(60000)
            self.assertIn(
                "ED-Frame OK (1 rows)", controller._mining_market_status,
            )
            self.assertIn(
                "Ardent OK (1 rows)", controller._mining_market_status,
            )
            self.assertIn(
                "EDData NOT NEEDED", controller._mining_market_status,
            )

    def test_known_mining_origin_prefers_journal_then_cached_edsm(self):
        controller = CockpitController.__new__(CockpitController)
        controller._state = {
            "system": "Current", "currentPosition": [1, 2, 3],
        }
        controller._mining_market_cache = {
            "origin": {"system": "Cubeo", "coordinates": [4, 5, 6]},
        }
        controller._system_coordinate_index = Mock(return_value={})

        self.assertEqual(
            controller._known_mining_origin("current")["source"], "Journal",
        )
        self.assertEqual(
            controller._known_mining_origin("cubeo")["coordinates"],
            [4, 5, 6],
        )

    def test_community_overlap_is_searchable_without_confirmed_hotspot(self):
        controller = CockpitController.__new__(CockpitController)
        controller._mining_rows_cache_key = ("community",)
        controller._mining_rows = Mock(return_value=[{
            "system": "Reported", "ring": "Reported 1 A Ring",
            "distanceLy": 1, "observedAt": datetime.now(timezone.utc).isoformat(),
            "evidence": "LIVE_REPORTED", "ringTypeName": "Unknown",
            "hotspots": [], "communityOverlapReports": [{
                "commodity": "platinum", "reportedResTypes": ["HAZARDOUS"],
                "verifiedAt": None,
            }],
        }])
        rows = controller.miningFindPageForMethod(
            "Platinum", 100, "ALL EVIDENCE", "ALL RESERVES", "LASER")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["targetMatch"], "COMMUNITY_OVERLAP")
        self.assertNotIn("CONFIRMED", rows[0]["targetMatchName"])
        self.assertFalse(rows[0]["hotspots"])
        self.assertEqual(controller.miningFindPageForMethod(
            "Platinum", 100, "ALL EVIDENCE", "ALL RESERVES", "UNKNOWN METHOD"), [])

    def test_controller_ranks_observed_yield_before_hotspot_and_ring_type(self):
        controller = CockpitController.__new__(CockpitController)
        controller._mining_rows_cache_key = ("rank",)
        common = {
            "observedAt": datetime.now(timezone.utc).isoformat(),
            "reserveLevel": "PristineResources", "sourceCount": 1,
            "planetaryMiningLocationCount": 0,
        }
        controller._mining_rows = Mock(return_value=[{
            **common, "system": "Ring Type", "ring": "Ring Type A Ring",
            "distanceLy": 1.0, "distanceToArrivalLs": 100,
            "evidence": "LIVE_REPORTED", "ringTypeName": "Metallic",
            "hotspots": [],
        }, {
            **common, "system": "Hotspot", "ring": "Hotspot A Ring",
            "distanceLy": 2.0, "distanceToArrivalLs": 100,
            "evidence": "LIVE_REPORTED", "ringTypeName": "Metallic",
            "hotspots": [{"commodity": "platinum", "count": 1}],
            "sourceCount": 2,
        }, {
            **common, "system": "Observed Belt", "ring": "Observed A Belt",
            "distanceLy": 20.0, "distanceToArrivalLs": None,
            "evidence": "LOCAL_CONFIRMED", "ringTypeName": "Unknown",
            "hotspots": [], "prospectorSampleCount": 3,
            "yieldStats": [{
                "commodity": "platinum", "prospectorHits": 2,
                "averageProportion": 25.0, "refinedCount": 1,
            }],
        }, {
            **common, "system": "Negative Sample", "ring": "Negative A Ring",
            "distanceLy": 0.5, "distanceToArrivalLs": 50,
            "evidence": "LOCAL_CONFIRMED", "ringTypeName": "Metallic",
            "hotspots": [{"commodity": "platinum", "count": 1}],
            "prospectorSampleCount": 4, "yieldStats": [],
        }])

        rows = controller.miningFindPageForMethod(
            "Platinum", 100, "ALL EVIDENCE", "ALL RESERVES", "LASER"
        )

        self.assertEqual(
            [row["system"] for row in rows],
            ["Observed Belt", "Hotspot", "Ring Type", "Negative Sample"],
        )
        self.assertEqual(rows[0]["targetMatch"], "LOCAL_YIELD")
        self.assertIn("2/3 PROSPECTORS", rows[0]["targetMatchName"])
        self.assertIn("AVG 25.0%", rows[0]["targetMatchName"])
        self.assertIn("HOTSPOT CONFIRMED", rows[1]["targetMatchName"])
        self.assertIn("YIELD UNCONFIRMED", rows[2]["targetMatchName"])
        self.assertIn("NOT CONCLUSIVE", rows[3]["targetMatchName"])

    NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)

    def test_local_scan_and_saa_form_one_confirmed_ring_candidate(self):
        result = project_local_mining_evidence(FIXTURE["local_events"])

        self.assertEqual(len(result["candidates"]), 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["system"], "Synthetic Mining System")
        self.assertEqual(candidate["ring"], "Synthetic Mining System 1 A Ring")
        self.assertEqual(candidate["evidence"], "LOCAL_CONFIRMED")
        self.assertEqual(candidate["hotspots"], [
            {"commodity": "painite", "count": 1},
            {"commodity": "platinum", "count": 2},
        ])
        serialized = json.dumps(candidate)
        self.assertNotIn("must-not-project", serialized)
        self.assertNotIn("private display", serialized)

    def test_prospector_sample_is_not_falsely_bound_to_a_ring(self):
        result = project_local_mining_evidence(FIXTURE["local_events"])

        self.assertEqual(len(result["prospectorSamples"]), 1)
        sample = result["prospectorSamples"][0]
        self.assertFalse(sample["boundToRing"])
        self.assertEqual(sample["motherlode"], "alexandrite")
        self.assertEqual(sample["materials"], [
            {"commodity": "platinum", "proportion": 22.4},
        ])

    def test_ring_context_binds_and_aggregates_local_yield_until_departure(self):
        result = project_local_mining_evidence([{
            "event": "Location", "StarSystem": "Yield Test",
            "SystemAddress": 7, "StarPos": [1, 2, 3],
        }, {
            "event": "Scan", "timestamp": "2026-09-04T10:00:00Z",
            "BodyName": "Yield Test 2", "BodyID": 11,
            "ReserveLevel": "PristineResources", "Rings": [{
                "Name": "Yield Test 2 A Ring",
                "RingClass": "eRingClass_MetalRich",
            }],
        }, {
            "event": "SupercruiseExit", "timestamp": "2026-09-04T10:01:00Z",
            "StarSystem": "Yield Test", "SystemAddress": 7,
            "Body": "Yield Test 2 A Ring", "BodyID": 12,
            "BodyType": "PlanetaryRing",
        }, {
            "event": "ProspectedAsteroid", "timestamp": "2026-09-04T10:02:00Z",
            "Materials": [{"Name": "Platinum", "Proportion": 20.0}],
        }, {
            "event": "ProspectedAsteroid", "timestamp": "2026-09-04T10:03:00Z",
            "Materials": [{"Name": "Platinum", "Proportion": 30.0}],
        }, {
            "event": "ProspectedAsteroid", "timestamp": "2026-09-04T10:04:00Z",
            "Materials": [{"Name": "Osmium", "Proportion": 12.0}],
        }, {
            "event": "MiningRefined", "timestamp": "2026-09-04T10:05:00Z",
            "Type": "Platinum",
        }, {
            "event": "SupercruiseEntry", "timestamp": "2026-09-04T10:06:00Z",
            "StarSystem": "Yield Test", "SystemAddress": 7,
        }, {
            "event": "ProspectedAsteroid", "timestamp": "2026-09-04T10:07:00Z",
            "Materials": [{"Name": "Platinum", "Proportion": 99.0}],
        }])

        self.assertEqual(len(result["candidates"]), 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["prospectorSampleCount"], 3)
        platinum = next(
            row for row in candidate["yieldStats"]
            if row["commodity"] == "platinum"
        )
        self.assertEqual(platinum["prospectorHits"], 2)
        self.assertEqual(platinum["averageProportion"], 25.0)
        self.assertEqual(platinum["maxProportion"], 30.0)
        self.assertEqual(platinum["refinedCount"], 1)
        self.assertTrue(result["prospectorSamples"][0]["boundToRing"])
        self.assertFalse(result["prospectorSamples"][-1]["boundToRing"])

    def test_belt_location_context_safely_binds_local_yield(self):
        result = project_local_mining_evidence([{
            "event": "Location", "timestamp": "2026-09-04T10:00:00Z",
            "StarSystem": "Belt Test", "SystemAddress": 8,
            "StarPos": [1, 2, 3], "Body": "Belt Test A Belt Cluster 1",
            "BodyID": 2, "BodyType": "AsteroidCluster",
        }, {
            "event": "ProspectedAsteroid", "timestamp": "2026-09-04T10:01:00Z",
            "Materials": [{"Name": "Osmium", "Proportion": 12.5}],
        }, {
            "event": "MiningRefined", "timestamp": "2026-09-04T10:02:00Z",
            "Type": "Osmium",
        }])

        candidate = result["candidates"][0]
        self.assertEqual(candidate["ring"], "Belt Test A Belt Cluster 1")
        self.assertEqual(candidate["miningSiteType"], "BELT")
        self.assertEqual(candidate["prospectorSampleCount"], 1)
        self.assertEqual(candidate["yieldStats"][0]["commodity"], "osmium")
        self.assertEqual(candidate["yieldStats"][0]["refinedCount"], 1)

    def test_frontier_location_power_controller_is_bound_to_later_rings(self):
        result = project_local_mining_evidence([{
            "event": "FSDJump", "timestamp": "2026-09-04T10:00:00Z",
            "StarSystem": "Controlled", "SystemAddress": 81,
            "StarPos": [1, 2, 3], "ControllingPower": "Aisling Duval",
            "Powers": ["Aisling Duval", "Yuri Grom"],
            "PowerplayState": "Fortified",
        }, {
            "event": "Scan", "timestamp": "2026-09-04T10:01:00Z",
            "BodyName": "Controlled 4", "BodyID": 4,
            "ReserveLevel": "PristineResources", "Rings": [{
                "Name": "Controlled 4 A Ring",
                "RingClass": "eRingClass_Metalic",
            }],
        }])

        candidate = result["candidates"][0]
        self.assertEqual(candidate["controllingPower"], "Aisling Duval")
        self.assertEqual(candidate["powerState"], "Fortified")
        self.assertEqual(
            candidate["powers"], ["Aisling Duval", "Yuri Grom"]
        )

    def test_merge_combines_compact_local_yield_history(self):
        common = {
            "system": "Merge Test", "systemAddress": 9, "bodyId": 2,
            "ring": "Merge Test A Ring", "evidence": "LOCAL_CONFIRMED",
            "hotspots": [],
        }
        merged = merge_mining_candidates([{
            **common, "observedAt": "2026-09-04T10:00:00Z",
            "prospectorSampleCount": 2, "yieldStats": [{
                "commodity": "platinum", "prospectorHits": 1,
                "proportionTotal": 20.0, "proportionSamples": 1,
                "averageProportion": 20.0, "maxProportion": 20.0,
                "refinedCount": 1, "lastObservedAt": "2026-09-04T10:00:00Z",
            }],
        }, {
            **common, "observedAt": "2026-09-04T11:00:00Z",
            "prospectorSampleCount": 3, "yieldStats": [{
                "commodity": "platinum", "prospectorHits": 2,
                "proportionTotal": 60.0, "proportionSamples": 2,
                "averageProportion": 30.0, "maxProportion": 35.0,
                "refinedCount": 4, "lastObservedAt": "2026-09-04T11:00:00Z",
            }],
        }], now=self.NOW)[0]

        self.assertEqual(merged["prospectorSampleCount"], 5)
        self.assertEqual(merged["yieldStats"][0]["prospectorHits"], 3)
        self.assertAlmostEqual(
            merged["yieldStats"][0]["averageProportion"], 80 / 3, places=3
        )
        self.assertEqual(merged["yieldStats"][0]["maxProportion"], 35.0)
        self.assertEqual(merged["yieldStats"][0]["refinedCount"], 5)

    def test_community_yield_does_not_double_count_the_local_contributor(self):
        common = {
            "system": "Merge Test", "systemAddress": 9,
            "ring": "Merge Test A Ring", "evidence": "LOCAL_CONFIRMED",
            "hotspots": [],
        }
        local = {
            **common, "yieldAggregationScope": "LOCAL",
            "prospectorSampleCount": 2, "yieldStats": [{
                "commodity": "platinum", "prospectorHits": 2,
                "proportionSamples": 2, "proportionTotal": 50.0,
                "averageProportion": 25.0, "maxProportion": 30.0,
                "refinedCount": 1,
            }],
        }
        community = {
            **common, "yieldAggregationScope": "COMMUNITY",
            "prospectorSampleCount": 2, "yieldStats": [{
                "commodity": "platinum", "prospectorHits": 2,
                "proportionSamples": 2, "proportionTotal": 50.0,
                "averageProportion": 25.0, "maxProportion": 30.0,
            }],
        }
        merged = merge_mining_candidates([local, community], now=self.NOW)[0]
        self.assertEqual(merged["prospectorSampleCount"], 2)
        self.assertEqual(merged["yieldStats"][0]["proportionSamples"], 2)
        self.assertEqual(merged["yieldStats"][0]["averageProportion"], 25.0)
        self.assertEqual(merged["yieldStats"][0]["refinedCount"], 1)

    def test_spansh_dump_projects_catalog_candidate_and_source_timestamp(self):
        candidates = project_spansh_mining_candidates(
            FIXTURE["spansh_dump"], origin=[10.0, 20.0, 30.0]
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["evidence"], "CATALOG_CANDIDATE")
        self.assertEqual(candidate["distanceLy"], 5.0)
        self.assertEqual(candidate["ringType"], "Metallic")
        self.assertEqual(candidate["reserveLevel"], "MajorResources")
        self.assertEqual(candidate["observedAt"], "2026-09-02T13:00:00Z")
        self.assertEqual(candidate["hotspots"], [
            {"commodity": "platinum", "count": 1},
        ])

    def test_central_catalog_projects_ring_and_normalized_hotspots(self):
        candidates = project_edframe_mining_candidates({"results": [{
            "systemAddress": 42, "system": "Cubeo",
            "x": 3, "y": 4, "z": 0, "bodyId": 7,
            "body": "Cubeo 5", "ring": "Cubeo 5 A Ring",
            "ringType": "Metallic", "reserveLevel": "PristineResources",
            "distanceToArrivalLs": 1200,
            "hotspots": [{"commodity": "platinum", "count": 2}],
            "evidence": "LIVE_REPORTED", "source": "EDDN journal/1",
            "observedAt": "2026-10-03T10:00:00Z",
            "receivedAt": "2026-10-03T10:00:01Z",
        }]}, origin=[0, 0, 0])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["distanceLy"], 5.0)
        self.assertEqual(candidates[0]["hotspots"], [
            {"commodity": "platinum", "count": 2},
        ])
        self.assertIn("ED-Frame live catalog", candidates[0]["source"])

    def test_spansh_dump_retains_verified_market_demand_for_route_scoring(self):
        payload = json.loads(json.dumps(FIXTURE["spansh_dump"]))
        payload["system"]["controllingPower"] = "Aisling Duval"
        payload["system"]["powerState"] = "Reinforcement"
        payload["system"]["stations"] = [{
            "name": "Synthetic Mining Exchange",
            "distanceToArrival": 412.5,
            "landingPadSize": "L",
            "updateTime": "2026-09-02T13:05:00Z",
            "commodities": [{
                "name": "Platinum",
                "sellPrice": 287321,
                "demand": 15420,
            }],
        }]

        candidate = project_spansh_mining_candidates(payload)[0]

        self.assertEqual(candidate["controllingPower"], "Aisling Duval")
        self.assertEqual(candidate["powerState"], "Reinforcement")
        self.assertEqual(candidate["markets"], [{
            "commodity": "platinum",
            "station": "Synthetic Mining Exchange",
            "system": payload["system"]["name"],
            "sellPrice": 287321,
            "demand": 15420,
            "observedAt": "2026-09-02T13:05:00Z",
            "landingPadSize": "L",
            "distanceToArrivalLs": 412.5,
            "controllingPower": "Aisling Duval",
            "powerState": "Reinforcement",
            "powers": [],
            "systemState": "",
            "source": "Spansh system dump market",
        }])

    def test_invalid_or_partial_spansh_payload_stays_empty_or_unknown(self):
        self.assertEqual(project_spansh_mining_candidates({}), [])
        candidates = project_spansh_mining_candidates({
            "system": {
                "name": "Partial", "bodies": [{
                    "name": "Partial 1", "rings": [{"name": "A Ring"}],
                }],
            },
        })
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["hotspots"], [])
        self.assertEqual(candidates[0]["reserveLevel"], "")
        self.assertIsNone(candidates[0]["distanceLy"])

    def test_confirmation_age_never_invalidates_the_location_evidence(self):
        fresh = mining_candidate_freshness({
            "evidence": "LIVE_REPORTED",
            "observedAt": "2026-09-04T11:00:00Z",
        }, now=self.NOW)
        old = mining_candidate_freshness({
            "evidence": "LIVE_REPORTED",
            "observedAt": "2026-09-03T11:59:59Z",
        }, now=self.NOW)
        undated = mining_candidate_freshness({
            "evidence": "CATALOG_CANDIDATE", "observedAt": "",
        }, now=self.NOW)

        self.assertEqual(fresh["evidence"], "LIVE_REPORTED")
        self.assertFalse(fresh["stale"])
        self.assertEqual(old["evidence"], "LIVE_REPORTED")
        self.assertTrue(old["stale"])
        self.assertTrue(old["recheckRecommended"])
        self.assertEqual(old["confirmationStatus"], "RECHECK_RECOMMENDED")
        self.assertEqual(undated["evidence"], "CATALOG_CANDIDATE")
        self.assertEqual(
            undated["confirmationStatus"], "CONFIRMATION_TIME_UNKNOWN"
        )

    def test_merge_prefers_local_fields_and_preserves_all_sources(self):
        common = {
            "system": "Synthetic Mining System",
            "systemAddress": 123456789,
            "body": "Synthetic Mining System 1",
            "bodyId": 4,
            "ring": "Synthetic Mining System 1 A Ring",
            "distanceLy": 12.5,
        }
        catalog = {
            **common, "evidence": "CATALOG_CANDIDATE",
            "observedAt": "2026-09-04T11:30:00Z",
            "source": "Spansh dump catalog", "ringType": "Metallic",
            "reserveLevel": "MajorResources",
            "hotspots": [{"commodity": "painite", "count": 1}],
        }
        live = {
            **common, "evidence": "LIVE_REPORTED",
            "observedAt": "2026-09-04T11:40:00Z",
            "source": "EDDN journal/1", "ringType": "Metal Rich",
            "hotspots": [{"commodity": "platinum", "count": 2}],
        }
        local = {
            **common, "evidence": "LOCAL_CONFIRMED",
            "observedAt": "2026-09-04T11:20:00Z",
            "source": "Frontier Journal", "ringType": "eRingClass_Metalic",
            "reserveLevel": "", "hotspots": [
                {"commodity": "platinum", "count": 1},
            ],
        }

        merged = merge_mining_candidates(
            [catalog, live, local], now=self.NOW
        )

        self.assertEqual(len(merged), 1)
        candidate = merged[0]
        self.assertEqual(candidate["evidence"], "LOCAL_CONFIRMED")
        self.assertEqual(candidate["ringType"], "eRingClass_Metalic")
        self.assertEqual(candidate["reserveLevel"], "MajorResources")
        self.assertEqual(candidate["sourceCount"], 3)
        self.assertEqual(
            [row["sourceEvidence"] for row in candidate["observations"]],
            ["LOCAL_CONFIRMED", "LIVE_REPORTED", "CATALOG_CANDIDATE"],
        )
        self.assertEqual(candidate["hotspots"], [
            {"commodity": "painite", "count": 1},
            {"commodity": "platinum", "count": 1},
        ])

        remerged = merge_mining_candidates(
            [candidate], now=self.NOW + timedelta(minutes=5)
        )[0]
        self.assertEqual(remerged["sourceCount"], 3)
        self.assertEqual(remerged["observations"], candidate["observations"])

    def test_merge_uses_stable_identity_and_sorts_known_distance_first(self):
        candidates = [{
            "system": "Far", "systemAddress": 20, "bodyId": 1,
            "ring": "A Ring", "distanceLy": None,
            "evidence": "CATALOG_CANDIDATE",
            "observedAt": "2026-09-04T11:00:00Z",
        }, {
            "system": "Near", "systemAddress": 10, "bodyId": 1,
            "ring": "A Ring", "distanceLy": 4.0,
            "evidence": "CATALOG_CANDIDATE",
            "observedAt": "2026-09-04T11:00:00Z",
        }, {
            "system": "Renamed Near", "systemAddress": 10, "bodyId": 1,
            "ring": "A Ring", "distanceLy": 4.0,
            "evidence": "LIVE_REPORTED",
            "observedAt": "2026-09-04T11:30:00Z",
        }]

        merged = merge_mining_candidates(candidates, now=self.NOW)

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["systemAddress"], 10)
        self.assertEqual(merged[0]["sourceCount"], 2)
        self.assertEqual(merged[1]["systemAddress"], 20)


if __name__ == "__main__":
    unittest.main()
