import gzip
import json
from datetime import datetime, timedelta, timezone
import unittest

from ed_companion.navigation.mining_powerplay import (
    POWERPLAY_CATALOG_SCHEMA_VERSION,
    POWERPLAY_DUMP_URL,
    MiningPowerplayError,
    fetch_powerplay_catalog,
    powerplay_catalog_is_fresh,
    merge_powerplay_observations,
    project_powerplay_observations,
    project_powerplay_catalog,
)


class _Response:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


class MiningPowerplayCatalogTests(unittest.TestCase):
    def setUp(self):
        self.payload = [{
            "name": "Niflhel", "id64": 1234,
            "coords": {"x": 1, "y": 2, "z": 3},
            "power": "Aisling Duval", "powerState": "Stronghold",
            "state": "Boom", "date": "2026-10-01T00:00:00+00:00",
        }]

    def test_projects_only_complete_supported_powerplay_facts(self):
        rows = project_powerplay_catalog([
            *self.payload,
            {"name": "Broken", "id64": 0, "power": "Aisling Duval"},
        ])

        self.assertEqual(rows, [{
            "system": "Niflhel", "systemAddress": 1234,
            "coordinates": [1.0, 2.0, 3.0],
            "power": "Aisling Duval", "powerState": "Stronghold",
            "powerRelationship": "PRESENCE", "controlKnown": False,
            "systemState": "Boom",
            "observedAt": "2026-10-01T00:00:00+00:00",
            "source": "EDSM daily PowerPlay catalog",
        }])

    def test_headquarters_is_preserved_as_a_known_powerplay_state(self):
        row = dict(self.payload[0], name="Cubeo", powerState="Headquarters")

        projected = project_powerplay_catalog([row])

        self.assertEqual(projected[0]["system"], "Cubeo")
        self.assertEqual(projected[0]["powerState"], "Headquarters")
        self.assertFalse(projected[0]["controlKnown"])
        self.assertNotIn("controllingPower", projected[0])

    def test_eddn_location_preserves_explicit_control_separately_from_presence(self):
        rows = project_powerplay_observations({
            "$schemaRef": "https://eddn.edcd.io/schemas/journal/1",
            "message": {
                "event": "FSDJump", "timestamp": "2026-10-02T12:00:00Z",
                "StarSystem": "HR 6948", "SystemAddress": 99,
                "StarPos": [1, 2, 3], "ControllingPower": "Yuri Grom",
                "Powers": ["Yuri Grom", "Aisling Duval"],
                "PowerplayState": "Exploited",
            },
        })

        self.assertEqual(len(rows), 2)
        by_power = {row["power"]: row for row in rows}
        self.assertEqual(
            by_power["Yuri Grom"]["powerRelationship"], "CONTROL"
        )
        self.assertEqual(
            by_power["Aisling Duval"]["powerRelationship"], "PRESENCE"
        )
        self.assertEqual(
            by_power["Aisling Duval"]["controllingPower"], "Yuri Grom"
        )

    def test_powerplay_observation_merge_keeps_newest_fact(self):
        base = project_powerplay_observations({
            "event": "Location", "timestamp": "2026-10-01T12:00:00Z",
            "StarSystem": "Test", "SystemAddress": 10,
            "ControllingPower": "Aisling Duval",
            "Powers": ["Aisling Duval"], "PowerplayState": "Fortified",
        })
        newer = project_powerplay_observations({
            "event": "FSDJump", "timestamp": "2026-10-02T12:00:00Z",
            "StarSystem": "Test", "SystemAddress": 10,
            "ControllingPower": "Yuri Grom", "Powers": ["Aisling Duval"],
            "PowerplayState": "Exploited",
        })

        merged = merge_powerplay_observations(base, newer)

        aisling = next(row for row in merged if row["power"] == "Aisling Duval")
        self.assertEqual(aisling["controllingPower"], "Yuri Grom")
        self.assertEqual(aisling["powerState"], "Exploited")

    def test_fetch_uses_anonymous_bounded_daily_dump(self):
        calls = []

        def get(url, **kwargs):
            calls.append((url, kwargs))
            return _Response(gzip.compress(json.dumps(self.payload).encode()))

        catalog = fetch_powerplay_catalog(get=get)

        self.assertEqual(calls[0][0], POWERPLAY_DUMP_URL)
        self.assertEqual(calls[0][1]["timeout"], 45)
        self.assertIn("ED-Frame/", calls[0][1]["headers"]["User-Agent"])
        self.assertIn("github.com/CMDRForcer/ED-Frame", calls[0][1]["headers"]["User-Agent"])
        self.assertEqual(catalog["systems"][0]["system"], "Niflhel")
        self.assertEqual(
            catalog["schemaVersion"], POWERPLAY_CATALOG_SCHEMA_VERSION,
        )
        self.assertNotIn("commander", str(calls).casefold())

    def test_empty_or_malformed_catalog_is_rejected(self):
        with self.assertRaises(MiningPowerplayError):
            project_powerplay_catalog([])
        with self.assertRaises(MiningPowerplayError):
            fetch_powerplay_catalog(get=lambda *_args, **_kwargs: _Response(b"bad"))

    def test_freshness_is_explicit_and_time_bounded(self):
        now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        fresh = {"schemaVersion": POWERPLAY_CATALOG_SCHEMA_VERSION,
                 "fetchedAt": (now - timedelta(hours=23)).isoformat(),
                 "systems": self.payload}
        stale = {"schemaVersion": POWERPLAY_CATALOG_SCHEMA_VERSION,
                 "fetchedAt": (now - timedelta(hours=25)).isoformat(),
                 "systems": self.payload}
        legacy = {"fetchedAt": now.isoformat(), "systems": self.payload}

        self.assertTrue(powerplay_catalog_is_fresh(fresh, now=now))
        self.assertFalse(powerplay_catalog_is_fresh(stale, now=now))
        self.assertFalse(powerplay_catalog_is_fresh(legacy, now=now))


if __name__ == "__main__":
    unittest.main()
