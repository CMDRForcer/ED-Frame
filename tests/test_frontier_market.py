"""CAPI carrier market publication, identity and delivery regressions."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import gzip
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ed_companion.integrations.eddn import envelope, send, validate_prepared
from ed_companion.integrations.frontier_capi import FrontierCapiClient, FrontierCapiError
from ed_companion.integrations.frontier_market import (
    CAPI_MARKET_CONTEXT, FrontierMarketError, prepare_capi_market,
)
from ed_companion.phase14.controller import CockpitController


def fixtures():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    at = now.isoformat().replace("+00:00", "Z")
    profile = {"observedAt": at, "payload": {
        "commander": {"name": "Test Commander", "docked": True, "credits": 123},
        "lastSystem": {"name": "Test System"},
        "lastStarport": {"id": 42, "name": "Test Carrier"},
        "privateToken": "never-public",
    }}
    market = {"observedAt": at, "payload": {
        "id": 42, "name": "ABC-123", "commodities": [{
            "name": "Indite", "meanPrice": 0, "buyPrice": 0, "stock": 0,
            "stockBracket": 0, "sellPrice": 29964, "demand": 18702,
            "demandBracket": 2, "statusFlags": ["Consumer"],
            "private": "never-public",
        }],
    }}
    context = {"StarSystem": "Test System", "MarketID": 42,
               "StationType": "FleetCarrier", "CarrierDockingAccess": "all",
               "horizons": True, "odyssey": True, "gameversion": "4.4.2.1"}
    return profile, market, context, now


class FrontierMarketProjectionTests(unittest.TestCase):
    def setUp(self):
        self.profile, self.market, self.context, self.now = fixtures()

    def prepare(self):
        return prepare_capi_market(self.profile, self.market,
                                   commander="Test Commander", context=self.context, now=self.now)

    def test_carrier_purchase_order_keeps_zero_stock_and_real_demand(self):
        prepared = self.prepare()
        self.assertTrue(validate_prepared(prepared))
        row = prepared["message"]["commodities"][0]
        self.assertEqual((row["stock"], row["sellPrice"], row["demand"]), (0, 29964, 18702))
        self.assertEqual(prepared["message"]["marketId"], 42)
        wire = envelope(prepared, CAPI_MARKET_CONTEXT, "anonymous")
        self.assertEqual(wire["header"]["gameversion"], "CAPI-Live-market")
        self.assertNotIn("Test Commander", json.dumps(wire))
        self.assertNotIn("never-public", json.dumps(wire))

    def test_explicit_empty_orders_can_clear_a_carrier_market(self):
        self.market["payload"]["commodities"] = []
        prepared = self.prepare()
        self.assertEqual(prepared["message"]["commodities"], [])
        self.assertTrue(validate_prepared(prepared))

    def test_missing_null_or_invalid_inventory_is_never_an_empty_upload(self):
        for value in (None, {}, "unavailable"):
            with self.subTest(value=value):
                self.market["payload"]["commodities"] = value
                with self.assertRaises(FrontierMarketError):
                    self.prepare()
        self.market["payload"].pop("commodities")
        with self.assertRaises(FrontierMarketError):
            self.prepare()

    def test_incomplete_commodity_rejects_the_entire_snapshot(self):
        good = deepcopy(self.market["payload"]["commodities"][0])
        self.market["payload"]["commodities"].append({"name": "Gold", "stock": 123})
        with self.assertRaises(FrontierMarketError):
            self.prepare()
        self.assertEqual(self.market["payload"]["commodities"][0], good)

    def test_invalid_price_and_quantity_values_are_rejected(self):
        row = self.market["payload"]["commodities"][0]
        for key, value in (("stock", -1), ("demand", True), ("buyPrice", float("nan")),
                           ("sellPrice", float("inf")), ("stockBracket", 4), ("demandBracket", 1.5)):
            with self.subTest(key=key, value=value):
                original = row[key]
                row[key] = value
                with self.assertRaises(FrontierMarketError):
                    self.prepare()
                row[key] = original

    def test_prohibited_and_nonmarketable_goods_are_excluded(self):
        rows = self.market["payload"]["commodities"]
        rows.extend([{"name": "Narcotics", "legality": "Illegal"},
                     {"name": "PowerGoods", "categoryname": "NonMarketable"}])
        result = self.prepare()["message"]
        self.assertEqual([row["name"] for row in result["commodities"]], ["indite"])
        self.assertEqual(result["prohibited"], ["narcotics"])

    def test_duplicate_goods_are_not_silently_merged(self):
        rows = self.market["payload"]["commodities"]
        rows.append(deepcopy(rows[0]))
        with self.assertRaises(FrontierMarketError):
            self.prepare()

    def test_commander_station_and_docking_identity_must_match(self):
        changes = (
            (self.profile["payload"]["commander"], "name", "Other Commander"),
            (self.profile["payload"]["commander"], "docked", False),
            (self.profile["payload"]["lastStarport"], "id", 43),
            (self.profile["payload"]["lastSystem"], "name", "Other System"),
            (self.market["payload"], "id", 43),
            (self.context, "MarketID", None),
        )
        for container, key, value in changes:
            with self.subTest(key=key, value=value):
                original = container[key]
                container[key] = value
                with self.assertRaises(FrontierMarketError):
                    self.prepare()
                container[key] = original

    def test_old_future_or_unzoned_market_times_are_rejected(self):
        for value in ((self.now - timedelta(minutes=6)).isoformat(),
                      (self.now + timedelta(minutes=3)).isoformat(), "2026-11-01T12:00:00", ""):
            with self.subTest(value=value):
                self.market["observedAt"] = value
                with self.assertRaises(FrontierMarketError):
                    self.prepare()

    def test_newer_journal_market_takes_precedence(self):
        self.context["marketContext"] = {"MarketID": 42,
            "timestamp": (self.now + timedelta(seconds=1)).isoformat()}
        with self.assertRaisesRegex(FrontierMarketError, "newer Journal"):
            self.prepare()


class FrontierMarketDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.profile, self.market, context, _now = fixtures()
        self.prepared = prepare_capi_market(self.profile, self.market,
                                          commander="Test Commander", context=context)
        c = self.c = CockpitController.__new__(CockpitController)
        c._state = {"commander": "Test Commander"}
        c._eddn_context = context
        c._eddn_queue = []
        c._eddn_config = {"consent": True, "upload_enabled": True}
        c._eddn_profile_key = "test-profile"
        c._frontier_config = {"consent": True}
        c._frontier_busy = False
        c._frontier_request_token = 0
        c._profile_generation = 1
        c._frontier_tokens = SimpleNamespace(access_token="access-private", refresh_token="refresh-private",
            token_type="Bearer", expires_within=lambda seconds: False)
        c._frontier_client = Mock()
        c._frontier_watchdog = Mock()
        c._frontier_credential_store = Mock()
        c._frontier_last_sync = ""
        c._frontier_market_state = {}
        c._mining_market_store = None
        c._apply_frontier_profile = Mock()
        c._save_eddn = Mock(return_value=True)
        c._publish_eddn_delivery_change = Mock()
        c.connectionChanged = Mock()
        c.frontierFinished = Mock()
        self.workers = []
        c._start_network_worker = lambda target, _name: self.workers.append(target) or True

    def run_request(self, market=None):
        self.c._frontier_client.query_many.return_value = {
            "/profile": self.profile, "/market": market or self.market,
            "/shipyard": {"observedAt": self.market["observedAt"], "payload": {}},
        }
        self.c._start_frontier_profile_request(tokens=self.c._frontier_tokens)
        self.workers[-1]()
        result = self.c.frontierFinished.emit.call_args.args[0]
        self.c._finish_frontier(result)
        return result

    def test_refresh_bundles_market_and_preserves_profile_on_market_failure(self):
        result = self.run_request({"error": "Frontier market unavailable."})
        self.assertTrue(result["profile"])
        self.assertIn("unavailable", result["marketError"])
        self.assertEqual(self.c._eddn_queue, [])
        self.assertFalse(self.c._frontier_busy)
        self.c._apply_frontier_profile.assert_called_once()
        self.assertEqual(self.c._frontier_market_view()["stage"], "UNAVAILABLE")

    def test_complete_refresh_queues_public_market_with_capi_provenance(self):
        self.run_request()
        self.c._frontier_client.query_many.assert_called_once_with(
            ("/profile", "/shipyard", "/market"), optional_endpoints=("/shipyard", "/market"))
        self.assertEqual(len(self.c._eddn_queue), 1)
        job = self.c._eddn_queue[0]
        self.assertEqual(job["context"], CAPI_MARKET_CONTEXT)
        self.assertEqual(self.c._frontier_market_view()["stage"], "QUEUED")

    def test_disabled_eddn_still_reads_but_does_not_queue(self):
        self.c._eddn_config["upload_enabled"] = False
        self.run_request()
        self.assertEqual(self.c._eddn_queue, [])
        self.assertEqual(self.c._frontier_market_view()["stage"], "LOCAL_ONLY")

    def test_withdrawn_frontier_consent_starts_no_worker(self):
        self.c._frontier_config["consent"] = False
        self.c._start_frontier_profile_request(tokens=self.c._frontier_tokens)
        self.assertEqual(self.workers, [])

    def test_withdrawing_consent_invalidates_an_inflight_market(self):
        self.c._save_frontier_config = Mock()
        self.c._frontier_busy = True
        self.c._frontier_request_token = 7
        self.c.setFrontierConsent(False)
        self.c._finish_frontier({"requestToken": 7, "profileGeneration": 1,
                                "market": self.prepared, "profile": {"credits": 123}})
        self.assertEqual(self.c._eddn_queue, [])
        self.c._apply_frontier_profile.assert_not_called()

    def test_same_recent_journal_contents_do_not_upload_twice(self):
        self.c._enqueue_eddn(self.prepared)
        self.c._accept_frontier_market(self.prepared)
        self.assertEqual(len(self.c._eddn_queue), 1)
        self.assertEqual(self.c._frontier_market_view()["stage"], "QUEUED")

    def test_changed_demand_is_a_new_market_observation(self):
        self.c._enqueue_eddn(self.prepared)
        changed = deepcopy(self.prepared)
        changed["message"]["commodities"][0]["demand"] = 10000
        self.c._accept_frontier_market(changed)
        self.assertEqual(len(self.c._eddn_queue), 2)

    def test_same_contents_after_five_minutes_can_reconfirm_freshness(self):
        old = deepcopy(self.prepared)
        old["message"]["timestamp"] = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
        self.c._enqueue_eddn(old)
        self.c._accept_frontier_market(self.prepared)
        self.assertEqual(len(self.c._eddn_queue), 2)

    def test_newer_queued_market_is_not_overwritten(self):
        newer = deepcopy(self.prepared)
        newer["message"]["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        self.c._enqueue_eddn(newer)
        self.c._accept_frontier_market(self.prepared)
        self.assertEqual(len(self.c._eddn_queue), 1)
        self.assertEqual(self.c._frontier_market_view()["stage"], "UNCHANGED")

    def test_station_change_during_request_blocks_publication(self):
        self.c._eddn_context["MarketID"] = 43
        self.c._accept_frontier_market(self.prepared)
        self.assertEqual(self.c._eddn_queue, [])
        self.assertEqual(self.c._frontier_market_view()["stage"], "UNAVAILABLE")

    def test_gateway_receipt_updates_status_and_survives_queue_archival(self):
        self.c._accept_frontier_market(self.prepared)
        job = self.c._eddn_queue[0]
        captured = []
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self, _limit): return b"OK"
        def gateway(request, **_kwargs):
            captured.append(json.loads(gzip.decompress(request.data)))
            return Response()
        receipt = send(job["event"], job["context"], "anonymous", opener=gateway)
        with patch("ed_companion.phase14.controller_eddn.QTimer.singleShot"):
            self.c._finish_eddn(job["id"], True, json.dumps(receipt))
        self.assertEqual(self.c._frontier_market_view()["stage"], "ACCEPTED")
        self.assertEqual(captured[0]["header"]["gameversion"], "CAPI-Live-market")
        self.assertNotIn("private", json.dumps(captured))
        self.c._eddn_queue = []
        self.assertEqual(self.c._frontier_market_view()["stage"], "ACCEPTED")
        self.c._frontier_market_state = {}
        self.assertEqual(self.c._frontier_market_view()["stage"], "ACCEPTED")

    def test_timeout_invalidates_late_results(self):
        self.c._frontier_busy = True
        self.c._frontier_request_token = 7
        self.c._frontier_request_timed_out()
        self.c._finish_frontier({"requestToken": 7, "profileGeneration": 1,
                                "market": self.prepared, "profile": {"credits": 123}})
        self.assertEqual(self.c._eddn_queue, [])
        self.c._apply_frontier_profile.assert_not_called()


class OptionalMarketTransportTests(unittest.TestCase):
    def test_optional_market_error_keeps_profile_and_bundle_rate_limit(self):
        from tests.test_frontier_capi import FakeResponse, FakeSession
        session = FakeSession([FakeResponse(200, {"commander": {}}), FakeResponse(503, {})])
        sleeps = []
        client = FrontierCapiClient("private", session=session, clock=lambda: 0.0, sleeper=sleeps.append)
        result = client.query_many(("/profile", "/market"), optional_endpoints=("/market",))
        self.assertIn("/profile", result)
        self.assertIn("503", result["/market"]["error"])
        self.assertEqual(sleeps, [0.55])
        with self.assertRaises(FrontierCapiError):
            session.responses.append(FakeResponse(503, {}))
            client.query_many(("/profile",), optional_endpoints=("/market",))

    def test_optional_shipyard_rate_limit_pauses_market_and_honors_retry_after(self):
        from tests.test_frontier_capi import FakeResponse, FakeSession
        session = FakeSession([FakeResponse(200, {"commander": {}}),
            FakeResponse(429, {}, {"Retry-After": "90"}), FakeResponse(200, {"commander": {}})])
        sleeps = []
        client = FrontierCapiClient("private", session=session, clock=lambda: 0.0, sleeper=sleeps.append)
        result = client.query_many(("/profile", "/shipyard", "/market"),
                                   optional_endpoints=("/shipyard", "/market"))
        self.assertEqual(len(session.calls), 2)
        self.assertIn("paused", result["/market"]["error"])
        with self.assertRaises(FrontierCapiError) as raised:
            client.query("/profile")
        self.assertEqual(raised.exception.retry_after, 90)
        self.assertEqual(sleeps, [0.55])
        self.assertEqual(len(session.calls), 2)


if __name__ == "__main__":
    unittest.main()
