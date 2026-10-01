"""Missions and Community Goals derived purely from Journal events.

Both are read-only projections: Frontier gives no way to accept, abandon
or turn in a mission from outside the game, so this module only ever
answers "what is currently outstanding", never acts on it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_CLOSING_EVENTS = frozenset({"MissionCompleted", "MissionFailed", "MissionAbandoned"})

# Frontier's "Permit Acquisition Opportunity" missions (internal name
# MISSION_genericPermitN) grant their permit the instant they are accepted,
# but a longstanding Frontier bug means the mission itself often never
# receives a MissionCompleted/Failed/Abandoned event afterwards - it just
# sits in the Commander's mission list forever with no Expiry either.
# Tracked here (confirmed against a real Journal and reported widely on the
# Frontier issue tracker) so this never shows as something still to act on.
_STUCK_MISSION_NAME_FRAGMENTS = ("genericpermit",)


def _is_known_stuck_mission(name: object) -> bool:
    lowered = str(name or "").casefold()
    return any(fragment in lowered for fragment in _STUCK_MISSION_NAME_FRAGMENTS)


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if text.lstrip("-").isdigit():
        return int(text)
    return None


def active_missions(events: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Missions genuinely still open right now, soonest deadline first.

    Folds ``MissionAccepted``/``MissionRedirected`` against ``MissionID``
    into the set of open missions; any of ``MissionCompleted``,
    ``MissionFailed`` or ``MissionAbandoned`` removes it, regardless of
    ordering - a completion event can lag its own acceptance by minutes
    in an imported or replayed log, so this never trusts sequence alone.
    Permit-acquisition missions (see ``_is_known_stuck_mission``) are
    excluded outright since they never close on their own.

    Real progress (``progressDone``/``progressTotal``) is only reported for
    the two mission shapes Frontier actually journals per-step updates
    for: an in-space Cargo Depot haul (``CargoDepot``, exact
    ItemsDelivered/TotalItemsToDeliver) and a salvage-collection mission
    (``CollectCargo`` tagged with this ``MissionID``, tallied against the
    mission's own required ``Count``). A plain "carry commodity you
    already own to a station" delivery, a massacre's kill count, or a
    single-target assassination have no such per-step Journal event -
    Frontier only reports those as done or not, so no progress fraction is
    fabricated for them; ``progressKnown`` stays false.
    """
    missions: dict[int, dict[str, Any]] = {}
    closed: set[int] = set()
    salvage_collections: set[int] = set()
    collected_tally: dict[int, int] = {}
    for event in events or []:
        if not isinstance(event, dict):
            continue
        name = str(event.get("event") or "")
        mission_id = _as_int(event.get("MissionID"))
        if mission_id is None:
            continue
        if name == "MissionAccepted":
            if mission_id in closed or _is_known_stuck_mission(event.get("Name")):
                continue
            missions[mission_id] = {
                "missionId": mission_id,
                "acceptedAt": str(event.get("timestamp") or ""),
                "nameSymbol": str(event.get("Name") or ""),
                "name": str(
                    event.get("LocalisedName") or event.get("Name") or ""
                ),
                "faction": str(event.get("Faction") or ""),
                "issuerFaction": str(event.get("Faction") or ""),
                "destinationSystem": str(event.get("DestinationSystem") or ""),
                "destinationStation": str(event.get("DestinationStation") or ""),
                "expiry": str(event.get("Expiry") or ""),
                "reward": _as_int(event.get("Reward")),
                "donation": _as_int(event.get("Donation")),
                "commodity": str(event.get("Commodity_Localised") or ""),
                "commodityCount": _as_int(event.get("Count")),
                "target": str(
                    event.get("Target_Localised") or event.get("Target") or ""
                ),
                "targetSymbol": str(event.get("Target") or ""),
                "targetFaction": str(event.get("TargetFaction") or ""),
                "targetType": str(
                    event.get("TargetType_Localised")
                    or event.get("TargetType") or ""
                ),
                "targetTypeSymbol": str(event.get("TargetType") or ""),
                "killCount": _as_int(event.get("KillCount")),
                "wing": bool(event.get("Wing")),
                "progressKnown": False,
                "progressDone": 0,
                "progressTotal": 0,
            }
            if str(event.get("Commodity") or "").casefold().startswith("$usscargo"):
                salvage_collections.add(mission_id)
        elif name == "MissionRedirected" and mission_id in missions:
            row = missions[mission_id]
            row["destinationSystem"] = str(
                event.get("NewDestinationSystem") or row["destinationSystem"]
            )
            row["destinationStation"] = str(
                event.get("NewDestinationStation") or row["destinationStation"]
            )
        elif name == "CargoDepot" and mission_id in missions:
            done = _as_int(event.get("ItemsDelivered"))
            total = _as_int(event.get("TotalItemsToDeliver"))
            if done is not None and total:
                missions[mission_id].update({
                    "progressKnown": True, "progressDone": done, "progressTotal": total,
                })
        elif name == "CollectCargo" and mission_id in salvage_collections:
            collected_tally[mission_id] = collected_tally.get(mission_id, 0) + 1
        elif name in _CLOSING_EVENTS:
            missions.pop(mission_id, None)
            closed.add(mission_id)
            salvage_collections.discard(mission_id)

    for mission_id, row in missions.items():
        if row["progressKnown"] or mission_id not in salvage_collections:
            continue
        total = row.get("commodityCount")
        if total:
            row.update({
                "progressKnown": True,
                "progressDone": min(collected_tally.get(mission_id, 0), total),
                "progressTotal": total,
            })
    return sorted(missions.values(), key=lambda row: row["expiry"] or "9999")


def missions_summary(missions: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Roll-up stats for the active-missions list above."""
    missions = [row for row in missions or [] if isinstance(row, dict)]
    known_rewards = [
        row["reward"] for row in missions if row.get("reward") is not None
    ]
    expiries = sorted(str(row["expiry"]) for row in missions if row.get("expiry"))
    return {
        "activeCount": len(missions),
        "totalReward": sum(known_rewards),
        "missionsWithKnownReward": len(known_rewards),
        "nearestExpiry": expiries[0] if expiries else "",
    }


def _utc_datetime(value: object) -> datetime | None:
    """Parse a Journal timestamp without ever assuming local time."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def prioritized_missions(
    missions: list[dict[str, Any]] | None,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Decorate and sort active missions by actionable deadline.

    Frontier may keep an overdue mission in the local journal until its
    eventual failure event arrives.  Such a mission remains visible, but is
    labelled ``expired`` rather than silently discarded.  Missing or invalid
    expiries sort last and are explicitly labelled ``none``.
    """
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    else:
        instant = instant.astimezone(timezone.utc)
    rows: list[dict[str, Any]] = []
    for mission in missions or []:
        if not isinstance(mission, dict):
            continue
        row = dict(mission)
        expiry = _utc_datetime(row.get("expiry"))
        seconds = int((expiry - instant).total_seconds()) if expiry else None
        if seconds is None:
            status = "none"
        elif seconds <= 0:
            status = "expired"
        elif seconds <= 60 * 60:
            status = "critical"
        elif seconds <= 24 * 60 * 60:
            status = "soon"
        else:
            status = "active"
        row.update({
            "deadlineStatus": status,
            "secondsRemaining": seconds,
            "isMassacre": bool(
                _as_int(row.get("killCount")) is not None
                or "massacre" in str(row.get("nameSymbol") or "").casefold()
            ),
        })
        rows.append(row)
    priority = {"expired": 0, "critical": 1, "soon": 2, "active": 3, "none": 4}
    return sorted(
        rows,
        key=lambda row: (
            priority.get(str(row.get("deadlineStatus")), 4),
            row.get("secondsRemaining") is None,
            row.get("secondsRemaining") or 0,
            str(row.get("targetFaction") or "").casefold(),
            int(row.get("missionId") or 0),
        ),
    )


def massacre_stacks(
    missions: list[dict[str, Any]] | None,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Group massacre missions using Elite's actual stacking rule.

    Against one target faction, missions from different issuing factions can
    advance with the same kill.  Multiple missions from the *same* issuing
    faction form a sequential lane.  Therefore the exact effective kill
    requirement is the largest issuer-lane sum, not the sum of all missions.

    If target, issuer, or kill count evidence is missing, the projection keeps
    the missions visible but reports no exact effective total.  This is safer
    than inventing progress or an optimistic stack.
    """
    source = [row for row in missions or [] if isinstance(row, dict)]
    if now is None and all("deadlineStatus" in row for row in source):
        decorated = [dict(row) for row in source]
    else:
        decorated = prioritized_missions(source, now=now)
    grouped: dict[str, dict[str, Any]] = {}
    for mission in decorated:
        if not mission.get("isMassacre"):
            continue
        target = str(mission.get("targetFaction") or "").strip()
        group_key = target.casefold() if target else f"unknown:{mission.get('missionId')}"
        group = grouped.setdefault(group_key, {
            "id": group_key,
            "targetFaction": target,
            "missions": [],
            "issuerLanes": {},
            "missionCount": 0,
            "totalReward": 0,
            "missionsWithKnownReward": 0,
            "nearestExpiry": "",
            "stackEvidenceComplete": True,
        })
        group["missions"].append(mission)
        group["missionCount"] += 1
        reward = _as_int(mission.get("reward"))
        if reward is not None:
            group["totalReward"] += reward
            group["missionsWithKnownReward"] += 1
        expiry = str(mission.get("expiry") or "")
        if expiry and (not group["nearestExpiry"] or expiry < group["nearestExpiry"]):
            group["nearestExpiry"] = expiry

        issuer = str(mission.get("issuerFaction") or "").strip()
        kills = _as_int(mission.get("killCount"))
        if not target or not issuer or kills is None or kills <= 0:
            group["stackEvidenceComplete"] = False
            continue
        issuer_key = issuer.casefold()
        lane = group["issuerLanes"].setdefault(issuer_key, {
            "issuerFaction": issuer,
            "missionCount": 0,
            "requiredKills": 0,
            "missionIds": [],
        })
        lane["missionCount"] += 1
        lane["requiredKills"] += kills
        lane["missionIds"].append(mission.get("missionId"))

    result = []
    for group in grouped.values():
        lanes = sorted(
            group.pop("issuerLanes").values(),
            key=lambda lane: (-lane["requiredKills"], lane["issuerFaction"].casefold()),
        )
        complete = bool(group["stackEvidenceComplete"])
        nominal = sum(
            int(mission["killCount"])
            for mission in group["missions"]
            if _as_int(mission.get("killCount")) is not None
        )
        effective = max((lane["requiredKills"] for lane in lanes), default=0)
        group.update({
            "issuerLanes": lanes,
            "issuerCount": len(lanes),
            "nominalKills": nominal if complete else None,
            "effectiveKills": effective if complete else None,
            "killsSavedByStacking": nominal - effective if complete else None,
            "deadlineStatus": group["missions"][0].get("deadlineStatus", "none"),
            "secondsRemaining": group["missions"][0].get("secondsRemaining"),
        })
        result.append(group)
    priority = {"expired": 0, "critical": 1, "soon": 2, "active": 3, "none": 4}
    return sorted(
        result,
        key=lambda group: (
            priority.get(str(group.get("deadlineStatus")), 4),
            group.get("secondsRemaining") is None,
            group.get("secondsRemaining") or 0,
            str(group.get("targetFaction") or "").casefold(),
        ),
    )


def community_goals_overview(
    events: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Community Goals still open, from the most recent ``CommunityGoal``.

    Frontier resends the full current roster on every ``CommunityGoal``
    event, not an incremental diff - so only the newest one is read, never
    merged with older ones. A goal Frontier marks ``IsComplete`` has
    concluded (Frontier keeps reporting it for a while afterwards) and is
    left out here rather than shown as still open.
    """
    latest = next(
        (
            event for event in reversed(events or [])
            if isinstance(event, dict) and event.get("event") == "CommunityGoal"
        ),
        None,
    )
    if not latest:
        return []
    goals = []
    for goal in latest.get("CurrentGoals", []) or []:
        if not isinstance(goal, dict) or goal.get("CGID") is None or goal.get("IsComplete"):
            continue
        top_tier = goal.get("TopTier") if isinstance(goal.get("TopTier"), dict) else {}
        goals.append({
            "cgid": _as_int(goal.get("CGID")),
            "title": str(goal.get("Title") or ""),
            "system": str(goal.get("SystemName") or ""),
            "market": str(goal.get("MarketName") or ""),
            "expiry": str(goal.get("Expiry") or ""),
            "currentTotal": _as_int(goal.get("CurrentTotal")) or 0,
            "playerContribution": _as_int(goal.get("PlayerContribution")) or 0,
            "numContributors": _as_int(goal.get("NumContributors")) or 0,
            "tierReached": str(goal.get("TierReached") or ""),
            "topTierName": str(top_tier.get("Name") or ""),
            "playerInTopRank": bool(goal.get("PlayerInTopRank")),
            "topRankSize": _as_int(goal.get("TopRankSize")) or 0,
            "percentileBandKnown": "PlayerPercentileBand" in goal,
            "percentileBand": _as_int(goal.get("PlayerPercentileBand")) or 0,
        })
    return goals
