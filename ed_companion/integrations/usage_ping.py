"""Count active installations, with no Commander or hardware information."""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import logging
import os
from pathlib import Path
import threading
from uuid import UUID, uuid4

import requests

from ed_companion import APP_VERSION, is_development_build
from ed_companion.persistence import atomic_write, load_json_file
from ed_companion.navigation.mining_market import EDFRAME_CATALOG_BASE

_LOG = logging.getLogger(__name__)
_STATE_LOCK = threading.RLock()
TIMEOUT_SECONDS = 5


def utc_day():
    return datetime.now(timezone.utc).date().isoformat()


class UsagePing:
    """One small config at the app root, shared by every Commander profile.

    A persisted attempt marker prevents retries after failures or restarts.
    Each new UTC day is a new observation, never a replay of a missed day.
    The controller submits ``ping`` to its existing background scheduler.
    """

    def __init__(self, config_root: Path):
        self.path = Path(config_root) / "usage_ping.json"
        self._state = self._load()

    def _load(self):
        state = load_json_file(self.path, {}, encoding="utf-8")
        state = dict(state) if isinstance(state, dict) else {}
        # The former local UI opt-out is retired. Preserve ID and day markers.
        state.pop("enabled", None)
        for key in ("last_attempt_day", "last_successful_day"):
            try:
                date.fromisoformat(state.get(key, ""))
            except (TypeError, ValueError):
                state.pop(key, None)
        return state

    @property
    def install_id(self):
        try:
            value = UUID(str(self._state.get("install_id", "")))
            return str(value) if value.version == 4 else ""
        except ValueError:
            return ""

    def _save(self, state):
        # Only our three keys are persisted; no profile projection is accepted.
        state = {key: state[key] for key in (
            "install_id", "last_attempt_day", "last_successful_day"
        ) if key in state}
        if not atomic_write(self.path, json.dumps(state, indent=2) + "\n"):
            raise OSError("Usage configuration could not be saved")
        self._state = state

    def ensure_install_id(self):
        with _STATE_LOCK:
            self._state = self._load()
            if not self.install_id:
                self._save({**self._state, "install_id": str(uuid4())})
            return self.install_id

    def allowed(self, catalog_enabled):
        return (not is_development_build()
                and os.environ.get("EDFRAME_NO_USAGE_PING") != "1"
                and bool(catalog_enabled))

    def due(self, catalog_enabled):
        return self.allowed(catalog_enabled) and self._state.get("last_attempt_day", "") < utc_day()

    def ping(self, *, catalog_enabled, post=None, base_url=EDFRAME_CATALOG_BASE):
        try:
            # Check again when the queued background job actually runs.
            if not self.allowed(catalog_enabled() if callable(catalog_enabled) else catalog_enabled):
                return False
            with _STATE_LOCK:
                self._state = self._load()
                day = utc_day()
                if self._state.get("last_attempt_day", "") >= day:
                    return False
                identity = self.ensure_install_id()
                self._save({**self._state, "last_attempt_day": day})
            if not self.allowed(catalog_enabled() if callable(catalog_enabled) else catalog_enabled):
                return False
            response = (post or requests.post)(
                base_url.rstrip("/") + "/v1/usage/ping",
                json={"install_id": identity, "app_version": APP_VERSION},
                headers={"User-Agent": f"ED-Frame/{APP_VERSION}"},
                timeout=TIMEOUT_SECONDS,
                allow_redirects=False,
            )
            if not 200 <= response.status_code < 300:
                raise RuntimeError("Usage endpoint returned a non-success status")
            with _STATE_LOCK:
                self._save({**self._load(), "last_successful_day": day})
            return True
        except Exception:
            # Do not log the body, identifier, URL or exception text. Never
            # publish to activityChanged, connectionChanged or notifications.
            _LOG.info("Anonymous installation ping failed; no retry today")
            return False
