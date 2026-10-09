"""Small, anonymous Powerplay catalog used by Mining Finder.

EDSM publishes a daily Powerplay-only dump.  At roughly a few megabytes it is
the practical serverless counterpart to MeritMiner's own database: it tells us
which Powers are present in a system and which system state they report without
downloading the galaxy/station dumps.  It does *not* identify the controlling
Power; that fact must come from an explicit Frontier/EDDN observation.
"""

from __future__ import annotations

import gzip
import json
from math import isfinite
from datetime import datetime, timezone
from typing import Any, Iterable

from ed_companion import APP_VERSION


POWERPLAY_DUMP_URL = "https://www.edsm.net/dump/powerPlay.json.gz"
EDFRAME_POWERPLAY_URL = "https://vps-20b25c36.vps.ovh.net/v1/mining/powerplay"
EDFRAME_POWERPLAY_LOOKUP_URL = EDFRAME_POWERPLAY_URL + "/lookup"
SPANSH_POWERPLAY_SOURCE = "Spansh system dump Powerplay"
POWERPLAY_CATALOG_SOURCE = "EDSM daily PowerPlay catalog"
POWERPLAY_CATALOG_SCHEMA_VERSION = 3
POWERPLAY_STATES = frozenset({
    "Unoccupied", "Exploited", "Fortified", "Stronghold", "Headquarters",
})


class MiningPowerplayError(RuntimeError):
    """A concise, user-displayable Powerplay catalog failure."""


def fetch_edframe_powerplay(*, origin: list, max_distance: float, get: Any,
                           timeout: int = 10, diagnostics: dict | None = None,
                           systems: list[str] | None = None) -> list[dict[str, Any]]:
    """Read all advertised pages, retaining usable facts on continuation failure.

    ``systems`` requests exact systems (including sale systems outside the mine
    radius). Older servers are detected explicitly, never mistaken for a
    successful exact lookup just because they ignored the new query parameter.
    """
    if diagnostics is not None:
        diagnostics.clear()
    if systems and not origin:
        # Named batches do not use a spatial origin on the server. This is a
        # query placeholder only, never stored as system coordinates.
        origin = [0, 0, 0]
    if len(origin or []) != 3:
        raise MiningPowerplayError("Powerplay query requires coordinates")
    try:
        origin = [float(value) for value in origin]
        if not all(isfinite(value) for value in origin):
            raise ValueError("Non-finite coordinates")
    except (TypeError, ValueError) as exc:
        raise MiningPowerplayError("Invalid Powerplay coordinates") from exc
    params = {
        **dict(zip(("x", "y", "z"), origin)),
        "max_distance": max(1, min(2000, float(max_distance))),
        "max_age_hours": 24, "limit": 200,
    }
    wanted = list(dict.fromkeys(str(name).strip().casefold() for name in systems or []
                               if str(name).strip()))
    if wanted:
        if len(wanted) > 200 or any(len(name) > 100 for name in wanted):
            raise MiningPowerplayError("Powerplay lookup exceeds the system batch limit")
        params["system"] = wanted
        params["include_coverage"] = True
    else:
        # Backward compatible: older servers ignore the larger-page opt-in.
        params["regional_page_size"] = 1000
    rows = []
    cursors = set()
    system_count = 0
    for page in range(100):
        try:
            response = get(EDFRAME_POWERPLAY_URL, params=dict(params), timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise MiningPowerplayError("Invalid server Powerplay response")
            if wanted and payload.get("selection") != "systems":
                raise MiningPowerplayError("Server does not support exact Powerplay batches yet")
            count = payload.get("systemCount", params["limit"])
            if (type(count) is not int
                    or not 0 <= count <= params.get("regional_page_size", params["limit"])
                    or (payload.get("hasMore") and count == 0)):
                raise MiningPowerplayError("Invalid server Powerplay page size")
        except Exception as exc:
            if not rows or diagnostics is None:
                raise
            diagnostics.update(bounded=True, partialError=type(exc).__name__)
            break
        rows.extend(_public_powerplay_rows(payload["results"]))
        system_count += count
        has_more = bool(payload.get("hasMore"))
        if diagnostics is not None:
            diagnostics.update(bounded=has_more, pages=page + 1,
                               complete=payload.get("hasMore") is False)
            if wanted and isinstance(payload.get("coverage"), list):
                diagnostics["coverage"] = [
                    {key: item[key] for key in ("system", "state", "observedAt") if key in item}
                    for item in payload["coverage"] if isinstance(item, dict)
                    and str(item.get("system") or "").casefold() in wanted
                    and item.get("state") in {"CURRENT", "STALE", "MISSING"}
                ]
        if not has_more:
            break
        if not wanted and system_count >= 20_000:
            if diagnostics is not None:
                diagnostics.update(bounded=True, complete=False)
            break
        if not wanted:
            remaining = 20_000 - system_count
            params["regional_page_size"] = min(1000, remaining)
            params["limit"] = min(200, remaining)
        cursor = payload.get("nextCursor")
        if not isinstance(cursor, str) or not cursor or cursor in cursors:
            break  # Legacy/truncated response: preserve facts, report incomplete.
        cursors.add(cursor)
        params["cursor"] = cursor
    if wanted:
        rows = [row for row in rows if str(row["system"]).casefold() in wanted]
    return merge_powerplay_observations([], rows, limit=max(20_000, len(rows)))


def _public_powerplay_rows(sources: list) -> list[dict[str, Any]]:
    """Validate public live facts without inventing control from presence."""
    rows = []
    now = datetime.now(timezone.utc)
    for source in sources:
        if not isinstance(source, dict):
            continue
        # Whitelist public fields. An explicit controller must be present;
        # never trust a claimed CONTROL relationship alone.
        unoccupied = (source.get("powerState") == "Unoccupied"
                      and "controllingPower" in source and not source["controllingPower"])
        if (not source.get("system") or not source.get("observedAt")
                or (not source.get("power") and not unoccupied)
                or (source.get("powerState") == "Unoccupied" and source.get("controllingPower"))):
            continue
        try:
            stamp = datetime.fromisoformat(str(source["observedAt"]).replace("Z", "+00:00"))
            stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
            age = (now - stamp).total_seconds()
        except ValueError:
            continue
        if not -300 <= age <= 24 * 3600 or source.get("powerState") not in POWERPLAY_STATES:
            continue
        row = {key: source[key] for key in (
            "system", "systemAddress", "coordinates", "power", "powerState",
            "controllingPower", "powers", "powersKnown", "observedAt",
        ) if key in source}
        controller = str(row.get("controllingPower") or "").strip()
        row.update({
            "source": "ED-Frame live catalog · " + (
                SPANSH_POWERPLAY_SOURCE if source.get("source") == SPANSH_POWERPLAY_SOURCE
                else "EDDN journal/1"
            ),
            "controlKnown": bool(controller),
            "powerRelationship": "UNOCCUPIED" if unoccupied and not row.get("power")
                else "CONTROL" if controller and controller.casefold()
                == str(row.get("power") or "").casefold() else "PRESENCE",
        })
        rows.append(row)
    return rows


def missing_powerplay_targets(routes, observations=(), *, retry_after=None,
                             now=None) -> list[dict[str, Any]]:
    """Deduplicate mine AND sale systems across all displayed unknown routes.

    Ring freshness is unrelated to Powerplay freshness. Only a recent explicit
    control/state observation (or an explicit Unoccupied state) avoids a lookup.
    """
    now = now or datetime.now(timezone.utc)
    retry_after = retry_after or {}
    targets = {}
    for row in routes:
        if (row.get("optimization") != "POWERPLAY MERITS"
                or row.get("powerplayStatus") != "POWERPLAY_DATA_MISSING"):
            continue
        if "selectedPower" in row and str(row["selectedPower"] or "").strip().casefold() in {"", "any", "unconfirmed"}:
            continue  # Selecting a Power is user input, not missing server data.
        for name, coordinates in ((row.get("system"), row.get("coordinates")),
                                  (row.get("sellSystem"), row.get("sellCoordinates"))):
            name = str(name or "").strip()
            key = name.casefold()
            if not key or float(retry_after.get(key, 0) or 0) > now.timestamp():
                continue
            target = targets.setdefault(key, {"system": name, "coordinates": []})
            if isinstance(coordinates, (list, tuple)) and len(coordinates) == 3:
                target["coordinates"] = list(coordinates)
    for fact in observations or ():
        if not isinstance(fact, dict):
            continue
        key = str(fact.get("system") or "").strip().casefold()
        if key not in targets:
            continue
        try:
            stamp = datetime.fromisoformat(str(fact.get("observedAt") or "").replace("Z", "+00:00"))
            stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
            fresh = -300 <= (now - stamp).total_seconds() <= 86400
        except ValueError:
            continue
        coordinates = fact.get("coordinates") or targets[key].get("coordinates")
        if (fresh and isinstance(coordinates, (list, tuple)) and len(coordinates) == 3
                and fact.get("powerState") in POWERPLAY_STATES and (
                fact.get("controllingPower") or fact.get("powerState") == "Unoccupied")):
            targets.pop(key)
    return list(targets.values())


def fetch_powerplay_targets(targets, *, origin, get, diagnostics=None, enrich=False):
    """Batch precise missing systems; old servers use small spatial lookups.

    The compatibility path uses only known coordinates, never a galaxy dump or
    another ring query. Its facts still undergo the same freshness/whitelist
    validation. Callers run this on a cancellable network worker.
    """
    diagnostics = diagnostics if diagnostics is not None else {}
    rows, checked, failed, coverage = [], [], [], []
    targets = list(targets)
    legacy = False
    for start in range(0, len(targets), 200):
        batch = targets[start:start + 200]
        names = [target["system"] for target in batch]
        if not legacy:
            try:
                rows.extend(fetch_edframe_powerplay(
                    origin=origin, max_distance=2000, get=get, systems=names,
                    diagnostics=diagnostics,
                ))
                if diagnostics.get("bounded"):
                    raise MiningPowerplayError("Incomplete exact Powerplay lookup")
                coverage.extend(diagnostics.get("coverage", []))
                checked.extend(names)
                continue
            except MiningPowerplayError as exc:
                if "does not support exact" not in str(exc):
                    raise
                legacy = True
        diagnostics["legacy"] = True
        for target in batch:
            coordinates = target.get("coordinates") or []
            if len(coordinates) != 3:
                failed.append(target["system"])
                continue
            local_coverage = {}
            try:
                facts = fetch_edframe_powerplay(
                    origin=coordinates, max_distance=1, get=get,
                    diagnostics=local_coverage,
                )
                if local_coverage.get("bounded"):
                    failed.append(target["system"])
                    continue
                rows.extend(fact for fact in facts if str(fact["system"]).casefold()
                            == target["system"].casefold())
                checked.append(target["system"])
            except Exception:
                failed.append(target["system"])
    result = {"rows": rows, "checked": checked, "failed": failed}
    if coverage:
        result["coverage"] = coverage
    if enrich:
        known = {str(row.get("system") or "").casefold() for row in rows
                 if row.get("controllingPower") or row.get("powerState") == "Unoccupied"}
        missing = list({target["system"].casefold(): target["system"] for target in targets
            if target["system"].casefold() not in known}.values())
        selected = missing[:6]
        result["enrichmentDeferred"] = missing[6:]
        if selected:
            try:
                response = get(EDFRAME_POWERPLAY_LOOKUP_URL,
                    params={"system": selected}, timeout=60)
                response.raise_for_status()
                payload = response.json()
                if (not isinstance(payload, dict) or payload.get("selection") != "systems"
                        or not isinstance(payload.get("results"), list)
                        or not isinstance(payload.get("lookup"), list)):
                    raise MiningPowerplayError("Invalid targeted Powerplay enrichment")
                wanted = {name.casefold() for name in selected}
                additions = [row for row in _public_powerplay_rows(payload["results"])
                             if row["system"].casefold() in wanted]
                result["rows"] = merge_powerplay_observations(rows, additions,
                    limit=max(20_000, len(rows) + len(additions)))
                result["enrichment"] = [{key: item[key] for key in
                    ("system", "state", "source", "observedAt") if key in item}
                    for item in payload["lookup"] if isinstance(item, dict)
                    and str(item.get("system") or "").casefold() in wanted
                    and item.get("state") in {
                        "CURRENT", "FETCHED", "MISSING", "STALE", "ERROR", "BUSY", "NO_ADDRESS"
                    }]
                refreshed = {row["system"].casefold(): row for row in additions}
                for item in result.get("coverage", []):
                    if item["system"].casefold() in refreshed:
                        item.update(state="CURRENT", observedAt=refreshed[item["system"].casefold()]["observedAt"])
            except Exception as exc:
                # Existing servers remain usable while the additive endpoint
                # rolls out; a failed fallback never discards the first lookup.
                result["enrichment"] = [{"system": name, "state": "ERROR"} for name in selected]
                result["enrichmentError"] = type(exc).__name__
    return result


def project_spansh_powerplay(payload, system, system_address, *, now=None):
    """Keep only explicit, recent, identity-matched Spansh system snapshots."""
    data = payload.get("system") if isinstance(payload, dict) else None
    if (not isinstance(data, dict) or not isinstance(data.get("name"), str)
            or data["name"].strip().casefold() != system.strip().casefold()):
        return []
    try:
        address = int(data.get("id64"))
        if type(data.get("id64")) is not int or address != int(system_address) or not 0 < address < 2**64:
            return []
        if not isinstance(data.get("date"), str):
            return []
        stamp = datetime.fromisoformat(data["date"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return []
        age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
    except (ValueError, TypeError, OverflowError):
        return []
    if not -300 <= age <= 86400:
        return []
    state = data.get("powerState")
    controller = data.get("controllingPower", "")
    participants = data.get("powers")
    if (not isinstance(state, str) or state not in POWERPLAY_STATES or not isinstance(controller, str)
            or len(controller) > 100
            or (participants is not None and (not isinstance(participants, list)
                or len(participants) > 32
                or any(not isinstance(power, str) or not power.strip() or len(power) > 100
                       for power in participants)))):
        return []
    controller = controller.strip()
    if (not controller and state != "Unoccupied") or (controller and state == "Unoccupied"):
        return []
    coords = data.get("coords")
    if not isinstance(coords, dict) or any(isinstance(coords.get(axis), bool) for axis in ("x", "y", "z")):
        return []
    coordinates = _coordinates(coords)
    if len(coordinates) != 3 or not all(isfinite(value) for value in coordinates):
        return []
    powers = list(dict.fromkeys(power.strip() for power in participants or []))
    if controller and controller.casefold() not in {power.casefold() for power in powers}:
        powers.append(controller)
    return [{
        "system": data["name"].strip(), "systemAddress": address, "coordinates": coordinates,
        "power": power, "powerState": state, "controllingPower": controller,
        "powers": list(powers), "powersKnown": isinstance(participants, list),
        "powerRelationship": "UNOCCUPIED" if not power else
            "CONTROL" if power.casefold() == controller.casefold() else "PRESENCE",
        "controlKnown": bool(controller), "observedAt": data["date"],
        "source": SPANSH_POWERPLAY_SOURCE,
    } for power in powers or [""]]


def _coordinates(value: Any) -> list[float]:
    if not isinstance(value, dict):
        return []
    try:
        return [float(value[axis]) for axis in ("x", "y", "z")]
    except (KeyError, TypeError, ValueError):
        return []


def project_powerplay_observations(
    payload: Any, received_at: str = "",
) -> list[dict[str, Any]]:
    """Project authoritative Frontier location facts from Journal/EDDN.

    Unlike EDSM's presence rows, Frontier's ``ControllingPower`` explicitly
    identifies control.  One compact row per participating Power lets the
    planner combine that fact with the daily range/state catalog.
    """
    message = payload.get("message") if isinstance(payload, dict) else None
    source = "EDDN journal/1"
    if not isinstance(message, dict):
        message = payload if isinstance(payload, dict) else None
        source = "Frontier Journal"
    if not isinstance(message, dict) or str(
        message.get("event") or ""
    ) not in {"Location", "FSDJump", "CarrierJump"}:
        return []
    system = str(message.get("StarSystem") or "").strip()
    state = str(message.get("PowerplayState") or "").strip()
    controller = str(message.get("ControllingPower") or "").strip()
    participants = message.get("Powers")
    if participants is not None and not isinstance(participants, list):
        return []
    powers = list(dict.fromkeys(
        str(value).strip() for value in message.get("Powers", []) or []
        if isinstance(value, str) and value.strip()
    ))
    if controller and controller.casefold() not in {
        value.casefold() for value in powers
    }:
        powers.append(controller)
    unoccupied = state == "Unoccupied" and not controller
    if (not system or state not in POWERPLAY_STATES or (not powers and not unoccupied)
            or (state == "Unoccupied" and controller)):
        return []
    try:
        address = int(message.get("SystemAddress") or 0)
    except (TypeError, ValueError):
        address = 0
    coordinates = message.get("StarPos")
    if isinstance(coordinates, (list, tuple)) and len(coordinates) == 3:
        try:
            coordinates = [float(value) for value in coordinates]
            if not all(isfinite(value) for value in coordinates):
                return []
        except (TypeError, ValueError):
            coordinates = []
    else:
        coordinates = []
    observed_at = str(
        message.get("timestamp") or received_at or ""
    ).strip()
    return [{
        "system": system,
        "systemAddress": address,
        "coordinates": coordinates,
        "power": power,
        "powerState": state,
        "controllingPower": controller,
        "powers": list(powers),
        "powersKnown": isinstance(participants, list),
        "powerRelationship": (
            "UNOCCUPIED" if unoccupied and not power
            else "CONTROL" if controller.casefold() == power.casefold()
            else "PRESENCE"
        ),
        "controlKnown": bool(controller),
        "observedAt": observed_at,
        "source": source,
    } for power in powers or [""]]


def merge_powerplay_observations(
    existing: Any, additions: Any, *, limit: int = 20_000,
) -> list[dict[str, Any]]:
    """Keep the newest compact observation for each system and Power."""
    latest: dict[tuple[Any, ...], tuple[datetime, dict[str, Any]]] = {}
    for source in [*(existing or []), *(additions or [])]:
        if not isinstance(source, dict):
            continue
        system = str(source.get("system") or "").strip()
        power = str(source.get("power") or "").strip()
        try:
            address = int(source.get("systemAddress") or 0)
        except (TypeError, ValueError):
            address = 0
        if not system or (not power and not (
                source.get("powerState") == "Unoccupied"
                and "controllingPower" in source and not source["controllingPower"])):
            continue
        key = (
            ("address", address) if address > 0
            else ("name", system.casefold()),
            power.casefold(),
        )
        try:
            stamp = datetime.fromisoformat(str(source.get("observedAt") or "").replace("Z", "+00:00"))
            stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
            stamp = stamp.astimezone(timezone.utc)
        except ValueError:
            stamp = datetime.min.replace(tzinfo=timezone.utc)
        current = latest.get(key)
        if current is None or stamp >= current[0]:
            latest[key] = (stamp, dict(source))
    return [row for _stamp, row in sorted(
        latest.values(), key=lambda item: item[0], reverse=True,
    )[:max(1, int(limit or 1))]]


def project_powerplay_catalog(payload: Any) -> list[dict[str, Any]]:
    """Project the dump into stable fields and reject malformed assertions."""
    if not isinstance(payload, list):
        raise MiningPowerplayError("Powerplay catalog returned invalid JSON")
    result = []
    seen: set[tuple[int, str]] = set()
    for source in payload:
        if not isinstance(source, dict):
            continue
        system = str(source.get("name") or "").strip()
        power = str(source.get("power") or "").strip()
        state = str(source.get("powerState") or "").strip()
        try:
            address = int(source.get("id64") or 0)
        except (TypeError, ValueError):
            address = 0
        coordinates = _coordinates(source.get("coords"))
        if (
            not system or not power or state not in POWERPLAY_STATES
            or address <= 0 or not coordinates
        ):
            continue
        key = (address, power.casefold())
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "system": system,
            "systemAddress": address,
            "coordinates": coordinates,
            "power": power,
            "powerState": state,
            # One EDSM row is emitted for every Power present in a system.
            # Never interpret ``power`` as the controller.
            "powerRelationship": "PRESENCE",
            "controlKnown": False,
            "systemState": str(source.get("state") or "").strip(),
            "observedAt": str(source.get("date") or "").strip(),
            "source": POWERPLAY_CATALOG_SOURCE,
        })
    if not result:
        raise MiningPowerplayError("Powerplay catalog contained no usable systems")
    return result


def fetch_powerplay_catalog(
    *, get: Any, timeout: int = 45,
) -> dict[str, Any]:
    """Download and validate the anonymous daily Powerplay-only dump."""
    response = get(
        POWERPLAY_DUMP_URL,
        timeout=timeout,
        headers={
            "User-Agent": (
                f"ED-Frame/{APP_VERSION} "
                "(+https://github.com/CMDRForcer/ED-Frame)"
            ),
        },
    )
    response.raise_for_status()
    body = bytes(response.content or b"")
    if not body:
        raise MiningPowerplayError("Powerplay catalog download was empty")
    # Guard against accidentally receiving a galaxy dump or an error document.
    if len(body) > 80 * 1024 * 1024:
        raise MiningPowerplayError("Powerplay catalog exceeded the safe size limit")
    try:
        decoded = gzip.decompress(body) if body.startswith(b"\x1f\x8b") else body
        payload = json.loads(decoded.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MiningPowerplayError("Powerplay catalog could not be decoded") from exc
    rows = project_powerplay_catalog(payload)
    return {
        "schemaVersion": POWERPLAY_CATALOG_SCHEMA_VERSION,
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": POWERPLAY_CATALOG_SOURCE,
        "sourceUrl": POWERPLAY_DUMP_URL,
        "systems": rows,
    }


def powerplay_catalog_is_fresh(
    catalog: Any, *, now: datetime | None = None, max_age_hours: int = 24,
) -> bool:
    if (
        not isinstance(catalog, dict)
        or catalog.get("schemaVersion") != POWERPLAY_CATALOG_SCHEMA_VERSION
        or not catalog.get("systems")
    ):
        return False
    text = str(catalog.get("fetchedAt") or "").strip()
    try:
        fetched = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    age = (now or datetime.now(timezone.utc)) - fetched.astimezone(timezone.utc)
    return age.total_seconds() <= max(1, int(max_age_hours)) * 3600


def catalog_rows(catalog: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(catalog, dict):
        return ()
    rows = catalog.get("systems")
    return rows if isinstance(rows, list) else ()
