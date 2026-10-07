"""Public-only, expiring Journal signal contributions (never raw Journal)."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math

PUBLIC_SIGNAL_TYPES = {"HGE", "CONFLICT_ZONE", "SEEKING_MEDS", "SEEKING_FOODS"}


def public_signal_observations(rows, *, now=None, local_only=True):
    now = now or datetime.now(timezone.utc)
    result = []
    for row in rows or []:
        if not isinstance(row, dict) or row.get("self_test"):
            continue
        if local_only and (row.get("source") != "Local Elite Journal"
                           or row.get("evidence_kind") not in {"LOCAL_JOURNAL", "ENTERED"}):
            continue
        try:
            stamp = datetime.fromisoformat(str(row.get("signal_timestamp", "")).replace("Z", "+00:00"))
            lifetime = float(row.get("time_remaining", 0))
            position = [float(v) for v in row.get("star_pos", [])]
            address = row.get("system_address")
            if address is not None:
                if isinstance(address, bool):
                    continue
                address = int(address)
                if not 0 < address < 2**63:
                    continue
            kind = str(row.get("find_type", ""))
            system = str(row.get("system", "")).strip()
            faction = str(row.get("faction") or "")
            state = str(row.get("state") or "")
            if (stamp.tzinfo is None or stamp > now + timedelta(minutes=2)
                    or not math.isfinite(lifetime) or not 1 <= lifetime <= 7200 or lifetime != int(lifetime)
                    or stamp + timedelta(seconds=lifetime) <= now
                    or len(position) != 3 or not all(math.isfinite(v) and abs(v) <= 1000000 for v in position)
                    or kind not in PUBLIC_SIGNAL_TYPES or not 1 <= len(system) <= 128
                    or len(faction) > 256 or len(state) > 128
                    or any(ord(c) < 32 for c in system + faction + state)):
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        result.append({"system": system, "system_address": address, "star_pos": position,
                       "signal_timestamp": stamp.astimezone(timezone.utc).isoformat(),
                       "time_remaining": int(lifetime), "find_type": kind,
                       "faction": faction, "state": state})
        if len(result) >= 100:
            break
    return result


def signal_observation_key(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def send_signal_observations(rows, post):
    from .mining_market import EDFRAME_CATALOG_BASE
    response = post(EDFRAME_CATALOG_BASE + "/v1/state-signals/observations",
                    json={"observations": rows}, timeout=15)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("accepted") != len(rows) or payload.get("rejected", 0):
        raise ValueError("Signal observations were not fully accepted")
    return payload
