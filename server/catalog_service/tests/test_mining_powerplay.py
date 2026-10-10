import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from edframe_catalog.api import search_mining_powerplay, _decode_state_cursor, _encode_state_cursor
from fastapi import HTTPException
from edframe_catalog.database import upsert_powerplay_snapshot
from edframe_catalog.projection import project_powerplay_snapshot


class MiningPowerplayServerTests(unittest.TestCase):
    def test_power_filter_precedes_page_limit_and_exact_lookups_remain_unfiltered(self):
        conn=MagicMock();conn.execute.return_value.fetchall.return_value=[]
        with patch('edframe_catalog.api.connection') as factory:
            factory.return_value.__enter__.return_value=conn
            for goal in ('REINFORCE','UNDERMINE','ACQUIRE'):
                search_mining_powerplay(0,0,0,power='Aisling Duval',goal=goal)
                sql,values=conn.execute.call_args.args
                self.assertIn('jsonb_array_elements(facts)',sql)
                self.assertIn('Aisling Duval',values)
                if goal=='ACQUIRE':self.assertIn('Unoccupied',sql)
            search_mining_powerplay(0,0,0,system=['Mine'],power='Aisling Duval',goal='REINFORCE')
            self.assertNotIn('jsonb_array_elements(facts)',conn.execute.call_args.args[0])
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

    def test_unoccupied_without_participants_is_a_durable_public_snapshot(self):
        payload = self.payload()
        payload["message"].update(PowerplayState="Unoccupied")
        payload["message"].pop("Powers")
        payload["message"].pop("ControllingPower")
        snapshot = project_powerplay_snapshot(payload, payload["message"]["timestamp"])
        self.assertIsNotNone(snapshot)
        facts = json.loads(snapshot["facts"])
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["powerState"], "Unoccupied")
        self.assertEqual(facts[0]["power"], "")
        self.assertEqual(facts[0]["powers"], [])
        self.assertNotIn("PRIVATE", str(snapshot))
        connection = MagicMock()
        self.assertEqual(upsert_powerplay_snapshot(connection, snapshot), 1)

    def test_exact_coverage_reports_old_and_missing_without_serving_old_facts(self):
        now = datetime.now(timezone.utc)
        fresh = {"facts": [{"system": "Fresh"}], "identity": "fresh", "observed_at": now}
        connection = MagicMock()
        connection.execute.return_value.fetchall.side_effect = [[fresh], [
            {"identity": "fresh", "system_name": "Fresh", "observed_at": now},
            {"identity": "old", "system_name": "Old", "observed_at": now - timedelta(hours=25)},
        ]]
        with patch("edframe_catalog.api.connection") as factory:
            factory.return_value.__enter__.return_value = connection
            result = search_mining_powerplay(1, 2, 3, system=["Fresh", "Old", "Missing"], include_coverage=True)
        self.assertEqual(result["results"], [{"system": "Fresh"}])
        self.assertEqual([item["state"] for item in result["coverage"]], ["CURRENT", "STALE", "MISSING"])
        self.assertIsNone(result["coverage"][-1]["observedAt"])
        self.assertEqual(connection.execute.call_count, 2)
        sql, args = connection.execute.call_args.args
        self.assertIn("identity = ANY(%s)", sql)
        self.assertEqual(args, (["fresh", "old", "missing"],))
        self.assertNotIn("facts", sql)  # Diagnostic reads need no historical payload transfer.

    def test_regional_coverage_opt_in_never_starts_a_global_historical_query(self):
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = []
        with patch("edframe_catalog.api.connection") as factory:
            factory.return_value.__enter__.return_value = connection
            result = search_mining_powerplay(1, 2, 3, include_coverage=True)
        self.assertNotIn("coverage", result)
        self.assertEqual(connection.execute.call_count, 1)

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
            {"facts": [{"system": "One"}], "identity": "one", "observed_at": datetime.now(timezone.utc)},
            {"facts": [{"system": "Two"}]}]
        with patch("edframe_catalog.api.connection") as factory:
            factory.return_value.__enter__.return_value = connection
            result = search_mining_powerplay(1, 2, 3, max_distance=100, limit=1)
        self.assertEqual(result["results"], [{"system": "One"}])
        self.assertTrue(result["hasMore"])
        sql, values = connection.execute.call_args.args
        self.assertIn("INTERVAL '1 hour'", sql)
        self.assertEqual(values, (24, 1, 2, 3, 100, 2))
        self.assertEqual(_decode_state_cursor(result["nextCursor"])[1:], ("mining-powerplay", "one"))

    def test_exact_batch_uses_identity_index_not_radius_and_never_interpolates_names(self):
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = []
        with patch("edframe_catalog.api.connection") as factory:
            factory.return_value.__enter__.return_value = connection
            result = search_mining_powerplay(1, 2, 3, system=[" Mine ", "MINE", "Sale's Hub"])
        sql, values = connection.execute.call_args.args
        self.assertIn("identity = ANY(%s)", sql)
        self.assertNotIn("POWER(x", sql)
        self.assertNotIn("Sale's Hub", sql)
        self.assertEqual(values, (24, ["mine", "sale's hub"], 201))
        self.assertEqual(result["selection"], "systems")
        self.assertFalse(result["hasMore"])

    def test_cursor_orders_equal_timestamps_by_system_identity(self):
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = []
        stamp = datetime.now(timezone.utc)
        cursor = _encode_state_cursor(stamp, "mining-powerplay", "one")
        with patch("edframe_catalog.api.connection") as factory:
            factory.return_value.__enter__.return_value = connection
            search_mining_powerplay(1, 2, 3, cursor=cursor)
        sql, values = connection.execute.call_args.args
        self.assertIn("observed_at < %s", sql)
        self.assertIn("identity > %s", sql)
        self.assertEqual(values[-4:], (stamp, stamp, "one", 201))

    def test_invalid_or_excessive_queries_do_not_reach_database(self):
        for kwargs in ({"system": []}, {"system": [" "]},
                       {"system": ["x"] * 201}, {"system": ["x" * 101]},
                       {"cursor": "bad"},
                       {"cursor": _encode_state_cursor(datetime.now(timezone.utc), "mining-sites", "one")}):
            with self.subTest(kwargs=kwargs), patch("edframe_catalog.api.connection") as factory:
                with self.assertRaises(HTTPException):
                    search_mining_powerplay(1, 2, 3, **kwargs)
                factory.assert_not_called()
