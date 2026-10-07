import unittest
from unittest.mock import MagicMock
from edframe_catalog.mining_metadata import enrich_ring_metadata


class RingMetadataTests(unittest.TestCase):
    def enrich(self, row, metadata):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = metadata
        return enrich_ring_metadata(conn, [row])[0]

    def test_parent_body_metadata_enriches_ring_without_changing_id(self):
        row = dict(system="HIP 1", systemAddress=1, ring="HIP 1 A Ring", bodyId=12, ringType="", reserveLevel="", yieldStats=[1])
        result = self.enrich(row, [dict(system_name="HIP 1", system_address=1, ring_name="HIP 1 A Ring", ring_type="Metallic", reserve_level="Pristine", source="Scan", observed_at="2026-10-07")])
        self.assertEqual(result["ringType"], "Metallic")
        self.assertEqual(result["bodyId"], 12)
        self.assertEqual(result["yieldStats"], [1])
        self.assertEqual(result["ringMetadataEvidence"][0]["source"], "Scan")

    def test_wrong_ring_and_system_address_are_excluded(self):
        row = dict(system="HIP 1", systemAddress=1, ring="HIP 1 A Ring")
        result = self.enrich(row, [dict(system_name="HIP 1", system_address=2, ring_name="HIP 1 A Ring", ring_type="Metallic"), dict(system_name="HIP 1", system_address=1, ring_name="HIP 1 B Ring", ring_type="Rocky")])
        self.assertNotIn("ringType", result)

    def test_conflict_stays_unknown_and_known_field_is_preserved(self):
        metadata = [dict(system_name="HIP 1", ring_name="A", ring_type=value, reserve_level="Pristine") for value in ("Metallic", "Rocky")]
        result = self.enrich(dict(system="HIP 1", ring="A"), metadata)
        self.assertNotIn("ringType", result)
        self.assertEqual(result["reserveLevel"], "Pristine")
        result = self.enrich(dict(system="HIP 1", ring="A", ringType="Icy"), metadata)
        self.assertEqual(result["ringType"], "Icy")

    def test_complete_rows_do_not_trigger_query(self):
        conn = MagicMock()
        enrich_ring_metadata(conn, [dict(system="HIP 1", ring="A", ringType="Metallic", reserveLevel="Pristine")])
        conn.execute.assert_not_called()
