"""Small, anonymous Powerplay catalog used by Mining Finder.

EDSM publishes a daily Powerplay-only dump.  At roughly a few megabytes it is
the practical serverless counterpart to MeritMiner's own database: it tells us
which Power can acquire an unoccupied system and which systems are exploited,
fortified or strongholds without downloading the galaxy/station dumps.
"""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from typing import Any, Iterable


POWERPLAY_DUMP_URL = "https://www.edsm.net/dump/powerPlay.json.gz"
POWERPLAY_CATALOG_SOURCE = "EDSM daily PowerPlay catalog"
POWERPLAY_STATES = frozenset({
    "Unoccupied", "Exploited", "Fortified", "Stronghold",
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
    response = get(POWERPLAY_DUMP_URL, timeout=timeout)
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
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": POWERPLAY_CATALOG_SOURCE,
        "sourceUrl": POWERPLAY_DUMP_URL,
        "systems": rows,
    }


def powerplay_catalog_is_fresh(
    catalog: Any, *, now: datetime | None = None, max_age_hours: int = 24,
) -> bool:
    if not isinstance(catalog, dict) or not catalog.get("systems"):
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
