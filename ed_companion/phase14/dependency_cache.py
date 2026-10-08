"""Small, content-based dependency revisions for UI-owned projections.

Never snapshot the global state or the regional ring catalog here. Callers
provide only their own small inputs; equality also detects same-sized and
in-place updates without hashing/serializing a large state on every binding.
"""

from copy import deepcopy
import hashlib
import json


def mining_candidates_signature(rows):
    """Build once in the Journal-state worker, never in a QML getter."""
    return hashlib.sha256(json.dumps(
        rows, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def profile_dependency(owner):
    context = getattr(owner, "profile_context", None)
    return (getattr(owner, "_profile_generation", 0), getattr(context, "key", ""))


def dependency_revision(owner, name, dependencies):
    snapshots = getattr(owner, "_dependency_snapshots", None)
    if snapshots is None:
        snapshots = owner._dependency_snapshots = {}
    previous = snapshots.get(name)
    if previous is not None and previous[1] == dependencies:
        return previous[0]
    revision = previous[0] + 1 if previous is not None else 1
    snapshots[name] = (revision, deepcopy(dependencies))
    return revision


def invalidate_state_cache(owner):
    # Keep only projections with complete domain-specific keys. Every existing
    # broad-state cache (including finance and BGS) still invalidates normally.
    fleet = owner._derived_cache.get("commander_fleet")
    owner._derived_cache.clear()
    if fleet is not None:
        owner._derived_cache["commander_fleet"] = fleet
