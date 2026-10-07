import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from starlette.requests import Request
from edframe_catalog.projection import project_state_sightings, project_state_signals
from edframe_catalog.api import receive_state_signal_observations, _signal_rate_buckets


class SignalSightingsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc).isoformat()
        self.frame = {"$schemaRef": "https://eddn.edcd.io/schemas/fsssignaldiscovered/1",
                      "message": {"StarSystem": "Sol", "SystemAddress": 1, "StarPos": [0, 0, 0],
                                  "signals": [{"timestamp": self.now,
                                               "USSType": "$USS_Type_VeryValuableSalvage;"}]}}
        _signal_rate_buckets.clear()

    def test_no_timer_retained_as_sighting_not_live(self):
        seen = project_state_sightings(self.frame, self.now)
        self.assertEqual(len(seen), 1)
        self.assertEqual(project_state_signals(self.frame, self.now), [])
        observation = json.loads(seen[0]["observation"])
        self.assertEqual(observation["time_remaining"], 0)
        self.assertFalse(observation["lifetime_verified"])
        self.assertNotIn("expires_at", seen[0])

    def test_latest_sighting_identity_is_bounded_not_one_row_per_scan(self):
        first = project_state_sightings(self.frame, self.now)[0]
        self.frame["message"]["signals"][0]["timestamp"] = "2026-01-01T00:00:00Z"
        self.assertEqual(project_state_sightings(self.frame, self.now), [])
        self.frame["message"]["signals"][0]["timestamp"] = self.now
        second = project_state_sightings(self.frame, self.now)[0]
        self.assertEqual(first["identity"], second["identity"])

    def test_non_supported_fss_reports_are_not_hges(self):
        self.frame["message"]["signals"][0]["USSType"] = "$USS_Type_MissionTarget;"
        self.assertEqual(project_state_sightings(self.frame, self.now), [])

    def observation(self, **changes):
        return dict(system="Sol", system_address=1, star_pos=[0, 0, 0],
                    signal_timestamp=self.now, time_remaining=600, find_type="HGE",
                    faction="Public faction", state="Boom", Commander="PRIVATE", **changes)

    def request(self):
        return Request({"type": "http", "headers": [], "client": ("test", 123)})

    def test_direct_upload_is_public_and_not_local_evidence_on_receivers(self):
        conn = MagicMock()
        with patch("edframe_catalog.api.connection") as factory, patch("edframe_catalog.api.upsert_state_find_batch", return_value=1) as write:
            factory.return_value.__enter__.return_value = conn
            result = receive_state_signal_observations(self.request(), {"observations": [self.observation()]})
        self.assertEqual(result["accepted"], 1)
        rows = write.call_args.args[2]
        observation = json.loads(rows[0]["observation"])
        self.assertNotIn("PRIVATE", str(observation))
        self.assertEqual(observation["evidence_kind"], "EDDN_SIGNAL")
        self.assertEqual(observation["source"], "ED-Frame community Journal")
        self.assertTrue(observation["lifetime_verified"])

    def test_unsupported_empty_and_oversized_batches_rejected(self):
        for rows in ([], [{}], [{}]*101):
            with self.assertRaises(HTTPException) as raised:
                receive_state_signal_observations(self.request(), {"observations": rows})
            self.assertEqual(raised.exception.status_code, 422)

    def test_request_budget_is_bounded(self):
        for _ in range(6):
            with self.assertRaises(HTTPException):
                receive_state_signal_observations(self.request(), {"observations": [{}]})
        with self.assertRaises(HTTPException) as raised:
            receive_state_signal_observations(self.request(), {"observations": [{}]})
        self.assertEqual(raised.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
