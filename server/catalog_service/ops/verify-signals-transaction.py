"""Real PostgreSQL/API-path verification; ALL fixture writes are rolled back."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from starlette.requests import Request
from edframe_catalog import api
from edframe_catalog.database import connection, upsert_state_sighting_batch, upsert_signal_systems
from edframe_catalog.projection import project_state_sightings

name = "__EDFRAME_SIGNAL_TRANSACTION_TEST__"
original = api.connection
with connection() as conn:
    @contextmanager
    def transaction():
        yield conn

    api.connection = transaction
    try:
        now = datetime.now(timezone.utc)
        row = dict(system=name, system_address=None, star_pos=[0, 0, 0],
                   signal_timestamp=now.isoformat(), time_remaining=600,
                   find_type="HGE", faction="", state="Boom", Commander="PRIVATE")
        request = Request({"type": "http", "headers": [], "client": ("transaction-test", 0)})
        result = api.receive_state_signal_observations(request, {"observations": [row]})
        assert result["accepted"] == 1
        stored = conn.execute("SELECT observation FROM state_signals WHERE system_name=%s", (name,)).fetchone()["observation"]
        assert stored["time_remaining"] == 600 and "PRIVATE" not in str(stored)
        frame = {"$schemaRef": "https://eddn.edcd.io/schemas/fsssignaldiscovered/1",
                 "message": {"StarSystem": name, "StarPos": [0, 0, 0], "signals": [
                     {"timestamp": now.isoformat(), "USSType": "$USS_Type_VeryValuableSalvage;"}]}}
        sightings = project_state_sightings(frame, now.isoformat())
        upsert_signal_systems(conn, sightings)
        upsert_state_sighting_batch(conn, sightings)
        cursor = api._encode_state_cursor(now-timedelta(seconds=2), "", "")
        page = api.sync_state_finds(cursor=cursor, x=0, y=0, z=0, max_distance=1, limit=1000)
        found = [item for item in page["results"] if item.get("row", {}).get("system") == name]
        assert {item["kind"] for item in found} == {"SIGNAL", "SIGHTING"}
        assert all(item["row"]["time_remaining"] == 0 for item in found if item["kind"] == "SIGHTING")
    finally:
        conn.rollback()
        api.connection = original
    for table, field in (("state_signals", "system_name"), ("state_signal_sightings", "system_name"), ("systems", "name")):
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {field}=%s", (name,)).fetchone()["n"] == 0
print(json.dumps({"status": "PASS", "apiAccepted": 1, "regionalKinds": ["SIGNAL", "SIGHTING"],
                  "fixtureWrites": "ALL ROLLED BACK"}))
