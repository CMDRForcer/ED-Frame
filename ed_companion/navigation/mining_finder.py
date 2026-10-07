"""Pure projections for Mining Finder evidence; no I/O or UI dependencies."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from math import sqrt
from typing import Any, Iterable

from .mining_contract import MINING_FRESHNESS_SECONDS
from .mining_commodities import RHINO_SURFACE, mining_commodity_id

SPANSH_DUMP_URL = "https://spansh.co.uk/api/dump/{system_address}"
EDFRAME_CATALOG_SITES_URL = (
    "https://vps-20b25c36.vps.ovh.net/v1/sites/search"
)
EDFRAME_YIELD_OBSERVATIONS_URL = (
    "https://vps-20b25c36.vps.ovh.net/v1/yields/observations"
)

MINING_EVIDENCE_RANK = {
    "STALE": 0,
    "CATALOG_CANDIDATE": 1,
    "LIVE_REPORTED": 2,
    "LOCAL_CONFIRMED": 3,
}

NON_COMMODITY_SAA_SIGNALS = frozenset({
    "biological", "geological", "human", "guardian", "thargoid", "other",
    "planetarymininglocation",
})

MINING_BODY_TYPES = frozenset({
    "planetaryring", "stellarring", "asteroidcluster",
})

MINING_CATALOG_IDENTITY_VERSION = 2


def fetch_spansh_system_dump(system_address: int, get: Any, timeout: int = 20):
    """Fetch one documented public-system dump without sending private data."""
    try:
        address = int(system_address)
    except (TypeError, ValueError) as exc:
        raise ValueError("A numeric current system address is required") from exc
    if address <= 0:
        raise ValueError("A positive current system address is required")
    response = get(SPANSH_DUMP_URL.format(system_address=address), timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    system = payload.get("system") if isinstance(payload, dict) else None
    if not isinstance(system, dict) or int(system.get("id64") or 0) != address:
        raise ValueError("Spansh returned no matching system dump")
    return payload


def project_edframe_mining_candidates(
    payload: Any, origin: Any = None,
) -> list[dict[str, Any]]:
    """Project anonymous rows from the central ED-Frame mining catalog."""
    rows = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("ED-Frame mining catalog returned invalid data")
    result = []
    for source in rows:
        if not isinstance(source, dict):
            continue
        system = _text(source.get("system"))
        ring = _text(source.get("ring"))
        coordinates = _coordinates([
            source.get("x"), source.get("y"), source.get("z"),
        ])
        if not system or not ring:
            continue
        result.append({
            "system": system,
            "systemAddress": source.get("systemAddress"),
            "coordinates": coordinates,
            "distanceLy": _distance(origin, coordinates),
            "body": _text(source.get("body")),
            "bodyId": source.get("bodyId"),
            "ring": ring,
            "miningSiteType": (
                "BELT" if "belt cluster" in ring.casefold() else "RING"
            ),
            "ringType": _text(source.get("ringType")),
            "reserveLevel": _text(source.get("reserveLevel")),
            "distanceToArrivalLs": source.get("distanceToArrivalLs"),
            "hotspots": _signal_rows(source.get("hotspots")),
            "prospectorSampleCount": int(
                source.get("prospectorSampleCount", 0) or 0
            ),
            "yieldAggregationScope": "COMMUNITY",
            "communityOverlapReports": [
                dict(report) for report in (source.get("communityOverlapReports") or [])
                if isinstance(report, dict)
            ],
            "ringAssociationStatus": _text(source.get("ringAssociationStatus")),
            "systemPositionEvidence": dict(source.get("systemPositionEvidence") or {}),
            "yieldStats": [
                dict(stat) for stat in (source.get("yieldStats") or [])
                if isinstance(stat, dict)
                and _commodity_id(stat.get("commodity"))
            ],
            "evidence": _text(source.get("evidence")) or "LIVE_REPORTED",
            "observedAt": _text(source.get("observedAt")),
            "learnedAt": _text(source.get("receivedAt"))
                         or _text(source.get("observedAt")),
            "source": "ED-Frame live catalog · " + (
                _text(source.get("source")) or "EDDN"
            ),
            "markets": [],
        })
    return result


def fetch_edframe_mining_candidates(
    system: str, get: Any, *, commodity: str = "", origin: Any = None,
    timeout: int = 20, max_distance: float | None = None,
    diagnostics: dict | None = None,
) -> list[dict[str, Any]]:
    """Fetch one system from the central catalog without identity data."""
    requested = _text(system)
    if not requested:
        raise ValueError("A system name is required")
    params: dict[str, Any] = {"system": requested, "limit": 200}
    # Physical rings do not disappear when observations become old. Freshness
    # is assessed from observedAt downstream, never from the retrieval time.
    params["max_age_days"] = 3650
    params["include_community_overlaps"] = True
    coordinates = _coordinates(origin)
    if max_distance is not None:
        if not coordinates or not 0 < float(max_distance) <= 2000:
            raise ValueError("Regional mining search requires coordinates and radius")
        params.pop("system")
        params.update(dict(zip(("x", "y", "z"), coordinates)))
        params["max_distance"] = float(max_distance)
    commodity_id = mining_commodity_id(commodity)
    if commodity_id and commodity_id != "allcommodities":
        params["commodity"] = commodity_id
    response = get(EDFRAME_CATALOG_SITES_URL, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    candidates = project_edframe_mining_candidates(payload, origin)
    if diagnostics is not None:
        diagnostics.update({"count": len(candidates), "bounded": bool(
            payload.get("hasMore") or len(payload["results"]) >= 200
        )})
    return candidates


def project_local_yield_observations(
    local_evidence: Any, *, exclude_keys: set[str] | None = None,
    limit: int = 0,
) -> list[dict[str, Any]]:
    """Build the public, Commander-free subset of local prospector samples."""
    if not isinstance(local_evidence, dict):
        return []
    candidates = [
        row for row in (local_evidence.get("candidates") or [])
        if isinstance(row, dict)
    ]
    by_site = {
        _candidate_identity(row): row
        for row in candidates
        if _text(row.get("system")) and _text(row.get("ring"))
    }
    observations = []
    for sample in local_evidence.get("prospectorSamples") or []:
        if not isinstance(sample, dict) or not sample.get("boundToRing"):
            continue
        site = by_site.get(_candidate_identity(sample))
        if site is None:
            continue
        materials = []
        for material in sample.get("materials") or []:
            if not isinstance(material, dict):
                continue
            commodity = _commodity_id(material.get("commodity"))
            try:
                proportion = float(material.get("proportion"))
            except (TypeError, ValueError):
                continue
            if commodity and 0 <= proportion <= 100:
                materials.append({
                    "commodity": commodity,
                    "proportion": round(proportion, 4),
                })
        if not materials:
            continue
        observation = {
            "system": _text(site.get("system")),
            "systemAddress": site.get("systemAddress"),
            "coordinates": _coordinates(site.get("coordinates")),
            "body": _text(site.get("body")),
            "bodyId": site.get("bodyId"),
            "ring": _text(site.get("ring")),
            "ringType": _text(site.get("ringType")),
            "reserveLevel": _text(site.get("reserveLevel")),
            "distanceToArrivalLs": site.get("distanceToArrivalLs"),
            "observedAt": _text(sample.get("observedAt")),
            "materials": sorted(
                materials, key=lambda row: row["commodity"]
            ),
        }
        if exclude_keys and yield_observation_key(observation) in exclude_keys:
            continue
        observations.append(observation)
        if limit > 0 and len(observations) >= limit:
            break
    return observations


def yield_observation_key(observation: Any) -> str:
    """Return a stable local receipt key without adding user identity."""
    payload = json.dumps(
        observation if isinstance(observation, dict) else {},
        sort_keys=True, ensure_ascii=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def send_edframe_yield_observations(
    observations: Iterable[dict[str, Any]], post: Any, timeout: int = 20,
) -> dict[str, Any]:
    """Send one bounded anonymous batch to the ED-Frame catalog."""
    rows = [dict(row) for row in observations if isinstance(row, dict)]
    if len(rows) > 100:
        raise ValueError("A yield upload batch may contain at most 100 samples")
    response = post(
        EDFRAME_YIELD_OBSERVATIONS_URL,
        json={"observations": rows}, timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("ED-Frame yield service returned invalid data")
    return payload


def _text(value: Any) -> str:
    return str(value or "").strip()


def _missing(value: Any) -> bool:
    return value is None or value == "" or value == () or value == []


def _commodity_id(value: Any) -> str:
    value = _text(value)
    if value.startswith("$") and value.endswith("_Name;"):
        folded = value[1:-6].casefold()
    else:
        folded = value.casefold()
    prefix = "$saa_signaltype_"
    if folded.startswith(prefix) and folded.endswith(";"):
        folded = folded[len(prefix):-1]
    identifier = mining_commodity_id(folded)
    return "" if identifier in NON_COMMODITY_SAA_SIGNALS else identifier


def is_mining_commodity_signal(value: Any) -> bool:
    """Reject known DSS category markers while retaining mineral identifiers."""
    folded = _text(value).casefold()
    if folded.startswith("$saa_signaltype_") and folded.endswith(";"):
        folded = folded[len("$saa_signaltype_"):-1]
    return bool(folded and folded not in NON_COMMODITY_SAA_SIGNALS)


def _coordinates(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return []
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return []


def _distance(origin: Any, destination: Any) -> float | None:
    start = _coordinates(origin)
    end = _coordinates(destination)
    if not start or not end:
        return None
    return round(sqrt(sum((a - b) ** 2 for a, b in zip(start, end))), 1)


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _canonical_mining_site_name(value: Any) -> str:
    """Normalize equivalent Journal/EDDN/Spansh ring spellings.

    Public sources alternate between e.g. ``Delkar 7 a`` and
    ``Delkar 7 A Ring``.  Body ids are also not consistently present, so the
    stable identity is the system plus the normalized site name; body metadata
    is merged into that identity instead of splitting it.
    """
    name = " ".join(_text(value).split()).casefold()
    if name.endswith(" ring"):
        name = name[:-5].rstrip()
    return name


def _candidate_identity(candidate: dict[str, Any]) -> tuple[Any, ...]:
    try:
        system_address = int(candidate.get("systemAddress") or 0)
    except (TypeError, ValueError):
        system_address = 0
    system_key = (
        ("address", system_address) if system_address > 0
        else ("name", _text(candidate.get("system")).casefold())
    )
    site_name = _canonical_mining_site_name(candidate.get("ring"))
    system_name = " ".join(_text(candidate.get("system")).split()).casefold()
    # Fully qualified Frontier ring names already contain their body context.
    # For rare source rows that only say "A Ring", retain a body discriminator
    # so two different bodies in the same system are never over-merged.
    if system_name and not (
        site_name == system_name or site_name.startswith(system_name + " ")
    ):
        body_name = " ".join(
            _text(candidate.get("body")).split()
        ).casefold()
        if body_name:
            return system_key + ("body", body_name, site_name)
        if candidate.get("bodyId") is not None:
            return system_key + ("body-id", candidate.get("bodyId"), site_name)
    return system_key + (site_name,)


def is_belt_candidate(candidate: dict[str, Any]) -> bool:
    """Recognize belt clusters across Journal, EDDN and catalog shapes."""
    if not isinstance(candidate, dict):
        return False
    if _text(candidate.get("miningSiteType")).casefold() == "belt":
        return True
    ring_name = _text(candidate.get("ring")).casefold()
    body_name = _text(candidate.get("body")).casefold()
    return (
        "belt cluster" in ring_name
        or ring_name.endswith(" belt")
        or "belt cluster" in body_name
    )


def mining_candidate_positions(
    candidates: Iterable[dict[str, Any]],
) -> dict[tuple[Any, ...], int]:
    """Build the stable ring identity index used by incremental merges."""
    positions = {}
    row_index = 0
    for row in candidates or []:
        if not isinstance(row, dict):
            continue
        if _text(row.get("ring")):
            positions[_candidate_identity(row)] = row_index
        row_index += 1
    return positions


def merge_mining_candidate_batch(
    existing: Iterable[dict[str, Any]],
    additions: Iterable[dict[str, Any]],
    now: datetime | None = None,
    positions: dict[tuple[Any, ...], int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge a relay batch without rebuilding every unaffected ring."""
    rows = [row for row in existing or [] if isinstance(row, dict)]
    positions = (
        positions
        if positions is not None
        else mining_candidate_positions(rows)
    )
    displaced = []
    for incoming in merge_mining_candidates(additions, now=now):
        key = _candidate_identity(incoming)
        index = positions.get(key)
        if index is None:
            positions[key] = len(rows)
            rows.append(incoming)
            continue
        previous = rows[index]
        merged = merge_mining_candidates([previous, incoming], now=now)
        if merged:
            displaced.append(previous)
            rows[index] = merged[0]
    return rows, displaced


def mining_candidate_freshness(
    candidate: dict[str, Any], now: datetime | None = None,
    policy: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Apply an explicit ED-Frame age policy without asserting game persistence."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    source_evidence = _text(candidate.get("sourceEvidence")) or _text(
        candidate.get("evidence")
    )
    observed = _timestamp(candidate.get("observedAt"))
    limits = policy or MINING_FRESHNESS_SECONDS
    limit = limits.get(source_evidence)
    age_seconds = max(0, int((now - observed).total_seconds())) if observed else None
    stale = observed is None or limit is None or age_seconds > limit
    row = dict(candidate)
    row.update({
        "sourceEvidence": source_evidence,
        "evidence": source_evidence,
        "stale": stale,
        "recheckRecommended": stale,
        "confirmationStatus": (
            "CONFIRMATION_TIME_UNKNOWN" if observed is None
            else "RECHECK_RECOMMENDED" if stale
            else "RECENTLY_CONFIRMED"
        ),
        "ageSeconds": age_seconds,
        "freshnessLimitSeconds": limit,
    })
    return row


def merge_mining_candidates(
    candidates: Iterable[dict[str, Any]], now: datetime | None = None,
    policy: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Merge identical rings while retaining every source observation."""
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for candidate in candidates or []:
        if not isinstance(candidate, dict) or not _text(candidate.get("ring")):
            continue
        row = mining_candidate_freshness(candidate, now=now, policy=policy)
        groups.setdefault(_candidate_identity(row), []).append(row)

    merged = []
    fill_fields = (
        "system", "systemAddress", "coordinates", "distanceLy", "body",
        "bodyId", "ring", "ringType", "reserveLevel", "distanceToArrivalLs",
        "miningSiteType", "controllingPower", "powerState", "powers",
        "systemState",
    )
    for observations in groups.values():
        observations.sort(key=lambda row: (
            not row.get("stale"),
            MINING_EVIDENCE_RANK.get(row["sourceEvidence"], 0),
            _timestamp(row.get("observedAt")) or datetime.min.replace(
                tzinfo=timezone.utc
            ),
        ), reverse=True)
        strongest = dict(observations[0])
        for field in fill_fields:
            if not _missing(strongest.get(field)):
                continue
            for source in observations[1:]:
                value = source.get(field)
                if not _missing(value):
                    strongest[field] = value
                    break

        hotspots: dict[str, dict[str, Any]] = {}
        for source in observations:
            for hotspot in source.get("hotspots") or []:
                if not isinstance(hotspot, dict):
                    continue
                commodity = _text(hotspot.get("commodity")).casefold()
                if commodity and commodity not in hotspots:
                    hotspots[commodity] = dict(hotspot)
        strongest["hotspots"] = [hotspots[key] for key in sorted(hotspots)]
        overlap_reports = {}
        for source in observations:
            for report in source.get("communityOverlapReports") or []:
                if not isinstance(report, dict):
                    continue
                key = (report.get("sourceUrl"), report.get("sourceRevision"),
                       report.get("sourceRow"))
                overlap_reports[key] = dict(report)
        strongest["communityOverlapReports"] = list(overlap_reports.values())
        strongest["planetaryMiningLocationCount"] = max(
            int(source.get("planetaryMiningLocationCount", 0) or 0)
            for source in observations
        )
        community_observations = [
            source for source in observations
            if source.get("yieldAggregationScope") == "COMMUNITY"
        ]
        local_observations = [
            source for source in observations
            if source.get("yieldAggregationScope") != "COMMUNITY"
        ]
        community_samples = max((
            int(source.get("prospectorSampleCount", 0) or 0)
            for source in community_observations
        ), default=0)
        local_samples = sum(
            int(source.get("prospectorSampleCount", 0) or 0)
            for source in local_observations
        )
        strongest["prospectorSampleCount"] = (
            max(community_samples, local_samples)
            if community_observations and local_observations
            else community_samples + local_samples
        )
        yield_stats: dict[str, dict[str, Any]] = {}
        stat_sources: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        for source in observations:
            for stat in source.get("yieldStats") or []:
                if not isinstance(stat, dict):
                    continue
                commodity = _commodity_id(stat.get("commodity"))
                if not commodity:
                    continue
                stat_sources.setdefault(commodity, []).append((source, stat))
        selected_scopes = set()
        for commodity, entries in stat_sources.items():
            community_entries = [
                entry for entry in entries
                if entry[1].get("yieldAggregationScope", entry[0].get(
                    "yieldAggregationScope"
                )) == "COMMUNITY"
            ]
            local_entries = [
                entry for entry in entries
                if entry not in community_entries
            ]
            # Server aggregates overlap: snapshots are not independent samples.
            # Use the newest community snapshot, not their sum (nor a historic
            # larger snapshot after corrections). Local/community overlap is
            # handled conservatively below because uploaded samples may recur.
            community_entries = ([max(community_entries, key=lambda entry: (
                _text(entry[0].get("learnedAt")),
                _text(entry[1].get("lastObservedAt")),
            ))] if community_entries else [])
            measurement_entries = community_entries or local_entries
            selected_scope = "COMMUNITY" if community_entries else "LOCAL"
            if community_entries and local_entries:
                community_best = max(community_entries, key=lambda entry: int(
                    entry[1].get("proportionSamples",
                                 entry[1].get("prospectorHits", 0)) or 0
                ))
                community_count = int(
                    community_best[1].get(
                        "proportionSamples",
                        community_best[1].get("prospectorHits", 0),
                    ) or 0
                )
                local_count = sum(int(
                    stat.get("proportionSamples", stat.get(
                        "prospectorHits", 0
                    )) or 0
                ) for _source, stat in local_entries)
                measurement_entries = (
                    [community_best]
                    if community_count >= local_count else local_entries
                )
                selected_scope = (
                    "COMMUNITY" if community_count >= local_count else "LOCAL"
                )
            for source, stat in measurement_entries:
                combined = yield_stats.setdefault(commodity, {
                    "commodity": commodity,
                    "prospectorHits": 0,
                    "proportionTotal": 0.0,
                    "proportionSamples": 0,
                    "maxProportion": None,
                    "refinedCount": 0,
                    "lastObservedAt": "",
                })
                hits = int(stat.get("prospectorHits", 0) or 0)
                proportion_samples = int(
                    stat.get("proportionSamples", hits) or 0
                )
                proportion_total = stat.get("proportionTotal")
                if proportion_total is None:
                    proportion_total = (
                        float(stat.get("averageProportion", 0) or 0)
                        * proportion_samples
                    )
                combined["prospectorHits"] += hits
                combined["proportionSamples"] += proportion_samples
                combined["proportionTotal"] += float(proportion_total or 0)
                maximum = stat.get("maxProportion")
                if maximum is not None:
                    maximum = float(maximum)
                    current_maximum = combined["maxProportion"]
                    combined["maxProportion"] = (
                        maximum if current_maximum is None
                        else max(current_maximum, maximum)
                    )
                combined["lastObservedAt"] = max(
                    combined["lastObservedAt"],
                    _text(stat.get("lastObservedAt")),
                )
            combined = yield_stats[commodity]
            combined["yieldAggregationScope"] = selected_scope
            selected_scopes.add(selected_scope)
            combined["refinedCount"] = sum(
                int(stat.get("refinedCount", 0) or 0)
                for source, stat in entries
                if source.get("yieldAggregationScope") != "COMMUNITY"
            )
        strongest["yieldStats"] = []
        for commodity in sorted(yield_stats):
            stat = yield_stats[commodity]
            sample_count = stat["proportionSamples"]
            stat["averageProportion"] = (
                round(stat["proportionTotal"] / sample_count, 3)
                if sample_count else None
            )
            stat["proportionTotal"] = round(stat["proportionTotal"], 3)
            strongest["yieldStats"].append(stat)
        if selected_scopes:
            strongest["yieldAggregationScope"] = (
                next(iter(selected_scopes)) if len(selected_scopes) == 1 else "MIXED"
            )
        strongest["learnedAt"] = max(
            (_text(source.get("learnedAt")) for source in observations),
            default="",
        )
        evidence_rows = []
        evidence_keys = set()
        for source in observations:
            summaries = [{
                "evidence": source.get("evidence"),
                "sourceEvidence": source.get("sourceEvidence"),
                "observedAt": source.get("observedAt"),
                "source": source.get("source"),
                "stale": source.get("stale"),
            }]
            summaries.extend(
                row for row in (source.get("observations") or [])
                if isinstance(row, dict)
            )
            for summary in summaries:
                stable_summary = {
                    key: value for key, value in summary.items()
                    if key != "stale"
                }
                key = json.dumps(
                    stable_summary, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"),
                )
                if key not in evidence_keys:
                    evidence_keys.add(key)
                    evidence_rows.append(dict(summary))
        strongest["observations"] = evidence_rows
        strongest["sourceCount"] = len(evidence_rows)
        merged.append(strongest)

    return sorted(merged, key=lambda row: (
        row.get("distanceLy") is None,
        float(row.get("distanceLy") or 0),
        _text(row.get("system")).casefold(),
        _text(row.get("ring")).casefold(),
    ))


def _signal_rows(signals: Any) -> list[dict[str, Any]]:
    rows = []
    if isinstance(signals, dict):
        iterable = signals.items()
    elif isinstance(signals, list):
        iterable = (
            (
                row.get("Type") or row.get("commodity"),
                row.get("Count") if "Count" in row else row.get("count"),
            )
            for row in signals if isinstance(row, dict)
        )
    else:
        iterable = ()
    for raw_type, raw_count in iterable:
        commodity = _commodity_id(raw_type)
        if not commodity:
            continue
        try:
            count = max(0, int(raw_count or 0))
        except (TypeError, ValueError):
            count = 0
        rows.append({"commodity": commodity, "count": count})
    return sorted(rows, key=lambda row: row["commodity"])


def _named_signal_count(signals: Any, signal_id: str) -> int:
    """Return the reported count for a non-commodity DSS/FSS signal."""
    wanted = mining_commodity_id(signal_id)
    total = 0
    if isinstance(signals, dict):
        iterable = signals.items()
    elif isinstance(signals, list):
        iterable = (
            (row.get("Type"), row.get("Count"))
            for row in signals if isinstance(row, dict)
        )
    else:
        iterable = ()
    for raw_type, raw_count in iterable:
        if mining_commodity_id(raw_type) != wanted:
            continue
        try:
            total += max(0, int(raw_count or 0))
        except (TypeError, ValueError):
            continue
    return total


def project_local_mining_evidence(
    events: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Project rings, samples and every locally refined commodity."""
    system = ""
    system_address = None
    star_pos: list[float] = []
    rings: dict[str, dict[str, Any]] = {}
    candidates: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    refined: dict[str, dict[str, Any]] = {}
    active_srv = ""
    active_ring = ""
    controlling_power = ""
    powerplay_state = ""
    powers: list[str] = []

    def ensure_ring(
        ring_name: str, body_id: Any, observed_at: str, source: str,
    ) -> dict[str, Any] | None:
        if not ring_name:
            return None
        key = ring_name.casefold()
        row = rings.get(key)
        if row is None:
            row = {
                "system": system,
                "systemAddress": system_address,
                "coordinates": list(star_pos),
                "body": "",
                "bodyId": body_id,
                "ring": ring_name,
                "ringType": "",
                "reserveLevel": "",
                "distanceToArrivalLs": None,
                "controllingPower": controlling_power,
                "powerState": powerplay_state,
                "powers": list(powers),
                "hotspots": [],
                "evidence": "LOCAL_CONFIRMED",
                "observedAt": observed_at,
                "source": source,
                "yieldAggregationScope": "LOCAL",
            }
            rings[key] = row
            candidates.append(row)
        return row

    def update_ring_yield(
        row: dict[str, Any], commodity: str, observed_at: str,
        *, proportion: float | None = None, refined_count: int = 0,
    ) -> None:
        if not commodity:
            return
        stats = row.setdefault("_yieldStats", {})
        stat = stats.setdefault(commodity, {
            "commodity": commodity,
            "prospectorHits": 0,
            "proportionTotal": 0.0,
            "proportionSamples": 0,
            "maxProportion": None,
            "refinedCount": 0,
            "lastObservedAt": "",
        })
        if proportion is not None:
            stat["prospectorHits"] += 1
            stat["proportionTotal"] += proportion
            stat["proportionSamples"] += 1
            stat["maxProportion"] = (
                proportion if stat["maxProportion"] is None
                else max(stat["maxProportion"], proportion)
            )
        stat["refinedCount"] += refined_count
        stat["lastObservedAt"] = max(stat["lastObservedAt"], observed_at)

    for event in events or []:
        if not isinstance(event, dict):
            continue
        name = _text(event.get("event"))
        if name == "LaunchSRV":
            active_srv = _text(event.get("SRVType")).casefold()
            continue
        if name == "DockSRV":
            active_srv = ""
            continue
        if name in {"Location", "FSDJump", "CarrierJump"}:
            active_ring = ""
            system = _text(event.get("StarSystem")) or system
            system_address = event.get("SystemAddress", system_address)
            star_pos = _coordinates(event.get("StarPos")) or star_pos
            controlling_power = _text(event.get("ControllingPower"))
            powerplay_state = _text(event.get("PowerplayState"))
            powers = [
                _text(value) for value in event.get("Powers", []) or []
                if _text(value)
            ]
            body_type = _text(event.get("BodyType")).casefold()
            site_name = _text(event.get("Body") or event.get("BodyName"))
            if name == "Location" and body_type in MINING_BODY_TYPES and site_name:
                row = ensure_ring(
                    site_name, event.get("BodyID"),
                    _text(event.get("timestamp")),
                    f"Frontier Journal · {event.get('BodyType')} location",
                )
                if row:
                    row["miningSiteType"] = (
                        "BELT" if body_type in {"stellarring", "asteroidcluster"}
                        else "RING"
                    )
                    active_ring = site_name.casefold()
            continue
        if name == "SupercruiseEntry":
            active_ring = ""
            continue
        if name == "SupercruiseExit":
            system = _text(event.get("StarSystem")) or system
            system_address = event.get("SystemAddress", system_address)
            star_pos = _coordinates(event.get("StarPos")) or star_pos
            body_type = _text(event.get("BodyType")).casefold()
            ring_name = _text(event.get("Body") or event.get("BodyName"))
            if body_type in MINING_BODY_TYPES and ring_name:
                row = ensure_ring(
                    ring_name, event.get("BodyID"),
                    _text(event.get("timestamp")),
                    f"Frontier Journal · {event.get('BodyType')} arrival",
                )
                if row:
                    row["miningSiteType"] = (
                        "BELT" if body_type in {"stellarring", "asteroidcluster"}
                        else "RING"
                    )
                active_ring = ring_name.casefold() if row else ""
            else:
                active_ring = ""
            continue
        if name == "Scan":
            reserve = _text(event.get("ReserveLevel"))
            body = _text(event.get("BodyName"))
            for ring in event.get("Rings") or []:
                if not isinstance(ring, dict) or not _text(ring.get("Name")):
                    continue
                ring_name = _text(ring["Name"])
                row = ensure_ring(
                    ring_name, event.get("BodyID"),
                    _text(event.get("timestamp")), "Frontier Journal · Scan",
                )
                row.update({
                    "system": system,
                    "systemAddress": system_address,
                    "coordinates": list(star_pos),
                    "body": body,
                    "bodyId": event.get("BodyID"),
                    "ringType": _text(ring.get("RingClass")),
                    "reserveLevel": reserve,
                    "distanceToArrivalLs": event.get("DistanceFromArrivalLS"),
                    "observedAt": _text(event.get("timestamp")),
                    "source": "Frontier Journal · Scan",
                })
            continue
        if name in {"SAASignalsFound", "FSSBodySignals"}:
            ring_name = _text(event.get("BodyName"))
            row = ensure_ring(
                ring_name, event.get("BodyID"),
                _text(event.get("timestamp")),
                f"Frontier Journal · {name}",
            )
            if row is None:
                continue
            row["hotspots"] = _signal_rows(event.get("Signals"))
            planetary_count = _named_signal_count(
                event.get("Signals"), "planetarymininglocation"
            )
            if planetary_count:
                row["planetaryMiningLocationCount"] = planetary_count
            row["observedAt"] = _text(event.get("timestamp")) or row["observedAt"]
            row["source"] = f"Frontier Journal · Scan + {name}"
            continue
        if name == "ProspectedAsteroid":
            materials = []
            for material in event.get("Materials") or []:
                if not isinstance(material, dict):
                    continue
                commodity = _commodity_id(material.get("Name"))
                if not commodity:
                    continue
                try:
                    proportion = float(material.get("Proportion"))
                except (TypeError, ValueError):
                    proportion = None
                materials.append({
                    "commodity": commodity, "proportion": proportion,
                })
            samples.append({
                "system": system,
                "systemAddress": system_address,
                "ring": rings[active_ring]["ring"] if active_ring else "",
                "bodyId": (
                    rings[active_ring].get("bodyId") if active_ring else None
                ),
                "observedAt": _text(event.get("timestamp")),
                "content": _text(event.get("Content")),
                "remaining": event.get("Remaining"),
                "motherlode": _commodity_id(event.get("MotherlodeMaterial")),
                "materials": materials,
                "boundToRing": bool(active_ring),
                "evidence": "LOCAL_CONFIRMED",
                "source": "Frontier Journal · ProspectedAsteroid",
            })
            if active_ring:
                ring_row = rings[active_ring]
                ring_row["prospectorSampleCount"] = int(
                    ring_row.get("prospectorSampleCount", 0) or 0
                ) + 1
                for material in materials:
                    update_ring_yield(
                        ring_row, material["commodity"],
                        _text(event.get("timestamp")),
                        proportion=material["proportion"],
                    )
            continue
        if name == "MiningRefined":
            commodity = _commodity_id(event.get("Type"))
            if not commodity:
                continue
            row = refined.setdefault(commodity, {
                "id": commodity,
                "count": 0,
                "lastObservedAt": "",
                "methods": [],
                "source": "Frontier Journal · MiningRefined",
            })
            row["count"] += 1
            row["lastObservedAt"] = max(
                row["lastObservedAt"], _text(event.get("timestamp"))
            )
            if "rhino" in active_srv and RHINO_SURFACE not in row["methods"]:
                row["methods"].append(RHINO_SURFACE)
            if active_ring:
                update_ring_yield(
                    rings[active_ring], commodity,
                    _text(event.get("timestamp")), refined_count=1,
                )
    for candidate in candidates:
        stats = candidate.pop("_yieldStats", {})
        candidate["yieldStats"] = []
        for commodity in sorted(stats):
            stat = stats[commodity]
            count = stat["proportionSamples"]
            stat["proportionTotal"] = round(stat["proportionTotal"], 3)
            stat["averageProportion"] = (
                round(stat["proportionTotal"] / count, 3)
                if count else None
            )
            candidate["yieldStats"].append(stat)
    return {
        "candidates": candidates,
        "prospectorSamples": samples,
        "refinedCommodities": sorted(
            refined.values(), key=lambda row: row["id"]
        ),
    }


def project_eddn_mining_candidates(
    payload: dict[str, Any], received_at: str = "",
) -> list[dict[str, Any]]:
    """Project only explicit public mining fields from an EDDN journal frame."""
    if not isinstance(payload, dict):
        return []
    schema = _text(payload.get("$schemaRef")).casefold()
    message = payload.get("message")
    supported_schema = (
        "/journal/1" in schema or "/fssbodysignals/1" in schema
    )
    if not supported_schema or not isinstance(message, dict):
        return []
    event_name = _text(message.get("event"))
    if event_name not in {"Scan", "SAASignalsFound", "FSSBodySignals"}:
        return []
    location = {
        "event": "Location",
        "StarSystem": _text(message.get("StarSystem")),
        "SystemAddress": message.get("SystemAddress"),
        "StarPos": _coordinates(message.get("StarPos")),
        "ControllingPower": _text(message.get("ControllingPower")),
        "PowerplayState": _text(message.get("PowerplayState")),
        "Powers": [
            _text(value) for value in message.get("Powers", []) or []
            if _text(value)
        ],
    }
    event = {
        "event": event_name,
        "timestamp": _text(message.get("timestamp")) or received_at,
        "BodyName": _text(message.get("BodyName")),
        "BodyID": message.get("BodyID"),
    }
    if event_name == "Scan":
        event.update({
            "ReserveLevel": _text(message.get("ReserveLevel")),
            "DistanceFromArrivalLS": message.get("DistanceFromArrivalLS"),
            "Rings": [{
                "Name": _text(ring.get("Name")),
                "RingClass": _text(ring.get("RingClass")),
            } for ring in message.get("Rings") or [] if isinstance(ring, dict)],
        })
    else:
        event["Signals"] = [{
            "Type": _text(signal.get("Type")),
            "Count": signal.get("Count"),
        } for signal in message.get("Signals") or [] if isinstance(signal, dict)]
    rows = project_local_mining_evidence([location, event])["candidates"]
    source_schema = (
        "fssbodysignals/1" if "/fssbodysignals/1" in schema else "journal/1"
    )
    for row in rows:
        row.update({
            "evidence": "LIVE_REPORTED",
            "source": f"EDDN {source_schema} · {event_name}",
            "learnedAt": _text(received_at) or _text(message.get("timestamp")),
        })
    return rows


def _spansh_mining_markets(system: dict[str, Any]) -> list[dict[str, Any]]:
    """Retain only mineable commodity demand from an optional dump market."""
    rows = []
    for station in system.get("stations") or []:
        if not isinstance(station, dict):
            continue
        commodities = station.get("commodities") or station.get("market") or []
        if isinstance(commodities, dict):
            commodities = commodities.get("commodities") or []
        for commodity in commodities if isinstance(commodities, list) else []:
            if not isinstance(commodity, dict):
                continue
            identifier = mining_commodity_id(
                commodity.get("name") or commodity.get("commodity")
                or commodity.get("symbol")
            )
            if not identifier:
                continue
            try:
                sell_price = max(0, int(
                    commodity.get("sellPrice")
                    or commodity.get("sell_price") or 0
                ))
                demand = max(0, int(commodity.get("demand") or 0))
            except (TypeError, ValueError):
                continue
            if sell_price <= 0 or demand <= 0:
                continue
            landing_pad_size = _text(station.get("landingPadSize"))
            landing_pads = station.get("landingPads")
            if not landing_pad_size and isinstance(landing_pads, dict):
                for key, label in (
                    ("large", "L"), ("medium", "M"), ("small", "S"),
                ):
                    try:
                        available = int(landing_pads.get(key, 0) or 0)
                    except (TypeError, ValueError):
                        available = 0
                    if available > 0:
                        landing_pad_size = label
                        break
            rows.append({
                "commodity": identifier,
                "station": _text(station.get("name")),
                "system": _text(system.get("name")),
                "sellPrice": sell_price,
                "demand": demand,
                "observedAt": _text(
                    commodity.get("updateTime") or station.get("updateTime")
                    or system.get("date")
                ),
                "landingPadSize": landing_pad_size,
                "distanceToArrivalLs": station.get("distanceToArrival"),
                "controllingPower": _text(
                    station.get("controllingPower")
                    or system.get("controllingPower")
                ),
                "powerState": _text(
                    station.get("powerState") or system.get("powerState")
                ),
                "powers": [
                    _text(item) for item in system.get("powers") or []
                    if _text(item)
                ],
                "systemState": _text(system.get("state")),
                "source": "Spansh system dump market",
            })
    return rows


def project_spansh_mining_candidates(
    payload: dict[str, Any], origin: Any = None,
) -> list[dict[str, Any]]:
    """Project the documented Spansh dump response into catalog candidates."""
    system = payload.get("system") if isinstance(payload, dict) else None
    if not isinstance(system, dict):
        return []
    coordinates_object = system.get("coords")
    coordinates = _coordinates([
        coordinates_object.get("x"),
        coordinates_object.get("y"),
        coordinates_object.get("z"),
    ]) if isinstance(coordinates_object, dict) else []
    rows = []
    markets = _spansh_mining_markets(system)
    for body in system.get("bodies") or []:
        if not isinstance(body, dict):
            continue
        for ring in body.get("rings") or []:
            if not isinstance(ring, dict) or not _text(ring.get("name")):
                continue
            signal_block = ring.get("signals")
            signal_block = signal_block if isinstance(signal_block, dict) else {}
            rows.append({
                "system": _text(system.get("name")),
                "systemAddress": system.get("id64"),
                "coordinates": coordinates,
                "distanceLy": _distance(origin, coordinates),
                "body": _text(body.get("name")),
                "bodyId": body.get("bodyId"),
                "ring": _text(ring.get("name")),
                "miningSiteType": (
                    "BELT" if "belt cluster" in _text(
                        ring.get("name")
                    ).casefold() else "RING"
                ),
                "ringType": _text(ring.get("type")),
                "reserveLevel": _text(body.get("reserveLevel")),
                "distanceToArrivalLs": body.get("distanceToArrival"),
                "hotspots": _signal_rows(signal_block.get("signals")),
                "evidence": "CATALOG_CANDIDATE",
                "observedAt": _text(
                    signal_block.get("updateTime")
                    or body.get("updateTime") or system.get("date")
                ),
                "source": "Spansh dump catalog",
                "markets": [dict(row) for row in markets],
                "controllingPower": _text(system.get("controllingPower")),
                "powerState": _text(system.get("powerState")),
                "powers": [
                    _text(item) for item in system.get("powers") or []
                    if _text(item)
                ],
                "systemState": _text(system.get("state")),
            })
    return rows
