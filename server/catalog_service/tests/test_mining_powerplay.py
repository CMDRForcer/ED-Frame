import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from edframe_catalog.api import search_mining_powerplay
from edframe_catalog.database import upsert_powerplay_snapshot
from edframe_catalog.projection import project_powerplay_snapshot


class MiningPowerplayServerTests(unittest.TestCase):
    def payload(self):
        return {"$schemaRef": "https://eddn.edcd.io/schemas/journal/1",
            "message": {"event": "FSDJump", "StarSystem": "Cubeo",
                "SystemAddress": 42, "StarPos": [1, 2, 3],
                "Powers": ["Aisling Duval", "Zachary Hudson"],
                "ControllingPower": "Aisling Duval", "PowerplayState": "Stronghold",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "Commander": "PRIVATE", "Ship": "PRIVATE"}}

    def test_projection_is_public_and_control_is_explicit(self):
        payload = self.payload()
        row = project_powerplay_snapshot(payload, payload["message"]["timestamp"])
        self.assertEqual(row["identity"], "cubeo")
        facts = json.loads(row["facts"])
        self.assertEqual(len(facts), 2)
        self.assertEqual(facts[0]["powerRelationship"], "CONTROL")
        self.assertEqual(facts[1]["powerRelationship"], "PRESENCE")
        self.assertNotIn("PRIVATE", json.dumps(row))

    def test_presence_does_not_become_control(self):
        payload = self.payload()
        payload["message"].pop("ControllingPower")
        row = project_powerplay_snapshot(payload, payload["message"]["timestamp"])
        self.assertTrue(all(not fact["controlKnown"] for fact in json.loads(row["facts"])))

    def test_rejects_other_schemas_and_invalid_timestamp(self):
        payload = self.payload()
        payload["$schemaRef"] = "https://eddn.edcd.io/schemas/commodity/3"
        self.assertIsNone(project_powerplay_snapshot(payload, ""))
        payload = self.payload()
        payload["message"]["timestamp"] = "broken"
        self.assertIsNone(project_powerplay_snapshot(payload, ""))

    def test_upsert_replaces_system_snapshot_only_if_not_older(self):
        connection = MagicMock()
        self.assertEqual(upsert_powerplay_snapshot(connection, None), 0)
        row = project_powerplay_snapshot(self.payload(), datetime.now(timezone.utc).isoformat())
        self.assertEqual(upsert_powerplay_snapshot(connection, row), 1)
        sql = connection.execute.call_args.args[0]
        self.assertIn("ON CONFLICT (identity)", sql)
        self.assertIn("EXCLUDED.observed_at >= mining_powerplay.observed_at", sql)

    def test_api_is_bounded_fresh_and_reports_truncation(self):
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = [
            {"facts": [{"system": "One"}]}, {"facts": [{"system": "Two"}]}]
        with patch("edframe_catalog.api.connection") as factory:
            factory.return_value.__enter__.return_value = connection
            result = search_mining_powerplay(1, 2, 3, max_distance=100, limit=1)
        self.assertEqual(result["results"], [{"system": "One"}])
        self.assertTrue(result["hasMore"])
        sql, values = connection.execute.call_args.args
        self.assertIn("INTERVAL '1 hour'", sql)
        self.assertEqual(values, (24, 1, 2, 3, 100, 2))
