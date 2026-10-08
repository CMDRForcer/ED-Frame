"""Prepare regional State Finds on a worker; evidence/BGS rules are unchanged."""
from ed_companion.navigation.hge import partition_hge_observations
from ed_companion.navigation.state_find_catalog import (
    merge_edframe_state_find_page, retain_state_find_region,
)


def prepare_state_find_page(existing, page, region, *, limit, archive=None):
    merged, stats = merge_edframe_state_find_page(existing, page, limit=None)
    active, historical = partition_hge_observations(merged)
    retained = retain_state_find_region(active, origin=region["origin"], limit=limit)
    retained_ids = {id(row) for row in retained}
    overflow = [row for row in active if id(row) not in retained_ids]
    if historical or overflow:
        # Historical facts are durable before they leave the active snapshot.
        if archive is None:
            raise OSError("State Finds history archive unavailable")
        archive.archive("hge_observations", [*historical, *overflow])
    return {"preparedRows": retained, "preparedStats": stats,
            "preparedMeta": {"cursor": str(page.get("nextCursor") or "").strip(),
                             "lastSuccess": str(page.get("generatedAt") or ""),
                             "region": region}}
