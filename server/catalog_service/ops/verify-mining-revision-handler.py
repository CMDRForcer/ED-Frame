"""Ephemeral proposed handler vs deployed paging on one READ-ONLY snapshot.

JSON stdin contains `revision` module and an undecorated `handler` function.
Only this disposable Python process gets the proposed functions. No route
registration, lifespan initialization, source installation or database writes.
"""

import contextlib
import hashlib
import json
import sys
import time

from edframe_catalog import api
from edframe_catalog.database import connection


def digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str,
                                    separators=(",", ":")).encode()).hexdigest()


def collect(read, query, *, versioned=False):
    query = {**query, "offset": 0}
    if versioned:
        query["snapshot_protocol"] = 1
    rows, references = [], []
    started = time.monotonic()
    first = None
    for page in range(1, 51):
        result = read(**query)
        first = first or result
        rows.extend(result["results"])
        references.extend(result["communityReferences"])
        if not result["hasMore"]:
            if versioned:
                assert result["snapshotComplete"] is True
            assert len({row["siteIdentity"] for row in rows}) == len(rows)
            return rows, references, first, dict(pages=page, rows=len(rows),
                references=len(references), seconds=round(time.monotonic() - started, 4))
        query.update(cursor=result["nextCursor"], offset=result["nextOffset"])
        if versioned:
            assert result["snapshotComplete"] is False
            query.update(snapshot_revision=first["revision"], snapshot_static=first["snapshotStatic"])
    raise AssertionError("Unexpected paging budget exhaustion")


def main():
    sources = json.loads(sys.stdin.read())
    revision_namespace = {"__package__": "edframe_catalog", "__file__": __file__}
    exec(compile(sources["revision"], "<ephemeral-revision>", "exec"), revision_namespace)
    static = lambda: hashlib.sha256(b"read-only-handler-comparison").hexdigest()
    revision_namespace["static_revision"] = static
    print(json.dumps({"readOnly": True, "sourceSha256": {
        key: hashlib.sha256(sources[key].encode()).hexdigest() for key in ("revision", "handler")}}), flush=True)
    for radius in sources.get("radii", (50, 250)):
        with connection() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            conn.execute("SET LOCAL statement_timeout = '15s'")
            conn.execute("SET LOCAL lock_timeout = '1s'")
            @contextlib.contextmanager
            def same_snapshot():
                yield conn
            # Imported API is in this disposable process, not the API worker.
            api.connection = same_snapshot
            namespace = {**api.__dict__, "connection": same_snapshot,
                         "mining_revision": revision_namespace["mining_revision"],
                         "static_revision": static,
                         "MINING_SNAPSHOT_PROTOCOL_ENABLED": True}
            exec(compile(sources["handler"], "<ephemeral-handler>", "exec"), namespace)
            proposed = namespace["search_sites"]
            query = dict(commodity="platinum", max_age_days=3650,
                         x=110.9375, y=-113.0625, z=41.21875, max_distance=float(radius),
                         limit=1000, regional_page_size=5000,
                         include_ring_candidates=True, include_community_overlaps=True)
            old, old_refs, _, old_stats = collect(api.search_sites, query)
            new, new_refs, first, new_stats = collect(proposed, query, versioned=True)
            assert old == new, "Ring payloads/order changed"
            assert old_refs == new_refs, "Reference payloads/order changed"
            started = time.monotonic()
            unchanged = proposed(**query, offset=0, snapshot_protocol=1, known_revision=first["revision"])
            assert unchanged["notModified"] is True and unchanged["snapshotComplete"] is True
            assert unchanged["results"] == [] and unchanged["communityReferences"] == []
            print(json.dumps({"radius": radius, "equalRows": True, "equalReferences": True,
                              "rowSha256": digest(new), "referenceSha256": digest(new_refs),
                              "legacy": old_stats, "proposed": new_stats,
                              "unchanged": {"requests": 1, "rows": 0,
                                            "seconds": round(time.monotonic() - started, 4)}}), flush=True)
            conn.rollback()


if __name__ == "__main__":
    main()
