"""Extracted from ed_companion/phase14/controller.py as part of the
controller.py modularization (no behavior change)."""

import json
import hashlib
import logging
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import requests
from copy import deepcopy
from .dependency_cache import invalidate_state_cache
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtQuick import QQuickWindow

from ed_companion import APP_VERSION
from ed_companion.i18n import (
    DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, TranslationCatalog,
)
from ed_companion.persistence import atomic_write, load_json_file
from ed_companion.history_archive import HistoryArchive
from ed_companion.integrations.inara import (
    INARA_BATCH_WINDOW_SECONDS,
    INARA_MAX_REQUESTS_PER_MINUTE,
    INARA_MIN_REQUEST_INTERVAL_SECONDS,
    INARA_PENDING_EVENT_LIMIT,
    INARA_RATE_LIMIT_COOLDOWN_SECONDS,
    INARA_RETRY_BASE_SECONDS,
    INARA_RETRY_MAX_SECONDS,
    InaraError,
    community_goals_event,
    extract_community_goals,
    extract_profile_ships,
    material_event,
    prepare_journal_batch,
    profile_event,
    send_events,
)
from ed_companion.integrations.frontier_capi import (
    FRONTIER_CLIENT_ID,
    FRONTIER_REDIRECT_URI,
    FrontierAuthError,
    FrontierCapiClient,
    FrontierCapiError,
    build_pkce_authorization,
    exchange_authorization_code,
    parse_authorization_callback,
    project_profile_snapshot,
    refresh_frontier_tokens,
)
from ed_companion.integrations.frontier_credentials import (
    FrontierCredentialError,
    FrontierCredentialStore,
)
from ed_companion.build_import import (
    BuildImportError, JOURNAL_BLUEPRINT_NAMES, empty_build_import_preview,
    preview_build,
)
from ed_companion.loadout_export import build_loadout_export, write_loadout_export
from ed_companion.engineering import (
    build_unlock_guide,
    describe_engineering_effect,
    load_unlock_catalog,
)
from ed_companion.engineering.portraits import engineer_portrait_url
from ed_companion.integrations.eddn import (
    EDDN_PENDING_JOB_LIMIT,
    EDDN_REPLAY_DELAY_MS,
    EDDN_RELAY_URL,
    EddnError,
    EddnRelayDecodeError,
    decode_relay_frame,
    load_navroute_source,
    navroute_rejection_reason,
    prepare_event as prepare_eddn_event,
    prepare_station_snapshot,
    repair_legacy_prepared as repair_legacy_eddn_prepared,
    rebuild_context as rebuild_eddn_context,
    send as send_eddn_event,
    supports_event as supports_eddn_event,
    station_snapshot_mismatch_reason,
    should_log_station_rejection,
    should_log_rejection,
    schema_parity_report,
    update_context as update_eddn_context,
    upload_allowed as eddn_upload_allowed,
    validate_prepared as validate_eddn_prepared,
)
from ed_companion.navigation.hge import (
    apply_system_bgs_snapshot_batch,
    extract_signal_finds,
    extract_system_bgs_snapshot,
    infer_hge_materials,
    hge_match_class,
    is_hge_route_relevant,
    is_hge_material,
    merge_hge_observation_batch,
    partition_hge_observations,
    purge_legacy_signal_classifications,
    readable_faction_state,
    recent_unverified_hge_summary,
    rank_all_hge_sightings,
    rank_hge_candidate_systems,
    rank_state_find_systems,
)
from ed_companion.navigation.mining_finder import (
    fetch_spansh_system_dump,
    is_mining_commodity_signal,
    merge_mining_candidate_batch,
    mining_candidate_freshness,
    project_eddn_mining_candidates,
    project_spansh_mining_candidates,
)
from ed_companion.navigation.mining_commodities import (
    MINING_COMMODITIES,
    RHINO_SURFACE,
    mining_commodity_catalog,
    mining_commodity_id,
    mining_commodities_for_method,
)
from ed_companion.navigation.trader_type_cache import normalize_timestamp
from ed_companion.navigation.trader_search import (
    fetch_tech_broker_catalog_updates,
    fetch_trader_catalog_updates,
    merge_tech_broker_catalog,
    merge_trader_catalog,
    spansh_trader_type_evidence,
)
from ed_companion.navigation.trader_type_cache import TraderTypeCache
from ed_companion.trader_config import (
    SPANSH_MINIMUM_AGE_HOURS,
    SPANSH_TIMEOUT_SECONDS,
)
from ed_companion.services import (
    latest_delivery_proof,
    normalize_upload_queue,
    partition_upload_queue,
)
from ed_companion.diagnostics import filtered_log_lines
from ed_companion.exobiology import exobiology_distance_check

from .dashboard_views import (
    build_commander_cards,
    build_finance_history,
    build_finance_summary,
    build_interface_activity_feed,
    filter_finance_history,
    build_logbook_view,
    decorate_logbook_entry,
)

from .state import (
    active_profile_identity,
    attach_operation_experimental_effects,
    attach_operation_plan_context,
    assign_plans_to_nearest_engineers,
    blueprint_catalog,
    build_engineering_plan,
    build_experimental_plan,
    build_state,
    commander_status_credits,
    dismiss_craft_tracking_issue,
    dismiss_historical_craft_tracking_issues,
    dismiss_selected_craft_tracking_issues,
    discard_bound_module_plans,
    duplicate_ship_plan,
    engineering_run_preflight,
    journal_dir,
    journal_change_signature,
    journal_craft_baseline,
    journal_paths_for_profile,
    latest_profile_location,
    latest_loadout_slots,
    merge_capi_commander_overview,
    merge_capi_fleet,
    merge_capi_loadout,
    profiled_journal_events,
    ProfileContext,
    LOGBOOK_FILTERS,
    load_logbook_notes,
    logbook_entries,
    normalize,
    move_ship_plan,
    module_matches_type,
    partition_engineer_assignments,
    planner_mode,
    real_engineers,
    read_json,
    read_journal_tail_records,
    remove_ship_task,
    replace_ship_plan,
    runtime_data_dir,
    resolve_profile_context,
    set_journal_dir,
    reference_data_dir,
    select_operation_action,
    scope_operation_action_materials,
    set_prioritized_ship_plan,
    set_tech_broker_track,
    user_trader_catalog_path,
    write_logbook_note,
    write_ship_tasks,
)

LOGGER = logging.getLogger(__name__)

INARA_ACTIVE_RECEIPT_LIMIT = 100
from .controller_core import CoreControllerMixin
EDDN_ACTIVE_RECEIPT_LIMIT = 100
FRONTIER_REQUEST_WATCHDOG_MS = 120_000
COMMANDER_CARD_IDS = (
    "ranks", "major-reputation", "finances", "current-ship",
    "minor-reputation", "squadron",
)
HGE_OBSERVATION_LIMIT = 10000
BGS_OBSERVATION_BATCH_SECONDS = 30
MINING_OBSERVATION_BATCH_SECONDS = 30
MINING_TRANSIENT_FIELDS = frozenset({
    "ageSeconds", "confirmationStatus", "freshnessLimitSeconds",
    "recheckRecommended", "stale",
})
HGE_CLASSIFIER_VERSION = 2


def state_with_live_location(state, location):
    """Apply an exact Journal location without waiting for a full state build."""
    if not isinstance(location, dict):
        return state, False
    system = str(location.get("system") or "").strip()
    position = location.get("currentPosition")
    if (
        not system or not isinstance(position, (list, tuple))
        or len(position) != 3
    ):
        return state, False
    try:
        position = [float(value) for value in position]
    except (TypeError, ValueError):
        return state, False
    if not all(math.isfinite(value) for value in position):
        return state, False
    current = dict(state or {})
    changed = (
        str(current.get("system") or "").strip() != system
        or list(current.get("currentPosition") or []) != position
    )
    if not changed:
        return state, False
    current.update({
        "system": system,
        "currentPosition": position,
        "currentSystemAddress": location.get("currentSystemAddress"),
    })
    return current, True


def _last_complete_json_record(path: Path) -> dict[str, Any]:
    """Read only the final newline-complete Journal record."""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        end = handle.tell()
        if end <= 0:
            return {}
        handle.seek(end - 1)
        if handle.read(1) not in {b"\n", b"\r"}:
            return {}
        position = end
        buffer = b""
        while position > 0:
            chunk_size = min(65536, position)
            position -= chunk_size
            handle.seek(position)
            buffer = handle.read(chunk_size) + buffer
            lines = buffer.splitlines()
            if position == 0 or len(lines) >= 2:
                line = lines[-1] if lines else b""
                if line:
                    record = json.loads(line.decode("utf-8-sig", errors="replace"))
                    return record if isinstance(record, dict) else {}
        return {}


class JournalHealthMixin:
    """Extracted from CockpitController (controller.py modularization).

    Call self._init_journal_health() from CockpitController.__init__() at the
    exact point the extracted lines used to occupy - this avoids relying
    on cooperative super().__init__() ordering across mixins, which would
    be fragile here given real temporal setup dependencies between domains.
    """

    journalHealthChanged = Signal()
    journalHealthReady = Signal(object)
    journalLocationReady = Signal(object)
    journalInputsReady = Signal(object)

    def _journal_input_scope(self):
        return (getattr(self, "_profile_generation", 0), self.profile_context.key,
                getattr(self, "_journal_input_epoch", 0))

    def _request_journal_inputs(self, *, force=False):
        """One periodic disk snapshot, never a stat/resolve/cache lock from Qt."""
        scope = self._journal_input_scope()
        active = getattr(self, "_active_journal_inputs", None)
        now = time.monotonic()
        cached = getattr(self, "_journal_inputs_cache", {})
        if active or (not force and (cached.get("scope") == scope
                                    or getattr(self, "_journal_input_attempt_scope", None) == scope)
                      and now - getattr(self, "_journal_inputs_at", 0) < 1.2):
            return
        request = (scope, now)
        self._journal_input_attempt_scope = scope
        self._active_journal_inputs = request

        def worker():
            result = {"request": request, "scope": scope}
            try:
                directory = journal_dir()
                result["root"] = str(directory)
                result["stamp"] = journal_change_signature()
                if result["stamp"][0] != result["root"]:
                    raise RuntimeError("Journal directory changed during input snapshot")
                path = directory / "Status.json"
                try:
                    stat = path.stat()
                    result["statusStamp"] = (int(stat.st_size), int(stat.st_mtime_ns))
                except OSError:
                    result["statusStamp"] = None
                status = read_json(path, {})
                result["status"] = status if isinstance(status, dict) else {}
            except Exception as exc:
                result["error"] = type(exc).__name__
                LOGGER.exception("Journal input snapshot could not be read")
            self.journalInputsReady.emit(result)

        if not self._start_network_worker(worker, "journal-inputs"):
            self._active_journal_inputs = None

    @Slot(object)
    def _finish_journal_inputs(self, result):
        if result.get("request") != getattr(self, "_active_journal_inputs", None):
            return
        self._active_journal_inputs = None
        if (getattr(self, "_shutdown_complete", False)
                or result.get("scope") != self._journal_input_scope()):
            return
        self._journal_inputs_at = time.monotonic()
        if result.get("error"):
            # Do not authorize sharing/location checks from a failed disk poll.
            self._journal_inputs_cache = {}
            return
        old = getattr(self, "_journal_inputs_cache", {})
        if old.get("scope") == result["scope"] and old.get("status") == result["status"]:
            result["status"] = old["status"]
        self._journal_inputs_cache = result
        if old.get("root") != result["root"]:
            self.journalHealthChanged.emit()
        self._apply_journal_poll(result)

    def _live_location_key(self):
        if not hasattr(self, "_network_threads_lock"):
            stamp = journal_change_signature()
        else:
            self._request_journal_inputs()
            cached = getattr(self, "_journal_inputs_cache", {})
            stamp = (cached.get("stamp") if cached.get("scope") == self._journal_input_scope()
                     else None)
        return (self._profile_generation, self.profile_context.key, stamp)

    def _live_profile_location(self, *, key=None):
        """Both metadata and profile/location/history locks stay on workers."""
        key = self._live_location_key() if key is None else key
        if key[-1] is None or getattr(self, "_active_journal_inputs", None):
            return {}
        cached = getattr(self, "_journal_location_cache", {})
        if (cached.get("key") != key
                and not getattr(self, "_active_journal_location", None)
                and getattr(self, "_journal_location_failed_key", None) != key):
            self._active_journal_location = key

            def worker():
                result = {"key": key}
                try:
                    context = resolve_profile_context()
                    result.update(context=context, location=latest_profile_location(),
                                  paths=journal_paths_for_profile(context.identity))
                    result["verifiedStamp"] = journal_change_signature()
                except Exception as exc:
                    result["error"] = type(exc).__name__
                    LOGGER.exception("Live Journal location could not be prepared")
                self.journalLocationReady.emit(result)

            if not self._start_network_worker(worker, "journal-live-location"):
                self._active_journal_location = None
                self._journal_location_failed_key = key
        # Do not use an unverified old system for an exobiology distance check.
        return cached.get("location", {}) if cached.get("key") == key else {}

    @Slot(object)
    def _finish_journal_location(self, result):
        if result.get("key") != getattr(self, "_active_journal_location", None):
            return
        self._active_journal_location = None
        if result["key"] != self._live_location_key():
            self._live_profile_location()
            return
        if getattr(self, "_active_journal_inputs", None):
            return  # Re-resolve after the newer metadata snapshot is available.
        if result.get("error"):
            self._journal_location_failed_key = result["key"]
            return
        if result.get("verifiedStamp") != result["key"][-1]:
            self._request_journal_inputs(force=True)
            return
        if result["context"] != self.profile_context:
            self._journal_location_failed_key = result["key"]
            self.refresh()  # The full state worker owns coherent profile switching.
            return
        self._journal_location_cache = result
        self._journal_location_failed_key = None
        self._eddn_profile_paths_cache = result["paths"]
        self._eddn_profile_paths_signature = (self.profile_context.identity, result["key"][-1])
        live_state, changed = state_with_live_location(self._state, result["location"])
        if changed:
            self._state = live_state
            self._state_revision += 1
            invalidate_state_cache(self)
            self.stateChanged.emit()
            self.hgeChanged.emit()
        self._poll_exobiology_distance_check()
        self._scan_eddn_journal()


    def _journal_health_runtime(self):
        return {"watcherActive": bool(self._journal_auto and getattr(self, "timer", None)
                                      and self.timer.isActive()),
                "pollIntervalMs": 1200 if self._journal_auto else 0,
                "renderer": self._renderer_active}

    def _journal_health(self):
        if not hasattr(self, "_network_threads_lock"):
            data = self._read_journal_health()
            data.pop("_modifiedAt", None)
            return data
        inputs = getattr(self, "_journal_inputs_cache", {})
        root = inputs.get("root", "") if inputs.get("scope") == self._journal_input_scope() else ""
        now = time.monotonic()
        cached = getattr(self, "_journal_health_cache", {})
        runtime = self._journal_health_runtime()
        if (not getattr(self, "_active_journal_health", None)
                and (cached.get("scope") != self._journal_input_scope()
                     or (root and cached.get("root") != root)
                     or now - getattr(self, "_journal_health_requested_at", 0) >= 1.2)):
            request = (self._journal_input_scope(), now)
            self._active_journal_health = request
            self._journal_health_requested_at = now

            def worker():
                directory = None
                try:
                    directory = journal_dir()
                    data = self._read_journal_health(directory, runtime)
                except Exception as exc:
                    LOGGER.exception("Journal health could not be prepared")
                    data = {"status": "ERROR", "directoryExists": False,
                            "fileCount": 0, "latestFile": "", "ageSeconds": -1,
                            "sizeBytes": 0, "parserOk": False, "lastEvent": "",
                            "error": type(exc).__name__, **runtime}
                self.journalHealthReady.emit({"request": request, "root": str(directory or ""), "data": data})

            if not self._start_network_worker(worker, "journal-health"):
                self._active_journal_health = None
        if cached.get("scope") != self._journal_input_scope() or (root and cached.get("root") != root):
            return {"status": "CHECKING", "directoryExists": False, "fileCount": 0,
                    "latestFile": "", "ageSeconds": -1, "sizeBytes": 0,
                    "parserOk": False, "lastEvent": "", "error": "", **runtime}
        data = dict(cached["data"])
        modified = data.pop("_modifiedAt", None)
        age = max(0, int(time.time() - modified)) if modified is not None else -1
        data["ageSeconds"] = age
        if data["parserOk"]:
            data["status"] = "LIVE" if age <= 15 else "READY"
        data.update(runtime)
        return data

    @Slot(object)
    def _finish_journal_health(self, result):
        if result["request"] != getattr(self, "_active_journal_health", None):
            return
        self._active_journal_health = None
        if result["request"][0] != self._journal_input_scope():
            return
        inputs = getattr(self, "_journal_inputs_cache", {})
        if (inputs.get("scope") == self._journal_input_scope()
                and inputs.get("root") != result["root"]):
            return
        self._journal_health_cache = {"root": result["root"], "scope": result["request"][0], "data": result["data"]}
        self.journalHealthChanged.emit()
        self.connectionChanged.emit()

    def _read_journal_health(self, directory=None, runtime=None):
        directory = directory if directory is not None else journal_dir()
        runtime = runtime if runtime is not None else self._journal_health_runtime()
        try:
            files = sorted(
                directory.glob("Journal.*.log"),
                key=lambda path: path.stat().st_mtime,
            )
        except OSError:
            files = []
        latest = files[-1] if files else None
        age = -1
        size = 0
        parser_ok = False
        last_event = ""
        error = ""
        modified_at = None
        if latest:
            try:
                stat = latest.stat()
                modified_at = stat.st_mtime
                age = max(0, int(time.time() - stat.st_mtime))
                size = int(stat.st_size)
                record = _last_complete_json_record(latest)
                if record:
                    parser_ok = isinstance(record, dict)
                    last_event = str(record.get("event") or "")
            except (OSError, ValueError, TypeError) as exc:
                error = str(exc)
        status = (
            "LIVE" if latest and parser_ok and age <= 15
            else "READY" if latest and parser_ok
            else "ERROR" if latest else "NO JOURNAL"
        )
        return {
            "status": status,
            "directoryExists": directory.exists(),
            "fileCount": len(files),
            "latestFile": latest.name if latest else "",
            "ageSeconds": age,
            "sizeBytes": size,
            "parserOk": parser_ok,
            "lastEvent": last_event,
            **runtime,
            "error": error,
            "_modifiedAt": modified_at,
        }


    journalAuto = Property(
        bool, lambda self: self._journal_auto, notify=CoreControllerMixin.uiChanged,
    )


    journalHealth = Property(
        "QVariantMap", lambda self: self._journal_health(),
        notify=journalHealthChanged,
    )


    def _journal_path(self):
        if not hasattr(self, "_network_threads_lock"):
            return str(journal_dir())
        self._request_journal_inputs()
        cached = getattr(self, "_journal_inputs_cache", {})
        return str(cached.get("root", "")) if cached.get("scope") == self._journal_input_scope() else ""

    journalPath = Property(str, lambda self: self._journal_path(), notify=journalHealthChanged)


    @Slot(bool)
    def setJournalAuto(self, enabled):
        self._journal_auto = bool(enabled)
        saved = self._save_ui_config()
        if not saved:
            self.uiChanged.emit()
            self.journalHealthChanged.emit()
            return
        self._activity = (
            "Automatic Journal updates enabled."
            if self._journal_auto else "Automatic Journal updates paused."
        )
        self.uiChanged.emit()
        self.activityChanged.emit()
        self.journalHealthChanged.emit()


    @Slot()
    def reloadJournalNow(self):
        self.clearCraftConfirmation()
        self.refresh()
        self._scan_eddn_journal()


    @Slot(str)
    def setJournalPath(self, path):
        if set_journal_dir(path):
            self._journal_input_epoch = getattr(self, "_journal_input_epoch", 0) + 1
            self._journal_inputs_cache = {}
            self._journal_health_cache = {}
            self._journal_location_cache = {}
            self._last_journal_stamp = None
            self._last_commander_status_stamp = None
            self._selected_ship = ""
            self.refresh()
            if hasattr(self, "_network_threads_lock"):
                self._request_journal_inputs(force=True)
            self._activity = "Journal directory updated."
        else:
            value = Path(str(path or "").strip()).expanduser()
            self._activity = (
                "Journal directory could not be saved; previous path remains active."
                if value.is_dir()
                else "Journal directory does not exist."
            )
        self.activityChanged.emit()


    @Slot()
    def pollJournal(self):
        if self._shutdown_complete:
            return
        if hasattr(self, "_network_threads_lock"):
            self._request_journal_inputs(force=True)
            return
        self._apply_journal_poll()

    def _apply_journal_poll(self, inputs=None):
        if inputs is None:
            self._poll_surface_nav()
        else:
            self._poll_surface_nav(status=inputs["status"])
        if not self._journal_auto:
            self._maybe_start_inara_auto()
            self._process_eddn_queue()
            return
        # The startup/refresh worker owns the large Journal parse. Avoid
        # contending for its cache lock from Qt while the first projection is
        # still being built.
        if not self._journal_state_ready:
            self._maybe_start_inara_auto()
            self._process_eddn_queue()
            return
        if inputs is None:
            self._poll_commander_status_credits()
        else:
            self._poll_commander_status_credits(status=inputs["status"], stamp=inputs["statusStamp"])
        self._poll_exobiology_distance_check()
        stamp = inputs["stamp"] if inputs is not None else journal_change_signature()
        if self._last_journal_stamp is None:
            self._last_journal_stamp = stamp
            self._queue_inara_journal_scan()
        elif stamp != self._last_journal_stamp:
            self._last_journal_stamp = stamp
            location = (self._live_profile_location() if hasattr(self, "_network_threads_lock")
                        else latest_profile_location())
            live_state, location_changed = state_with_live_location(self._state, location)
            if location_changed:
                self._state = live_state
                self._state_revision += 1
                invalidate_state_cache(self)
                self.stateChanged.emit()
                self.hgeChanged.emit()
            self.refresh()
        self._maybe_start_inara_auto()
        self._scan_eddn_journal()
        self._process_eddn_queue()
