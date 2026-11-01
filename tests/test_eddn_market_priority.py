"""Station uploads may bypass signal backlogs without changing delivery guards."""

from copy import deepcopy
import time
import unittest
from unittest.mock import Mock

from ed_companion.phase14.controller import CockpitController


def job(identifier, schema="fsssignaldiscovered/1", **overrides):
    return {"id": identifier, "event": {"schema": schema, "message": {}},
            "context": {}, "status": "queued", "profile_key": "test-profile",
            **overrides}


class EddnMarketPriorityTests(unittest.TestCase):
    def setUp(self):
        self.c = CockpitController.__new__(CockpitController)
        self.c._sync_eddn_profile = lambda: True
        self.c._eddn_busy = False
        self.c._eddn_profile_key = "test-profile"
        self.c._eddn_config = {"consent": True, "upload_enabled": True, "uploader_id": "anonymous"}
        self.c._save_eddn = Mock()
        self.c._publish_eddn_delivery_change = Mock()
        self.c.connectionChanged = Mock()
        self.c._start_network_worker = Mock(return_value=True)

    def selected(self, rows):
        self.c._eddn_queue = deepcopy(rows)
        self.c._process_eddn_queue()
        return [r["id"] for r in self.c._eddn_queue if r["status"] == "sending"]

    def test_live_market_bypasses_signal_backlog_without_dropping_it(self):
        rows = [job(str(i)) for i in range(126)] + [job("market", "commodity/3")]
        self.assertEqual(self.selected(rows), ["market"])
        self.assertEqual(sum(r["status"] == "queued" for r in self.c._eddn_queue), 126)

    def test_journal_and_capi_markets_keep_their_original_order(self):
        self.assertEqual(self.selected([job("signal"), job("journal", "commodity/3"),
            job("capi", "commodity/3")]), ["journal"])

    def test_ship_and_module_inventories_also_bypass_signals(self):
        for schema in ("outfitting/2", "outfitting/3", "shipyard/2"):
            with self.subTest(schema=schema):
                self.c._eddn_busy = False
                self.assertEqual(self.selected([job("signal"), job("station", schema)]), ["station"])

    def test_backoff_and_completed_markets_do_not_block_due_signals(self):
        self.assertEqual(self.selected([
            job("retry", "commodity/3", status="retry", next_retry_at=time.time() + 3600),
            job("done", "commodity/3", status="sent"), job("signal")]), ["signal"])

    def test_foreign_market_is_rejected_before_any_transmission(self):
        self.assertEqual(self.selected([job("signal"), job("foreign", "commodity/3", profile_key="other")]), [])
        self.assertEqual(self.c._eddn_queue[-1]["status"], "failed")
        self.c._start_network_worker.assert_not_called()

    def test_upload_switch_and_profile_gate_still_block_transmission(self):
        self.c._eddn_config["upload_enabled"] = False
        self.assertEqual(self.selected([job("market", "commodity/3")]), [])
        self.c._eddn_config["upload_enabled"] = True
        self.c._sync_eddn_profile = lambda: False
        self.assertEqual(self.selected([job("market", "commodity/3")]), [])
        self.c._start_network_worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
