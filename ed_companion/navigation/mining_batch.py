"""Lossless ring merging and history work without Qt/UI dependencies."""

import sqlite3
import json
import hashlib

from ed_companion.history_archive import HistoryArchive
from ed_companion.worker_budget import WorkerBudget
from ed_companion.navigation.catalog_json import CatalogDictFactory, catalog_record_snapshot
from ed_companion.navigation.mining_finder import (
    merge_mining_candidate_batch, mining_candidate_positions,
)


def mining_observation_key(row):
    """A re-fetch is not a new sighting; genuine observation/fact changes are.

    Preserve the complete latest payload in history; exclude only retrieval
    timestamps and computed view values from identity, not observedAt/evidence.
    """
    ignored = {"learnedAt", "distanceLy", "ageSeconds", "stale",
               "recheckRecommended", "confirmationStatus", "freshnessLimitSeconds"}
    def facts(value):
        if isinstance(value, dict):
            return {key: facts(field) for key, field in value.items() if key not in ignored}
        if isinstance(value, (list, tuple)):
            return [facts(item) for item in value]
        return value
    return hashlib.sha256(json.dumps(facts(row), sort_keys=True,
                                     ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def prepare_mining_batch(existing, incoming, *, positions=None, archive=None,
                        archive_path=None, transient_fields=(), snapshot_arrays=False):
    # Compaction must never mutate rows still displayed by the UI or referenced
    # by an earlier queued catalog save. The position map is worker-owned too.
    # Untouched immutable rows are shared, not copied 270,000 times per relay
    # batch. Copy on write only when removing derived fields below.
    old = [row for row in existing if isinstance(row, dict)]
    additions = [dict(row) for row in incoming if isinstance(row, dict)]
    index = dict(positions) if positions is not None else mining_candidate_positions(old)
    records = CatalogDictFactory()
    budget = WorkerBudget()
    def prepare_row(row):
        if snapshot_arrays:
            return catalog_record_snapshot(row, factory=records, exclude=transient_fields)
        return records.copy_record(row, exclude=transient_fields)
    merged, displaced = merge_mining_candidate_batch(
        old, additions, positions=index,
        prepare_row=prepare_row,
        checkpoint=budget.checkpoint,
    )
    error = ""
    try:
        if archive is None and archive_path is not None:
            archive = HistoryArchive(archive_path)
        if archive is not None:
            def observation_key(row):
                budget.checkpoint()
                return mining_observation_key(row)
            archive.archive("mining_observations", additions, key_field=observation_key)
            archive.archive("mining_catalog", displaced, key_field=observation_key)
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        error = type(exc).__name__
    candidates = merged if not error else [*old, *additions]
    for row_index, row in enumerate(candidates):
        budget.checkpoint()
        if any(field in row for field in transient_fields):
            candidates[row_index] = prepare_row(row)
        elif error and snapshot_arrays and row_index >= len(old):
            candidates[row_index] = prepare_row(row)
    return {
        "candidates": candidates,
        "positions": index if not error else mining_candidate_positions(candidates),
        "archiveError": error,
    }
