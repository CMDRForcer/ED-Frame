"""Lossless live-signal batching; existing BGS/evidence rules stay unchanged."""
import sqlite3

from .hge import (apply_system_bgs_snapshot_batch, merge_hge_observation_batch,
                  partition_hge_observations)


def prepare_hge_batch(existing, snapshots, additions, *, limit, archive,
                      displaced_rows, next_expiry):
    error = ""

    def preserve(rows):
        nonlocal error
        if not rows:
            return True
        try:
            archive.archive("hge_observations", rows)
            return True
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            error = type(exc).__name__
            return False

    # Capture new Journal/relay facts in the ORIGINAL profile before a delayed
    # GUI completion or profile change can detach their in-memory batch.
    incoming = [*additions, *(row for snapshot in snapshots
                             for row in (snapshot.get("observations") or []))]
    if not preserve(incoming):
        return {"error": error}
    updated, applied = apply_system_bgs_snapshot_batch(existing, snapshots, None)
    updated, changed = merge_hge_observation_batch(updated, additions, None)
    displaced = displaced_rows(existing, updated, snapshots, additions)
    if not preserve(displaced):
        updated.extend(displaced)
    active, historical = partition_hge_observations(updated)
    overflow_count = max(0, len(active) - limit)
    retired = [*historical, *active[:overflow_count]]
    removed = 0
    if preserve(retired):
        updated = active[overflow_count:]
        removed = len(retired)
    return {"sightings": updated, "changed": bool(applied or changed or removed),
            "stats": {"bgsApplied": int(applied or 0),
                      "signalsMerged": len(additions) if changed else 0,
                      "expiredRemoved": removed},
            "nextExpiry": next_expiry(updated), "archiveError": error}
