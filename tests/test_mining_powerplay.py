import gzip
import json
from datetime import datetime, timedelta, timezone
import unittest

from ed_companion.navigation.mining_powerplay import (
    POWERPLAY_DUMP_URL,
    MiningPowerplayError,
    fetch_powerplay_catalog,
    powerplay_catalog_is_fresh,
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
            "systemState": "Boom",
            "observedAt": "2026-10-01T00:00:00+00:00",
            "source": "EDSM daily PowerPlay catalog",
        }])

    def test_fetch_uses_anonymous_bounded_daily_dump(self):
        calls = []

        def get(url, **kwargs):
            calls.append((url, kwargs))
            return _Response(gzip.compress(json.dumps(self.payload).encode()))

        catalog = fetch_powerplay_catalog(get=get)

        self.assertEqual(calls, [(POWERPLAY_DUMP_URL, {"timeout": 45})])
        self.assertEqual(catalog["systems"][0]["system"], "Niflhel")
        self.assertNotIn("commander", str(calls).casefold())

    def test_empty_or_malformed_catalog_is_rejected(self):
        with self.assertRaises(MiningPowerplayError):
            project_powerplay_catalog([])
        with self.assertRaises(MiningPowerplayError):
            fetch_powerplay_catalog(get=lambda *_args, **_kwargs: _Response(b"bad"))

    def test_freshness_is_explicit_and_time_bounded(self):
        now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        fresh = {"fetchedAt": (now - timedelta(hours=23)).isoformat(),
                 "systems": self.payload}
        stale = {"fetchedAt": (now - timedelta(hours=25)).isoformat(),
                 "systems": self.payload}

        self.assertTrue(powerplay_catalog_is_fresh(fresh, now=now))
        self.assertFalse(powerplay_catalog_is_fresh(stale, now=now))


if __name__ == "__main__":
    unittest.main()
