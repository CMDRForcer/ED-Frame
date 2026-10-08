"""Append after proposed revision + search_sites definitions in API Python.

No TestClient lifespan, schema initialization, source install or mutation.
Exercises the proposed handler against retained public data, read-only.
"""
import hashlib
import json
import time

static_revision = lambda: hashlib.sha256(b"ephemeral-readonly-handler-probe").hexdigest()
query = dict(commodity="platinum", max_age_days=3650, x=110.9375, y=-113.0625,
             z=41.21875, max_distance=50., limit=100, offset=0,
             include_community_overlaps=True, include_ring_candidates=True,
             snapshot_protocol=1)
for attempt in range(2):
    started = time.monotonic()
    first = search_sites(**query)
    revision = first["revision"]
    rows = list(first["results"])
    pages = 1
    current = first
    try:
        while current["hasMore"]:
            assert not current["snapshotComplete"]
            current = search_sites(**{**query, "offset": current["nextOffset"],
                        "cursor": current["nextCursor"], "snapshot_revision": revision,
                        "snapshot_static": first["snapshotStatic"]})
            assert current["revision"] == revision
            rows.extend(current["results"])
            pages += 1
        assert current["snapshotComplete"]
        assert len({r["siteIdentity"] for r in rows}) == len(rows)
        loaded = time.monotonic() - started
        started = time.monotonic()
        unchanged = search_sites(**query, known_revision=revision)
        seconds = time.monotonic() - started
        if not unchanged["notModified"]:
            raise HTTPException(status_code=409, detail="Domain changed during probe")
        assert unchanged["snapshotComplete"] and unchanged["results"] == []
        print(json.dumps(dict(readOnlyHandler=True, radius=50, rows=len(rows), pages=pages,
                              complete=True, notModified=True, unchangedRows=0,
                              fullSeconds=round(loaded, 4), confirmSeconds=round(seconds, 4))), flush=True)
        break
    except HTTPException as exc:
        if exc.status_code != 409 or attempt:
            raise
