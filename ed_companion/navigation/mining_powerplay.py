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
from datetime import datetime, timezone
from typing import Any, Iterable

from ed_companion import APP_VERSION


POWERPLAY_DUMP_URL = "https://www.edsm.net/dump/powerPlay.json.gz"
POWERPLAY_CATALOG_SOURCE = "EDSM daily PowerPlay catalog"
POWERPLAY_CATALOG_SCHEMA_VERSION = 3
POWERPLAY_STATES = frozenset({
    "Unoccupied", "Exploited", "Fortified", "Stronghold", "Headquarters",
})


class MiningPowerplayError(RuntimeError):
    """A concise, user-displayable Powerplay catalog failure."""


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
    powers = [
        str(value).strip() for value in message.get("Powers", []) or []
        if str(value).strip()
    ]
    if controller and controller.casefold() not in {
        value.casefold() for value in powers
    }:
        powers.append(controller)
    if not system or not state or not powers:
        return []
    try:
        address = int(message.get("SystemAddress") or 0)
    except (TypeError, ValueError):
        address = 0
    coordinates = message.get("StarPos")
    if isinstance(coordinates, (list, tuple)) and len(coordinates) == 3:
        try:
            coordinates = [float(value) for value in coordinates]
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
        "powerRelationship": (
            "CONTROL" if controller.casefold() == power.casefold()
            else "PRESENCE"
        ),
        "controlKnown": bool(controller),
        "observedAt": observed_at,
        "source": source,
    } for power in powers]


def merge_powerplay_observations(
    existing: Any, additions: Any, *, limit: int = 20_000,
) -> list[dict[str, Any]]:
    """Keep the newest compact observation for each system and Power."""
    latest: dict[tuple[Any, ...], dict[str, Any]] = {}
    for source in [*(existing or []), *(additions or [])]:
        if not isinstance(source, dict):
            continue
        system = str(source.get("system") or "").strip()
        power = str(source.get("power") or "").strip()
        try:
            address = int(source.get("systemAddress") or 0)
        except (TypeError, ValueError):
            address = 0
        if not system or not power:
            continue
        key = (
            ("address", address) if address > 0
            else ("name", system.casefold()),
            power.casefold(),
        )
        current = latest.get(key)
        if current is None or str(source.get("observedAt") or "") >= str(
            current.get("observedAt") or ""
        ):
            latest[key] = dict(source)
    return sorted(
        latest.values(),
        key=lambda row: str(row.get("observedAt") or ""),
        reverse=True,
    )[:max(1, int(limit or 1))]


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
