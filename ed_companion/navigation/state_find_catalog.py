"""Incremental client for ED-Frame's anonymous public State Finds catalog."""

from __future__ import annotations

from typing import Any
import math

from .hge import (
    EVIDENCE_RANK,
    apply_system_bgs_snapshot_batch,
    merge_hge_observation_batch,
)
from .mining_market import EDFRAME_CATALOG_BASE, MiningMarketError


def fetch_edframe_state_find_delta(
    *, cursor: str = "", get: Any, timeout: int = 20, limit: int = 500,
    origin: Any = None, radius_ly: float = 250,
) -> dict[str, Any]:
    """Fetch and validate one resumable page of current public intelligence."""
    bounded_limit = max(1, min(1000, int(limit or 500)))
    params: dict[str, Any] = {"limit": bounded_limit}
    region = state_find_region(origin, radius_ly) if origin is not None else None
    if origin is not None and region is None:
        raise MiningMarketError("State Finds needs a finite three-dimensional position")
    if region:
        params.update(dict(zip(("x", "y", "z"), region["origin"])))
        params["max_distance"] = region["radiusLy"]
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
    if region and payload.get("region") != region:
        raise MiningMarketError("Server did not confirm the requested State Finds region")
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
        elif kind in {"SIGNAL", "SIGHTING"} and isinstance(item.get("row"), dict):
            row = dict(item["row"])
            if kind == "SIGHTING":
                row.update(time_remaining=0, lifetime_verified=False,
                           evidence_kind="EDDN_SIGNAL", local_verified=False)
            signals.append(row)
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
        "region": region,
    }


def state_find_region(origin: Any, radius_ly: float = 250) -> dict[str, Any] | None:
    """Stable region identity; a cursor must never be reused at another origin."""
    if not isinstance(origin, (list, tuple)) or len(origin) != 3:
        return None
    try:
        position = [float(value) for value in origin]
        radius = float(radius_ly)
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(value) and abs(value) <= 1000000 for value in position):
        return None
    if not math.isfinite(radius) or not 0 < radius <= 2000:
        return None
    return {"origin": position, "radiusLy": radius}


def retain_state_find_region(
    observations: list[dict[str, Any]], *, origin: Any = None, limit: int = 10000,
) -> list[dict[str, Any]]:
    """Keep local evidence first, then nearby remote facts within the same bound."""
    rows = list(observations)
    region = state_find_region(origin)
    if not region or len(rows) <= max(1, int(limit)):
        return rows[-max(1, int(limit)):]

    def priority(row):
        evidence = str(row.get("evidence_kind") or "BGS_PREDICTION")
        local = evidence in {"LOCAL_JOURNAL", "ENTERED"}
        position = state_find_region(row.get("star_pos"))
        distance = sum((a - b) ** 2 for a, b in zip(
            region["origin"], position["origin"]
        )) if position else float("inf")
        return (local, -distance, EVIDENCE_RANK.get(evidence, 0),
                str(row.get("signal_timestamp") or row.get("received_at") or ""))

    return sorted(rows, key=priority)[-max(1, int(limit)):]


def _signal_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(row.get("system") or "").casefold(),
        str(row.get("signal_timestamp") or ""),
        str(row.get("faction") or "").casefold(),
        str(row.get("state") or "").casefold(),
        str(row.get("find_type") or "HGE"),
    )


def merge_edframe_state_find_page(
    observations: list[dict[str, Any]], page: dict[str, Any], *, limit: int | None = 10000,
    origin: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Merge server facts while preserving stronger local evidence."""
    # Keep the original evidence/source contract intact: transport provenance
    # must not turn a BGS prediction into a confirmed signal or change identity.
    snapshots = []
    for snapshot in page.get("snapshots") or []:
        if not isinstance(snapshot, dict):
            continue
        snapshots.append({**snapshot, "observations": [
            {**row, "catalog_transport": "ED-Frame server"}
            for row in snapshot.get("observations") or [] if isinstance(row, dict)
        ]})
    merged, snapshots_applied = apply_system_bgs_snapshot_batch(
        observations, snapshots, limit=None,
    )
    strongest = {
        _signal_key(row): EVIDENCE_RANK.get(
            str(row.get("evidence_kind") or "BGS_PREDICTION"), 0
        )
        for row in merged if isinstance(row, dict)
    }
    accepted = {}
    live_keys = {_signal_key(row) for row in merged if int(row.get("time_remaining", 0) or 0) > 0}
    for row in page.get("signals") or []:
        if not isinstance(row, dict):
            continue
        key = _signal_key(row)
        if key in live_keys and int(row.get("time_remaining", 0) or 0) <= 0:
            continue
        incoming_rank = EVIDENCE_RANK.get(
            str(row.get("evidence_kind") or "EDDN_SIGNAL"), 1
        )
        if strongest.get(key, -1) > incoming_rank:
            continue
        strongest[key] = incoming_rank
        if int(row.get("time_remaining", 0) or 0) > 0:
            live_keys.add(key)
        accepted[key] = {**row, "catalog_transport": "ED-Frame server"}
    merged, _changed = merge_hge_observation_batch(
        merged, list(accepted.values()), limit=None,
    )
    retained = merged if limit is None else retain_state_find_region(merged, origin=origin, limit=limit)
    return retained, {
        "snapshotsApplied": snapshots_applied,
        "signalsApplied": len(accepted),
        "mergedRows": len(retained),
    }
