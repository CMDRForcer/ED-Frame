"""Incremental client for ED-Frame's anonymous public State Finds catalog."""

from __future__ import annotations

from typing import Any

from .hge import (
    EVIDENCE_RANK,
    apply_system_bgs_snapshot_batch,
    merge_hge_observation_batch,
)
from .mining_market import EDFRAME_CATALOG_BASE, MiningMarketError


def fetch_edframe_state_find_delta(
    *, cursor: str = "", get: Any, timeout: int = 20, limit: int = 500,
) -> dict[str, Any]:
    """Fetch and validate one resumable page of current public intelligence."""
    bounded_limit = max(1, min(1000, int(limit or 500)))
    params: dict[str, Any] = {"limit": bounded_limit}
    current_cursor = str(cursor or "").strip()
    if current_cursor:
        params["cursor"] = current_cursor
    response = get(
        f"{EDFRAME_CATALOG_BASE}/v1/sync/state-finds",
        params=params,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise MiningMarketError("ED-Frame returned an invalid State Finds response")
    results = payload.get("results")
    if not isinstance(results, list):
        raise MiningMarketError("ED-Frame State Finds results are invalid")
    snapshots, signals = [], []
    for item in results:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").upper()
        if kind == "BGS" and isinstance(item.get("snapshot"), dict):
            snapshots.append(item["snapshot"])
        elif kind == "SIGNAL" and isinstance(item.get("row"), dict):
            signals.append(item["row"])
    next_cursor = str(payload.get("nextCursor") or "").strip()
    has_more = bool(payload.get("hasMore"))
    if results and not next_cursor:
        raise MiningMarketError("ED-Frame State Finds response has no cursor")
    if has_more and (not results or next_cursor == current_cursor):
        raise MiningMarketError("ED-Frame State Finds cursor did not advance")
    return {
        "snapshots": snapshots,
        "signals": signals,
        "nextCursor": next_cursor,
        "hasMore": has_more,
        "generatedAt": str(payload.get("generatedAt") or ""),
        "rowCount": len(results),
    }


def _signal_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(row.get("system") or "").casefold(),
        str(row.get("signal_timestamp") or ""),
        str(row.get("faction") or "").casefold(),
        str(row.get("state") or "").casefold(),
        str(row.get("find_type") or "HGE"),
    )


def merge_edframe_state_find_page(
    observations: list[dict[str, Any]], page: dict[str, Any], *, limit: int = 10000,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Merge server facts while preserving stronger local evidence."""
    merged, snapshots_applied = apply_system_bgs_snapshot_batch(
        observations, page.get("snapshots") or [], limit=None,
    )
    strongest = {
        _signal_key(row): EVIDENCE_RANK.get(
            str(row.get("evidence_kind") or "BGS_PREDICTION"), 0
        )
        for row in merged if isinstance(row, dict)
    }
    accepted = []
    for row in page.get("signals") or []:
        if not isinstance(row, dict):
            continue
        key = _signal_key(row)
        incoming_rank = EVIDENCE_RANK.get(
            str(row.get("evidence_kind") or "EDDN_SIGNAL"), 1
        )
        if strongest.get(key, -1) > incoming_rank:
            continue
        strongest[key] = incoming_rank
        accepted.append(row)
    merged, _changed = merge_hge_observation_batch(
        merged, accepted, limit=None,
    )
    retained = merged[-max(1, int(limit)):]
    return retained, {
        "snapshotsApplied": snapshots_applied,
        "signalsApplied": len(accepted),
        "mergedRows": len(retained),
    }
