import io
import json
import os
import unittest
from unittest.mock import patch
from edframe_catalog.outfitting_write_policy import (
    require_outfitting_reader, shared_outfitting_writes_enabled,
)
from edframe_catalog.database import _replace_normalized_station_offers


class Connection:
    def __init__(self): self.calls = []
    def execute(self, sql, params): self.calls.append((sql, params)); return self


class OutfittingWritePolicyTests(unittest.TestCase):
    def test_sparse_writes_are_opt_in(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(shared_outfitting_writes_enabled())
            with patch("edframe_catalog.outfitting_write_policy.urlopen") as call:
                require_outfitting_reader()
            call.assert_not_called()

    def test_sparse_collector_refuses_legacy_reader(self):
        with patch.dict(os.environ, {"EDFRAME_SHARED_OUTFITTING_FRESHNESS": "1"}):
            with patch("edframe_catalog.outfitting_write_policy.urlopen",
                       return_value=io.BytesIO(b'{"status":"ok"}')):
                with self.assertRaises(RuntimeError):
                    require_outfitting_reader()

    def test_sparse_collector_accepts_compatible_reader(self):
        body=json.dumps({"capabilities":{"sharedOutfittingFreshness":True}}).encode()
        with patch.dict(os.environ, {"EDFRAME_SHARED_OUTFITTING_FRESHNESS": "1"}):
            with patch("edframe_catalog.outfitting_write_policy.urlopen",
                       return_value=io.BytesIO(body)):
                require_outfitting_reader()

    def test_sparse_filter_preserves_price_verification_times(self):
        conn=Connection()
        with patch.dict(os.environ, {"EDFRAME_SHARED_OUTFITTING_FRESHNESS": "1"}):
            _replace_normalized_station_offers(conn,{},kind="OUTFITTING",
                                               parent_table="station_outfitting")
        sql=conn.calls[0][0]
        self.assertIn("LEFT JOIN station_module_offers retained",sql)
        self.assertIn("incoming.price_observed_at >= retained.price_observed_at",sql)
        self.assertIn("observed_at = station_module_offers.observed_at",sql)
        self.assertIn("EXCLUDED.price_observed_at >=",sql)
        self.assertIn("IS DISTINCT FROM",sql)

    def test_shipyard_keeps_existing_partial_inventory_semantics(self):
        conn=Connection()
        with patch.dict(os.environ, {"EDFRAME_SHARED_OUTFITTING_FRESHNESS": "1"}):
            _replace_normalized_station_offers(conn,{},kind="SHIPYARD",
                                               parent_table="station_shipyards")
        self.assertIn("observed_at = EXCLUDED.observed_at",conn.calls[0][0])
        self.assertNotIn("LEFT JOIN station_ship_offers retained",conn.calls[0][0])


if __name__ == "__main__": unittest.main()
