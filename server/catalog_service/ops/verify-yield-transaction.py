"""Exercise the anonymous yield write path and always roll it back."""

from datetime import datetime, timezone

import requests

from edframe_catalog.database import connection, upsert_yield_observations
from edframe_catalog.projection import project_yield_observations


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload = {"observations": [{
        "system": "ED-Frame Transaction Test",
        "systemAddress": 999999999,
        "coordinates": [1, 2, 3],
        "bodyId": 1,
        "ring": "ED-Frame Transaction Test 1 A Ring",
        "observedAt": now,
        "materials": [{"commodity": "Osmium", "proportion": 17.5}],
    }]}
    rows = project_yield_observations(payload, now)
    if len(rows) != 1:
        raise RuntimeError("yield projection rejected the transaction fixture")
    with connection() as conn:
        written = upsert_yield_observations(conn, rows)
        retained = conn.execute(
            "SELECT COUNT(*) AS value FROM mining_yield_samples "
            "WHERE sample_id = %s",
            (rows[0]["sample_id"],),
        ).fetchone()["value"]
        if written != 1 or retained != 1:
            raise RuntimeError(
                f"yield write mismatch: written={written}, retained={retained}"
            )
        conn.rollback()
    with connection() as conn:
        after_rollback = conn.execute(
            "SELECT COUNT(*) AS value FROM mining_yield_samples "
            "WHERE sample_id = %s",
            (rows[0]["sample_id"],),
        ).fetchone()["value"]
    if after_rollback:
        raise RuntimeError("transaction fixture survived rollback")
    print("TRANSACTIONAL_YIELD_TEST OK · 1 sample + material · rollback clean")
    base_url = "http://127.0.0.1:8000"
    empty = requests.post(
        f"{base_url}/v1/yields/observations",
        json={"observations": []}, timeout=10,
    )
    empty.raise_for_status()
    if empty.json().get("accepted") != 0:
        raise RuntimeError("empty public yield request was not idempotent")
    sites = requests.get(
        f"{base_url}/v1/sites/search",
        params={"system": "Cubeo", "limit": 1}, timeout=15,
    )
    sites.raise_for_status()
    results = sites.json().get("results") or []
    if not results or not {
        "prospectorSampleCount", "yieldStats"
    }.issubset(results[0]):
        raise RuntimeError("public site search lacks measured-yield fields")
    print("PUBLIC_YIELD_API OK · POST + site projection")


if __name__ == "__main__":
    main()
