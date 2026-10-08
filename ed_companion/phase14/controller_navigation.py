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
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtQuick import QQuickWindow

from ed_companion import APP_VERSION
from ed_companion.navigation.mining_refresh import fetch_mining_refresh
from ed_companion.navigation.mining_snapshot import MiningSnapshotStore
from ed_companion.navigation.mining_batch import prepare_mining_batch
from ed_companion.navigation.state_find_batch import prepare_state_find_page
from ed_companion.navigation.hge_batch import prepare_hge_batch
from ed_companion.navigation.catalog_json import load_catalog_json, iter_catalog_json
from .dependency_cache import dependency_revision, profile_dependency
from ed_companion.i18n import (
    DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, TranslationCatalog,
)
from ed_companion.persistence import atomic_write, atomic_write_chunks, load_json_file
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
    MINING_CATALOG_IDENTITY_VERSION,
    MINING_EVIDENCE_RANK,
    fetch_edframe_mining_candidates,
    fetch_spansh_system_dump,
    is_belt_candidate,
    is_mining_commodity_signal,
    merge_mining_candidate_batch,
    merge_mining_candidates,
    mining_candidate_positions,
    mining_candidate_freshness,
    project_eddn_mining_candidates,
    project_local_yield_observations,
    project_spansh_mining_candidates,
    send_edframe_yield_observations,
    yield_observation_key,
)
from ed_companion.navigation.mining_commodities import mining_ring_types_for_method, mining_ring_type_key
from ed_companion.navigation.mining_commodities import (
    MINING_COMMODITIES,
    RHINO_SURFACE,
    mining_commodity_catalog,
    mining_commodity_id,
    mining_commodity_name,
    mining_commodities_for_method,
)
from ed_companion.navigation.mining_planner import (
    market_filter_diagnostics,
    plan_mining_routes,
)
from ed_companion.navigation.mining_market import (
    fetch_edframe_catalog_health,
    fetch_edframe_catalog_status,
    fetch_edframe_market_delta,
    fetch_edframe_station_offer_delta,
    fetch_edframe_station_offers,
    fetch_edframe_system_coordinates,
    fetch_edsm_system_coordinates,
    fetch_market_imports,
    latest_market_rows,
    market_provider_status_summary,
    nearby_catalog_markets,
    project_local_market_snapshot,
)
from ed_companion.navigation.shipyard_finder import (
    build_module_families,
    catalog_suggestions,
    module_catalog_with_ship_fit,
    rank_station_offers,
    ship_catalog_with_access,
)
from ed_companion.navigation.state_find_catalog import (
    fetch_edframe_state_find_delta,
    merge_edframe_state_find_page,
    retain_state_find_region,
    state_find_region,
)
from ed_companion.navigation.mining_powerplay import (
    catalog_rows,
    fetch_powerplay_catalog,
    fetch_edframe_powerplay,
    fetch_powerplay_targets,
    missing_powerplay_targets,
    merge_powerplay_observations,
    powerplay_catalog_is_fresh,
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


MINING_MARKET_RETRY_SECONDS = (120, 300, 900, 1800)
MINING_MARKET_WARM_INTERVAL_SECONDS = 60
MINING_MARKET_WARM_COMMODITIES = (
    "platinum", "painite", "osmium", "monazite", "musgravite",
    "alexandrite", "lowtemperaturediamond", "opal", "tritium",
    "palladium", "gold", "silver",
)

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


def _merge_edframe_market_delta_page(store, page):
    """Durably merge one page before advancing its resumable cursor."""
    rows = [row for row in page.get("rows", []) if isinstance(row, dict)]
    ingested = store.ingest(rows, create_backup=False)
    next_cursor = str(page.get("nextCursor") or "").strip()
    if next_cursor:
        # Cursor follows ingestion: a crash can replay a page but can never
        # skip rows that were not durably merged first.
        store.set_metadata("edframe_market_sync_cursor", next_cursor)
    stamp = str(page.get("generatedAt") or "")
    if stamp:
        store.set_metadata("edframe_market_sync_last_success", stamp)
    return {
        **page,
        "ingested": ingested,
        "rowCount": len(rows),
        "localCount": store.count(),
    }


def _merge_edframe_station_offer_delta_page(store, page):
    """Durably merge station offers before advancing their cursor."""
    rows = [row for row in page.get("rows", []) if isinstance(row, dict)]
    ingested = store.ingest_station_offers(rows)
    next_cursor = str(page.get("nextCursor") or "").strip()
    if next_cursor:
        store.set_metadata("edframe_station_offer_sync_cursor", next_cursor)
    stamp = str(page.get("generatedAt") or "")
    if stamp:
        store.set_metadata("edframe_station_offer_sync_last_success", stamp)
    return {
        **page,
        "ingested": ingested,
        "rowCount": len(rows),
        "localSummary": store.station_offer_summary(),
    }


class NavigationMixin:
    """Extracted from CockpitController (controller.py modularization).

    Call self._init_navigation() from CockpitController.__init__() at the
    exact point the extracted lines used to occupy - this avoids relying
    on cooperative super().__init__() ordering across mixins, which would
    be fragile here given real temporal setup dependencies between domains.
    """

    miningChanged = Signal()

    shipyardFinderChanged = Signal()
    shipyardFinderSearchFinished = Signal(object)


    miningVerificationChanged = Signal()


    miningSyncFinished = Signal(object)


    miningMarketFinished = Signal(object)
    localMiningMarketFinished = Signal(object)

    miningObservationBatchFinished = Signal(object)
    hgeObservationBatchFinished = Signal(object)


    edFrameCatalogStatusFinished = Signal(object)


    edFrameCatalogSyncFinished = Signal(object)


    edFrameStateFindSyncFinished = Signal(object)

    edFrameStationOfferSyncFinished = Signal(object)

    edFrameYieldUploadFinished = Signal(object)
    edFrameSignalUploadFinished = Signal(object)

    edFrameStationPriceUploadFinished = Signal(object)


    miningPowerplayFinished = Signal(object)


    miningCatalogLoaded = Signal(object)


    miningRowsReady = Signal(object)
    miningPlanReady = Signal(object)


    miningVerificationProgress = Signal(object)


    miningVerificationFinished = Signal(object)


    traderSyncFinished = Signal(bool, str)

    def _shipyard_module_projection(self):
        """Cache current-hull compatibility away from repeated QML reads."""
        state = self._state if isinstance(getattr(self, "_state", None), dict) else {}
        slots = state.get("activeShipSlots", []) or []
        slot_signature = tuple(sorted(
            (
                str(row.get("group") or ""),
                str(row.get("slot") or ""),
                int(row.get("slotSize") or 0),
                str(row.get("restriction") or ""),
                str(row.get("moduleId") or ""),
                bool(row.get("empty")),
                bool(row.get("engineered")),
            )
            for row in slots if isinstance(row, dict)
        ))
        catalog = getattr(self, "_shipyard_module_catalog", []) or []
        cache_key = (
            id(catalog), str(state.get("activeShipId") or ""), str(state.get("activeShipType") or ""), slot_signature,
            json.dumps(state.get("activeShipFitStats", {}), sort_keys=True),
        )
        if cache_key != getattr(self, "_shipyard_module_fit_cache_key", None):
            projected = module_catalog_with_ship_fit(catalog, slots, str(state.get("activeShipType") or ""), ship_stats=state.get("activeShipFitStats"))
            self._shipyard_module_fit_cache_key = cache_key
            self._shipyard_module_fit_cache = (
                projected, build_module_families(projected),
            )
        return getattr(self, "_shipyard_module_fit_cache", ([], []))

    shipyardFinderSuggestions = Property(
        "QVariantList",
        lambda self: list(
            getattr(self, "_shipyard_finder_suggestions", []) or []
        ),
        notify=shipyardFinderChanged,
    )
    shipyardFinderResults = Property(
        "QVariantList",
        lambda self: list(getattr(self, "_shipyard_finder_results", []) or []),
        notify=shipyardFinderChanged,
    )
    shipyardShipCatalog = Property(
        "QVariantList",
        lambda self: ship_catalog_with_access(
            getattr(self, "_shipyard_ship_catalog", []) or [],
            (
                self._state.get("commanderOverview", {})
                if isinstance(getattr(self, "_state", None), dict) else {}
            ),
        ),
        notify=shipyardFinderChanged,
    )
    shipyardModuleCatalog = Property(
        "QVariantList",
        lambda self: list(self._shipyard_module_projection()[0]),
        notify=CoreControllerMixin.stateChanged,
    )
    shipyardModuleFamilies = Property(
        "QVariantList",
        lambda self: list(self._shipyard_module_projection()[1]),
        notify=CoreControllerMixin.stateChanged,
    )
    shipyardCurrentShip = Property(
        str,
        lambda self: str(
            self._state.get("activeShipType")
            or self._state.get("activeShip") or ""
        ) if isinstance(getattr(self, "_state", None), dict) else "",
        notify=CoreControllerMixin.stateChanged,
    )
    shipyardCurrentShipFitKnown = Property(
        bool,
        lambda self: bool(self._state.get("activeShipSlots", []))
        if isinstance(getattr(self, "_state", None), dict) else False,
        notify=CoreControllerMixin.stateChanged,
    )
    shipyardCurrentShipSlots = Property(
        "QVariantList",
        lambda self: list(self._state.get("activeShipSlots", []) or [])
        if isinstance(getattr(self, "_state", None), dict) else [],
        notify=CoreControllerMixin.stateChanged,
    )
    shipyardFinderBusy = Property(
        bool,
        lambda self: bool(getattr(self, "_shipyard_finder_busy", False)),
        notify=shipyardFinderChanged,
    )
    shipyardFinderStatus = Property(
        str,
        lambda self: str(getattr(self, "_shipyard_finder_status", "Ready")),
        notify=shipyardFinderChanged,
    )

    @Slot(str, str)
    def requestShipyardSuggestions(self, kind, query):
        if str(kind or "").upper() == "MODULES":
            catalog = getattr(self, "_shipyard_module_catalog", [])
        else:
            catalog = ship_catalog_with_access(
                getattr(self, "_shipyard_ship_catalog", []),
                (
                    self._state.get("commanderOverview", {})
                    if isinstance(getattr(self, "_state", None), dict) else {}
                ),
            )
        self._shipyard_finder_suggestions = catalog_suggestions(
            catalog, query,
            limit=100 if str(kind or "").upper() == "MODULES" else 12,
        )
        self.shipyardFinderChanged.emit()

    @Slot()
    def clearShipyardFinder(self):
        self._shipyard_finder_search_token = getattr(
            self, "_shipyard_finder_search_token", 0
        ) + 1
        self._shipyard_finder_suggestions = []
        self._shipyard_finder_results = []
        self._shipyard_finder_busy = False
        self._shipyard_finder_status = "Ready · choose a module or ship"
        self.shipyardFinderChanged.emit()

    @Slot(str, str, str, int, str, str, "QVariantMap")
    def searchShipyardOffers(
        self, kind, symbol, origin_system, max_distance_ly, pad_filter,
        access_filter, item,
    ):
        normalized_kind = str(kind or "").upper()
        wanted = str(symbol or "").strip().casefold()
        origin_name = str(origin_system or "").strip()
        if normalized_kind not in {"MODULES", "SHIPS"} or not wanted:
            self._shipyard_finder_status = "Select a module or ship first"
            self.shipyardFinderChanged.emit()
            return
        if not origin_name:
            self._shipyard_finder_status = "Enter a start system"
            self.shipyardFinderChanged.emit()
            return
        self._shipyard_finder_search_token = getattr(
            self, "_shipyard_finder_search_token", 0
        ) + 1
        token = self._shipyard_finder_search_token
        self._shipyard_finder_busy = True
        self._shipyard_finder_status = "Searching local and server catalogs…"
        self.shipyardFinderChanged.emit()
        item_snapshot = dict(item or {})

        def perform_search():
            source = "LOCAL CATALOG"
            server_error = ""
            server_rows = []
            if bool(getattr(self, "_edframe_catalog_enabled", True)):
                try:
                    server_rows = fetch_edframe_station_offers(
                        kind=normalized_kind, item=wanted,
                        get=requests.get, timeout=20, limit=200,
                    )
                    source = "ED-FRAME SERVER + LOCAL CATALOG"
                except Exception as exc:  # local fallback is intentional
                    server_error = str(exc)
            store = getattr(self, "_mining_market_store", None)
            local_rows = []
            if store is not None:
                try:
                    local_rows = store.stations_offering(
                        wanted,
                        kind=(
                            "OUTFITTING"
                            if normalized_kind == "MODULES" else "SHIPYARD"
                        ),
                    )
                except (OSError, sqlite3.DatabaseError) as exc:
                    server_error = server_error or str(exc)
            merged = {}

            def price_quality(row):
                offer_key = (
                    "moduleOffer" if normalized_kind == "MODULES"
                    else "shipOffer"
                )
                offer = row.get(offer_key)
                offer = offer if isinstance(offer, dict) else {}
                if offer.get("buyPrice") is None and row.get("buyPrice") is None:
                    return 0
                price_source = str(
                    offer.get("priceSource") or row.get("priceSource") or ""
                ).casefold().replace(" ", "")
                if normalized_kind == "SHIPS":
                    # Only a completed purchase is exact ship-price evidence.
                    # In particular, a local Shipyard.json trade-in row must
                    # never displace a server-side ShipyardBuy confirmation.
                    return 4 if "shipyardbuy" in price_source else 1
                price_type = str(offer.get("priceType") or "").upper()
                if offer.get("priceObservedAt") or price_type == "OBSERVED":
                    return 3
                if price_type == "INFERRED":
                    return 2
                return 1

            # Combine both catalogs by evidence quality.  A local CAPI base
            # value fills a server gap, but never replaces an exact observed
            # station price merely because it arrived later.
            for row in [*server_rows, *local_rows]:
                key = (
                    int(row.get("marketId") or 0),
                    str(row.get("station") or "").casefold(),
                )
                current = merged.get(key)
                if current is None or price_quality(row) >= price_quality(current):
                    merged[key] = row
            origin = self._known_mining_origin(origin_name)
            if not origin:
                try:
                    origin = fetch_edframe_system_coordinates(
                        origin_name, get=requests.get, timeout=15,
                    )
                except Exception:
                    origin = {}
            coordinates = (
                origin.get("coordinates") if isinstance(origin, dict) else None
            )
            rows = rank_station_offers(
                merged.values(), kind=normalized_kind,
                origin_coordinates=coordinates,
                max_distance_ly=int(max_distance_ly or 0),
                pad_filter=pad_filter, item=item_snapshot,
                commander_overview=(
                    self._state.get("commanderOverview", {})
                    if isinstance(getattr(self, "_state", None), dict) else {}
                ),
                permit_rules=getattr(self, "_shipyard_permit_rules", {}),
                price_rules=getattr(self, "_ship_price_rules", {}),
                access_filter=access_filter,
            ) if coordinates is not None else []
            self.shipyardFinderSearchFinished.emit({
                "token": token, "rows": rows, "source": source,
                "originKnown": coordinates is not None,
                "available": len(merged), "error": server_error,
            })

        def worker():
            try:
                perform_search()
            except Exception as exc:
                LOGGER.exception("Shipyard Finder search failed")
                self.shipyardFinderSearchFinished.emit({
                    "token": token, "rows": [], "source": "LOCAL CATALOG",
                    "originKnown": True, "available": 0,
                    "error": str(exc), "failed": True,
                })

        if not self._start_network_worker(worker, "shipyard-offer-search"):
            self._shipyard_finder_busy = False
            self._shipyard_finder_status = "Search unavailable during shutdown"
            self.shipyardFinderChanged.emit()

    @Slot(object)
    def _finish_shipyard_finder_search(self, payload):
        result = payload if isinstance(payload, dict) else {}
        if int(result.get("token") or -1) != getattr(
            self, "_shipyard_finder_search_token", 0
        ):
            return
        rows = result.get("rows", [])
        self._shipyard_finder_results = (
            list(rows) if isinstance(rows, list) else []
        )
        self._shipyard_finder_busy = False
        if result.get("failed"):
            self._shipyard_finder_status = (
                "Search failed · retained catalog unchanged"
            )
        elif not result.get("originKnown"):
            self._shipyard_finder_status = (
                "Start-system coordinates unavailable · no distance guessed"
            )
        elif self._shipyard_finder_results:
            self._shipyard_finder_status = (
                f"{len(self._shipyard_finder_results)} offers · {result.get('source') or 'LOCAL CATALOG'}"
            )
        elif int(result.get("available") or 0) > 0:
            self._shipyard_finder_status = "Offers known, but none match range or pad filters"
        else:
            self._shipyard_finder_status = "No observed station availability yet"
        self.shipyardFinderChanged.emit()


    def _mining_market_cache_status(self, retained=None):
        cache = getattr(self, "_mining_market_cache", {})
        markets = cache.get("markets", []) if isinstance(cache, dict) else []
        store = getattr(self, "_mining_market_store", None)
        try:
            if retained is None:
                retained = store.count() if store is not None else 0
        except (OSError, sqlite3.DatabaseError):
            retained = 0
        if not retained:
            catalog = getattr(self, "_mining_market_catalog", {})
            retained = (
                len(catalog.get("markets", []))
                if isinstance(catalog, dict)
                and isinstance(catalog.get("markets", []), list) else 0
            )
        fetched = str(cache.get("fetchedAt") or "") if isinstance(cache, dict) else ""
        if not isinstance(markets, list) or not markets:
            return (
                f"Ready · {retained} retained market observations"
                if retained else
                "Ready · market data loads when a route is searched"
            )
        return (
            f"Cached EDDN market data · {len(markets)} sell markets"
            + (f" · {retained} retained" if retained else "")
            + (f" · {fetched}" if fetched else "")
        )


    def _load_trader_sync_status(self):
        data = self._read_local_json(self.trader_catalog_file, {})
        count = len(data.get("stations", [])) if isinstance(data, dict) else 0
        fetched = str(data.get("fetched_at") or "") if isinstance(data, dict) else ""
        return (
            f"Offline catalog active · 1,622 bundled + {count} live updates"
            + (f" · {fetched}" if fetched else "")
        )


    @classmethod
    def _hge_displaced_history_rows(
        cls, before, after, snapshots, additions,
    ):
        """Compare only systems/signals touched by the current relay batch."""
        system_addresses = {
            row.get("system_address") for row in snapshots or []
            if isinstance(row, dict) and row.get("system_address") is not None
        }
        system_names = {
            normalize(row.get("system")) for row in snapshots or []
            if isinstance(row, dict) and row.get("system_address") is None
        }
        signal_keys = {
            (
                row.get("system"), row.get("signal_timestamp"),
                row.get("faction"), row.get("state"),
                row.get("find_type", "HGE"),
            )
            for row in additions or [] if isinstance(row, dict)
        }

        def touched(row):
            if not isinstance(row, dict):
                return False
            bgs_match = row.get("source") == "EDDN System BGS" and (
                row.get("system_address") in system_addresses
                or (
                    row.get("system_address") is None
                    and normalize(row.get("system")) in system_names
                )
            )
            signal_match = (
                row.get("system"), row.get("signal_timestamp"),
                row.get("faction"), row.get("state"),
                row.get("find_type", "HGE"),
            ) in signal_keys
            return bgs_match or signal_match

        return cls._displaced_history_rows(
            (row for row in before or [] if touched(row)),
            (row for row in after or [] if touched(row)),
        )


    def _edmc_parallel_status(self, journal=None, delivery=None, snapshots=None):
        """Give a scoped, evidence-based EDMC replacement verdict."""
        journal = journal if journal is not None else self._journal_health()
        delivery = delivery if delivery is not None else self._eddn_delivery_summary()
        snapshots = snapshots if snapshots is not None else self._eddn_station_snapshot_view()
        upload_enabled = bool(
            self._eddn_config.get("consent")
            and self._eddn_config.get("upload_enabled")
        )
        journal_status = str(journal.get("status") or "NO JOURNAL")
        failed = int(delivery.get("failed", 0) or 0)
        station_attention = sum(
            1 for row in snapshots
            if row.get("status") in {"FAILED", "INVALID", "NOT CURRENT", "STALE"}
        )
        if journal_status not in {"LIVE", "READY"}:
            verdict = "YES — JOURNAL IS NOT HEALTHY"
            tone = "ERROR"
            reason = "ED-Frame cannot currently prove reliable Journal processing. Keep EDMC until the Journal status is LIVE or READY."
        elif not upload_enabled:
            verdict = "YES — EDDN SHARING IS OFF"
            tone = "WARNING"
            reason = "ED-Frame reads the Journal, but anonymous EDDN upload is disabled. EDMC is still needed if you want to contribute community data."
        elif failed:
            verdict = "RECOMMENDED — EDDN ERRORS PENDING"
            tone = "WARNING"
            reason = f"ED-Frame has {failed} failed EDDN delivery job(s). Resolve or safely retry them before retiring EDMC."
        else:
            verdict = "NO — FOR JOURNAL + EDDN"
            tone = "READY"
            reason = "ED-Frame is processing the Journal and its EDDN sender is enabled. Running EDMC in parallel is not required for these paths."
        station_note = (
            f"{station_attention} station snapshot(s) need attention. Opening the matching Elite station page refreshes them; EDMC cannot create data Elite has not exposed."
            if station_attention else
            "Station snapshots have no current error or stale-data warning."
        )
        return {
            "verdict": verdict,
            "tone": tone,
            "reason": reason,
            "stationNote": station_note,
            "capiNote": "Frontier CAPI is not covered. Keep a CAPI-capable companion only if you need CAPI-dependent account, fleet or carrier data.",
        }


    def _save_hge_cache(self, already_partitioned=False):
        if not already_partitioned:
            active, historical = partition_hge_observations(self._hge_sightings)
            overflow = active[:-HGE_OBSERVATION_LIMIT]
            retained = active[-HGE_OBSERVATION_LIMIT:]
            if self._archive_history("hge_observations", [*historical, *overflow]):
                self._hge_sightings = retained
        if not hasattr(self, "_hge_file_lock"):
            self._hge_file_lock = threading.Lock()
            self._hge_save_sequence = 0
            self._hge_save_sequences = {}
        if not hasattr(self, "_hge_save_sequences"):
            self._hge_save_sequences = {}
        if not hasattr(self, "_hge_save_sequence"):
            self._hge_save_sequence = 0
        self._hge_save_sequence += 1
        sequence = self._hge_save_sequence
        path = self.hge_cache_file
        path_key = str(path)
        self._hge_save_sequences[path_key] = sequence
        snapshot = self._hge_sightings

        def write_snapshot():
            with self._hge_file_lock:
                if self._hge_save_sequences.get(path_key) != sequence:
                    return
                try:
                    atomic_write(
                        path,
                        json.dumps(
                            snapshot, ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    )
                except OSError as exc:
                    LOGGER.warning(
                        "HGE cache save failed: %s", type(exc).__name__
                    )

        if getattr(self, "_shutdown_complete", False):
            write_snapshot()
        elif not self._start_network_worker(write_snapshot, "hge-cache-save"):
            write_snapshot()


    @Slot()
    def _invalidate_hge_cache(self) -> None:
        self._hge_revision += 1
        self._drop_derived({"hge_targets", "hge_finder_rows"})


    def _start_mining_catalog_load(self):
        """Load a potentially large profile catalog without blocking Qt."""
        if not hasattr(self, "_mining_catalog_load_token"):
            self._mining_catalog_load_token = 0
        self._mining_catalog_load_token += 1
        token = self._mining_catalog_load_token
        generation = self._profile_generation
        profile_key = self.profile_context.key
        path = self.mining_catalog_file
        powerplay_path = getattr(self, "mining_powerplay_catalog_file", None)
        powerplay_observations_path = getattr(self, "mining_powerplay_observations_file", None)

        def worker():
            catalog = load_json_file(path, {"candidates": []}, loader=load_catalog_json)
            identity_migrated = (
                int(catalog.get("identityVersion", 0) or 0)
                < MINING_CATALOG_IDENTITY_VERSION
            )
            if identity_migrated:
                catalog["candidates"] = merge_mining_candidates(
                    catalog.get("candidates", [])
                )
                catalog["identityVersion"] = MINING_CATALOG_IDENTITY_VERSION
            self._compact_mining_catalog_rows(catalog.get("candidates", []))
            candidates = catalog.get("candidates", [])
            positions = mining_candidate_positions(candidates)
            system_names, system_keys = self._mining_system_name_index(
                candidates
            )
            public_links = {}
            for name, source, default in (("catalog", powerplay_path, {}),
                                          ("observations", powerplay_observations_path, [])):
                if source is None:
                    continue
                public_links[name] = load_json_file(source, default, loader=load_catalog_json)
            self.miningCatalogLoaded.emit((
                token, generation, profile_key, str(path), catalog, positions,
                system_names, system_keys,
                identity_migrated,
                public_links,
            ))

        return self._start_network_worker(worker, "mining-catalog-load")


    @staticmethod
    def _compact_mining_catalog_rows(rows):
        """Drop time-derived fields that are recalculated for every view."""
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            for field in MINING_TRANSIENT_FIELDS:
                row.pop(field, None)
        return rows


    @Slot(object)
    def _finish_mining_catalog_load(self, payload):
        token, generation, profile_key, path, catalog, *extra = payload
        positions = extra[0] if extra and isinstance(extra[0], dict) else None
        system_names = extra[1] if len(extra) > 1 else None
        system_keys = extra[2] if len(extra) > 2 else None
        identity_migrated = bool(extra[3]) if len(extra) > 3 else False
        if (
            token != self._mining_catalog_load_token
            or generation != self._profile_generation
            or profile_key != self.profile_context.key
            or path != str(self.mining_catalog_file)
            or not isinstance(catalog, dict)
        ):
            return
        loaded = catalog.get("candidates", [])
        current = self._mining_catalog.get("candidates", [])
        loaded = loaded if isinstance(loaded, list) else []
        current = current if isinstance(current, list) else []
        positions = positions or mining_candidate_positions(loaded)
        if current:
            merged, _displaced = merge_mining_candidate_batch(
                loaded, current, positions=positions,
            )
        else:
            merged = loaded
        if current:
            self._compact_mining_catalog_rows(merged)
        self._mining_catalog = {
            **catalog,
            "identityVersion": MINING_CATALOG_IDENTITY_VERSION,
            "candidates": merged,
        }
        self._mining_catalog_revision = getattr(
            self, "_mining_catalog_revision", 0
        ) + 1
        self._mining_catalog_positions = positions
        self._mining_catalog_positions_identity = id(merged)
        if not isinstance(system_names, list) or not isinstance(system_keys, list):
            system_names, system_keys = self._mining_system_name_index(loaded)
        self._mining_system_names = system_names
        self._mining_system_name_keys = system_keys
        self._add_mining_system_names(current)
        self._mining_rows_cache_key = None
        self._mining_rows_cache = []
        public_links = extra[4] if len(extra) > 4 else {}
        if isinstance(public_links.get("catalog"), dict):
            existing = getattr(self, "_mining_powerplay_catalog", {})
            loaded_links = public_links["catalog"]
            self._mining_powerplay_catalog = {
                **loaded_links, **existing,
                "systems": [*catalog_rows(loaded_links), *catalog_rows(existing)],
            }
        if isinstance(public_links.get("observations"), list):
            self._mining_powerplay_observations = [
                *public_links["observations"],
                *getattr(self, "_mining_powerplay_observations", []),
            ]
        if public_links:
            self._mining_powerplay_status = "Cached · {} Powerplay system links".format(
                len(catalog_rows(getattr(self, "_mining_powerplay_catalog", {}))))
            self.connectionChanged.emit()
        if identity_migrated:
            self._save_mining_catalog()
        self.miningChanged.emit()


    def _mining_positions_for(self, candidates):
        if (
            getattr(self, "_mining_catalog_positions_identity", None)
            == id(candidates)
            and isinstance(getattr(self, "_mining_catalog_positions", None), dict)
        ):
            return self._mining_catalog_positions
        positions = mining_candidate_positions(candidates)
        self._mining_catalog_positions = positions
        self._mining_catalog_positions_identity = id(candidates)
        return positions


    @staticmethod
    def _mining_system_name_index(candidates):
        canonical = {}
        for row in candidates if isinstance(candidates, list) else []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("system") or "").strip()
            if name:
                canonical.setdefault(name.casefold(), name)
        pairs = sorted(canonical.items())
        return (
            [name for _key, name in pairs],
            [key for key, _name in pairs],
        )


    def _add_mining_system_names(self, candidates):
        names = getattr(self, "_mining_system_names", [])
        keys = getattr(self, "_mining_system_name_keys", [])
        if not isinstance(names, list) or not isinstance(keys, list):
            names, keys = [], []
        for row in candidates if isinstance(candidates, list) else []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("system") or "").strip()
            key = name.casefold()
            if not key:
                continue
            index = bisect_left(keys, key)
            if index < len(keys) and keys[index] == key:
                continue
            keys.insert(index, key)
            names.insert(index, name)
        self._mining_system_names = names
        self._mining_system_name_keys = keys


    def _save_mining_catalog(self):
        self._save_mining_json(self.mining_catalog_file, self._mining_catalog)


    def _save_mining_json(self, path, snapshot):
        # Serializing a mature catalog can take hundreds of milliseconds.
        # Keep that work off the Qt thread and let only the newest queued
        # snapshot win. Shutdown still performs a final synchronous save.
        if not hasattr(self, "_mining_file_lock"):
            self._mining_file_lock = threading.Lock()
            self._mining_save_sequence = 0
            self._mining_save_sequences = {}
        if not hasattr(self, "_mining_save_sequences"):
            self._mining_save_sequences = {}
        if not hasattr(self, "_mining_save_sequence"):
            self._mining_save_sequence = 0
        self._mining_save_sequence += 1
        sequence = self._mining_save_sequence
        path_key = str(path)
        self._mining_save_sequences[path_key] = sequence

        def write_snapshot():
            with self._mining_file_lock:
                if self._mining_save_sequences.get(path_key) != sequence:
                    return
                try:
                    atomic_write_chunks(path, iter_catalog_json(snapshot))
                except OSError as exc:
                    LOGGER.warning(
                        "Mining catalog save failed: %s", type(exc).__name__
                    )

        if getattr(self, "_shutdown_complete", False):
            write_snapshot()
        elif not self._start_network_worker(
            write_snapshot, "mining-catalog-save"
        ):
            write_snapshot()


    def _hge_targets(self):
        return self._cached_derived(
            "hge_targets", (self._state_revision, self._hge_revision),
            self._build_hge_targets,
        )


    def _build_hge_targets(self):
        wanted = {
            normalize(material.get("key")): material
            for material in self._state.get("materials", [])
            if int(material.get("missing", 0) or 0) > 0
            and is_hge_material(str(material.get("key") or ""))
        }
        best = {}
        for sighting in rank_all_hge_sightings(
            self._hge_sightings, self._state.get("currentPosition")
        ):
            age = float(sighting.get("age_seconds", 2700))
            if age > 2700:
                continue
            freshness = max(0.20, 1.0 - age / 2700)
            distance = sighting.get("distance_ly")
            for candidate in sighting.get("materials", []) or []:
                key = normalize(candidate.get("material"))
                if key not in wanted:
                    continue
                confidence = float(
                    candidate.get("confidence", 0.0) or 0.0
                ) * freshness
                score = confidence * 100.0 - (distance or 0.0) * 0.08
                rank = (
                    -score,
                    distance if distance is not None else float("inf"),
                )
                if key not in best or rank < best[key][0]:
                    best[key] = (rank, {**sighting, "confidence": confidence})
        rows = []
        for normalized_key, material in wanted.items():
            key = str(material.get("key") or "")
            target = best.get(normalized_key, ((), {}))[1]
            rows.append({
                "key": key,
                "name": material.get("name") or key,
                "missing": int(material.get("missing", 0) or 0),
                "active": bool(target),
                "system": target.get("system", ""),
                "state": target.get("state", ""),
                "ageMinutes": int(target.get("age_seconds", 0) // 60)
                if target else -1,
                "distance": float(target.get("distance_ly", -1) or -1)
                if target else -1,
                "confidence": float(target.get("confidence", 0) or 0),
            })
        return sorted(rows, key=lambda row: (
            not row["active"], -row["confidence"], row["name"].casefold()
        ))


    def _hge_finder_rows(self):
        return self._cached_derived(
            "hge_finder_rows", (self._state_revision, self._hge_revision),
            self._build_hge_finder_rows,
        )


    def _build_hge_finder_rows(self):
        material_names = {
            normalize(row.get("key")): str(row.get("name") or row.get("key") or "")
            for row in self._state.get("materials", [])
        }
        rows = []
        for sighting in rank_all_hge_sightings(
            self._state.get("localHgeSightings", []),
            self._state.get("currentPosition")
        ):
            state = readable_faction_state(
                sighting.get("state_raw") or sighting.get("state")
            )
            probable_materials = sighting.get("materials") or infer_hge_materials(
                state, sighting.get("allegiance")
            )
            materials = [
                material_names.get(
                    normalize(item.get("material")),
                    str(item.get("material") or "").replace("_", " ").title(),
                )
                for item in probable_materials
            ]
            rows.append({
                "system": str(sighting.get("system") or ""),
                "faction": str(sighting.get("faction") or "Unknown faction"),
                "state": state or "Unknown state",
                "allegiance": str(sighting.get("allegiance") or ""),
                "distance": (
                    round(float(sighting["distance_ly"]), 1)
                    if sighting.get("distance_ly") is not None else -1
                ),
                "remainingSeconds": int(sighting.get("remaining_seconds", 0)),
                "remainingMinutes": max(
                    1, int(sighting.get("remaining_seconds", 0) // 60)
                ),
                "materials": ", ".join(materials) if materials else
                "Contents not predictable from available state data",
                "selfTest": bool(sighting.get("self_test")),
                "localVerified": True,
                "status": "VERIFIED",
            })
        return rows


    def _hge_candidate_rows(self):
        cache_key = (
            id(self._hge_sightings), len(self._hge_sightings), id(self._state)
        )
        if cache_key == self._hge_candidate_cache_key:
            return self._hge_candidate_cache_rows
        rows = self._build_hge_candidate_rows(
            self._state, self._hge_sightings
        )
        self._hge_candidate_cache_key = cache_key
        self._hge_candidate_cache_rows = rows
        self._hge_material_filter_cache = None
        return rows


    def _build_hge_candidate_rows(self, state, sightings):
        material_names = {
            normalize(row.get("key")): str(row.get("name") or row.get("key") or "")
            for row in state.get("materials", [])
        }
        rows = []
        for candidate in rank_hge_candidate_systems(
            sightings, state.get("currentPosition"),
            current_system=state.get("system", ""),
            current_system_address=state.get("currentSystemAddress"),
        ):
            predictions = [
                {
                    "name": material_names.get(
                        normalize(item.get("material")),
                        str(item.get("material") or "").replace("_", " ").title(),
                    ),
                    "confidence": int(round(float(item.get("confidence", 0)) * 100)),
                }
                for item in candidate.get("materials", [])
            ]
            scan = state.get("localHgeScan", {}) or {}
            same_system = (
                str(candidate.get("system") or "").casefold()
                == str(scan.get("system") or "").casefold()
            )
            status = str(scan.get("status") or "UNKNOWN") if same_system else "UNKNOWN"
            rows.append({
                "system": candidate.get("system", ""),
                "distance": (
                    round(float(candidate["distance_ly"]), 1)
                    if candidate.get("distance_ly") is not None else -1
                ),
                "reportCount": int(candidate.get("report_count", 0) or 0),
                "lastReportedMinutes": int(
                    candidate.get("last_reported_minutes", 0) or 0
                ),
                "factions": ", ".join(candidate.get("factions", [])[:3])
                or "Faction not reported",
                "states": ", ".join(candidate.get("states", [])[:3])
                or "State not reported",
                "materials": ", ".join(item["name"] for item in predictions)
                if predictions else "Contents not predictable from available state data",
                "prediction": ", ".join(
                    f"{item['name']} ({item['confidence']}%)" for item in predictions
                ) if predictions else "No reliable material prediction",
                "predictionBasis": str(
                    candidate.get("prediction_basis") or "BGS data unavailable"
                ),
                "candidateOnly": True,
                "selfTest": False,
                "status": status,
            })
        return rows


    def _mining_rows(self):
        cache_key = self._mining_rows_identity(
            self._state, self._mining_catalog
        )
        if getattr(self, "_mining_rows_cache_key", None) == cache_key:
            return self._mining_rows_cache
        # Production controllers prepare the 60+ MB catalog view in a worker.
        # Lightweight test shells retain the deterministic synchronous path.
        if hasattr(self, "_network_threads_lock"):
            self._queue_mining_rows_build()
            return getattr(self, "_mining_rows_cache", [])
        rows = self._build_mining_rows(self._state, self._mining_catalog)
        self._mining_rows_cache_key = cache_key
        self._mining_rows_cache = rows
        return rows


    def _mining_rows_identity(self, state, catalog):
        local = state.get("localMiningEvidence", {})
        local_rows = local.get("candidates") if isinstance(local, dict) else ()
        local_rows = local_rows if isinstance(local_rows, list) else ()
        catalog_rows = catalog.get("candidates", [])
        catalog_rows = catalog_rows if isinstance(catalog_rows, list) else []
        origin = state.get("currentPosition")
        # Production Journal workers fingerprint immutable local rows once.
        # Imported/legacy states and small test shells use content comparison.
        signature = state.get("_miningCandidatesSignature")
        local_identity = (signature, len(local_rows)) if isinstance(signature, str) else local_rows
        local_revision = dependency_revision(self, "mining-local-rows", (
            profile_dependency(self), local_identity,
        ))
        return (
            id(catalog), id(catalog_rows), len(catalog_rows), local_revision,
            getattr(self, "_mining_catalog_revision", 0),
            str(catalog.get("resetAt") or ""),
            str(state.get("system") or "").casefold(),
            tuple(origin) if isinstance(origin, (list, tuple)) else (),
            # Invalidate cached result freshness hourly. Rebuilding a ~50 MB
            # catalog every minute stalls filter controls.
            int(time.time() // 3600),
        )


    def _build_mining_rows(self, state, mining_catalog, *, decorate=True):
        local = state.get("localMiningEvidence", {})
        local_rows = local.get("candidates", []) if isinstance(local, dict) else []
        catalog = mining_catalog.get("candidates", [])
        catalog_rows = catalog if isinstance(catalog, list) else []
        reset_at = str(mining_catalog.get("resetAt") or "")
        if reset_at:
            local_rows = [
                row for row in local_rows
                if str(row.get("observedAt") or "") > reset_at
            ]
            catalog_rows = [
                row for row in catalog_rows
                if str(row.get("learnedAt") or "") > reset_at
            ]
        origin = state.get("currentPosition")
        # The persisted catalog is already normalized on ingestion. Merge the
        # much smaller local delta into it instead of reprocessing every ring.
        if local_rows:
            rows, _displaced = merge_mining_candidate_batch(catalog_rows, local_rows)
        else:
            # No delta means no ring identity index is needed. Building one
            # for 270k rows only to throw it away costs time and allocator RAM.
            rows = [row for row in catalog_rows if isinstance(row, dict)]
        if not decorate:
            # Share immutable source rows; only actual results need UI labels.
            return rows
        rows = [dict(row) for row in rows]
        current = str(state.get("system") or "").casefold()
        for row in rows:
            legacy_planetary_count = sum(
                int(item.get("count", 0) or 0)
                for item in row.get("hotspots", [])
                if isinstance(item, dict)
                and mining_commodity_id(item.get("commodity"))
                == "planetarymininglocation"
            )
            row["planetaryMiningLocationCount"] = max(
                int(row.get("planetaryMiningLocationCount", 0) or 0),
                legacy_planetary_count,
            )
            row["hotspots"] = [
                item for item in row.get("hotspots", [])
                if isinstance(item, dict)
                and is_mining_commodity_signal(item.get("commodity"))
            ]
            if current and str(row.get("system") or "").casefold() == current:
                row["distanceLy"] = 0.0
            elif (isinstance(origin, (list, tuple)) and len(origin) == 3
                  and isinstance(row.get("coordinates"), (list, tuple))
                  and len(row["coordinates"]) == 3):
                try:
                    row["distanceLy"] = round(math.sqrt(sum(
                        (float(left) - float(right)) ** 2
                        for left, right in zip(origin, row["coordinates"])
                    )), 1)
                except (TypeError, ValueError):
                    row["distanceLy"] = None
            row["hotspotNames"] = ", ".join(
                self._mining_display_name(item.get("commodity"))
                for item in row.get("hotspots", []) if isinstance(item, dict)
            ) or "No hotspot signals recorded"
            row["ringTypeName"] = self._mining_display_name(
                row.get("ringType")
            ).replace("E Ring Class ", "") or "Unknown"
            row["reserveName"] = self._mining_display_name(
                row.get("reserveLevel")
            ).replace(" Resources", "") or "Unknown"
        return rows


    def _queue_mining_rows_build(self):
        cache_key = self._mining_rows_identity(
            self._state, self._mining_catalog
        )
        if getattr(self, "_mining_rows_cache_key", None) == cache_key:
            return False
        if getattr(self, "_mining_rows_build_in_flight", False):
            self._mining_rows_build_dirty = True
            return False
        self._mining_rows_build_token = getattr(
            self, "_mining_rows_build_token", 0
        ) + 1
        token = self._mining_rows_build_token
        generation = self._profile_generation
        profile_key = self.profile_context.key
        state = self._state
        catalog = self._mining_catalog
        self._mining_rows_build_in_flight = True
        self._mining_rows_build_dirty = False

        def worker():
            try:
                rows = self._build_mining_rows(state, catalog, decorate=False)
                summary = self._summarize_mining_rows(rows)
                result = (
                    token, generation, profile_key, cache_key,
                    rows, summary, "",
                )
            except Exception as exc:
                result = (
                    token, generation, profile_key, cache_key, [], {},
                    f"{type(exc).__name__}: {exc}",
                )
            self.miningRowsReady.emit(result)

        if not self._start_network_worker(worker, "mining-rows-build"):
            self._mining_rows_build_in_flight = False
            return False
        return True


    @Slot(object)
    def _finish_mining_rows_build(self, payload):
        token, generation, profile_key, cache_key, rows, summary, error = payload
        if token != self._mining_rows_build_token:
            return
        self._mining_rows_build_in_flight = False
        current = (
            generation == self._profile_generation
            and profile_key == self.profile_context.key
        )
        current_key = self._mining_rows_identity(
            self._state, self._mining_catalog
        ) if current else None
        if current and not error and cache_key == current_key:
            self._mining_rows_cache_key = cache_key
            self._mining_rows_cache = rows
            self._mining_rows_summary_identity = id(rows)
            self._mining_rows_summary = summary
            self._mining_cache_summary_key = None
            self._mining_find_cache_key = None
            self._mining_find_cache = []
            self.miningChanged.emit()
        elif current and error:
            LOGGER.warning("Mining rows background build failed: %s", error)
        dirty = getattr(self, "_mining_rows_build_dirty", False)
        self._mining_rows_build_dirty = False
        if current and (dirty or cache_key != current_key):
            self._queue_mining_rows_build()


    @staticmethod
    def _mining_display_name(value):
        commodity = MINING_COMMODITIES.get(mining_commodity_id(value))
        if commodity:
            return str(commodity["name"])
        text = str(value or "").replace("_", " ").strip()
        if text.casefold().startswith("$saa signaltype ") and text.endswith(";"):
            text = text[len("$saa signaltype "):-1]
        text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
        return text.title()


    @Slot(str, int, str, str, result="QVariantList")
    def miningFindPage(self, commodity, nearby_ly, evidence, reserve_filter):
        return self._mining_find_page(
            commodity, nearby_ly, evidence, reserve_filter, ""
        )


    @Slot(str, int, str, str, str, result="QVariantList")
    def miningFindPageForMethod(
        self, commodity, nearby_ly, evidence, reserve_filter, method,
    ):
        return self._mining_find_page(
            commodity, nearby_ly, evidence, reserve_filter, method
        )


    @Slot(str, int, result="QStringList")
    def miningSystemSuggestions(self, query, limit=8):
        """Return fast local prefix matches while preserving free text input."""
        key = str(query or "").strip().casefold()
        if not key:
            return []
        limit = max(1, min(20, int(limit or 8)))
        names = getattr(self, "_mining_system_names", [])
        keys = getattr(self, "_mining_system_name_keys", [])
        result = []
        seen = set()

        current = str(getattr(self, "_state", {}).get("system") or "").strip()
        if current and current.casefold().startswith(key):
            result.append(current)
            seen.add(current.casefold())

        if not isinstance(names, list) or not isinstance(keys, list):
            return result
        index = bisect_left(keys, key)
        while index < len(keys) and len(result) < limit:
            candidate_key = keys[index]
            if not candidate_key.startswith(key):
                break
            if candidate_key not in seen:
                result.append(names[index])
                seen.add(candidate_key)
            index += 1
        return result


    def _mining_market_rows_for_query(self, query):
        """Reuse accumulated observations while a fresh query is loading."""
        market_cache = getattr(self, "_mining_market_cache", {})
        cached_query = (
            market_cache.get("query", {})
            if isinstance(market_cache, dict) else {}
        )
        current_rows = (
            market_cache.get("markets", [])
            if isinstance(cached_query, dict) and cached_query == query else []
        )
        origin = self._known_mining_origin(query.get("startSystem"))
        store = getattr(self, "_mining_market_store", None)
        if store is not None:
            retained_rows = store.nearby(
                query.get("commodity"),
                origin_system=query.get("startSystem"),
                origin_coordinates=(origin or {}).get("coordinates"),
                max_distance=query.get("nearbyLy", 0),
            )
        else:
            # Compatibility for lightweight controller doubles in unit tests.
            retained_rows = nearby_catalog_markets(
                getattr(self, "_mining_market_catalog", {}),
                query.get("commodity"),
                origin_system=query.get("startSystem"),
                origin_coordinates=(origin or {}).get("coordinates"),
                max_distance=query.get("nearbyLy", 0),
            )
        return latest_market_rows(retained_rows, current_rows)


    def _maybe_auto_refresh_mining_markets(self):
        """Warm one useful stale market target without changing the open route."""
        if getattr(self, "_mining_market_busy", False) or getattr(
            self, "_shutdown_complete", False
        ):
            return
        retry_timer = getattr(self, "_mining_market_retry_timer", None)
        if retry_timer is not None and retry_timer.isActive():
            return
        store = getattr(self, "_mining_market_store", None)
        target = store.next_warm_target() if store is not None else {}
        if isinstance(target, dict) and target.get("startSystem") \
                and target.get("commodity"):
            self._start_mining_market_refresh(target, background=True)
            return
        # Compatibility and one-time upgrade path: a pre-queue profile's last
        # visible query becomes its first warm target.
        cache = getattr(self, "_mining_market_cache", {})
        query = cache.get("query", {}) if isinstance(cache, dict) else {}
        if not isinstance(query, dict) or not query.get("startSystem") \
                or not query.get("commodity"):
            return
        if store is None or not hasattr(store, "remember_warm_target"):
            self.refreshMiningMarkets(
                query.get("startSystem"), query.get("commodity"),
                int(query.get("nearbyLy", 0) or 0),
                int(query.get("minDemand", 0) or 0),
                int(query.get("maxMarketAgeHours", 0) or 0),
                str(query.get("landingPad") or "ANY"),
            )
            return
        self._remember_mining_warm_targets(query)
        target = store.next_warm_target()
        if target:
            self._start_mining_market_refresh(target, background=True)


    @Slot(str, str, int, int, int, int, str, result="QVariantMap")
    def miningMarketDiagnostics(
        self, start_system, commodity, nearby_ly, min_demand, max_demand,
        max_market_age_hours, landing_pad,
    ):
        query = {
            "startSystem": str(start_system or "").strip().casefold(),
            "commodity": mining_commodity_id(commodity),
            "nearbyLy": int(nearby_ly or 0),
            "minDemand": int(min_demand or 0),
            "maxMarketAgeHours": int(max_market_age_hours or 0),
            "landingPad": str(landing_pad or "ANY").upper(),
        }
        if getattr(self, "_async_mining_plan_enabled", False):
            values = (start_system, commodity, nearby_ly, min_demand, max_demand,
                      max_market_age_hours, landing_pad)
            if getattr(self, "_mining_plan_diagnostics_args", None) == values:
                return self._mining_plan_diagnostics
            cached = getattr(self, "_mining_market_cache", {}).get("query", {})
            return {"originKnown": bool(self._known_mining_origin(start_system)),
                    "catalogMarkets": 0,
                    "cacheMatches": isinstance(cached, dict) and cached == query}
        cache = getattr(self, "_mining_market_cache", {})
        cached_query = cache.get("query", {}) if isinstance(cache, dict) else {}
        cache_matches = isinstance(cached_query, dict) and cached_query == query
        markets = self._mining_market_rows_for_query(query)
        diagnostics = market_filter_diagnostics(
            markets, commodity,
            landing_pad=landing_pad,
            min_demand=min_demand,
            max_demand=max_demand,
            max_market_age_hours=max_market_age_hours,
        )
        diagnostics["cacheMatches"] = cache_matches
        diagnostics["catalogMarkets"] = len(markets)
        diagnostics["originKnown"] = bool(
            self._known_mining_origin(start_system)
        )
        return diagnostics


    @Slot(
        str, str, int, str, str, bool, str, str, int, int, int, int, bool,
        bool, bool, bool, str, str, str, str, str,
        result="QVariantList",
    )
    def miningPlanRoutes(
        self, start_system, commodity, nearby_ly, reserve_filter, ring_filter,
        rings_only, method, optimization, min_demand, max_demand,
        max_market_age_hours, result_limit, require_hotspot, prefer_res,
        prefer_secondary, require_system_state, landing_pad, power,
        power_goal, opposing_power, system_state,
    ):
        args = (start_system, commodity, nearby_ly, reserve_filter, ring_filter,
                rings_only, method, optimization, min_demand, max_demand,
                max_market_age_hours, result_limit, require_hotspot, prefer_res,
                prefer_secondary, require_system_state, landing_pad, power,
                power_goal, opposing_power, system_state)
        if getattr(self, "_async_mining_plan_enabled", False):
            return self._queue_mining_plan(args)
        return self._compute_mining_plan_routes(*args)


    def _mining_plan_key(self, args):
        state = self._state
        return (profile_dependency(self), args, getattr(self, "_mining_rows_cache_key", None),
                self._mining_rows_identity(state, self._mining_catalog),
                getattr(self, "_mining_market_revision", 0),
                id(getattr(self, "_mining_market_cache", None)),
                id(getattr(self, "_mining_powerplay_catalog", None)),
                id(getattr(self, "_mining_powerplay_observations", None)),
                dependency_revision(self, "mining-plan-verification",
                                    getattr(self, "_mining_market_verification_states", {})),
                int(time.time() // 60))


    def _queue_mining_plan(self, args):
        rows = self._mining_rows()
        key = self._mining_plan_key(args)
        self._mining_plan_requested_args = args
        if getattr(self, "_mining_plan_cache_key", None) == key:
            return self._mining_plan_cache
        previous = (getattr(self, "_mining_plan_cache", [])
                    if (getattr(self, "_mining_plan_cache_key", None) or (None, None))[:2] == key[:2]
                    else [])
        if getattr(self, "_active_mining_plan", None) is not None:
            return previous
        # A plain Python domain facade, not a QObject used across threads.
        snapshot = NavigationMixin()
        for name in ("_state", "_mining_market_cache", "_mining_market_catalog",
                     "_mining_market_store", "_mining_powerplay_catalog",
                     "_mining_powerplay_observations", "_data_dir", "_reference_data_dir"):
            if hasattr(self, name):
                setattr(snapshot, name, getattr(self, name))
        snapshot._mining_market_verification_states = {
            name: dict(value) for name, value in
            getattr(self, "_mining_market_verification_states", {}).items()
        }
        snapshot._network_threads_lock = True  # Raw shared rows need distances.
        snapshot._mining_rows_cache_key = getattr(self, "_mining_rows_cache_key", None)
        snapshot._mining_rows = lambda: rows
        snapshot._valid_star_position = type(self)._valid_star_position
        snapshot._system_coordinate_index = type(self)._system_coordinate_index.__get__(snapshot)
        request_id = uuid.uuid4().hex
        self._active_mining_plan = request_id

        def worker():
            try:
                routes = snapshot._compute_mining_plan_routes(*args)
                diagnostic_args = (args[0], args[1], args[2], args[8], args[9], args[10], args[16])
                diagnostics = snapshot.miningMarketDiagnostics(*diagnostic_args)
                result = (request_id, key, args, routes, diagnostic_args, diagnostics, "")
            except Exception as exc:
                LOGGER.exception("Background mining route plan failed")
                result = (request_id, key, args, [], (), {}, str(exc))
            self.miningPlanReady.emit(result)

        if not self._start_network_worker(worker, "mining-route-plan"):
            self._active_mining_plan = None
        elif hasattr(self, "timer"):
            QTimer.singleShot(0, self.miningChanged.emit)
        return previous


    @Slot(object)
    def _finish_mining_plan(self, result):
        request_id, key, args, rows, diagnostic_args, diagnostics, error = result
        if request_id != getattr(self, "_active_mining_plan", None):
            return
        self._active_mining_plan = None
        requested = getattr(self, "_mining_plan_requested_args", None)
        if requested == args and key == self._mining_plan_key(args):
            same_query = (getattr(self, "_mining_plan_cache_key", None)
                          or (None, None))[:2] == key[:2]
            previous = getattr(self, "_mining_plan_cache", []) if same_query else []
            self._mining_plan_cache_key = key
            # A failed same-query refresh is not evidence of zero matches.
            # Keep the last complete result; another query/profile never gets it.
            self._mining_plan_cache = previous if error or previous == rows else rows
            if not error or not same_query:
                self._mining_plan_diagnostics_args = diagnostic_args
                self._mining_plan_diagnostics = diagnostics
            if error:
                self._mining_sync_status = "Route planning failed · " + error
        self._mining_plan_result_revision = getattr(self, "_mining_plan_result_revision", 0) + 1
        self.miningChanged.emit()


    miningPlanBusy = Property(bool, lambda self: bool(getattr(self, "_active_mining_plan", None)), notify=miningChanged)


    def _compute_mining_plan_routes(
        self, start_system, commodity, nearby_ly, reserve_filter, ring_filter,
        rings_only, method, optimization, min_demand, max_demand,
        max_market_age_hours, result_limit, require_hotspot, prefer_res,
        prefer_secondary, require_system_state, landing_pad, power,
        power_goal, opposing_power, system_state,
    ):
        candidates = self._mining_find_page(
            commodity, nearby_ly, "ALL EVIDENCE", reserve_filter, method,
            start_system, rings_only,
        )
        query = {
            "startSystem": str(start_system or "").strip().casefold(),
            "commodity": mining_commodity_id(commodity),
            "nearbyLy": int(nearby_ly or 0),
            "minDemand": int(min_demand or 0),
            "maxMarketAgeHours": int(max_market_age_hours or 0),
            "landingPad": str(landing_pad or "ANY").upper(),
        }
        market_query = dict(query)
        if prefer_secondary:
            # MORE RESOURCES needs retained observations for every commodity,
            # not just the primary one. The planner still accepts only
            # evidence-backed secondary resources and exact-station markets.
            market_query["commodity"] = "allcommodities"
        markets = self._mining_market_rows_for_query(market_query)
        routes = plan_mining_routes(
            candidates, commodity, optimization,
            min_demand=min_demand,
            max_market_age_hours=max_market_age_hours,
            result_limit=result_limit,
            require_hotspot=require_hotspot,
            prefer_res=prefer_res,
            ring_filter=ring_filter,
            rings_only=rings_only,
            prefer_secondary=prefer_secondary,
            require_system_state=require_system_state,
            landing_pad=landing_pad,
            power=power,
            power_goal=power_goal,
            opposing_power=opposing_power,
            max_demand=max_demand,
            system_state=system_state,
            markets=markets,
            powerplay_systems=[
                *catalog_rows(getattr(self, "_mining_powerplay_catalog", {})),
                *getattr(self, "_mining_powerplay_observations", []),
            ],
        )
        verification_states = getattr(
            self, "_mining_market_verification_states", {},
        )
        for row in routes:
            if not isinstance(row, dict) or not row.get(
                "sameSystemSaleRequired"
            ):
                continue
            route_commodity = mining_commodity_id(
                row.get("selectedCommodity") or commodity
            )
            system = str(row.get("system") or "").strip()
            key = f"{system.casefold()}\x1f{route_commodity}"
            row["marketVerificationKey"] = key
            state = dict(verification_states.get(key) or {})
            check_state = str(state.get("state") or "")
            if row.get("marketStatus") != "NO_MARKET_DATA":
                continue
            if check_state == "QUEUED":
                row.update({
                    "verificationStatus": "NOT_YET_CHECKED",
                    "powerplayVerificationState": "NOT_YET_CHECKED",
                    "powerplayVerificationLabel": "NOT YET CHECKED",
                    "verificationGroupLabel": "MARKET DATA NOT YET CHECKED",
                    "pendingReason": (
                        "Market lookup is queued; it was not queried in this "
                        "verification pass because the six-target budget was full"
                    ),
                })
            elif check_state == "CHECKING":
                row.update({
                    "verificationStatus": "MARKET_CHECK_RUNNING",
                    "powerplayVerificationState": "MARKET_CHECK_RUNNING",
                    "powerplayVerificationLabel": "MARKET CHECK RUNNING",
                    "verificationGroupLabel": "MARKET CHECK RUNNING",
                    "pendingReason": "Market lookup is running in this verification pass",
                })
            elif check_state == "NO_DATA":
                row["pendingReason"] = str(
                    state.get("reason")
                    or "Server returned no market data for this system and commodity"
                )
        return routes


    def _mining_find_page(
        self, commodity, nearby_ly, evidence, reserve_filter, method,
        start_system="", rings_only=False,
    ):
        commodity = normalize(str(commodity or "ALL COMMODITIES"))
        commodity_id = mining_commodity_id(commodity)
        selected = MINING_COMMODITIES.get(commodity_id)
        method = str(method or "").upper()
        evidence = str(evidence or "ALL EVIDENCE")
        reserve_filter = str(reserve_filter or "ALL RESERVES")
        nearby_limit = int(nearby_ly or 0)
        source_rows = self._mining_rows()
        requested_origin = str(start_system or "").strip()
        current_state = getattr(self, "_state", {})
        current_system = str(current_state.get("system") or "").strip()
        custom_origin = bool(
            requested_origin
            and requested_origin.casefold() != current_system.casefold()
        )
        origin_coordinates = None
        if custom_origin:
            for candidate in source_rows:
                if (
                    str(candidate.get("system") or "").strip().casefold()
                    == requested_origin.casefold()
                ):
                    origin_coordinates = self._valid_star_position(
                        candidate.get("coordinates")
                    )
                    if origin_coordinates is not None:
                        break
            if origin_coordinates is None:
                market_origin = getattr(
                    self, "_mining_market_cache", {},
                ).get("origin", {})
                if (
                    isinstance(market_origin, dict)
                    and str(market_origin.get("system") or "").strip().casefold()
                    == requested_origin.casefold()
                ):
                    origin_coordinates = self._valid_star_position(
                        market_origin.get("coordinates")
                    )
            if origin_coordinates is None:
                try:
                    coordinate_index = self._system_coordinate_index()
                except (AttributeError, OSError):
                    coordinate_index = {}
                origin_coordinates = self._valid_star_position(
                    coordinate_index.get(requested_origin.casefold())
                )
        if custom_origin and nearby_limit > 0 and origin_coordinates is None:
            # A radius cannot be applied honestly until the free-text origin
            # has coordinates. Returning every catalog row used to trigger a
            # galaxy-wide plan on the GUI thread and could freeze ACQUIRE for
            # more than a minute. The refresh below resolves and persists the
            # origin asynchronously, then miningChanged reruns this search.
            return []
        distance_origin = self._valid_star_position(
            origin_coordinates if custom_origin else current_state.get("currentPosition")
        ) if custom_origin or hasattr(self, "_network_threads_lock") else None
        cache_key = (
            getattr(self, "_mining_rows_cache_key", None), commodity_id,
            nearby_limit, evidence, reserve_filter, method,
            requested_origin.casefold(),
            tuple(origin_coordinates) if origin_coordinates is not None else None,
            bool(rings_only),
            # Cheap filtering/planning freshness must keep advancing even
            # when unrelated Journal events no longer rebuild all ring rows.
            int(time.time() // 60),
        )
        if getattr(self, "_mining_find_cache_key", None) == cache_key:
            return self._mining_find_cache
        all_commodities = commodity == normalize("ALL COMMODITIES")
        all_commodity_catalog = (
            self._mining_commodity_catalog() if all_commodities else []
        )
        result = []
        for source_row in source_rows:
            if rings_only and is_belt_candidate(source_row):
                continue
            # Reject on scalar/index-like fields before allocating a dict or
            # walking hotspot lists. Most large catalogs fail distance first.
            distance = source_row.get("distanceLy")
            if custom_origin or hasattr(self, "_network_threads_lock"):
                row_coordinates = self._valid_star_position(
                    source_row.get("coordinates")
                )
                if (
                    str(source_row.get("system") or "").strip().casefold()
                    == (requested_origin or current_system).casefold()
                ):
                    distance = 0.0
                elif distance_origin is not None and row_coordinates is not None:
                    distance = round(math.sqrt(sum(
                        (left - right) ** 2
                        for left, right in zip(
                            distance_origin, row_coordinates
                        )
                    )), 1)
                else:
                    distance = None
            if nearby_limit > 0 and (not custom_origin or origin_coordinates is not None) and (
                distance is None or float(distance) > nearby_limit
            ):
                continue
            # Freshness is time-dependent, so update only rows that survived
            # the cheap distance test instead of rebuilding the full catalog.
            fresh_row = mining_candidate_freshness(source_row)
            if evidence == "RECHECK_RECOMMENDED":
                if not fresh_row.get("recheckRecommended"):
                    continue
            elif (
                evidence != "ALL EVIDENCE"
                and fresh_row.get("evidence") != evidence
            ):
                continue
            reserve = normalize(source_row.get("reserveLevel"))
            if reserve_filter == "PRISTINE + MAJOR" and not (
                "pristine" in reserve or "major" in reserve
            ):
                continue
            if reserve_filter == "PRISTINE" and "pristine" not in reserve:
                continue
            if reserve_filter == "MAJOR" and "major" not in reserve:
                continue
            target_stat = next((
                item for item in source_row.get("yieldStats", [])
                if isinstance(item, dict)
                and mining_commodity_id(item.get("commodity")) == commodity_id
            ), None) if not all_commodities else None
            local_hits = int(
                (target_stat or {}).get("prospectorHits", 0) or 0
            )
            local_refined = int(
                (target_stat or {}).get("refinedCount", 0) or 0
            )
            local_positive = local_hits > 0 or local_refined > 0
            if selected and method and method != RHINO_SURFACE:
                known_ring = mining_ring_type_key(source_row.get("ringType") or source_row.get("ringTypeName"))
                allowed_rings = {
                    mining_ring_type_key(value)
                    for value in mining_ring_types_for_method(commodity_id, method)
                }
                if known_ring and known_ring != "unknown" and allowed_rings and known_ring not in allowed_rings:
                    continue
            community_overlap = bool(selected and method in selected.get("methods", ())) and any(
                isinstance(report, dict) and report.get("commodity") == commodity_id
                and report.get("reportedResTypes")
                for report in source_row.get("communityOverlapReports") or []
            )
            local_samples = int(
                source_row.get("prospectorSampleCount", 0) or 0
            )
            planetary_count = int(source_row.get("planetaryMiningLocationCount", 0) or 0)
            if method == RHINO_SURFACE:
                planetary_count = max(planetary_count, sum(
                    int(item.get("count", 0) or 0) for item in source_row.get("hotspots", [])
                    if isinstance(item, dict) and mining_commodity_id(item.get("commodity")) == "planetarymininglocation"
                ))
                if not planetary_count:
                    continue
            elif not all_commodities:
                hotspot_ids = {
                    mining_commodity_id(item.get("commodity"))
                    for item in source_row.get("hotspots", [])
                    if isinstance(item, dict)
                }
                if commodity_id not in hotspot_ids and not local_positive and not community_overlap:
                    if not (
                        selected and method
                        and method in selected.get("methods", ())
                    ):
                        continue
                    ring_type = mining_ring_type_key(source_row.get("ringType") or source_row.get("ringTypeName"))
                    eligible = {
                        mining_ring_type_key(value) for value in mining_ring_types_for_method(commodity_id, method)
                    }
                    if not ring_type or ring_type not in eligible:
                        continue
            row = fresh_row
            row["hotspots"] = [item for item in row.get("hotspots", [])
                               if isinstance(item, dict) and is_mining_commodity_signal(item.get("commodity"))]
            row["planetaryMiningLocationCount"] = planetary_count
            row["hotspotNames"] = ", ".join(self._mining_display_name(item.get("commodity"))
                                            for item in row["hotspots"]) or "No hotspot signals recorded"
            row["ringTypeName"] = self._mining_display_name(row.get("ringType")).replace("E Ring Class ", "") or "Unknown"
            row["reserveName"] = self._mining_display_name(row.get("reserveLevel")).replace(" Resources", "") or "Unknown"
            row["distanceLy"] = distance
            row["routeOriginSystem"] = requested_origin or current_system
            row["routeOriginKnown"] = not custom_origin or origin_coordinates is not None
            row["localSampleCount"] = local_samples
            row["localYieldHits"] = local_hits
            row["localRefinedCount"] = local_refined
            row["localAverageProportion"] = (
                (target_stat or {}).get("averageProportion")
            )
            if all_commodities:
                commodity_evidence = {}
                for stat in row.get("yieldStats", []):
                    if not isinstance(stat, dict) or not (
                        int(stat.get("prospectorHits", 0) or 0)
                        or int(stat.get("refinedCount", 0) or 0)
                    ):
                        continue
                    identifier = mining_commodity_id(stat.get("commodity"))
                    if identifier:
                        commodity_evidence[identifier] = 0
                for hotspot in row.get("hotspots", []):
                    if not isinstance(hotspot, dict):
                        continue
                    identifier = mining_commodity_id(hotspot.get("commodity"))
                    if identifier:
                        commodity_evidence[identifier] = min(
                            commodity_evidence.get(identifier, 9), 1,
                        )
                ring_type = normalize(row.get("ringTypeName"))
                for catalog_row in all_commodity_catalog:
                    methods = {
                        str(value).upper()
                        for value in catalog_row.get("methods", ())
                    }
                    ring_types = {
                        mining_ring_type_key(value)
                        for value in mining_ring_types_for_method(catalog_row.get("id"), method)
                    }
                    if method and method not in methods:
                        continue
                    if ring_types and mining_ring_type_key(row.get("ringType") or row.get("ringTypeName")) not in ring_types:
                        continue
                    identifier = mining_commodity_id(catalog_row.get("id"))
                    if identifier:
                        commodity_evidence[identifier] = min(
                            commodity_evidence.get(identifier, 9), 2,
                        )
                known_ring = mining_ring_type_key(row.get("ringType") or row.get("ringTypeName"))
                if known_ring and known_ring != "unknown" and method != RHINO_SURFACE:
                    commodity_evidence = {
                        identifier: rank for identifier, rank in commodity_evidence.items()
                        if not mining_ring_types_for_method(identifier, method)
                        or known_ring in {mining_ring_type_key(value) for value in mining_ring_types_for_method(identifier, method)}
                    }
                candidates = sorted(
                    commodity_evidence.items(),
                    key=lambda item: (
                        item[1], mining_commodity_name(item[0]).casefold(),
                    ),
                )
                row["candidateCommodities"] = [{
                    "id": identifier,
                    "name": mining_commodity_name(identifier),
                    "evidence": (
                        "LOCAL_YIELD" if rank == 0
                        else "HOTSPOT" if rank == 1 else "RING_TYPE"
                    ),
                } for identifier, rank in candidates]
            if method == RHINO_SURFACE:
                row["targetMatch"] = "PLANETARY_MINING_LOCATION"
                row["targetMatchName"] = (
                    "PLANETARY MINING LOCATION · COMMODITY UNCONFIRMED"
                )
                row["ringTypeName"] = "Planetary surface"
                row["reserveName"] = "Unknown"
                row["hotspotNames"] = (
                    f"{int(row['planetaryMiningLocationCount'])} "
                    "planetary mining locations reported"
                )
            elif not all_commodities:
                hotspot_ids = {
                    mining_commodity_id(item.get("commodity"))
                    for item in row.get("hotspots", []) if isinstance(item, dict)
                }
                if local_positive:
                    row["targetMatch"] = "LOCAL_YIELD"
                    if local_hits:
                        label = (
                            f"LOCAL YIELD OBSERVED · {local_hits}/{local_samples} "
                            "PROSPECTORS"
                        )
                        average = row.get("localAverageProportion")
                        if average is not None:
                            label += f" · AVG {float(average):.1f}%"
                        if local_refined:
                            label += f" · {local_refined} REFINED"
                    else:
                        label = f"LOCAL REFINED · {local_refined} UNITS"
                    row["targetMatchName"] = label
                elif commodity_id in hotspot_ids:
                    row["targetMatch"] = "HOTSPOT"
                    row["targetMatchName"] = (
                        f"HOTSPOT CONFIRMED · {int(row.get('sourceCount', 1) or 1)} "
                        "SOURCE(S)"
                    )
                elif community_overlap:
                    row["targetMatch"] = "COMMUNITY_OVERLAP"
                    row["targetMatchName"] = "COMMUNITY OVERLAP REPORTED · CHECK DATE UNKNOWN"
                else:
                    row["targetMatch"] = "RING_TYPE"
                    row["targetMatchName"] = (
                        "RING TYPE ONLY · YIELD UNCONFIRMED"
                    )
                if local_samples and not local_positive:
                    row["targetMatchName"] += (
                        f" · LOCAL SAMPLE 0/{local_samples} · NOT CONCLUSIVE"
                    )
            else:
                best_evidence = (
                    row.get("candidateCommodities", [{}])[0].get("evidence")
                    if row.get("candidateCommodities") else "RING_TYPE"
                )
                row["targetMatch"] = best_evidence
                row["targetMatchName"] = (
                    f"{len(row.get('candidateCommodities', []))} CONCRETE "
                    "COMMODITIES · BEST EVIDENCE " + best_evidence.replace(
                        "_", " "
                    )
                )
            result.append(row)
        if not all_commodities:
            def mining_rank(row):
                target = row.get("targetMatch")
                evidence_rank = MINING_EVIDENCE_RANK.get(
                    row.get("sourceEvidence") or row.get("evidence"), 0
                )
                if target == "LOCAL_YIELD":
                    match_rank = 0
                elif row.get("localSampleCount") and not (
                    row.get("localYieldHits") or row.get("localRefinedCount")
                ):
                    match_rank = 4
                elif target in {"HOTSPOT", "PLANETARY_MINING_LOCATION"}:
                    match_rank = 1 if evidence_rank >= MINING_EVIDENCE_RANK[
                        "LIVE_REPORTED"
                    ] else 2
                elif target == "RING_TYPE":
                    match_rank = 3
                else:
                    match_rank = 5
                reserve_name = normalize(row.get("reserveLevel"))
                reserve_rank = (
                    0 if "pristine" in reserve_name
                    else 1 if "major" in reserve_name else 2
                )
                distance = row.get("distanceLy")
                arrival = row.get("distanceToArrivalLs")
                return (
                    match_rank,
                    bool(row.get("stale")),
                    -evidence_rank,
                    -int(row.get("sourceCount", 0) or 0),
                    reserve_rank,
                    distance is None,
                    float(distance or 0),
                    arrival is None,
                    float(arrival or 0),
                    str(row.get("system") or "").casefold(),
                    str(row.get("ring") or "").casefold(),
                )

            # This sorts only the already filtered/cached result. The large
            # catalog projection remains off the UI thread and untouched.
            result.sort(key=mining_rank)
        self._mining_find_cache_key = cache_key
        self._mining_find_cache = result
        return result


    @Slot(str, result="QVariantMap")
    def miningLoadoutReadiness(self, method):
        method = str(method or "LASER").upper()
        module_ids = [normalize(row.get("moduleId")) for row in
                      self._state.get("moduleSlots", []) if isinstance(row, dict)]
        cargo = int(self._state.get("selectedShipStats", {}).get(
            "cargoCapacity", 0
        ) or 0)
        checks = []

        def check(label, *markers):
            installed = any(any(marker in module for marker in markers)
                            for module in module_ids)
            checks.append({"label": label, "installed": installed})

        if method == "LASER":
            check("Prospector", "prospector", "multidronecontrolmining")
            check("Collector", "collector", "collection", "multidronecontrolmining")
            check("Refinery", "refinery")
        elif method == "CORE":
            check("Seismic charge launcher", "miningseismchrgwarhd")
            check("Abrasion blaster", "miningabrasionblaster")
            check("Pulse wave analyser", "cloudscanner", "mrascanner")
            check("Collector", "collector", "collection", "multidronecontrolmining")
            check("Refinery", "refinery")
        elif method == "SUBSURFACE":
            check("Sub-surface displacement missile", "miningsubsurfdispmisle")
            check("Prospector", "prospector", "multidronecontrolmining")
            check("Collector", "collector", "collection", "multidronecontrolmining")
            check("Refinery", "refinery")
        else:
            vehicle = self._state.get("vehicleState", {})
            rhino = any("rhino" in normalize(row.get("type")) for row in
                        vehicle.get("vehicles", []) if isinstance(row, dict))
            checks.append({"label": "Rhino observed in vehicle inventory",
                           "installed": rhino})
        checks.append({"label": f"Cargo capacity ({cargo} t)", "installed": cargo > 0})
        ready = bool(checks) and all(row["installed"] for row in checks)
        return {
            "method": method,
            "ready": ready,
            "status": "READY" if ready else "INCOMPLETE",
            "summary": " · ".join(
                ("✓ " if row["installed"] else "✕ ") + row["label"]
                for row in checks
            ),
        }


    def _mining_commodity_filters(self):
        return [
            "ALL COMMODITIES",
            *(row["name"] for row in self._mining_commodity_catalog()),
        ]


    def _mining_commodity_catalog(self):
        local = self._state.get("localMiningEvidence", {})
        observed = local.get("refinedCommodities", []) \
            if isinstance(local, dict) else []
        observed = list(observed) if isinstance(observed, list) else []
        for row in self._mining_rows():
            for hotspot in row.get("hotspots", []):
                if isinstance(hotspot, dict):
                    observed.append({"id": hotspot.get("commodity")})
        return mining_commodity_catalog(observed)


    @Slot(str, result="QStringList")
    def miningCommodityFiltersForMethod(self, method):
        local = self._state.get("localMiningEvidence", {})
        observed = local.get("refinedCommodities", []) \
            if isinstance(local, dict) else []
        rows = mining_commodities_for_method(method, observed)
        return ["ALL COMMODITIES", *(row["name"] for row in rows)]


    @Slot(str, str, result="QStringList")
    def miningRingFiltersForCommodity(self, commodity, method):
        """Return only ring types in which the selected commodity can occur."""
        if str(method or "").upper() == RHINO_SURFACE:
            return ["ANY RING"]

        selected = MINING_COMMODITIES.get(mining_commodity_id(commodity))
        ring_types = mining_ring_types_for_method(commodity, method) if selected else ()
        result = []
        for value in ring_types:
            normalized = str(value or "").strip().upper()
            if normalized and normalized not in result:
                result.append(normalized)
        result.append("ANY RING")
        return result


    @staticmethod
    def _summarize_mining_rows(rows):
        """Calculate stored-record quality; safe to run in the row worker."""
        counts = {key: 0 for key in (
            "LOCAL_CONFIRMED", "LIVE_REPORTED", "CATALOG_CANDIDATE", "STALE"
        )}
        latest = ""
        systems = set()
        with_system = 0
        with_coordinates = 0
        with_ring = 0
        with_ring_type = 0
        with_reserve = 0
        with_resource_evidence = 0
        current = 0

        def known_text(value):
            return str(value or "").strip().casefold() not in {
                "", "unknown", "unconfirmed", "none",
            }

        for source in rows:
            row = source if "stale" in source else mining_candidate_freshness(source)
            evidence = str(row.get("evidence") or "STALE")
            counts[evidence] = counts.get(evidence, 0) + 1
            observed = str(row.get("observedAt") or "")
            if observed > latest:
                latest = observed
            system = str(row.get("system") or "").strip()
            if system:
                systems.add(system.casefold())
                with_system += 1
            coordinates = row.get("coordinates")
            with_coordinates += int(
                isinstance(coordinates, (list, tuple))
                and len(coordinates) == 3
                and all(value is not None for value in coordinates)
            )
            with_ring += int(bool(
                str(row.get("ring") or row.get("body") or "").strip()
            ))
            with_ring_type += int(known_text(
                row.get("ringTypeName") or row.get("ringType")
            ))
            with_reserve += int(known_text(
                row.get("reserveName") or row.get("reserveLevel")
            ))
            with_resource_evidence += int(bool(
                row.get("hotspots") or row.get("yieldStats")
                or int(row.get("planetaryMiningLocationCount", 0) or 0)
            ))
            current += int(not bool(row.get("stale")))

        total = len(rows)

        def percentage(value):
            return int(round(100 * value / total)) if total else 0

        completeness_known = (
            with_system + with_ring + with_coordinates + with_ring_type
            + with_reserve + with_resource_evidence
        )
        return {
            "total": total,
            "systems": len(systems),
            "local": counts["LOCAL_CONFIRMED"],
            "live": counts["LIVE_REPORTED"],
            "catalog": counts["CATALOG_CANDIDATE"],
            "stale": counts["STALE"],
            "withHotspots": sum(bool(row.get("hotspots")) for row in rows),
            "recordCompleteness": int(round(
                100 * completeness_known / (total * 6)
            )) if total else 0,
            "coordinatesPercent": percentage(with_coordinates),
            "ringPercent": percentage(with_ring),
            "ringTypePercent": percentage(with_ring_type),
            "reservePercent": percentage(with_reserve),
            "resourceEvidencePercent": percentage(with_resource_evidence),
            "currentPercent": percentage(current),
            "latestAt": latest.replace("T", " ")[:16] if latest else "—",
        }


    def _mining_cache_summary(self):
        rows = self._mining_rows()
        powerplay_rows = catalog_rows(getattr(
            self, "_mining_powerplay_catalog", {}
        ))
        powerplay_total = len(powerplay_rows) + len(getattr(
            self, "_mining_powerplay_observations", []
        ))
        cache_key = (
            id(rows), len(rows),
            int(getattr(self, "_mining_market_revision", 0) or 0),
            id(getattr(self, "_mining_powerplay_catalog", None)),
            powerplay_total,
        )
        if getattr(self, "_mining_cache_summary_key", None) == cache_key:
            return self._mining_cache_summary_cache
        if getattr(self, "_mining_rows_summary_identity", None) == id(rows):
            base = dict(getattr(self, "_mining_rows_summary", {}))
        else:
            base = self._summarize_mining_rows(rows)
        store = getattr(self, "_mining_market_store", None)
        try:
            market_total = int(store.count()) if store is not None else 0
        except (OSError, sqlite3.DatabaseError):
            market_total = 0
        result = {
            **base,
            "marketTotal": market_total,
            "powerplayTotal": powerplay_total,
        }
        self._mining_cache_summary_key = cache_key
        self._mining_cache_summary_cache = result
        return result


    traderRoute = Property(
        "QVariantList", lambda self: self._get("traderRoute", []),
        notify=CoreControllerMixin.materialsChanged,
    )


    miningCommodityFilters = Property(
        "QStringList", lambda self: self._mining_commodity_filters(),
        notify=CoreControllerMixin.stateChanged,
    )


    def _mining_ui_revision(self):
        state = self._state
        local = state.get("localMiningEvidence", {})
        local = local if isinstance(local, dict) else {}
        stats = state.get("selectedShipStats", {}) or {}
        vehicle = state.get("vehicleState", {}) or {}
        return dependency_revision(self, "mining-ui", (
            self._mining_rows_identity(state, self._mining_catalog),
            # Background publication is itself a relevant UI change: without
            # this fence the first empty/interim result could remain visible.
            getattr(self, "_mining_rows_cache_key", None),
            getattr(self, "_mining_plan_result_revision", 0),
            getattr(self, "_mining_market_revision", 0),
            getattr(self, "_mining_market_verification_states", {}),
            local.get("refinedCommodities", []),
            state.get("activeShipId"), state.get("selectedShipId"),
            tuple(row.get("moduleId") for row in state.get("moduleSlots", [])
                  if isinstance(row, dict)),
            stats.get("cargoCapacity"), vehicle.get("vehicles", []),
            (state.get("powerplayOverview", {}) or {}).get("power"),
            int(time.time() // 60),
        ))


    miningRevision = Property(
        int, lambda self: self._mining_ui_revision(),
        notify=CoreControllerMixin.stateChanged,
    )


    pinnedMiningSystems = Property(
        "QVariantList", lambda self: sorted(self._mining_pins),
        notify=miningChanged,
    )


    @Slot(str)
    def toggleMiningPin(self, key):
        key = str(key or "").strip()
        if not key:
            return
        if key in self._mining_pins:
            self._mining_pins.discard(key)
        else:
            self._mining_pins.add(key)
            cache = getattr(self, "_mining_market_cache", {})
            query = cache.get("query", {}) if isinstance(cache, dict) else {}
            store = getattr(self, "_mining_market_store", None)
            if store is not None and isinstance(query, dict):
                store.remember_warm_target(query, priority=120, used=False)
        self._persist_json(
            self.mining_pins_file, sorted(self._mining_pins), "Mining Finder pins",
        )
        self.miningChanged.emit()


    miningCacheSummary = Property(
        "QVariantMap", lambda self: self._mining_cache_summary(),
        notify=miningChanged,
    )


    miningSyncBusy = Property(
        bool, lambda self: self._mining_sync_busy, notify=miningChanged,
    )


    miningSyncStatus = Property(
        str, lambda self: self._mining_sync_status, notify=miningChanged,
    )


    miningMarketSyncBusy = Property(
        bool, lambda self: (
            bool(getattr(self, "_pending_mining_market_query", None))
            or bool((getattr(self, "_active_mining_observation_batch", None) or {}).get("searchRefresh"))
            or (
                getattr(self, "_mining_market_busy", False)
                and not getattr(self, "_mining_market_background", False)
            )
        ),
        notify=miningChanged,
    )


    miningMarketSyncStatus = Property(
        str, lambda self: getattr(
            self, "_mining_market_status", "Ready"
        ), notify=miningChanged,
    )


    miningVerificationBusy = Property(
        bool,
        lambda self: getattr(self, "_mining_verification_busy", False),
        notify=miningVerificationChanged,
    )


    miningVerificationStatus = Property(
        str,
        lambda self: getattr(
            self, "_mining_verification_status",
            "Ready · verifies top routes after search",
        ),
        notify=miningVerificationChanged,
    )


    miningVerificationCompleted = Property(
        int,
        lambda self: int(getattr(
            self, "_mining_verification_completed", 0
        ) or 0),
        notify=miningVerificationChanged,
    )


    miningVerificationTotal = Property(
        int,
        lambda self: int(getattr(
            self, "_mining_verification_total", 0
        ) or 0),
        notify=miningVerificationChanged,
    )


    edFrameCatalogEnabled = Property(
        bool,
        lambda self: bool(getattr(self, "_edframe_catalog_enabled", True)),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameCatalogBusy = Property(
        bool,
        lambda self: bool(getattr(self, "_edframe_catalog_busy", False)),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameCatalogOnline = Property(
        bool,
        lambda self: bool(getattr(self, "_edframe_catalog_online", False)),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameCatalogStatus = Property(
        str,
        lambda self: str(getattr(
            self, "_edframe_catalog_status", "Not checked · local catalog active",
        )),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameCatalogLastSuccess = Property(
        str,
        lambda self: str(getattr(self, "_edframe_catalog_last_success", "")),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameCatalogStats = Property(
        "QVariantMap",
        lambda self: dict(getattr(self, "_edframe_catalog_stats", {}) or {}),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameCatalogLog = Property(
        "QVariantList",
        lambda self: list(getattr(self, "_edframe_catalog_log", []) or []),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameYieldSharingEnabled = Property(
        bool,
        lambda self: bool(getattr(
            self, "_edframe_yield_sharing_enabled", False
        )),
        notify=CoreControllerMixin.connectionChanged,
    )

    edFrameSignalSharingEnabled = Property(
        bool, lambda self: bool(getattr(self, "_edframe_signal_sharing_enabled", False)),
        notify=CoreControllerMixin.connectionChanged,
    )
    edFrameSignalUploadStatus = Property(
        str, lambda self: str(getattr(self, "_edframe_signal_upload_status", "")),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameStationPriceSharingEnabled = Property(
        bool,
        lambda self: bool(getattr(
            self, "_edframe_station_price_sharing_enabled", False
        )),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameStationPriceUploadBusy = Property(
        bool,
        lambda self: bool(getattr(
            self, "_edframe_station_price_upload_busy", False
        )),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameStationPriceUploadStatus = Property(
        str,
        lambda self: str(getattr(
            self, "_edframe_station_price_upload_status",
            "Off · observed ship prices remain local",
        )),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameYieldUploadBusy = Property(
        bool,
        lambda self: bool(getattr(
            self, "_edframe_yield_upload_busy", False
        )),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameYieldUploadStatus = Property(
        str,
        lambda self: str(getattr(
            self, "_edframe_yield_upload_status",
            "Off · measurements remain local",
        )),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameCatalogSyncBusy = Property(
        bool,
        lambda self: bool(getattr(self, "_edframe_catalog_sync_busy", False)),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameCatalogSyncStatus = Property(
        str,
        lambda self: str(getattr(
            self, "_edframe_catalog_sync_status",
            "Local catalog waiting for server check",
        )),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameStationOfferSyncBusy = Property(
        bool,
        lambda self: bool(getattr(
            self, "_edframe_station_offer_sync_busy", False
        )),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameStationOfferSyncStatus = Property(
        str,
        lambda self: str(getattr(
            self, "_edframe_station_offer_sync_status",
            "Station offers waiting for server check",
        )),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameStateFindSyncBusy = Property(
        bool,
        lambda self: bool(getattr(
            self, "_edframe_state_find_sync_busy", False
        )),
        notify=CoreControllerMixin.connectionChanged,
    )


    edFrameStateFindSyncStatus = Property(
        str,
        lambda self: str(getattr(
            self, "_edframe_state_find_sync_status",
            "State Finds waiting for server check",
        )),
        notify=CoreControllerMixin.connectionChanged,
    )


    miningCurrentAction = Property(
        str,
        lambda self: (
            "YIELD SHARE"
            if getattr(self, "_edframe_yield_upload_busy", False)
            else "SERVER CHECK"
            if getattr(self, "_edframe_catalog_busy", False)
            else "CATALOG SYNC"
            if getattr(self, "_edframe_catalog_sync_busy", False)
            else "STATION SYNC"
            if getattr(self, "_edframe_station_offer_sync_busy", False)
            else "STATE SYNC"
            if getattr(self, "_edframe_state_find_sync_busy", False)
            else "MARKET SYNC"
            if getattr(self, "_mining_market_busy", False)
            else "ROUTE CHECK"
            if getattr(self, "_mining_verification_busy", False)
            else "RING SYNC"
            if getattr(self, "_mining_sync_busy", False)
            else "READY"
        ),
        notify=miningChanged,
    )


    edmcParallelStatus = Property(
        "QVariantMap", lambda self: self._edmc_parallel_status(),
        notify=CoreControllerMixin.connectionChanged,
    )


    traderSyncBusy = Property(
        bool, lambda self: self._trader_sync_busy, notify=CoreControllerMixin.connectionChanged,
    )


    traderSyncStatus = Property(
        str, lambda self: self._trader_sync_status, notify=CoreControllerMixin.connectionChanged,
    )


    spanshCatalogSyncBusy = Property(
        bool,
        lambda self: (
            getattr(self, "_trader_sync_busy", False)
            or getattr(self, "_tech_broker_sync_busy", False)
            or getattr(self, "_mining_sync_busy", False)
        ),
        notify=CoreControllerMixin.connectionChanged,
    )


    spanshCatalogSyncStatus = Property(
        str,
        lambda self: (
            f"MATERIAL TRADERS · {self._trader_sync_status}\n"
            f"TECH BROKERS · {self._tech_broker_sync_status}\n"
            f"MINING RINGS · {getattr(self, '_mining_sync_status', 'Ready')}"
        ),
        notify=CoreControllerMixin.connectionChanged,
    )


    miningPowerplaySyncBusy = Property(
        bool,
        lambda self: getattr(self, "_mining_powerplay_busy", False),
        notify=CoreControllerMixin.connectionChanged,
    )


    miningPowerplaySyncStatus = Property(
        str,
        lambda self: getattr(self, "_mining_powerplay_status", "Ready"),
        notify=CoreControllerMixin.connectionChanged,
    )


    miningPowerplayLastRefresh = Property(
        str,
        lambda self: str(
            getattr(self, "_mining_powerplay_catalog", {}).get("fetchedAt") or ""
        ),
        notify=CoreControllerMixin.connectionChanged,
    )


    miningPowerplaySystemCount = Property(
        int,
        lambda self: len(
            getattr(self, "_mining_powerplay_catalog", {}).get("systems") or []
        ),
        notify=CoreControllerMixin.connectionChanged,
    )


    spanshAutoRefresh = Property(
        bool, lambda self: getattr(self, "_spansh_auto_refresh", False),
        notify=CoreControllerMixin.uiChanged,
    )


    spanshAutoRefreshHours = Property(
        int, lambda self: getattr(self, "_spansh_auto_refresh_hours", 24),
        notify=CoreControllerMixin.uiChanged,
    )


    spanshLastRefresh = Property(
        str, lambda self: getattr(self, "_spansh_last_refresh", ""),
        notify=CoreControllerMixin.uiChanged,
    )


    hgeTargets = Property(
        "QVariantList", lambda self: self._hge_targets(),
        notify=CoreControllerMixin.hgeChanged,
    )


    hgeFinderRows = Property(
        "QVariantList", lambda self: self._hge_finder_rows(),
        notify=CoreControllerMixin.hgeChanged,
    )


    hgeCandidateRows = Property(
        "QVariantList", lambda self: self._hge_candidate_rows(),
        notify=CoreControllerMixin.hgeChanged,
    )


    hgeUnverifiedSummary = Property(
        "QVariantMap",
        lambda self: recent_unverified_hge_summary(self._hge_sightings),
        notify=CoreControllerMixin.hgeChanged,
    )


    traderPreference = Property(
        str, lambda self: self._trader_preference, notify=CoreControllerMixin.uiChanged,
    )


    @Slot()
    def updateSpanshCatalogs(self):
        """Refresh only catalogs sourced from the Spansh APIs."""
        if (
            getattr(self, "_trader_sync_busy", False)
            or getattr(self, "_tech_broker_sync_busy", False)
            or getattr(self, "_mining_sync_busy", False)
        ):
            return
        if hasattr(self, "_spansh_auto_refresh"):
            self._spansh_last_refresh = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
            self._save_ui_config()
        self.updateTraderCatalog()
        self.updateTechBrokerCatalog()
        if (
            hasattr(self, "_mining_sync_busy")
            and self._state.get("currentSystemAddress")
        ):
            self.refreshMiningFinder()


    @Slot()
    def refreshMiningPowerplayCatalog(self):
        """Refresh the small daily catalog used for provable merit routes."""
        if getattr(self, "_mining_powerplay_busy", False):
            return
        if powerplay_catalog_is_fresh(
            getattr(self, "_mining_powerplay_catalog", {}), max_age_hours=6,
        ):
            self._mining_powerplay_status = "Daily catalog is already current"
            self.connectionChanged.emit()
            return
        request = {
            "id": uuid.uuid4().hex,
            "profileKey": self.profile_context.key,
            "generation": self._profile_generation,
            "path": str(self.mining_powerplay_catalog_file),
        }
        self._active_mining_powerplay_request = request
        self._mining_powerplay_busy = True
        self._mining_powerplay_status = "Refreshing anonymous daily catalog…"
        self.connectionChanged.emit()

        def worker():
            result = dict(request)
            try:
                result["catalog"] = fetch_powerplay_catalog(get=requests.get)
                result["success"] = True
            except Exception as exc:
                result.update({"success": False, "error": str(exc)})
            self.miningPowerplayFinished.emit(result)

        if not self._start_network_worker(worker, "mining-powerplay-sync"):
            self._active_mining_powerplay_request = None
            self._mining_powerplay_busy = False
            self._mining_powerplay_status = "Powerplay catalog unavailable during shutdown"
            self.connectionChanged.emit()


    @Slot(object)
    def _finish_mining_powerplay_sync(self, result):
        request = getattr(self, "_active_mining_powerplay_request", None)
        if not request or result.get("id") != request.get("id"):
            return
        self._active_mining_powerplay_request = None
        self._mining_powerplay_busy = False
        if not (
            result.get("profileKey") == self.profile_context.key
            and result.get("generation") == self._profile_generation
            and result.get("path") == str(self.mining_powerplay_catalog_file)
        ):
            self._mining_powerplay_status = "Discarded stale profile response"
            self.connectionChanged.emit()
            return
        if not result.get("success"):
            self._mining_powerplay_status = (
                "Catalog refresh failed · cached data retained · "
                + str(result.get("error") or "unknown error")
            )
            self.connectionChanged.emit()
            return
        catalog = result.get("catalog")
        if not isinstance(catalog, dict):
            self._mining_powerplay_status = "Catalog refresh returned invalid data"
            self.connectionChanged.emit()
            return
        self._mining_powerplay_catalog = catalog
        self._save_mining_json(self.mining_powerplay_catalog_file, catalog)
        count = len(catalog.get("systems") or [])
        self._mining_powerplay_status = f"EDSM daily · {count} Powerplay system links"
        self._mining_market_revision += 1
        self.miningChanged.emit()
        self.connectionChanged.emit()
        self.stateChanged.emit()


    @Slot(bool, int)
    def setSpanshAutoRefresh(self, enabled, hours):
        self._spansh_auto_refresh = bool(enabled)
        requested = int(hours or 24)
        self._spansh_auto_refresh_hours = (
            requested if requested in {6, 12, 24, 48} else 24
        )
        self._save_ui_config()
        self.uiChanged.emit()
        if self._spansh_auto_refresh:
            self._maybe_auto_refresh_spansh()


    def _append_edframe_catalog_log(self, message):
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        entries = list(getattr(self, "_edframe_catalog_log", []) or [])
        entries.insert(0, f"{stamp} · {str(message or '').strip()}")
        self._edframe_catalog_log = entries[:20]


    @Slot(bool)
    def setEdFrameCatalogEnabled(self, enabled):
        enabled = bool(enabled)
        if enabled == getattr(self, "_edframe_catalog_enabled", True):
            if enabled:
                self.refreshEdFrameCatalogStatus()
            return
        self._edframe_catalog_enabled = enabled
        self._active_edframe_catalog_request = None
        self._edframe_catalog_busy = False
        self._active_edframe_catalog_sync_request = None
        self._edframe_catalog_sync_busy = False
        self._edframe_catalog_sync_continue = False
        self._active_edframe_station_offer_sync_request = None
        self._edframe_station_offer_sync_busy = False
        self._edframe_station_offer_sync_continue = False
        self._active_edframe_state_find_sync_request = None
        self._edframe_state_find_sync_busy = False
        self._edframe_state_find_sync_continue = False
        self._edframe_catalog_online = False
        if enabled:
            self._edframe_catalog_status = "Enabled · checking server…"
            self._append_edframe_catalog_log("Online catalog enabled")
        else:
            self._edframe_catalog_status = "Disabled · local catalog active"
            self._edframe_catalog_sync_status = (
                "Paused · retained local catalog remains available"
            )
            self._edframe_station_offer_sync_status = (
                "Paused · retained local station offers remain available"
            )
            self._edframe_state_find_sync_status = (
                "Paused · retained local State Finds remain available"
            )
            self._append_edframe_catalog_log(
                "Online catalog disabled · retained local data stays available"
            )
        self._save_ui_config()
        self.connectionChanged.emit()
        self.miningChanged.emit()
        if enabled:
            self.refreshEdFrameCatalogStatus()


    @Slot(bool)
    def setEdFrameYieldSharingEnabled(self, enabled):
        enabled = bool(enabled)
        self._edframe_yield_sharing_enabled = enabled
        if enabled:
            self._edframe_yield_upload_status = (
                "Ready · checking local Prospector measurements…"
            )
            self._append_edframe_catalog_log(
                "Anonymous Prospector yield sharing enabled"
            )
        else:
            self._active_edframe_yield_upload = None
            self._edframe_yield_upload_busy = False
            self._edframe_yield_upload_status = (
                "Off · measurements remain local"
            )
            self._append_edframe_catalog_log(
                "Prospector yield sharing disabled · local measurements retained"
            )
        self._save_ui_config()
        self.connectionChanged.emit()
        if enabled:
            self._maybe_share_mining_yields()


    @Slot(bool)
    def setEdFrameStationPriceSharingEnabled(self, enabled):
        self._edframe_station_price_sharing_enabled = bool(enabled)
        self._edframe_station_price_upload_status = (
            "Ready · checking Outfitting and future ship purchases…"
            if enabled else "Off · module prices and ship purchases remain local"
        )
        self._append_edframe_catalog_log(
            "Anonymous module prices and confirmed ship purchases enabled"
            if enabled else
            "Module prices and ship purchases disabled · data stays local"
        )
        self._save_ui_config()
        self.connectionChanged.emit()
        if enabled:
            self._scan_local_shipyard_price_file()


    @Slot(object)
    def _finish_edframe_station_price_upload(self, result):
        key = str((result or {}).get("key") or "")
        if key != str(getattr(
            self, "_active_edframe_station_price_upload", ""
        ) or ""):
            return
        self._active_edframe_station_price_upload = None
        self._edframe_station_price_upload_busy = False
        if not getattr(self, "_edframe_station_price_sharing_enabled", False):
            return
        if not result.get("success"):
            error = str(result.get("error") or "unknown error")
            self._edframe_station_price_next_retry_at = time.monotonic() + 60.0
            self._edframe_station_price_upload_status = (
                "Upload paused · prices retained locally · " + error
            )
            self._append_edframe_catalog_log(
                "Station price upload failed · " + error
            )
            self.connectionChanged.emit()
            return
        accepted = int(
            (result.get("response") or {}).get("accepted", 0) or 0
        )
        sent = int(result.get("sent", 0) or 0)
        if sent > 0 and accepted == sent:
            self._edframe_station_price_last_key = key
            self._edframe_station_price_upload_status = (
                "Shared latest anonymous module prices or ship purchase"
            )
            self._append_edframe_catalog_log(
                f"Shared {accepted} observed station price list(s)"
            )
            self._save_ui_config()
        else:
            self._edframe_station_price_upload_status = (
                "Server did not accept every station price list · retained locally"
            )
        self.connectionChanged.emit()
        pending = getattr(
            self, "_pending_edframe_station_price_observation", None
        )
        self._pending_edframe_station_price_observation = None
        if pending and pending[0] != self._edframe_station_price_last_key:
            self._start_edframe_station_price_upload(*pending)


    @Slot(bool)
    def setEdFrameSignalSharingEnabled(self, enabled):
        self._edframe_signal_sharing_enabled = bool(enabled)
        self._edframe_signal_upload_status = "Enabled" if enabled else "Disabled"
        self._save_ui_config()
        self.connectionChanged.emit()
        if enabled:
            self._maybe_share_state_signals()

    def _maybe_share_state_signals(self):
        if (not getattr(self, "_edframe_signal_sharing_enabled", False)
                or getattr(self, "_edframe_signal_upload_busy", False)
                or getattr(self, "_shutdown_complete", False)
                or time.monotonic() < getattr(self, "_edframe_signal_next_upload_at", 0)):
            return
        from ed_companion.navigation.signal_sharing import public_signal_observations, signal_observation_key, send_signal_observations
        snapshot = self._state.get("localHgeSightings", [])
        if not snapshot:
            return
        generation = self._profile_generation
        known = set(getattr(self, "_edframe_signal_uploaded", set()))
        self._edframe_signal_upload_busy = True
        self._edframe_signal_next_upload_at = time.monotonic() + 60

        def worker():
            result = {"generation": generation, "keys": []}
            try:
                public = public_signal_observations(snapshot)
                pending = {signal_observation_key(row): row for row in public
                           if signal_observation_key(row) not in known}
                if (pending and self._edframe_signal_sharing_enabled
                        and self._profile_generation == generation
                        and not getattr(self, "_shutdown_complete", False)):
                    send_signal_observations(list(pending.values()), requests.post)
                    result["keys"] = list(pending)
                result["success"] = True
            except Exception:
                result["success"] = False
            self.edFrameSignalUploadFinished.emit(result)
        if not self._start_network_worker(worker, "edframe-signal-upload"):
            self._edframe_signal_upload_busy = False

    @Slot(object)
    def _finish_edframe_signal_upload(self, result):
        if result.get("generation") != self._profile_generation:
            return
        self._edframe_signal_upload_busy = False
        if not getattr(self, "_edframe_signal_sharing_enabled", False):
            return
        if result.get("success"):
            known = getattr(self, "_edframe_signal_uploaded", set())
            known.update(result.get("keys", []))
            self._edframe_signal_uploaded = set(sorted(known)[-2000:])
            self._edframe_signal_upload_status = "Shared" if result.get("keys") else "Ready"
        else:
            self._edframe_signal_upload_status = "Retry pending"
        self.connectionChanged.emit()
        QTimer.singleShot(60000, self._maybe_share_state_signals)

    def _maybe_share_mining_yields(self):
        if (
            not getattr(self, "_edframe_yield_sharing_enabled", False)
            or getattr(self, "_edframe_yield_upload_busy", False)
            or getattr(self, "_shutdown_complete", False)
        ):
            return
        local = self._state.get("localMiningEvidence", {})
        if not isinstance(local, dict) or not local.get("prospectorSamples"):
            self._edframe_yield_upload_status = (
                "Ready · no ring-bound Prospector measurements yet"
            )
            self.connectionChanged.emit()
            return
        request = {
            "id": uuid.uuid4().hex,
            "profileKey": self.profile_context.key,
            "generation": self._profile_generation,
            "receiptsPath": str(self.edframe_yield_receipts_file),
        }
        # State replacement is atomic and the published mapping is no longer
        # mutated.  Capture that immutable snapshot by reference so a large
        # Journal history is never copied on the Qt/UI thread.
        local_snapshot = local
        uploaded = set(getattr(self, "_edframe_yield_uploaded", set()))
        self._active_edframe_yield_upload = request
        self._edframe_yield_upload_busy = True
        self._edframe_yield_upload_status = (
            "Preparing anonymous Prospector measurements…"
        )
        self.connectionChanged.emit()

        def worker():
            result = dict(request)
            try:
                observations = project_local_yield_observations(
                    local_snapshot, exclude_keys=uploaded, limit=100,
                )
                pending = []
                batch_keys = set()
                for row in observations:
                    key = yield_observation_key(row)
                    if key in batch_keys:
                        continue
                    batch_keys.add(key)
                    pending.append((key, row))
                if not pending:
                    result.update({
                        "success": True, "empty": True,
                        "keys": [], "response": {"accepted": 0},
                    })
                else:
                    response = send_edframe_yield_observations(
                        [row for _key, row in pending], requests.post,
                    )
                    result.update({
                        "success": True,
                        "keys": [key for key, _row in pending],
                        "response": response,
                    })
            except Exception as exc:
                result.update({"success": False, "error": str(exc)})
            self.edFrameYieldUploadFinished.emit(result)

        if not self._start_network_worker(worker, "edframe-yield-upload"):
            self._active_edframe_yield_upload = None
            self._edframe_yield_upload_busy = False
            self._edframe_yield_upload_status = (
                "Paused during shutdown · measurements retained locally"
            )
            self.connectionChanged.emit()


    @Slot(object)
    def _finish_edframe_yield_upload(self, result):
        request = getattr(self, "_active_edframe_yield_upload", None)
        if not request or result.get("id") != request.get("id"):
            return
        self._active_edframe_yield_upload = None
        self._edframe_yield_upload_busy = False
        if not getattr(self, "_edframe_yield_sharing_enabled", False):
            return
        if not (
            result.get("profileKey") == self.profile_context.key
            and result.get("generation") == self._profile_generation
            and result.get("receiptsPath")
                == str(self.edframe_yield_receipts_file)
        ):
            self._edframe_yield_upload_status = (
                "Discarded stale profile upload response"
            )
            self.connectionChanged.emit()
            return
        if not result.get("success"):
            error = str(result.get("error") or "unknown error")
            self._edframe_yield_upload_status = (
                "Upload paused · local measurements retained · " + error
            )
            self._append_edframe_catalog_log(
                "Prospector yield upload failed · " + error
            )
            self.connectionChanged.emit()
            return
        keys = list(result.get("keys") or [])
        accepted = int(
            (result.get("response") or {}).get("accepted", 0) or 0
        )
        if keys and accepted == len(keys):
            self._edframe_yield_uploaded.update(keys)
            retained = sorted(self._edframe_yield_uploaded)
            self._persist_json(
                self.edframe_yield_receipts_file,
                {"uploaded": retained, "updatedAt": datetime.now(
                    timezone.utc
                ).isoformat(timespec="seconds")},
                "ED-Frame yield upload receipts",
            )
            self._edframe_yield_upload_status = (
                f"Shared {accepted} anonymous measurements · checking backlog"
            )
            self._append_edframe_catalog_log(
                f"Shared {accepted} anonymous Prospector measurements"
            )
            self.connectionChanged.emit()
            QTimer.singleShot(6000, self._maybe_share_mining_yields)
            return
        if keys:
            self._edframe_yield_upload_status = (
                "Server accepted only part of the batch · retained for retry"
            )
        else:
            self._edframe_yield_upload_status = (
                f"Up to date · {len(self._edframe_yield_uploaded):,} "
                "measurements shared"
            )
        self.connectionChanged.emit()


    @Slot()
    def refreshEdFrameCatalogStatus(self):
        if not getattr(self, "_edframe_catalog_enabled", True):
            self._edframe_catalog_status = "Disabled · local catalog active"
            self.connectionChanged.emit()
            self.miningChanged.emit()
            return
        if getattr(self, "_edframe_catalog_busy", False):
            return
        request = {"id": uuid.uuid4().hex}
        self._active_edframe_catalog_request = request
        self._edframe_catalog_busy = True
        self._edframe_catalog_status = "Checking server… · local catalog remains active"
        self.connectionChanged.emit()
        self.miningChanged.emit()

        def worker():
            try:
                health = fetch_edframe_catalog_health(
                    get=requests.get,
                )
            except Exception as exc:
                self.edFrameCatalogStatusFinished.emit({
                    **request,
                    "phase": "health",
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                return
            self.edFrameCatalogStatusFinished.emit({
                **request,
                "phase": "health",
                "success": True,
                "health": health,
            })
            try:
                status = fetch_edframe_catalog_status(get=requests.get)
                result = {
                    **request, "phase": "status", "success": True,
                    "status": status,
                }
            except Exception as exc:
                result = {
                    **request, "phase": "status", "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            self.edFrameCatalogStatusFinished.emit(result)

        if not self._start_network_worker(worker, "edframe-catalog-status"):
            self._active_edframe_catalog_request = None
            self._edframe_catalog_busy = False
            self._edframe_catalog_status = (
                "Unavailable during shutdown · local catalog active"
            )
            self.connectionChanged.emit()
            self.miningChanged.emit()


    def _record_catalog_source_result(self, source, *, success, error=""):
        """Small SQLite writes can still wait behind a large import: never
        acquire the writer lock from a production GUI completion callback.
        """
        store = getattr(self, "_mining_market_store", None)
        if store is None:
            return
        generation = getattr(self, "_profile_generation", 0)
        store_generation = getattr(store, "_store_generation", 0)

        def write():
            # Serialize with store reset, but on this tracked worker only.
            with getattr(store, "_lock", threading.RLock()):
                if (getattr(self, "_mining_market_store", None) is not store
                        or generation != getattr(self, "_profile_generation", 0)
                        or store_generation != getattr(store, "_store_generation", 0)
                        or not getattr(self, "_edframe_catalog_enabled", True)):
                    return
                try:
                    store.record_source_result(source, success=success, error=error)
                except (OSError, sqlite3.DatabaseError):
                    LOGGER.exception("Catalog source status could not be saved")

        if hasattr(self, "_network_threads_lock"):
            self._start_network_worker(write, "catalog-source-status")
        else:
            write()  # Lightweight/headless callers have no GUI event loop.


    @Slot(object)
    def _finish_edframe_catalog_status(self, result):
        request = getattr(self, "_active_edframe_catalog_request", None)
        if not request or result.get("id") != request.get("id"):
            return
        phase = str(result.get("phase") or "status")
        if not getattr(self, "_edframe_catalog_enabled", True):
            self._active_edframe_catalog_request = None
            self._edframe_catalog_busy = False
            return
        store = getattr(self, "_mining_market_store", None)
        if phase == "health" and result.get("success"):
            health = result.get("health") or {}
            self._edframe_catalog_online = True
            self._edframe_catalog_last_success = str(
                health.get("time")
                or datetime.now(timezone.utc).isoformat(timespec="seconds")
            )
            self._edframe_catalog_status = (
                "Online · loading catalog details… · local catalog active"
            )
            self._append_edframe_catalog_log(
                "Server online · loading catalog details"
            )
            if store is not None:
                self._record_catalog_source_result(
                    "ED-Frame catalog server", success=True,
                )
            self.connectionChanged.emit()
            self.miningChanged.emit()
            return

        self._active_edframe_catalog_request = None
        self._edframe_catalog_busy = False
        if not result.get("success"):
            error = str(result.get("error") or "unknown error")
            if phase == "status" and getattr(
                self, "_edframe_catalog_online", False
            ):
                self._edframe_catalog_status = (
                    "Online · catalog details temporarily unavailable · "
                    "local catalog active"
                )
                self._append_edframe_catalog_log(
                    f"Catalog details unavailable · {error}"
                )
            else:
                self._edframe_catalog_online = False
                self._edframe_catalog_status = (
                    "Offline · retained local catalog active"
                )
                self._append_edframe_catalog_log(f"Server unavailable · {error}")
                if store is not None:
                    self._record_catalog_source_result(
                        "ED-Frame catalog server", success=False, error=error,
                    )
        else:
            payload = result.get("status") or {}
            counts = payload.get("counts") or {}
            completeness = payload.get("completeness") or {}
            collector = payload.get("collector") or {}
            intake = payload.get("collector24h") or {}
            systems = int(counts.get("systems", 0) or 0)
            station_catalog_supported = "stations" in counts
            stations = (
                int(counts.get("stations", 0) or 0)
                if station_catalog_supported else -1
            )
            markets = int(counts.get("markets", 0) or 0)
            sites = int(counts.get("sites", 0) or 0)
            state_bgs = int(counts.get(
                "state_bgs_snapshots", counts.get("stateBgsSnapshots", 0)
            ) or 0)
            state_signals = int(counts.get(
                "state_signals", counts.get("stateSignals", 0)
            ) or 0)
            outfitting_stations = int(counts.get(
                "outfitting_stations", counts.get("outfittingStations", 0)
            ) or 0)
            shipyard_stations = int(counts.get(
                "shipyard_stations", counts.get("shipyardStations", 0)
            ) or 0)
            self._edframe_catalog_online = True
            self._edframe_catalog_last_success = str(
                payload.get("generatedAt")
                or datetime.now(timezone.utc).isoformat(timespec="seconds")
            )
            self._edframe_catalog_stats = {
                "freshMarkets1h": completeness.get("freshMarkets1h"),
                "freshMarkets24h": completeness.get("freshMarkets24h"),
                "collector24hMessages": intake.get("messages"),
                "collector24hUsedPercent": intake.get("usedPercent"),
                "collector24hErrors": intake.get("errors"),
                "systems": systems,
                "stations": stations,
                "markets": markets,
                "sites": sites,
                "yieldSamples": int(counts.get(
                    "yield_samples", counts.get("yieldSamples", 0)
                ) or 0),
                "measuredSites": int(counts.get(
                    "measured_sites", counts.get("measuredSites", 0)
                ) or 0),
                "measuredCommodities": int(counts.get(
                    "measured_commodities",
                    counts.get("measuredCommodities", 0),
                ) or 0),
                "stateBgsSnapshots": state_bgs,
                "stateSignals": state_signals,
                "stateSightings": counts.get("state_signal_sightings"),
                "outfittingStations": outfitting_stations,
                "shipyardStations": shipyard_stations,
                "moduleOffers": int(counts.get(
                    "module_offers", counts.get("moduleOffers", 0)
                ) or 0),
                "pricedModuleOffers": int(counts.get(
                    "priced_module_offers",
                    counts.get("pricedModuleOffers", 0),
                ) or 0),
                "shipOffers": int(counts.get(
                    "ship_offers", counts.get("shipOffers", 0)
                ) or 0),
                "pricedShipOffers": int(counts.get(
                    "priced_ship_offers", counts.get("pricedShipOffers", 0)
                ) or 0),
                "catalogModules": int(counts.get(
                    "catalog_modules", counts.get("catalogModules", 0)
                ) or 0),
                "catalogShips": int(counts.get(
                    "catalog_ships", counts.get("catalogShips", 0)
                ) or 0),
                "commodities": int(counts.get("commodities", 0) or 0),
                "marketCoordinatePercent": float(
                    completeness.get("marketCoordinatePercent", 0) or 0
                ),
                "marketDetailPercent": float(
                    completeness.get("marketDetailPercent", 0) or 0
                ),
                "stationTypePercent": float(
                    completeness.get("stationTypePercent", 0) or 0
                ),
                "stationLandingPadPercent": float(
                    completeness.get("stationLandingPadPercent", 0) or 0
                ),
                "stationServicesPercent": float(
                    completeness.get("stationServicesPercent", 0) or 0
                ),
                "siteCoordinatePercent": float(
                    completeness.get("siteCoordinatePercent", 0) or 0
                ),
                "siteHotspotPercent": float(
                    completeness.get("siteHotspotPercent", 0) or 0
                ),
                "collectorMessages": int(
                    collector.get("messages_total",
                                  collector.get("messages_seen", 0)) or 0
                ),
                "collectorErrors": int(
                    collector.get("errors_total", collector.get("errors", 0)) or 0
                ),
            }
            if not station_catalog_supported:
                self._edframe_catalog_stats.update({
                    "stationTypePercent": -1,
                    "stationLandingPadPercent": -1,
                    "stationServicesPercent": -1,
                })
            station_status = (
                f"{stations:,} stations"
                if station_catalog_supported
                else "station catalog pending server update"
            )
            self._edframe_catalog_status = (
                f"Online · {systems:,} systems · {station_status} · "
                f"{markets:,} markets · {sites:,} mining sites"
            )
            self._append_edframe_catalog_log(
                f"Server online · {stations:,} stations · "
                f"{markets:,} markets · {sites:,} sites · "
                f"{state_bgs:,} BGS · {state_signals:,} signals · "
                f"{outfitting_stations:,} outfitting · "
                f"{shipyard_stations:,} shipyards"
            )
            if store is not None:
                self._record_catalog_source_result(
                    "ED-Frame catalog server", success=True,
                )
            self._save_ui_config()
        self.connectionChanged.emit()
        self.miningChanged.emit()
        if phase == "status" and result.get("success") and store is not None:
            QTimer.singleShot(0, self.syncEdFrameCatalog)
            QTimer.singleShot(0, self.syncEdFrameStationOffers)
        if phase == "status" and result.get("success"):
            state_sync = getattr(self, "syncEdFrameStateFinds", None)
            if callable(state_sync):
                QTimer.singleShot(0, state_sync)


    @Slot()
    def syncEdFrameCatalog(self):
        """Incrementally merge the server catalog into profile-local SQLite."""
        if (
            not getattr(self, "_edframe_catalog_enabled", True)
            or getattr(self, "_shutdown_complete", False)
            or getattr(self, "_edframe_catalog_sync_busy", False)
        ):
            return
        store = getattr(self, "_mining_market_store", None)
        if store is None:
            return
        cursor = store.metadata("edframe_market_sync_cursor", "")
        continuing = bool(getattr(
            self, "_edframe_catalog_sync_continue", False,
        ))
        self._edframe_catalog_sync_continue = False
        if not continuing:
            self._edframe_catalog_sync_rows = 0
        request = {
            "id": uuid.uuid4().hex,
            "cursor": cursor,
            "generation": getattr(self, "_profile_generation", 0),
        }
        self._active_edframe_catalog_sync_request = request
        self._edframe_catalog_sync_busy = True
        if not cursor:
            self._edframe_catalog_sync_status = (
                "Initial incremental sync · retained local data stays active"
            )
        else:
            self._edframe_catalog_sync_status = (
                "Checking for market and station changes…"
            )
        self.connectionChanged.emit()
        self.miningChanged.emit()

        def worker():
            result = dict(request)
            try:
                page = fetch_edframe_market_delta(
                    cursor=cursor, get=requests.get,
                )
                result.update(_merge_edframe_market_delta_page(store, page))
                result["success"] = True
            except Exception as exc:
                result.update({
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                })
            self.edFrameCatalogSyncFinished.emit(result)

        if not self._start_network_worker(worker, "edframe-catalog-sync"):
            self._active_edframe_catalog_sync_request = None
            self._edframe_catalog_sync_busy = False
            self._edframe_catalog_sync_status = (
                "Paused during shutdown · retained local catalog active"
            )
            self.connectionChanged.emit()
            self.miningChanged.emit()


    @Slot(object)
    def _finish_edframe_catalog_sync(self, result):
        request = getattr(self, "_active_edframe_catalog_sync_request", None)
        if not request or result.get("id") != request.get("id"):
            return
        self._active_edframe_catalog_sync_request = None
        self._edframe_catalog_sync_busy = False
        if (
            not getattr(self, "_edframe_catalog_enabled", True)
            or result.get("generation") != getattr(self, "_profile_generation", 0)
        ):
            return
        store = getattr(self, "_mining_market_store", None)
        if store is None:
            return
        if not result.get("success"):
            error = str(result.get("error") or "unknown error")
            self._edframe_catalog_sync_status = (
                "Sync paused · retained local catalog active"
            )
            self._record_catalog_source_result(
                "ED-Frame incremental sync", success=False, error=error,
            )
            self._append_edframe_catalog_log(f"Incremental sync paused · {error}")
            self.connectionChanged.emit()
            self.miningChanged.emit()
            return
        ingested = int(result.get("ingested", 0) or 0)
        self._edframe_catalog_sync_rows = int(getattr(
            self, "_edframe_catalog_sync_rows", 0,
        ) or 0) + ingested
        local_count = int(result.get("localCount", 0) or 0)
        self._edframe_catalog_stats.update({
            "localMarkets": local_count,
            "lastSyncRows": self._edframe_catalog_sync_rows,
        })
        if ingested:
            self._mining_market_revision = getattr(
                self, "_mining_market_revision", 0,
            ) + 1
            self._mining_market_status = self._mining_market_cache_status(retained=local_count)
        if result.get("hasMore"):
            self._edframe_catalog_sync_status = (
                f"Syncing · {self._edframe_catalog_sync_rows:,} changes retained · "
                f"{local_count:,} local markets"
            )
            self.connectionChanged.emit()
            self.miningChanged.emit()
            self._edframe_catalog_sync_continue = True
            QTimer.singleShot(75, self.syncEdFrameCatalog)
            return
        self._record_catalog_source_result(
            "ED-Frame incremental sync", success=True,
        )
        backup_ok = (
            self._schedule_mining_market_backup()
            if self._edframe_catalog_sync_rows else True
        )
        self._edframe_catalog_sync_status = (
            f"Up to date · {local_count:,} local markets · "
            f"{self._edframe_catalog_sync_rows:,} changes merged"
        )
        if not backup_ok:
            self._edframe_catalog_sync_status += " · backup retry pending"
        self._append_edframe_catalog_log(
            f"Offline catalog current · {local_count:,} markets"
        )
        self.connectionChanged.emit()
        self.miningChanged.emit()


    @Slot()
    def syncEdFrameStationOffers(self):
        """Incrementally retain public outfitting and shipyard inventories."""
        if (
            not getattr(self, "_edframe_catalog_enabled", True)
            or getattr(self, "_shutdown_complete", False)
            or getattr(self, "_edframe_station_offer_sync_busy", False)
        ):
            return
        store = getattr(self, "_mining_market_store", None)
        if store is None:
            return
        cursor = store.metadata("edframe_station_offer_sync_cursor", "")
        continuing = bool(getattr(
            self, "_edframe_station_offer_sync_continue", False
        ))
        self._edframe_station_offer_sync_continue = False
        if not continuing:
            self._edframe_station_offer_sync_rows = 0
        request = {
            "id": uuid.uuid4().hex,
            "cursor": cursor,
            "generation": getattr(self, "_profile_generation", 0),
        }
        self._active_edframe_station_offer_sync_request = request
        self._edframe_station_offer_sync_busy = True
        self._edframe_station_offer_sync_status = (
            "Initial station offer sync…" if not cursor
            else "Checking outfitting and shipyard changes…"
        )
        self.connectionChanged.emit()
        self.miningChanged.emit()

        def worker():
            result = dict(request)
            try:
                page = fetch_edframe_station_offer_delta(
                    cursor=cursor, get=requests.get,
                )
                result.update(
                    _merge_edframe_station_offer_delta_page(store, page)
                )
                result["success"] = True
            except Exception as exc:
                result.update({
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                })
            self.edFrameStationOfferSyncFinished.emit(result)

        if not self._start_network_worker(worker, "edframe-station-offer-sync"):
            self._active_edframe_station_offer_sync_request = None
            self._edframe_station_offer_sync_busy = False
            self._edframe_station_offer_sync_status = (
                "Paused during shutdown · retained station offers stay active"
            )
            self.connectionChanged.emit()
            self.miningChanged.emit()


    @Slot(object)
    def _finish_edframe_station_offer_sync(self, result):
        request = getattr(
            self, "_active_edframe_station_offer_sync_request", None
        )
        if not request or result.get("id") != request.get("id"):
            return
        self._active_edframe_station_offer_sync_request = None
        self._edframe_station_offer_sync_busy = False
        if (
            not getattr(self, "_edframe_catalog_enabled", True)
            or result.get("generation") != getattr(self, "_profile_generation", 0)
        ):
            return
        store = getattr(self, "_mining_market_store", None)
        if store is None:
            return
        if not result.get("success"):
            error = str(result.get("error") or "unknown error")
            self._edframe_station_offer_sync_status = (
                "Sync paused · retained local station offers remain active"
            )
            self._record_catalog_source_result(
                "ED-Frame station offer sync", success=False, error=error,
            )
            self._append_edframe_catalog_log(
                f"Station offer sync paused · {error}"
            )
            self.connectionChanged.emit()
            self.miningChanged.emit()
            return
        ingested = int(result.get("ingested", 0) or 0)
        self._edframe_station_offer_sync_rows = int(getattr(
            self, "_edframe_station_offer_sync_rows", 0
        ) or 0) + ingested
        summary = dict(result.get("localSummary") or {})
        self._edframe_catalog_stats.update({
            "localOfferStations": int(summary.get("stations", 0) or 0),
            "localOutfittingStations": int(
                summary.get("outfittingStations", 0) or 0
            ),
            "localShipyardStations": int(
                summary.get("shipyardStations", 0) or 0
            ),
        })
        if result.get("hasMore"):
            self._edframe_station_offer_sync_status = (
                f"Syncing · {self._edframe_station_offer_sync_rows:,} "
                "inventories merged"
            )
            self.connectionChanged.emit()
            self.miningChanged.emit()
            self._edframe_station_offer_sync_continue = True
            QTimer.singleShot(75, self.syncEdFrameStationOffers)
            return
        self._record_catalog_source_result(
            "ED-Frame station offer sync", success=True,
        )
        backup_ok = (
            self._schedule_mining_market_backup()
            if self._edframe_station_offer_sync_rows else True
        )
        self._edframe_station_offer_sync_status = (
            f"Up to date · {int(summary.get('outfittingStations', 0) or 0):,} "
            "outfitting · "
            f"{int(summary.get('shipyardStations', 0) or 0):,} shipyards · "
            f"{self._edframe_station_offer_sync_rows:,} changes merged"
        )
        if not backup_ok:
            self._edframe_station_offer_sync_status += " · backup retry pending"
        self._append_edframe_catalog_log(
            "Station offers current · "
            f"{int(summary.get('stations', 0) or 0):,} local stations"
        )
        self.connectionChanged.emit()
        self.miningChanged.emit()


    @Slot()
    def _maybe_refresh_regional_state_finds(self):
        if (not getattr(self, "_edframe_catalog_enabled", True)
                or getattr(self, "_shutdown_complete", False)
                or getattr(self, "_edframe_state_find_sync_busy", False)):
            return
        region = state_find_region(getattr(self, "_state", {}).get("currentPosition"))
        meta = getattr(self, "_edframe_state_find_sync_meta", {}) or {}
        if not region or meta.get("region") == region:
            return
        remaining = 60 - (time.monotonic() - getattr(self, "_edframe_state_find_started_at", 0))
        if remaining > 0:
            if not getattr(self, "_edframe_state_find_region_retry", False):
                self._edframe_state_find_region_retry = True

                def retry():
                    self._edframe_state_find_region_retry = False
                    self._maybe_refresh_regional_state_finds()

                QTimer.singleShot(max(1, int(remaining * 1000)), retry)
            return
        self.syncEdFrameStateFinds()

    @Slot()
    def syncEdFrameStateFinds(self):
        """Merge one resumable server page into the profile-local cache."""
        if (
            not getattr(self, "_edframe_catalog_enabled", True)
            or getattr(self, "_shutdown_complete", False)
            or getattr(self, "_edframe_state_find_sync_busy", False)
        ):
            return
        meta = getattr(self, "_edframe_state_find_sync_meta", {})
        region = state_find_region(getattr(self, "_state", {}).get("currentPosition"))
        if not region:
            self._edframe_state_find_sync_status = "Waiting for Journal position · retained local State Finds active"
            self.connectionChanged.emit()
            return
        cursor = str(meta.get("cursor") or "") if isinstance(meta, dict) and meta.get("region") == region else ""
        continuing = bool(getattr(
            self, "_edframe_state_find_sync_continue", False
        ))
        self._edframe_state_find_sync_continue = False
        if not continuing:
            self._edframe_state_find_sync_rows = 0
        request = {
            "id": uuid.uuid4().hex,
            "cursor": cursor,
            "region": region,
            "generation": getattr(self, "_profile_generation", 0),
        }
        self._active_edframe_state_find_sync_request = request
        self._edframe_state_find_sync_busy = True
        self._edframe_state_find_started_at = time.monotonic()
        self._edframe_state_find_sync_status = (
            "Loading State Finds within 250 LY…" if not cursor
            else "Checking regional State Finds changes · 250 LY…"
        )
        self.connectionChanged.emit()

        def worker():
            result = dict(request)
            try:
                result["page"] = fetch_edframe_state_find_delta(
                    cursor=cursor, get=requests.get,
                    origin=region["origin"], radius_ly=region["radiusLy"],
                )
                result["success"] = True
            except Exception as exc:
                result.update({
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                })
            self.edFrameStateFindSyncFinished.emit(result)

        if not self._start_network_worker(worker, "edframe-state-find-sync"):
            self._active_edframe_state_find_sync_request = None
            self._edframe_state_find_sync_busy = False
            self._edframe_state_find_sync_status = (
                "Paused during shutdown · retained local State Finds active"
            )
            self.connectionChanged.emit()


    def _dispatch_state_find_storage(self, result):
        """Merge/archive/save a fetched page, keeping Qt busy state until done."""
        existing = self._hge_sightings
        cache_path, meta_path = self.hge_cache_file, self.state_find_sync_file
        archive = getattr(self, "_history_archive", None)
        archive_path = getattr(self, "history_archive_file", None)
        page, region = result["page"], result["region"]
        lock = self._hge_file_lock
        self._hge_save_sequence += 1
        sequence = self._hge_save_sequence
        self._hge_save_sequences[str(cache_path)] = sequence

        def current():
            active = getattr(self, "_active_edframe_state_find_sync_request", None)
            return (bool(active) and active.get("id") == result.get("id")
                    and result.get("generation") == getattr(self, "_profile_generation", 0)
                    and str(self.hge_cache_file) == str(cache_path)
                    and getattr(self, "_edframe_catalog_enabled", True)
                    and region == state_find_region(self._state.get("currentPosition")))

        def worker():
            # A retry must not inherit the previous attempt's rebase flag.
            prepared = {key: value for key, value in result.items()
                        if key not in ("rebase", "prepareBase", "preparedRows",
                                       "preparedStats", "preparedMeta")}
            prepared.update(storagePrepared=True, prepareBase=existing,
                            prepareSequence=sequence, preparePath=str(cache_path))
            try:
                if not current():
                    prepared.update(success=False, error="State Finds context changed")
                    return
                captured_archive = archive
                if captured_archive is None and archive_path is not None:
                    captured_archive = HistoryArchive(archive_path)
                prepared.update(prepare_state_find_page(
                    existing, page, region, limit=HGE_OBSERVATION_LIMIT,
                    archive=captured_archive,
                ))
                with lock:
                    if not current():
                        prepared.update(success=False, error="State Finds context changed")
                        return
                    if (self._hge_sightings is not existing
                            or self._hge_save_sequences.get(str(cache_path)) != sequence):
                        prepared["rebase"] = True
                    else:
                        # Keep the resumable cursor behind the durable facts.
                        if not atomic_write_chunks(cache_path, iter_catalog_json(prepared["preparedRows"])):
                            raise OSError("State Finds cache save failed")
                        if not atomic_write_chunks(meta_path, iter_catalog_json(prepared["preparedMeta"])):
                            raise OSError("State Finds sync cursor save failed")
            except (OSError, sqlite3.DatabaseError, TypeError, ValueError) as exc:
                prepared.update(success=False, error="State Finds storage: " + type(exc).__name__)
                LOGGER.exception("State Finds page storage failed")
            finally:
                # Location/profile changes still need a completion so the GUI
                # releases busy state (or rejects an already replaced request).
                self.edFrameStateFindSyncFinished.emit(prepared)

        self._edframe_state_find_sync_status = "Merging and saving State Finds in background…"
        if not self._start_network_worker(worker, "edframe-state-find-storage"):
            self._active_edframe_state_find_sync_request = None
            self._edframe_state_find_sync_busy = False
            self._edframe_state_find_sync_status = "Storage paused during shutdown · page will be retried"
        self.connectionChanged.emit()


    @Slot(object)
    def _finish_edframe_state_find_sync(self, result):
        request = getattr(
            self, "_active_edframe_state_find_sync_request", None
        )
        if not request or result.get("id") != request.get("id"):
            return
        if (
            not getattr(self, "_edframe_catalog_enabled", True)
            or result.get("generation") != getattr(self, "_profile_generation", 0)
        ):
            self._active_edframe_state_find_sync_request = None
            self._edframe_state_find_sync_busy = False
            return
        region = request.get("region")
        if not region or region != state_find_region(getattr(self, "_state", {}).get("currentPosition")):
            self._active_edframe_state_find_sync_request = None
            self._edframe_state_find_sync_busy = False
            self._edframe_state_find_sync_continue = False
            self._edframe_state_find_sync_status = "Location changed · regional refresh pending; retained local facts active"
            self.connectionChanged.emit()
            self._maybe_refresh_regional_state_finds()
            return
        if result.get("storagePrepared") and result.get("preparePath") != str(self.hge_cache_file):
            result = {**result, "success": False, "error": "State Finds cache path changed"}
        if (result.get("success") and hasattr(self, "_network_threads_lock")
                and (not result.get("storagePrepared") or result.get("rebase")
                     or result.get("prepareBase") is not self._hge_sightings
                     or result.get("prepareSequence") != self._hge_save_sequences.get(str(self.hge_cache_file)))):
            self._dispatch_state_find_storage({**result, "region": region})
            return
        self._active_edframe_state_find_sync_request = None
        self._edframe_state_find_sync_busy = False
        if not result.get("success"):
            error = str(result.get("error") or "unknown error")
            self._edframe_state_find_sync_status = (
                "Sync paused · retained local State Finds active"
            )
            self._append_edframe_catalog_log(f"State Finds sync paused · {error}")
            self.connectionChanged.emit()
            return
        page = result.get("page") or {}
        if result.get("storagePrepared"):
            merged, stats, meta = (result["preparedRows"], result["preparedStats"], result["preparedMeta"])
        else:
            # Headless/legacy direct callers retain their synchronous contract.
            self._finish_legacy_state_find_storage({**result, "region": region})
            return
        self._publish_state_find_page(page, merged, stats, meta)


    def _finish_legacy_state_find_storage(self, result):
        page, region = result.get("page") or {}, result["region"]
        merged, stats = merge_edframe_state_find_page(
            self._hge_sightings, page, limit=None,
        )
        active, historical = partition_hge_observations(merged)
        merged = retain_state_find_region(active, origin=region["origin"], limit=HGE_OBSERVATION_LIMIT)
        retained_ids = {id(row) for row in merged}
        overflow = [row for row in active if id(row) not in retained_ids]
        if (historical or overflow) and not self._archive_history(
            "hge_observations", [*historical, *overflow]
        ):
            self._edframe_state_find_sync_status = (
                "Sync paused · history archive failed; page will be retried"
            )
            self.connectionChanged.emit()
            return
        next_cursor = str(page.get("nextCursor") or "").strip()
        stamp = str(page.get("generatedAt") or "")
        meta = {"cursor": next_cursor, "lastSuccess": stamp, "region": region}
        # The facts are durably written before their cursor. A crash may replay
        # a page, but can never skip a page that was not stored.
        self._hge_save_sequence = int(getattr(
            self, "_hge_save_sequence", 0
        ) or 0) + 1
        self._hge_save_sequences[str(self.hge_cache_file)] = (
            self._hge_save_sequence
        )
        with self._hge_file_lock:
            cache_saved = self._persist_json(
                self.hge_cache_file, merged, "State Finds cache"
            )
        meta_saved = cache_saved and self._persist_json(
            self.state_find_sync_file, meta, "State Finds sync cursor"
        )
        if not meta_saved:
            self._edframe_state_find_sync_status = (
                "Sync paused · local save failed; page will be retried"
            )
            self.connectionChanged.emit()
            return
        self._publish_state_find_page(page, merged, stats, meta)


    def _publish_state_find_page(self, page, merged, stats, meta):
        self._hge_sightings = merged
        self._edframe_state_find_sync_meta = meta
        applied = int(stats.get("snapshotsApplied", 0) or 0) + int(
            stats.get("signalsApplied", 0) or 0
        )
        self._edframe_state_find_sync_rows = int(getattr(
            self, "_edframe_state_find_sync_rows", 0
        ) or 0) + applied
        self.hgeChanged.emit()
        if page.get("hasMore"):
            self._edframe_state_find_sync_status = (
                f"Syncing · {self._edframe_state_find_sync_rows:,} facts merged"
            )
            self.connectionChanged.emit()
            self._edframe_state_find_sync_continue = True
            QTimer.singleShot(75, self.syncEdFrameStateFinds)
            return
        self._edframe_state_find_sync_status = (
            f"Region current · 250 LY · {len(self._hge_sightings):,} retained active facts · "
            f"{self._edframe_state_find_sync_rows:,} changes merged"
        )
        self._append_edframe_catalog_log(
            f"State Finds current · {len(self._hge_sightings):,} active facts"
        )
        self.connectionChanged.emit()


    @Slot()
    def _maybe_auto_refresh_spansh(self):
        if not self._spansh_auto_refresh or self.spanshCatalogSyncBusy:
            return
        position = self._state.get("currentPosition") or []
        address = self._state.get("currentSystemAddress")
        if not isinstance(position, (list, tuple)) or len(position) != 3:
            return
        try:
            if int(address or 0) <= 0:
                return
        except (TypeError, ValueError):
            return
        last = None
        if self._spansh_last_refresh:
            try:
                last = datetime.fromisoformat(
                    self._spansh_last_refresh.replace("Z", "+00:00")
                )
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
            except ValueError:
                last = None
        if last is not None and (
            datetime.now(timezone.utc) - last.astimezone(timezone.utc)
        ).total_seconds() < self._spansh_auto_refresh_hours * 3600:
            return
        self.updateSpanshCatalogs()


    @Slot(str, str, int, int, int, str)
    def refreshMiningMarkets(
        self, start_system, commodity, nearby_ly, min_demand,
        max_market_age_hours, landing_pad,
    ):
        """Refresh verified EDDN-derived sell markets for one user query."""
        query = self._normalized_mining_market_query(
            start_system, commodity, nearby_ly, min_demand,
            max_market_age_hours, landing_pad,
        )
        if not query["startSystem"] or not query["commodity"]:
            self._mining_market_status = (
                "Market lookup needs a start system and commodity"
            )
            self.miningChanged.emit()
            return
        self._remember_mining_warm_targets(query)
        if query["commodity"] == "allcommodities":
            store = getattr(self, "_mining_market_store", None)
            if not self._known_mining_origin(query["startSystem"]):
                origin_query = dict(query)
                origin_query["commodity"] = MINING_MARKET_WARM_COMMODITIES[0]
                self._preempt_mining_market_warming()
                if getattr(self, "_mining_market_busy", False):
                    self._pending_mining_market_query = origin_query
                    self._mining_market_status = (
                        "Resolving start system after the active catalog update"
                    )
                    self.miningChanged.emit()
                else:
                    self._start_mining_market_refresh(
                        origin_query, background=False
                    )
                return
            target = store.next_warm_target() if store is not None else {}
            if store is not None and not target:
                # Warm-target persistence is asynchronous; the first search
                # must still start a concrete commodity on an empty catalog.
                target = {**query, "commodity": MINING_MARKET_WARM_COMMODITIES[0]}
            if not getattr(self, "_mining_market_busy", False) and target:
                self._start_mining_market_refresh(target, background=True)
            self._mining_market_status = (
                "Multi-commodity search · concrete markets are verified "
                "from the local catalog and the top displayed routes"
            )
            self.miningChanged.emit()
            return
        self._preempt_mining_market_warming()
        if getattr(self, "_mining_market_busy", False):
            self._pending_mining_market_query = query
            self._mining_market_status = (
                "User market lookup queued · runs immediately after "
                "the active catalog update"
            )
            self.miningChanged.emit()
            return
        self._start_mining_market_refresh(query, background=False)


    def _preempt_mining_market_warming(self):
        # Keep the durable warm target eligible for resumption. In-flight HTTP
        # calls finish normally; the canceled identity guards their next page,
        # write and completion, so foreground work can start immediately.
        active = getattr(self, "_active_mining_market_request", None)
        if active and active.get("background"):
            self._active_mining_market_request = None
            self._mining_market_busy = False
            self._mining_market_background = False
            self._pending_mining_market_query = None


    @staticmethod
    def _normalized_mining_market_query(
        start_system, commodity, nearby_ly, min_demand,
        max_market_age_hours, landing_pad,
    ):
        return {
            "startSystem": str(start_system or "").strip().casefold(),
            "commodity": mining_commodity_id(commodity),
            "nearbyLy": max(1, min(1000, int(nearby_ly or 1))),
            "minDemand": max(0, int(min_demand or 0)),
            "maxMarketAgeHours": max(1, int(max_market_age_hours or 1)),
            "landingPad": str(landing_pad or "ANY").upper(),
        }


    def _remember_mining_warm_targets(self, query):
        """Prioritize the active search and seed useful nearby commodities."""
        store = getattr(self, "_mining_market_store", None)
        if store is None or not isinstance(query, dict):
            return
        all_commodities = query.get("commodity") == "allcommodities"
        targets = [] if all_commodities else [(dict(query), 100, True)]
        for commodity in MINING_MARKET_WARM_COMMODITIES:
            if commodity == query.get("commodity"):
                continue
            companion = dict(query)
            companion["commodity"] = commodity
            # Defaults are deliberately below every explicit search. They are
            # retained across restarts but never displace recent user intent.
            targets.append((
                companion, 80 if all_commodities else 10, False,
            ))
        generation = getattr(self, "_profile_generation", 0)
        store_generation = getattr(store, "_store_generation", 0)
        requested_at = datetime.now(timezone.utc)

        def remember():
            with store._lock:
                if (getattr(self, "_mining_market_store", None) is not store
                        or generation != getattr(self, "_profile_generation", 0)
                        or store_generation != getattr(store, "_store_generation", 0)):
                    return
                try:
                    store.remember_warm_targets(targets, now=requested_at)
                except (OSError, sqlite3.DatabaseError):
                    LOGGER.exception("Mining warm targets could not be saved")

        if hasattr(self, "_network_threads_lock"):
            self._start_network_worker(remember, "mining-warm-targets")
        else:
            store.remember_warm_targets(targets)


    def _start_mining_market_refresh(self, query, *, background):
        """Start one market lookup; background runs never replace UI state."""
        if not powerplay_catalog_is_fresh(
            getattr(self, "_mining_powerplay_catalog", {}), max_age_hours=24,
        ):
            self.refreshMiningPowerplayCatalog()
        if self._mining_market_busy:
            return False
        retry_timer = getattr(self, "_mining_market_retry_timer", None)
        if retry_timer is not None:
            retry_timer.stop()
        query = self._normalized_mining_market_query(
            query.get("startSystem"), query.get("commodity"),
            query.get("nearbyLy"), query.get("minDemand"),
            query.get("maxMarketAgeHours"), query.get("landingPad"),
        )
        if not query["startSystem"] or not query["commodity"] \
                or query["commodity"] == "allcommodities":
            return False
        request = {
            "id": uuid.uuid4().hex,
            "profileKey": self.profile_context.key,
            "generation": self._profile_generation,
            "path": str(self.mining_market_cache_file),
            "siteSnapshotPath": str(self.mining_market_cache_file.with_name("mining_site_snapshots.sqlite3")),
            "query": query,
            "background": bool(background),
            "warmKey": "\x1f".join((
                query["startSystem"].casefold(), query["commodity"],
            )),
        }
        known_origin = self._known_mining_origin(query["startSystem"])
        if known_origin:
            request["origin"] = known_origin
        self._active_mining_market_request = request
        self._mining_market_busy = True
        self._mining_market_background = bool(background)
        self._mining_market_status = (
            f"Warming market catalog · {query['commodity']} near "
            f"{query['startSystem']}"
            if background else "Checking fresh EDDN market data…"
        )
        self.miningChanged.emit()

        def is_current():
            active = getattr(self, "_active_mining_market_request", None)
            return (
                not getattr(self, "_shutdown_complete", False)
                and bool(active) and active.get("id") == request["id"]
                and self.profile_context.key == request["profileKey"]
                and self._profile_generation == request["generation"]
                and str(self.mining_market_cache_file) == request["path"]
            )

        def worker():
            result = dict(request)
            try:
                result.update(fetch_mining_refresh(
                    query, origin=request.get("origin"),
                    include_edframe=include_edframe, is_current=is_current,
                    snapshot_path=request["siteSnapshotPath"],
                ))
            except Exception as exc:
                result.update(success=False, error=str(exc))
            self._persist_mining_market_result(result, store, persistence_lock)
            self.miningMarketFinished.emit(result)

        # Capture the exact profile store/path before dispatch; never resolve a
        # replacement profile's store from a delayed worker.
        store = getattr(self, "_mining_market_store", None)
        include_edframe = getattr(self, "_edframe_catalog_enabled", True)
        if not hasattr(self, "_mining_file_lock"):
            self._mining_file_lock = threading.Lock()
        persistence_lock = self._mining_file_lock
        request["failureCount"] = int(getattr(self, "_mining_market_failure_count", 0))
        if hasattr(self, "_data_dir"):
            request["coordinatePath"] = str(self._data_dir / "system_coordinates.json")
        if not self._start_network_worker(worker, "mining-market-sync"):
            self._active_mining_market_request = None
            self._mining_market_busy = False
            self._mining_market_background = False
            self._mining_market_status = "Market lookup unavailable during shutdown"
            self.miningChanged.emit()
            return False
        return True


    def _persist_mining_market_result(self, result, store, persistence_lock):
        """Persist on the tracked worker, serialized with explicit reset.

        A reset invalidates the active request before taking this same lock.
        It therefore either clears an already finished write or prevents the
        stale writer entirely. The GUI completion slot only publishes memory.
        """
        with persistence_lock:
            active = getattr(self, "_active_mining_market_request", None)
            if (not active or active.get("id") != result.get("id")
                    or result.get("profileKey") != self.profile_context.key
                    or result.get("generation") != self._profile_generation
                    or result.get("path") != str(self.mining_market_cache_file)):
                return
            try:
                # Ring success is independent of market-provider success. Save
                # only protocol-proven complete snapshots, under reset/profile
                # fencing on this worker, never in the GUI completion slot.
                snapshot = result.pop("siteSnapshot", None)
                if snapshot and result.get("siteSnapshotPath"):
                    try:
                        if not MiningSnapshotStore(result["siteSnapshotPath"]).save(snapshot):
                            result["persistenceError"] = "Ring snapshot exceeds cache capacity"
                    except (OSError, sqlite3.DatabaseError) as exc:
                        result["persistenceError"] = "Ring snapshot save failed: " + type(exc).__name__
                if result.get("coordinatePath"):
                    result["originUpdated"] = self._persist_mining_origin(
                        result.get("origin"), Path(result["coordinatePath"]),
                    )
                if not result.get("success"):
                    delay = MINING_MARKET_RETRY_SECONDS[min(
                        result.get("failureCount", 0), len(MINING_MARKET_RETRY_SECONDS) - 1,
                    )]
                    if store is not None:
                        store.mark_warm_target(
                            result.get("warmKey", ""), success=False,
                            error=str(result.get("error") or "unknown error"),
                            retry_seconds=delay,
                        )
                        retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                        store.record_source_result(
                            "EDDN market indexes", success=False,
                            error=str(result.get("error") or "unknown error"),
                            next_retry_at=retry_at.isoformat(timespec="seconds"),
                        )
                    return
                markets = [row for row in result.get("markets", []) if isinstance(row, dict)]
                result["fetchedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                if store is not None:
                    store.ingest(markets, fetched_at=result["fetchedAt"], create_backup=False)
                    store.mark_warm_target(result.get("warmKey", ""), success=True)
                    store.record_source_result("EDDN market indexes", success=True)
                    result["retained"] = store.count()
                    result["warmSummary"] = store.warm_summary()
                if not result.get("background"):
                    saved = self._persist_json(Path(result["path"]), {
                        "fetchedAt": result["fetchedAt"],
                        "query": dict(result.get("query") or {}),
                        "markets": markets, "origin": result.get("origin") or {},
                    }, "Mining market cache")
                    if not saved:
                        result["persistenceError"] = "Market snapshot could not be saved"
            except (OSError, sqlite3.DatabaseError) as exc:
                result["persistenceError"] = type(exc).__name__
                LOGGER.warning("Mining market persistence failed: %s", type(exc).__name__)


    def _launch_pending_mining_market_refresh(self):
        query = getattr(self, "_pending_mining_market_query", None)
        if not isinstance(query, dict):
            return False
        self._pending_mining_market_query = None
        return self._start_mining_market_refresh(query, background=False)


    def _known_mining_origin(self, system):
        name = str(system or "").strip()
        key = name.casefold()
        if not key:
            return {}
        state = getattr(self, "_state", {})
        if str(state.get("system") or "").strip().casefold() == key:
            coordinates = self._valid_star_position(
                state.get("currentPosition")
            )
            if coordinates is not None:
                return {
                    "system": str(state.get("system") or name).strip(),
                    "coordinates": coordinates,
                    "source": "Journal",
                }
        market_origin = getattr(self, "_mining_market_cache", {}).get(
            "origin", {}
        )
        if (
            isinstance(market_origin, dict)
            and str(market_origin.get("system") or "").strip().casefold() == key
            and self._valid_star_position(market_origin.get("coordinates"))
            is not None
        ):
            return dict(market_origin)
        try:
            coordinates = self._valid_star_position(
                self._system_coordinate_index().get(key)
            )
        except (AttributeError, OSError):
            coordinates = None
        return ({
            "system": name,
            "coordinates": coordinates,
            "source": "Local coordinate cache",
        } if coordinates is not None else {})


    def _persist_mining_origin(self, origin, path):
        if not isinstance(origin, dict):
            return False
        system = str(origin.get("system") or "").strip()
        coordinates = self._valid_star_position(origin.get("coordinates"))
        if not system or coordinates is None:
            return False
        saved_coordinates = load_json_file(path, {}, encoding="utf-8")
        if not isinstance(saved_coordinates, dict):
            saved_coordinates = {}
        existing_key = next((
            key for key in saved_coordinates
            if str(key).strip().casefold() == system.casefold()
        ), None)
        key = existing_key or system
        if self._valid_star_position(saved_coordinates.get(key)) == coordinates:
            return False
        saved_coordinates[key] = coordinates
        persisted = self._persist_json(
            path, saved_coordinates, "Mining Finder system coordinates",
        )
        return bool(persisted)


    def _ingest_local_mining_market_snapshot(self, snapshot, *, fingerprint=""):
        """Queue opened station markets independently of EDDN and UI locks."""
        if not isinstance(snapshot, dict):
            return 0
        system = str(snapshot.get("StarSystem") or "").strip().casefold()
        state = getattr(self, "_state", {})
        coordinates = None
        if str(state.get("system") or "").strip().casefold() == system:
            coordinates = self._valid_star_position(
                state.get("currentPosition")
            )
        rows = project_local_market_snapshot(
            snapshot, coordinates=coordinates,
        )
        store = getattr(self, "_mining_market_store", None)
        if not rows or store is None:
            return 0
        if hasattr(self, "_network_threads_lock"):
            generation = self._profile_generation
            store_generation = store._store_generation
            profile_key = self.profile_context.key
            if not hasattr(self, "_mining_file_lock"):
                self._mining_file_lock = threading.Lock()
            persistence_lock = self._mining_file_lock

            def worker():
                result = {"store": store, "generation": generation,
                          "profileKey": profile_key, "storeGeneration": store_generation,
                          "fingerprint": fingerprint, "rows": len(rows)}
                try:
                    with persistence_lock, store._lock:
                        if (getattr(self, "_mining_market_store", None) is not store
                                or generation != self._profile_generation
                                or store_generation != store._store_generation):
                            return
                        result["imported"] = store.ingest(rows, create_backup=False)
                        result["retained"] = store.count()
                except (OSError, sqlite3.DatabaseError) as exc:
                    result["error"] = type(exc).__name__
                    LOGGER.exception("Local mining market storage failed")
                finally:
                    self.localMiningMarketFinished.emit(result)

            return len(rows) if self._start_network_worker(worker, "local-mining-market") else 0
        imported = store.ingest(rows, create_backup=False)
        if imported:
            self._schedule_mining_market_backup()
            self._mining_market_revision += 1
            self._mining_market_status = (
                f"Local market observed · {len(rows)} mining commodities"
                f" · {store.count()} retained"
            )
            self.miningChanged.emit()
        return imported


    @Slot(object)
    def _finish_local_mining_market(self, result):
        store = result["store"]
        if (getattr(self, "_mining_market_store", None) is not store
                or result["generation"] != self._profile_generation
                or result["profileKey"] != self.profile_context.key
                or result["storeGeneration"] != store._store_generation):
            return
        if result.get("error"):
            if result.get("fingerprint") == getattr(self, "_local_market_snapshot_fingerprint", ""):
                self._local_market_snapshot_fingerprint = ""  # Retry the retained Market.json.
            self._mining_market_status = "Local market save deferred · will retry"
            self.miningChanged.emit()
        elif result.get("imported"):
            self._schedule_mining_market_backup()
            self._mining_market_revision += 1
            self._mining_market_status = (
                f"Local market observed · {result['rows']} mining commodities"
                f" · {result['retained']} retained"
            )
            self.miningChanged.emit()


    def _schedule_mining_market_backup(self):
        """Coalesce and throttle recovery snapshots off the GUI thread."""
        store = getattr(self, "_mining_market_store", None)
        if store is None:
            return False
        if getattr(self, "_mining_market_backup_running", False):
            return True
        if not store.backup_due():
            return True

        self._mining_market_backup_running = True

        def backup_once():
            try:
                store.backup()
            finally:
                self._mining_market_backup_running = False

        starter = getattr(self, "_start_network_worker", None)
        if callable(starter):
            started = bool(starter(backup_once, "mining-market-backup"))
            if not started:
                self._mining_market_backup_running = False
            return started
        try:
            return store.backup()
        finally:
            self._mining_market_backup_running = False


    def _publish_mining_powerplay(self, rows):
        if not rows:
            return False
        existing = getattr(self, "_mining_powerplay_observations", [])
        # A complete region can contain more than 20,000 system/Power facts.
        # Keep its coverage on subsequent targeted and relay merges as well;
        # the merge still retains only the newest fact per system and Power.
        merged = merge_powerplay_observations(
            existing, rows, limit=max(20_000, len(existing) + len(rows)),
        )
        if merged == existing:
            return False
        self._mining_powerplay_observations = merged
        self._mining_market_revision = getattr(self, "_mining_market_revision", 0) + 1
        self._save_mining_json(self.mining_powerplay_observations_file, merged)
        return True


    @Slot(object)
    def _finish_mining_market_sync(self, result):
        request = self._active_mining_market_request
        if not request or result.get("id") != request.get("id"):
            return
        background = bool(request.get("background"))
        self._active_mining_market_request = None
        self._mining_market_busy = False
        self._mining_market_background = False
        if not (
            result.get("profileKey") == self.profile_context.key
            and result.get("generation") == self._profile_generation
            and result.get("path") == str(self.mining_market_cache_file)
        ):
            self._mining_market_status = "Discarded stale profile market response"
            self.miningChanged.emit()
            return
        origin_updated = bool(result.get("originUpdated"))
        origin = result.get("origin") or {}
        if origin.get("system") and self._valid_star_position(origin.get("coordinates")):
            self._add_mining_system_names([{"system": origin["system"]}])
        # Profile checks above apply to all four independent data domains.
        # Reuse the bounded observation batch, keeping network work off the UI.
        for result_key, pending_key in (
            ("serverCandidates", "_pending_mining_candidates"),
            ("serverPowerplay", "_pending_mining_powerplay_observations"),
        ):
            rows = [row for row in result.get(result_key, []) if isinstance(row, dict)]
            if rows:
                if result_key == "serverPowerplay":
                    # Publish related facts BEFORE markets/notifications. Do not
                    # hold a user-search response in the 30-second relay batch.
                    self._publish_mining_powerplay(rows)
                elif (result_key == "serverCandidates"
                      and self._dispatch_mining_observation_batch(rows, search_refresh=not background)):
                    pass
                else:
                    setattr(self, pending_key, [*getattr(self, pending_key, []), *rows])
        if not result.get("success"):
            failure_count = int(getattr(
                self, "_mining_market_failure_count", 0
            ))
            delay = MINING_MARKET_RETRY_SECONDS[min(
                failure_count, len(MINING_MARKET_RETRY_SECONDS) - 1
            )]
            self._mining_market_failure_count = failure_count + 1
            retry_timer = getattr(self, "_mining_market_retry_timer", None)
            if retry_timer is not None and not getattr(
                self, "_shutdown_complete", False
            ):
                retry_timer.start(delay * 1000)
            self._mining_market_status = (
                ("Catalog warming paused" if background
                 else "Market lookup failed")
                + " · retained data unchanged"
                f" · retry in {delay // 60} min · "
                + str(result.get("error") or "unknown error")
            )
            if origin_updated:
                self._mining_market_revision += 1
            self.miningChanged.emit()
            if origin_updated:
                self.stateChanged.emit()
            self._launch_pending_mining_market_refresh()
            return
        markets = [
            row for row in result.get("markets", []) if isinstance(row, dict)
        ]
        fetched_at = result.get("fetchedAt") or datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not background:
            self._mining_market_cache = {
                "fetchedAt": fetched_at,
                "query": dict(result.get("query") or {}),
                "markets": markets,
                "origin": result.get("origin") or {},
            }
        retained = result.get("retained", 0)
        warm_summary = result.get("warmSummary", {})
        if getattr(self, "_mining_market_store", None) is not None:
            self._schedule_mining_market_backup()
        self._mining_market_failure_count = 0
        retry_timer = getattr(self, "_mining_market_retry_timer", None)
        if retry_timer is not None:
            retry_timer.stop()
        self._mining_market_revision += 1
        warm_progress = (
            f" · {warm_summary.get('fresh', 0)}/"
            f"{warm_summary.get('total', 0)} warm"
            if warm_summary.get("total") else ""
        )
        provider_status = result.get("providerStatus")
        provider_summary = (
            market_provider_status_summary(provider_status)
            if isinstance(provider_status, dict) and provider_status else ""
        )
        self._mining_market_status = (
            ("Catalog warmed" if background
             else "Community market data updated")
            + f" · {len(markets)} nearby · {retained} retained"
            + warm_progress
            + (f" · {provider_summary}" if provider_summary else "")
            + (f" · server rings {len(result.get('serverCandidates', []))}"
               if "serverCandidates" in result else "")
            + (" (snapshot unchanged)" if result.get("siteCoverage", {}).get("notModified") else "")
            + (f" · server Powerplay {len(result.get('serverPowerplay', []))}"
               if "serverPowerplay" in result else "")
            + (" · server rings unavailable (retained)" if result.get("siteError") else "")
            + (" · server Powerplay unavailable (Journal/EDSM retained)"
               if result.get("powerplayError") else "")
            + (" · bounded server selection (not full coverage)" if any(
                result.get(key, {}).get("bounded")
                for key in ("siteCoverage", "powerplayCoverage")
            ) else "")
            + (" · ring snapshot changed during paging; provisional results"
               if result.get("siteCoverage", {}).get("consistent") is False else "")
            + (" · local cache save failed (results available)"
               if result.get("persistenceError") else "")
        )
        launched_pending = self._launch_pending_mining_market_refresh()
        if not launched_pending and retry_timer is not None and not getattr(
            self, "_shutdown_complete", False
        ):
            retry_timer.start(MINING_MARKET_WARM_INTERVAL_SECONDS * 1000)
        self.miningChanged.emit()
        self.stateChanged.emit()


    @Slot()
    def updateTraderCatalog(self):
        if self._trader_sync_busy:
            return
        position = self._state.get("currentPosition") or []
        if not isinstance(position, (list, tuple)) or len(position) != 3:
            self._trader_sync_status = (
                "Cannot update: no current three-dimensional Journal position."
            )
            self.connectionChanged.emit()
            return
        existing = self._read_local_json(self.trader_catalog_file, {})
        try:
            fetched_at = datetime.fromisoformat(
                str(existing.get("fetched_at") or "").replace("Z", "+00:00")
            ).astimezone(timezone.utc)
        except (AttributeError, TypeError, ValueError):
            fetched_at = None
        if fetched_at and (
            datetime.now(timezone.utc) - fetched_at
        ).total_seconds() < SPANSH_MINIMUM_AGE_HOURS * 3600:
            self._trader_sync_status = "Spansh catalog is already current."
            self.connectionChanged.emit()
            return
        reference = tuple(float(value) for value in position)
        request_context = {
            "request_id": uuid.uuid4().hex,
            "profile_key": self.profile_context.key,
            "path_generation": self._profile_generation,
            "catalog_path": str(self.trader_catalog_file.resolve()),
        }
        self._trader_sync_busy = True
        self._trader_sync_status = (
            "Querying Spansh for nearby Raw, Manufactured and Encoded traders…"
        )
        self.connectionChanged.emit()

        def worker():
            try:
                result = fetch_trader_catalog_updates(
                    {"Raw", "Manufactured", "Encoded"},
                    reference,
                    post=requests.post,
                    timeout=SPANSH_TIMEOUT_SECONDS,
                    size=100,
                )
                if not result.get("stations"):
                    errors = "; ".join(
                        f"{key}: {value}"
                        for key, value in result.get("errors", {}).items()
                    )
                    raise LookupError(errors or "No valid trader rows returned")
                self.traderSyncFinished.emit(True, json.dumps({
                    "request": request_context, "result": result,
                }))
            except Exception as exc:
                self.traderSyncFinished.emit(False, json.dumps({
                    "request": request_context,
                    "error": f"{type(exc).__name__}: {exc}",
                }))

        self._start_network_worker(worker, "trader-catalog-sync")


    @Slot(bool, str)
    def _finish_trader_catalog_sync(self, success, payload):
        self._trader_sync_busy = False
        try:
            envelope = json.loads(payload)
            request_context = envelope["request"]
            target_path = Path(request_context["catalog_path"])
            current_request = (
                request_context.get("profile_key") == self.profile_context.key
                and request_context.get("path_generation") == self._profile_generation
                and target_path == self.trader_catalog_file.resolve()
            )
        except (KeyError, TypeError, ValueError):
            LOGGER.error("Trader Spansh completion has no valid request context")
            return
        if not success:
            if not current_request:
                LOGGER.warning(
                    "Discarded stale Trader status for Spansh request %s",
                    request_context.get("request_id", ""),
                )
                return
            self._trader_sync_status = (
                "Spansh update failed · offline catalog remains active · "
                f"{envelope.get('error', 'unknown error')}"
            )
            self.connectionChanged.emit()
            return
        try:
            result = envelope["result"]
            existing = self._read_local_json(target_path, {})
            rows = merge_trader_catalog(
                existing.get("stations", [])
                if isinstance(existing, dict) else [],
                result.get("stations", []),
            )
            document = {
                "source": "Local overlay merged from Spansh live station search",
                "fetched_at": result.get("fetched_at"),
                "reference_coords": result.get("reference_coords"),
                "stations": rows,
            }
            if not self._persist_json(target_path, document, "Trader catalog"):
                raise OSError("Trader catalog could not be saved to disk")
            type_cache = TraderTypeCache().load()
            cache_changed = False
            for row in result.get("stations", []):
                evidence = spansh_trader_type_evidence(
                    row, result.get("fetched_at")
                )
                if evidence and type_cache.update(evidence):
                    cache_changed = True
            if cache_changed:
                type_cache.save()
        except (KeyError, OSError, TypeError, ValueError) as exc:
            if not current_request:
                LOGGER.error(
                    "Stale Trader Spansh result could not be saved to %s: %s",
                    target_path, exc,
                )
                return
            self._trader_sync_status = (
                f"Live results received, but local merge failed · {exc}"
            )
            self.connectionChanged.emit()
            return
        if not current_request:
            LOGGER.info(
                "Saved stale Trader Spansh request %s to original profile %s",
                request_context.get("request_id", ""), target_path,
            )
            return
        errors = result.get("errors", {})
        self._trader_sync_status = (
            f"Catalog updated · 1,622 bundled + {len(rows)} saved live rows"
            + (
                " · partial: " + ", ".join(sorted(errors))
                if errors else " · all three trader types received"
            )
        )
        self.refresh()
        self.connectionChanged.emit()


    @Slot()
    def refreshHgeFinderLifetime(self):
        """Re-evaluate HGE expiry without rebuilding Journal-derived state."""
        self.hgeChanged.emit()
        if self._selected_material:
            key = str(self._selected_material.get("key") or "")
            self.selectMaterial(key)


    @staticmethod
    def _recently_verified_mining_route(row, now=None):
        """Return whether a route already contains a recent Spansh merge."""
        if not isinstance(row, dict):
            return False
        observations = row.get("observations") or []
        has_spansh = any(
            "spansh" in str(item.get("source") or "").casefold()
            for item in observations if isinstance(item, dict)
        ) or "spansh" in str(row.get("source") or "").casefold()
        if not has_spansh:
            return False
        try:
            learned_at = datetime.fromisoformat(
                str(row.get("learnedAt") or "").replace("Z", "+00:00")
            )
            if learned_at.tzinfo is None:
                learned_at = learned_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return False
        now = now or datetime.now(timezone.utc)
        return (now - learned_at.astimezone(timezone.utc)).total_seconds() < 21600


    @Slot(object, str)
    @Slot(object, str, str, int, int, str)
    def verifyMiningRoutes(
        self, routes, start_system, commodity="", max_market_age_hours=0,
        min_demand=0, landing_pad="ANY",
    ):
        """Batch missing mine/sale Powerplay facts separately from ring checks."""
        route_rows = [
            dict(row) for row in list(routes or [])[:100]
            if isinstance(row, dict)
        ]
        commodity_id = mining_commodity_id(commodity)
        if getattr(self, "_mining_verification_busy", False):
            self._pending_mining_verification = {
                "routes": route_rows,
                "startSystem": str(start_system or ""),
                "commodity": commodity_id,
                "maxMarketAgeHours": int(max_market_age_hours or 0),
                "minDemand": int(min_demand or 0),
                "landingPad": str(landing_pad or "ANY"),
            }
            self._mining_verification_status = (
                "Current verification continues · newest search queued"
            )
            self.miningVerificationChanged.emit()
            return

        now = datetime.now(timezone.utc)
        now_epoch = time.time()
        cache = getattr(self, "_mining_verification_cache", {})
        lookup_cache = getattr(self, "_mining_powerplay_lookup_cache", {})
        lookup_targets = missing_powerplay_targets(
            route_rows, getattr(self, "_mining_powerplay_observations", []),
            retry_after=lookup_cache, now=now,
        ) if getattr(self, "_edframe_catalog_enabled", True) else []
        powerplay_targets = []
        seen = set()
        cached = 0
        for row in route_rows[:30]:
            if row.get("optimization") == "POWERPLAY MERITS" and row.get("powerplayStatus"):
                continue  # Ring evidence is not a substitute for Powerplay facts.
            try:
                address = int(row.get("systemAddress"))
            except (TypeError, ValueError):
                continue
            if address <= 0 or address in seen:
                continue
            seen.add(address)
            retry_after = float(
                (cache.get(address) or {}).get("retryAfter", 0.0) or 0.0
            )
            if retry_after > now_epoch or self._recently_verified_mining_route(
                row, now=now,
            ):
                cached += 1
                continue
            powerplay_targets.append({
                "systemAddress": address,
                "system": str(row.get("system") or ""),
                "commodity": str(row.get("selectedCommodity") or commodity_id),
                "marketId": int(row.get("diagnosticMarketId", 0) or 0),
                "source": str(row.get("diagnosticMarketSource") or ""),
                "filterResult": str(row.get("marketStatus") or "UNKNOWN"),
                "finalReason": str(row.get("pendingReason") or ""),
            })

        market_cache = getattr(
            self, "_mining_powerplay_market_verification_cache", {},
        )
        market_targets = []
        market_seen = set()
        market_cached = 0
        market_candidates = []
        budget_market_keys = set()
        if commodity_id:
            pending_market_rows = []
            for row in route_rows:
                if (
                    str(row.get("optimization") or "").upper()
                    != "POWERPLAY MERITS"
                    or not row.get("sameSystemSaleRequired")
                    or row.get("marketMatchesFilters")
                ):
                    continue
                system = str(row.get("system") or "").strip()
                route_commodities = []
                selected_commodity = mining_commodity_id(
                    row.get("selectedCommodity")
                )
                if selected_commodity:
                    route_commodities.append(selected_commodity)
                if commodity_id == "allcommodities":
                    for candidate in row.get("candidateCommodities") or []:
                        candidate_id = mining_commodity_id(
                            candidate.get("id") or candidate.get("commodity")
                            if isinstance(candidate, dict) else candidate
                        )
                        if candidate_id and candidate_id not in route_commodities:
                            route_commodities.append(candidate_id)
                elif commodity_id not in route_commodities:
                    route_commodities.append(commodity_id)
                if system and route_commodities:
                    pending_market_rows.append((system, route_commodities, row))
            max_options = max((
                len(options) for _system, options, _row in pending_market_rows
            ), default=0)
            # Round-robin keeps the request budget useful: first verify one
            # concrete commodity for several visible systems, then try each
            # route's secondary commodities if capacity remains.
            for option_index in range(max_options):
                for system, route_commodities, row in pending_market_rows:
                    if option_index >= len(route_commodities):
                        continue
                    route_commodity = route_commodities[option_index]
                    key = f"{system.casefold()}\x1f{route_commodity}"
                    if key in market_seen:
                        continue
                    market_seen.add(key)
                    market_candidates.append({
                        "system": system,
                        "commodity": route_commodity,
                        "key": key,
                        "marketId": int(
                            row.get("diagnosticMarketId", 0) or 0
                        ),
                        "source": str(
                            row.get("diagnosticMarketSource") or ""
                        ),
                        "filterResult": str(
                            row.get("marketStatus") or "NO_MARKET_DATA"
                        ),
                        "finalReason": str(row.get("pendingReason") or ""),
                    })

            verification_states = dict(getattr(
                self, "_mining_market_verification_states", {},
            ))
            for target in market_candidates:
                key = target["key"]
                retry_after = float(
                    (market_cache.get(key) or {}).get(
                        "retryAfter", 0.0,
                    ) or 0.0
                )
                if retry_after > now_epoch:
                    market_cached += 1
                    budget_market_keys.add(key)
                    cached_state = str(
                        (market_cache.get(key) or {}).get("state") or ""
                    )
                    if cached_state:
                        verification_states[key] = {
                            "state": cached_state,
                            "reason": str(
                                (market_cache.get(key) or {}).get("reason") or ""
                            ),
                        }
                    continue
                if len(market_targets) < 6:
                    market_targets.append(target)
                    budget_market_keys.add(key)
                    verification_states[key] = {
                        "state": "CHECKING",
                        "reason": "Market lookup is running in this verification pass",
                    }
                else:
                    verification_states[key] = {
                        "state": "QUEUED",
                        "reason": (
                            "Market lookup was not queried in this pass because "
                            "the six-target budget was full"
                        ),
                    }
            self._mining_market_verification_states = verification_states

        total = len(seen) + len(lookup_targets) + len(budget_market_keys if commodity_id else ())
        completed = cached + market_cached
        self._mining_verification_total = total
        self._mining_verification_completed = completed
        self._mining_verification_failures = 0
        if not total:
            self._mining_verification_status = (
                "Powerplay checked recently · missing observations remain unknown"
                if any(row.get("powerplayStatus") == "POWERPLAY_DATA_MISSING" for row in route_rows)
                else "No displayed route has a verifiable system address"
            )
            self.miningVerificationChanged.emit()
            return
        if not powerplay_targets and not market_targets and not lookup_targets:
            self._mining_verification_status = (
                f"Top routes current · {completed}/{total} "
                + ("checks" if market_seen else "systems")
                + " verified"
            )
            self.miningVerificationChanged.emit()
            return

        origin = self._known_mining_origin(start_system)
        request = {
            "id": uuid.uuid4().hex,
            "profileKey": self.profile_context.key,
            "generation": self._profile_generation,
            "path": str(self.mining_catalog_file),
            "origin": list(origin.get("coordinates") or []),
            "targets": powerplay_targets,
            "powerplayTargets": powerplay_targets,
            "powerplayLookupTargets": lookup_targets,
            "marketTargets": market_targets,
            "commodity": commodity_id,
            "maxMarketAgeHours": int(max_market_age_hours or 0),
            "minDemand": int(min_demand or 0),
            "landingPad": str(landing_pad or "ANY"),
            "total": total,
            "completed": completed,
        }
        self._active_mining_verification_request = request
        self._mining_verification_busy = True
        self._mining_verification_status = (
            f"Verifying top routes · {completed}/{total} checks"
        )
        self.miningVerificationChanged.emit()
        if market_candidates:
            mining_changed = getattr(self, "miningChanged", None)
            if mining_changed is not None:
                try:
                    mining_changed.emit()
                except RuntimeError:
                    pass

        def log_target(queue_name, target, response_status, **updates):
            if not getattr(self, "_debug_mode", False):
                return
            record = {
                "queue": queue_name,
                "system": str(target.get("system") or ""),
                "commodity": str(target.get("commodity") or commodity_id),
                "marketId": int(
                    updates.get("marketId", target.get("marketId", 0)) or 0
                ),
                "source": str(
                    updates.get("source", target.get("source", "")) or ""
                ),
                "responseStatus": str(response_status or "UNKNOWN"),
                "filterResult": str(
                    updates.get(
                        "filterResult", target.get("filterResult", "UNKNOWN")
                    ) or "UNKNOWN"
                ),
                "finalReason": str(
                    updates.get(
                        "finalReason", target.get("finalReason", "")
                    ) or ""
                ),
            }
            self._write_log(
                "Mining verification target · "
                + json.dumps(record, ensure_ascii=False, sort_keys=True)
            )

        def fetch_target(target):
            address = target["systemAddress"]
            try:
                if getattr(self, "_edframe_catalog_enabled", True):
                    candidates = fetch_edframe_mining_candidates(
                        target["system"], requests.get,
                        commodity=request.get("commodity", ""),
                        origin=request["origin"],
                    )
                    if candidates:
                        learned_at = datetime.now(timezone.utc).isoformat(
                            timespec="seconds"
                        )
                        for candidate in candidates:
                            candidate["learnedAt"] = learned_at
                        return address, candidates
            except Exception:
                pass
            payload = fetch_spansh_system_dump(address, requests.get)
            candidates = project_spansh_mining_candidates(
                payload, request["origin"]
            )
            if not candidates:
                raise LookupError("Spansh returned no mining rings")
            learned_at = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
            for candidate in candidates:
                candidate["learnedAt"] = learned_at
            return address, candidates

        def worker():
            incoming = []
            succeeded = []
            failed = []
            market_rows = []
            market_succeeded = []
            market_failed = []
            completed = int(request["completed"])
            market_outcomes = []
            powerplay_result = {"rows": [], "checked": [], "failed": []}
            if lookup_targets:
                try:
                    with requests.Session() as session:
                        def get_current(*args, **kwargs):
                            active = getattr(self, "_active_mining_verification_request", None)
                            if (not active or active.get("id") != request["id"]
                                    or getattr(self, "_shutdown_complete", False)
                                    or self._profile_generation != request["generation"]
                                    or self.profile_context.key != request["profileKey"]):
                                raise RuntimeError("Powerplay lookup superseded")
                            return session.get(*args, **kwargs)
                        powerplay_result = fetch_powerplay_targets(
                            lookup_targets, origin=request["origin"], get=get_current,
                        )
                except Exception as exc:
                    powerplay_result["failed"] = [target["system"] for target in lookup_targets]
                    powerplay_result["error"] = type(exc).__name__
                completed += len(lookup_targets)
                self.miningVerificationProgress.emit({
                    "id": request["id"], "completed": completed, "total": total,
                    "failures": len(powerplay_result["failed"]),
                })
            if powerplay_targets:
                with ThreadPoolExecutor(
                    max_workers=min(2, len(powerplay_targets)),
                    thread_name_prefix="mining-verify",
                ) as pool:
                    futures = {
                        pool.submit(fetch_target, target): target
                        for target in powerplay_targets
                    }
                    for future in as_completed(futures):
                        target = futures[future]
                        try:
                            address, candidates = future.result()
                            succeeded.append(address)
                            incoming.extend(candidates)
                            source = str(
                                (candidates[0] if candidates else {}).get(
                                    "source"
                                ) or target.get("source") or ""
                            )
                            log_target(
                                "powerplay", target, "FOUND",
                                source=source,
                                finalReason=(
                                    target.get("finalReason")
                                    or "Powerplay/catalog evidence refreshed"
                                ),
                            )
                        except Exception as exc:
                            failed.append({
                                "systemAddress": target["systemAddress"],
                                "system": target["system"],
                                "error": f"{type(exc).__name__}: {exc}",
                            })
                            log_target(
                                "powerplay", target, "ERROR",
                                finalReason=f"{type(exc).__name__}: {exc}",
                            )
                        completed += 1
                        self.miningVerificationProgress.emit({
                            "id": request["id"],
                            "completed": completed,
                            "total": total,
                            "failures": len(failed) + len(market_failed) + len(powerplay_result["failed"]),
                        })
            hours = max(1, int(request.get("maxMarketAgeHours", 0) or 1))
            for target in market_targets:
                try:
                    rows = fetch_market_imports(
                        target["system"], target["commodity"],
                        max_distance=1,
                        max_days_ago=max(1, min(14, math.ceil(hours / 24))),
                        get=requests.get,
                        landing_pad=request.get("landingPad", "ANY"),
                        include_edframe=getattr(
                            self, "_edframe_catalog_enabled", True,
                        ),
                    )
                    market_rows.extend(rows)
                    market_succeeded.append(target["key"])
                    first = rows[0] if rows else {}
                    outcome_state = "FOUND" if rows else "NO_DATA"
                    outcome_reason = (
                        f"Server returned {len(rows)} market row(s)"
                        if rows else
                        "Server returned no market data for this system and commodity"
                    )
                    market_outcomes.append({
                        "key": target["key"],
                        "state": outcome_state,
                        "reason": outcome_reason,
                    })
                    log_target(
                        "market", target, outcome_state,
                        marketId=first.get("marketId", target.get("marketId", 0)),
                        source=first.get("source", target.get("source", "")),
                        filterResult=(
                            "RECHECK AFTER INGEST" if rows else "NO_MARKET_DATA"
                        ),
                        finalReason=outcome_reason,
                    )
                except Exception as exc:
                    market_failed.append({
                        "key": target["key"],
                        "system": target["system"],
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                    market_outcomes.append({
                        "key": target["key"],
                        "state": "ERROR",
                        "reason": f"{type(exc).__name__}: {exc}",
                    })
                    log_target(
                        "market", target, "ERROR",
                        finalReason=f"{type(exc).__name__}: {exc}",
                    )
                completed += 1
                self.miningVerificationProgress.emit({
                    "id": request["id"],
                    "completed": completed,
                    "total": total,
                    "failures": len(failed) + len(market_failed) + len(powerplay_result["failed"]),
                })
            result = dict(request)
            result.update({
                "candidates": incoming,
                "succeeded": succeeded,
                "failed": failed,
                "markets": market_rows,
                "marketSucceeded": market_succeeded,
                "marketFailed": market_failed,
                "marketOutcomes": market_outcomes,
                "powerplayLookup": powerplay_result,
            })
            self._persist_verified_mining_markets(result, verification_store, persistence_lock)
            self.miningVerificationFinished.emit(result)

        verification_store = getattr(self, "_mining_market_store", None)
        if not hasattr(self, "_mining_file_lock"):
            self._mining_file_lock = threading.Lock()
        persistence_lock = self._mining_file_lock
        if not self._start_network_worker(worker, "mining-route-verification"):
            self._active_mining_verification_request = None
            self._mining_verification_busy = False
            self._mining_verification_status = (
                "Route verification unavailable during shutdown"
            )
            self.miningVerificationChanged.emit()


    def _persist_verified_mining_markets(self, result, store, persistence_lock):
        """Finish database work before the verification's GUI publication."""
        result["storageProcessed"] = True
        with persistence_lock:
            active = getattr(self, "_active_mining_verification_request", None)
            if (not active or active.get("id") != result.get("id")
                    or result.get("profileKey") != self.profile_context.key
                    or result.get("generation") != self._profile_generation
                    or result.get("path") != str(self.mining_catalog_file)
                    or getattr(self, "_mining_market_store", None) is not store):
                return
            markets = result.get("markets") or []
            if store is not None and markets:
                try:
                    store.ingest(markets, create_backup=False)
                    store.record_source_result("Powerplay Verified market checks", success=True)
                    result["retained"] = store.count()
                except (OSError, sqlite3.DatabaseError) as exc:
                    result["storageError"] = type(exc).__name__
                    LOGGER.exception("Verified market storage failed")


    @Slot(object)
    def _finish_mining_verification_progress(self, progress):
        request = getattr(self, "_active_mining_verification_request", None)
        if not request or progress.get("id") != request.get("id"):
            return
        self._mining_verification_completed = int(
            progress.get("completed", 0) or 0
        )
        self._mining_verification_total = int(
            progress.get("total", 0) or 0
        )
        self._mining_verification_failures = int(
            progress.get("failures", 0) or 0
        )
        self._mining_verification_status = (
            f"Verifying top routes · {self._mining_verification_completed}/"
            f"{self._mining_verification_total} checks"
        )
        self.miningVerificationChanged.emit()


    @Slot(object)
    def _finish_mining_verification(self, result):
        request = getattr(self, "_active_mining_verification_request", None)
        if not request or result.get("id") != request.get("id"):
            return
        self._active_mining_verification_request = None
        self._mining_verification_busy = False
        context_matches = (
            result.get("profileKey") == self.profile_context.key
            and result.get("generation") == self._profile_generation
            and result.get("path") == str(self.mining_catalog_file)
        )
        # Late completions from a reset/profile switch must not populate retry
        # caches either; otherwise the new profile silently skips needed facts.
        if not context_matches:
            self._mining_verification_status = "Discarded stale profile verification"
            self.miningVerificationChanged.emit()
            return
        failed = list(result.get("failed") or [])
        succeeded = list(result.get("succeeded") or [])
        market_failed = list(result.get("marketFailed") or [])
        market_succeeded = list(result.get("marketSucceeded") or [])
        market_outcomes = {
            str(item.get("key") or ""): dict(item)
            for item in result.get("marketOutcomes") or []
            if isinstance(item, dict) and item.get("key")
        }
        now_epoch = time.time()
        cache = getattr(self, "_mining_verification_cache", {})
        for address in succeeded:
            cache[int(address)] = {"retryAfter": now_epoch + 21600}
        for failure in failed:
            try:
                address = int(failure.get("systemAddress"))
            except (TypeError, ValueError):
                continue
            cache[address] = {"retryAfter": now_epoch + 600}
        self._mining_verification_cache = cache
        market_cache = getattr(
            self, "_mining_powerplay_market_verification_cache", {},
        )
        for key in market_succeeded:
            outcome = market_outcomes.get(str(key), {})
            state = str(outcome.get("state") or "FOUND")
            reason = str(outcome.get("reason") or "")
            market_cache[str(key)] = {
                "retryAfter": now_epoch + 3600,
                "state": state,
                "reason": reason,
            }
        for failure in market_failed:
            key = str(failure.get("key") or "")
            if key:
                market_cache[key] = {
                    "retryAfter": now_epoch + 600,
                    "state": "ERROR",
                    "reason": str(failure.get("error") or ""),
                }
        self._mining_powerplay_market_verification_cache = market_cache
        verification_states = dict(getattr(
            self, "_mining_market_verification_states", {},
        ))
        for key, outcome in market_outcomes.items():
            verification_states[key] = {
                "state": str(outcome.get("state") or "FOUND"),
                "reason": str(outcome.get("reason") or ""),
            }
        for failure in market_failed:
            key = str(failure.get("key") or "")
            if key:
                verification_states[key] = {
                    "state": "ERROR",
                    "reason": str(failure.get("error") or ""),
                }
        self._mining_market_verification_states = verification_states
        lookup = result.get("powerplayLookup") or {}
        lookup_cache = dict(getattr(self, "_mining_powerplay_lookup_cache", {}))
        found = {str(row.get("system") or "").casefold() for row in lookup.get("rows", [])}
        for name in lookup.get("checked", []):
            key = str(name).casefold()
            lookup_cache[key] = now_epoch + (3600 if key in found else 600)
        for name in lookup.get("failed", []):
            lookup_cache[str(name).casefold()] = now_epoch + 120
        self._mining_powerplay_lookup_cache = {
            key: expiry for key, expiry in lookup_cache.items() if expiry > now_epoch
        }
        changed = self._publish_mining_powerplay(lookup.get("rows", []))
        incoming = [
            row for row in result.get("candidates", [])
            if isinstance(row, dict)
        ]
        if (context_matches and incoming
                and not self._dispatch_mining_observation_batch(incoming)):
            old = self._mining_catalog.get("candidates", [])
            old = old if isinstance(old, list) else []
            positions = self._mining_positions_for(old)
            merged, displaced = merge_mining_candidate_batch(
                old, incoming, positions=positions,
            )
            preserved = self._archive_history(
                "mining_observations", incoming
            )
            preserved = self._archive_history(
                "mining_catalog", displaced
            ) and preserved
            candidates = merged if preserved else [*old, *incoming]
            self._compact_mining_catalog_rows(candidates)
            self._mining_catalog = {
                "updatedAt": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "resetAt": str(self._mining_catalog.get("resetAt") or ""),
                "identityVersion": MINING_CATALOG_IDENTITY_VERSION,
                "candidates": candidates,
            }
            self._mining_catalog_revision = getattr(
                self, "_mining_catalog_revision", 0
            ) + 1
            self._mining_catalog_positions = (
                positions if candidates is merged
                else mining_candidate_positions(candidates)
            )
            self._mining_catalog_positions_identity = id(candidates)
            self._add_mining_system_names(incoming)
            self._mining_rows_cache_key = None
            self._mining_find_cache_key = None
            self._mining_find_cache = []
            self._save_mining_catalog()
            changed = True

        markets = [
            row for row in result.get("markets", [])
            if isinstance(row, dict)
        ]
        store = getattr(self, "_mining_market_store", None)
        if context_matches and markets and store is not None and not result.get("storageError"):
            if not result.get("storageProcessed"):
                # Legacy/headless direct completions, never the production worker.
                store.ingest(markets, create_backup=False)
                store.record_source_result("Powerplay Verified market checks", success=True)
            self._schedule_mining_market_backup()
            self._mining_market_revision = getattr(
                self, "_mining_market_revision", 0,
            ) + 1
            changed = True

        total = int(result.get("total", 0) or 0)
        self._mining_verification_completed = total
        self._mining_verification_total = total
        failure_count = len(failed) + len(market_failed) + len(lookup.get("failed", []))
        self._mining_verification_failures = failure_count
        if not context_matches:
            self._mining_verification_status = (
                "Discarded stale profile verification"
            )
        elif failure_count:
            self._mining_verification_status = (
                f"Top routes checked · {total - failure_count}/{total} verified · "
                f"{failure_count} temporarily unavailable"
            )
        elif lookup.get("checked"):
            missing = sum(str(name).casefold() not in found for name in lookup["checked"])
            self._mining_verification_status = (
                f"Top routes checked · {total}/{total} checks completed"
                + (f" · {missing} systems without recent Powerplay evidence" if missing else "")
            )
        else:
            self._mining_verification_status = (
                f"Top routes current · {total}/{total} systems verified"
            )
        if result.get("storageError"):
            self._mining_verification_status += " · market save failed: " + str(result["storageError"])
        self.miningVerificationChanged.emit()
        if changed or market_outcomes or market_failed:
            self.miningChanged.emit()
        if changed:
            self.stateChanged.emit()

        pending = getattr(self, "_pending_mining_verification", None)
        self._pending_mining_verification = None
        if pending and context_matches:
            self.verifyMiningRoutes(
                pending.get("routes", []), pending.get("startSystem", ""),
                pending.get("commodity", ""),
                pending.get("maxMarketAgeHours", 0),
                pending.get("minDemand", 0),
                pending.get("landingPad", "ANY"),
            )


    @Slot()
    def refreshMiningFinder(self):
        if self._mining_sync_busy:
            return
        address = self._state.get("currentSystemAddress")
        try:
            address = int(address)
        except (TypeError, ValueError):
            address = 0
        if not self._state.get("system") and address <= 0:
            self._mining_sync_status = "Current system unavailable"
            self.miningChanged.emit()
            return
        request = {
            "id": uuid.uuid4().hex,
            "profileKey": self.profile_context.key,
            "generation": self._profile_generation,
            "path": str(self.mining_catalog_file),
            "origin": list(self._state.get("currentPosition") or []),
            "system": str(self._state.get("system") or "").strip(),
        }
        self._active_mining_request = request
        self._mining_sync_busy = True
        self._mining_sync_status = "Refreshing current system · ED-Frame first…"
        self.miningChanged.emit()

        def worker():
            result = dict(request)
            candidates = []
            if getattr(self, "_edframe_catalog_enabled", True):
                try:
                    candidates = fetch_edframe_mining_candidates(
                        request["system"], requests.get,
                        origin=request["origin"],
                    )
                    if candidates and all(
                        row.get("hotspots") and not mining_candidate_freshness(row).get("stale")
                        for row in candidates
                    ):
                        result["candidates"] = candidates
                        result["success"] = True
                        self.miningSyncFinished.emit(result)
                        return
                except Exception:
                    pass
            try:
                if address <= 0:
                    raise ValueError("Spansh fallback requires system address")
                payload = fetch_spansh_system_dump(address, requests.get)
                result["candidates"] = merge_mining_candidates(
                    [*candidates, *project_spansh_mining_candidates(
                        payload, request["origin"]
                    )]
                )
                result["success"] = True
            except Exception as exc:
                result.update({"success": bool(candidates), "candidates": candidates,
                               "error": str(exc)})
            self.miningSyncFinished.emit(result)

        if not self._start_network_worker(worker, "mining-catalog-sync"):
            self._active_mining_request = None
            self._mining_sync_busy = False
            self._mining_sync_status = "Refresh unavailable during shutdown"
            self.miningChanged.emit()


    @Slot()
    def resetMiningCatalog(self):
        """Reset and safely rebuild the active profile's Mining Finder data."""
        existing = self._mining_catalog.get("candidates", [])
        if isinstance(existing, list) and not self._archive_history(
            "mining_catalog", existing
        ):
            self._mining_sync_status = (
                "Mining catalog reset stopped because history could not be saved"
            )
            self.miningChanged.emit()
            return
        self._active_mining_request = None
        self._mining_sync_busy = False
        self._active_mining_verification_request = None
        self._pending_mining_verification = None
        self._mining_verification_busy = False
        self._mining_verification_completed = 0
        self._mining_verification_total = 0
        self._mining_verification_failures = 0
        self._mining_verification_cache = {}
        self._mining_powerplay_lookup_cache = {}
        self._mining_powerplay_market_verification_cache = {}
        self._mining_market_verification_states = {}
        self._active_edframe_catalog_sync_request = None
        self._edframe_catalog_sync_busy = False
        self._edframe_catalog_sync_rows = 0
        self._edframe_catalog_sync_continue = False
        self._edframe_catalog_sync_status = (
            "Rebuild queued · retained data is cleared only for this profile"
        )
        self._mining_verification_status = (
            "Ready · verifies top routes after search"
        )
        self._pending_mining_candidates = []
        self._active_mining_observation_batch = None
        self._active_mining_market_request = None
        self._pending_mining_market_query = None
        self._mining_market_busy = False
        self._mining_market_background = False
        self._mining_market_failure_count = 0
        self._local_market_snapshot_fingerprint = ""
        retry_timer = getattr(self, "_mining_market_retry_timer", None)
        if retry_timer is not None:
            retry_timer.stop()
        if not hasattr(self, "_mining_catalog_load_token"):
            self._mining_catalog_load_token = 0
        self._mining_catalog_load_token += 1
        self._mining_catalog = {
            "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "resetAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "identityVersion": MINING_CATALOG_IDENTITY_VERSION,
            "candidates": [],
        }
        self._mining_catalog_revision = getattr(
            self, "_mining_catalog_revision", 0
        ) + 1
        self._mining_catalog_positions = {}
        self._mining_catalog_positions_identity = id(
            self._mining_catalog["candidates"]
        )
        self._mining_system_names = []
        self._mining_system_name_keys = []
        self._mining_rows_build_token = getattr(
            self, "_mining_rows_build_token", 0
        ) + 1
        self._mining_rows_build_in_flight = False
        self._mining_rows_build_dirty = False
        self._mining_rows_cache_key = None
        self._mining_rows_cache = []
        self._mining_find_cache_key = None
        self._mining_find_cache = []
        try:
            if not hasattr(self, "_mining_file_lock"):
                self._mining_file_lock = threading.Lock()
                self._mining_save_sequence = 0
                self._mining_save_sequences = {}
            if not hasattr(self, "_mining_save_sequences"):
                self._mining_save_sequences = {}
            if not hasattr(self, "_mining_save_sequence"):
                self._mining_save_sequence = 0
            # Supersede any queued snapshot, then serialize the explicit reset
            # behind an in-flight writer so an older catalog cannot reappear.
            self._mining_save_sequence += 1
            self._mining_save_sequences[
                str(self.mining_catalog_file)
            ] = self._mining_save_sequence
            with self._mining_file_lock:
                MiningSnapshotStore(self.mining_catalog_file.with_name("mining_site_snapshots.sqlite3")).reset()
                self.mining_catalog_file.unlink(missing_ok=True)
                load_json_file(self.mining_catalog_file, {}, encoding="utf-8")
                saved = atomic_write(
                    self.mining_catalog_file,
                    json.dumps(self._mining_catalog, indent=2),
                )
            store = getattr(self, "_mining_market_store", None)
            if store is not None:
                saved = store.reset() and saved
            self._mining_market_cache = {}
            if hasattr(self, "mining_market_cache_file"):
                saved = atomic_write(
                    self.mining_market_cache_file, json.dumps({}, indent=2),
                ) and saved
            legacy_path = getattr(
                self, "mining_market_catalog_legacy_file", None
            )
            if legacy_path is not None:
                Path(legacy_path).unlink(missing_ok=True)
            self._mining_market_revision = getattr(
                self, "_mining_market_revision", 0
            ) + 1
            self._mining_market_status = (
                "Market catalog reset · rebuilds from Journal and public data"
            )
        except (OSError, sqlite3.DatabaseError) as exc:
            saved = False
            LOGGER.warning("Mining catalog reset failed: %s", type(exc).__name__)
        self._mining_sync_status = (
            "Mining catalog reset · rebuilding from Journal and public data"
            if saved else "Mining catalog reset failed"
        )
        self.miningChanged.emit()
        self.stateChanged.emit()
        self.connectionChanged.emit()
        if saved and getattr(self, "_edframe_catalog_enabled", True):
            QTimer.singleShot(0, self.syncEdFrameCatalog)


    @Slot(object)
    def _finish_mining_sync(self, result):
        request = self._active_mining_request
        if not request or result.get("id") != request.get("id"):
            return
        self._active_mining_request = None
        self._mining_sync_busy = False
        context_matches = (
            result.get("profileKey") == self.profile_context.key
            and result.get("generation") == self._profile_generation
            and result.get("path") == str(self.mining_catalog_file)
        )
        if not context_matches:
            self._mining_sync_status = "Discarded stale profile response"
            self.miningChanged.emit()
            return
        if not result.get("success"):
            self._mining_sync_status = "Refresh failed: " + str(
                result.get("error") or "unknown error"
            )
            self.miningChanged.emit()
            return
        old = self._mining_catalog.get("candidates", [])
        incoming = list(result.get("candidates") or [])
        learned_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for row in incoming:
            row["learnedAt"] = learned_at
        if self._dispatch_mining_observation_batch(
            incoming, status=f"Current system refreshed · {len(incoming)} rings"
        ):
            return
        old = old if isinstance(old, list) else []
        positions = self._mining_positions_for(old)
        merged, _displaced = merge_mining_candidate_batch(
            old, incoming, positions=positions,
        )
        preserved = self._archive_history("mining_observations", incoming)
        preserved = self._archive_history(
            "mining_catalog",
            self._displaced_history_rows(
                old, merged, MINING_TRANSIENT_FIELDS
            ),
        ) and preserved
        candidates = (
            merged if preserved else [*old, *incoming]
        )
        self._compact_mining_catalog_rows(candidates)
        self._mining_catalog = {
            "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "resetAt": str(self._mining_catalog.get("resetAt") or ""),
            "identityVersion": MINING_CATALOG_IDENTITY_VERSION,
            "candidates": candidates,
        }
        self._mining_catalog_revision = getattr(
            self, "_mining_catalog_revision", 0
        ) + 1
        if candidates is merged:
            self._mining_catalog_positions = positions
        else:
            self._mining_catalog_positions = mining_candidate_positions(
                candidates
            )
        self._mining_catalog_positions_identity = id(candidates)
        self._add_mining_system_names(incoming)
        self._mining_rows_cache_key = None
        self._mining_find_cache_key = None
        self._mining_find_cache = []
        self._save_mining_catalog()
        self._mining_sync_status = f"Current system refreshed · {len(result.get('candidates') or [])} rings"
        self.miningChanged.emit()
        self.stateChanged.emit()


    def _mining_batch_context_matches(self, request):
        return (
            request.get("profileKey") == self.profile_context.key
            and request.get("generation") == self._profile_generation
            and request.get("path") == str(self.mining_catalog_file)
            and request.get("resetAt") == str(self._mining_catalog.get("resetAt") or "")
        )


    def _dispatch_mining_observation_batch(self, rows, *, status="", search_refresh=False):
        """Dispatch heavy work; only an initialized, running Qt controller opts in."""
        if not rows:
            return False
        if (getattr(self, "_shutdown_complete", False)
                or not hasattr(self, "_network_threads_lock")):
            return False  # Final durable flush and lightweight/headless callers.
        active = getattr(self, "_active_mining_observation_batch", None)
        if active and self._mining_batch_context_matches(active):
            self._pending_mining_candidates.extend(rows)
            if search_refresh:
                active["searchRefresh"] = True
            return True
        existing = self._mining_catalog.get("candidates", [])
        existing = existing if isinstance(existing, list) else []
        # Do not build a missing index on the UI thread. Workers copy a valid
        # index, or build their own. Freeze the cheap dictionary snapshot here:
        # a delayed worker must not see an index for a newer catalog/list.
        cached_positions = getattr(self, "_mining_catalog_positions", None)
        positions = (dict(cached_positions)
                     if getattr(self, "_mining_catalog_positions_identity", None) == id(existing)
                     and isinstance(cached_positions, dict) else None)
        request = {
            "id": uuid.uuid4().hex, "profileKey": self.profile_context.key,
            "generation": self._profile_generation, "path": str(self.mining_catalog_file),
            "resetAt": str(self._mining_catalog.get("resetAt") or ""),
            "revision": getattr(self, "_mining_catalog_revision", 0),
            "rows": rows, "status": status,
            "searchRefresh": bool(search_refresh),
        }
        archive = getattr(self, "_history_archive", None)
        archive_path = getattr(self, "history_archive_file", None)
        if archive_path is None and hasattr(self, "config_dir"):
            archive_path = Path(self.config_dir) / "data_history.sqlite3"
        self._active_mining_observation_batch = request

        def worker():
            result = dict(request)
            try:
                result.update(prepare_mining_batch(
                    existing, rows, positions=positions, archive=archive,
                    archive_path=archive_path, transient_fields=MINING_TRANSIENT_FIELDS,
                ))
            except Exception as exc:
                LOGGER.exception("Mining observation merge failed")
                result["error"] = type(exc).__name__
            self.miningObservationBatchFinished.emit(result)

        if not self._start_network_worker(worker, "mining-observation-merge"):
            self._active_mining_observation_batch = None
            return False
        return True


    @Slot(object)
    def _finish_mining_observation_batch(self, result):
        active = getattr(self, "_active_mining_observation_batch", None)
        if not active or active.get("id") != result.get("id"):
            return
        self._active_mining_observation_batch = None
        if not self._mining_batch_context_matches(result):
            return  # Explicit reset/profile switch must not resurrect old data.
        if (result.get("error") or result.get("revision") != getattr(
                self, "_mining_catalog_revision", 0)):
            # A baseline/current-system refresh landed while this snapshot was
            # merging. Rebase every observation, rather than overwrite it.
            self._pending_mining_candidates = [
                *result["rows"], *self._pending_mining_candidates,
            ]
            if result.get("error"):
                self._mining_sync_status = "Ring merge deferred · observations retained for retry"
                self.miningChanged.emit()
                return
        else:
            candidates = result["candidates"]
            self._mining_catalog = {
                "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "resetAt": result["resetAt"],
                "identityVersion": MINING_CATALOG_IDENTITY_VERSION,
                "candidates": candidates,
            }
            self._mining_catalog_revision = result["revision"] + 1
            self._mining_catalog_positions = result["positions"]
            self._mining_catalog_positions_identity = id(candidates)
            self._add_mining_system_names(result["rows"])
            self._mining_rows_cache_key = None
            self._mining_find_cache_key = None
            self._mining_find_cache = []
            self._save_mining_catalog()
            self._mining_sync_status = result.get("status") or (
                f"EDDN live · {len(result['rows'])} observations merged · "
                f"{len(candidates)} rings cached"
            )
            if result.get("archiveError"):
                self._eddn_status = "History archive could not be written; active data was retained."
                self.connectionChanged.emit()
            self.miningChanged.emit()
            self.stateChanged.emit()
        pending = self._pending_mining_candidates
        if pending and not getattr(self, "_shutdown_complete", False):
            self._pending_mining_candidates = []
            if not self._dispatch_mining_observation_batch(
                    pending, search_refresh=bool(active.get("searchRefresh"))):
                self._pending_mining_candidates = pending


    def _dispatch_hge_observation_batch(self, snapshots, additions):
        active = getattr(self, "_active_hge_observation_batch", None)
        if active and (active["generation"] != self._profile_generation
                       or active["path"] != str(self.hge_cache_file)
                       or active["profileKey"] != self.profile_context.key):
            self._active_hge_observation_batch = active = None
        if active:
            self._pending_bgs_snapshots = [*snapshots, *self._pending_bgs_snapshots]
            self._pending_hge_observations = [*additions, *self._pending_hge_observations]
            return
        base = self._hge_sightings
        request = {"id": uuid.uuid4().hex, "generation": self._profile_generation,
                   "profileKey": self.profile_context.key, "path": str(self.hge_cache_file),
                   "base": base, "snapshots": snapshots, "additions": additions}
        archive = self._history_archive
        self._active_hge_observation_batch = request

        def worker():
            result = dict(request)
            try:
                result.update(prepare_hge_batch(
                    base, snapshots, additions, limit=HGE_OBSERVATION_LIMIT,
                    archive=archive, displaced_rows=self._hge_displaced_history_rows,
                    next_expiry=self._hge_next_expiry_epoch,
                ))
            except Exception as exc:
                result["error"] = type(exc).__name__
                LOGGER.exception("Live signal batch failed")
            self.hgeObservationBatchFinished.emit(result)

        if not self._start_network_worker(worker, "hge-observation-merge"):
            self._active_hge_observation_batch = None
            self._pending_bgs_snapshots = [*snapshots, *self._pending_bgs_snapshots]
            self._pending_hge_observations = [*additions, *self._pending_hge_observations]

    @Slot(object)
    def _finish_hge_observation_batch(self, result):
        active = getattr(self, "_active_hge_observation_batch", None)
        if not active or active["id"] != result.get("id"):
            return
        self._active_hge_observation_batch = None
        if (result["generation"] != self._profile_generation
                or result["profileKey"] != self.profile_context.key
                or result["path"] != str(self.hge_cache_file)):
            return  # Original-profile inputs were archived by the worker.
        if result.get("error") or result["base"] is not self._hge_sightings:
            self._pending_bgs_snapshots = [*result["snapshots"], *self._pending_bgs_snapshots]
            self._pending_hge_observations = [*result["additions"], *self._pending_hge_observations]
            if result.get("error"):
                self._eddn_listener_status = "Live signal merge deferred · observations retained for retry"
                self.connectionChanged.emit()
                return
            self.flushHgeObservationBatch(True)
            return
        self._last_hge_batch_stats = result["stats"]
        self._next_hge_expiry_epoch = result["nextExpiry"]
        if result["changed"]:
            self._hge_sightings = result["sightings"]
            self._save_hge_cache(already_partitioned=True)
            self.hgeChanged.emit()
            if self._selected_material:
                self.selectMaterial(str(self._selected_material.get("key") or ""))
        if result.get("archiveError"):
            self._eddn_status = "History archive could not be written; active data was retained."
        self._eddn_listener_status = (
            f"Connected · {len(self._hge_sightings)} local observations · max 24 h"
        )
        self.connectionChanged.emit()
        if getattr(self, "_state_find_refresh_batch_pending", False):
            totals = getattr(self, "_state_find_refresh_batch_totals", {})
            self._state_find_refresh_batch_totals = {
                name: int(totals.get(name, 0)) + int(result["stats"].get(name, 0))
                for name in ("bgsApplied", "signalsMerged", "expiredRemoved")
            }
        if (self._pending_bgs_snapshots or self._pending_hge_observations) and not getattr(
                self, "_shutdown_complete", False):
            self.flushHgeObservationBatch(True)
        if (getattr(self, "_state_find_refresh_batch_pending", False)
                and not getattr(self, "_active_hge_observation_batch", None)):
            self._state_find_refresh_batch_pending = False
            self._complete_state_find_refresh(self._state_find_refresh_batch_totals)

    def _apply_hge_observation_batch_sync(self, snapshots, hge_rows):
        """Final shutdown/headless persistence retains the original contract."""
        previous_sightings = list(self._hge_sightings)
        updated, applied = apply_system_bgs_snapshot_batch(self._hge_sightings, snapshots, None)
        updated, hge_changed = merge_hge_observation_batch(updated, hge_rows, None)
        displaced = self._hge_displaced_history_rows(previous_sightings, updated, snapshots, hge_rows)
        if displaced and not self._archive_history("hge_observations", displaced):
            updated.extend(displaced)
        active, historical = partition_hge_observations(updated)
        overflow_count = max(0, len(active) - HGE_OBSERVATION_LIMIT)
        retired = [*historical, *active[:overflow_count]]
        if retired and self._archive_history("hge_observations", retired):
            updated, removed = active[overflow_count:], len(retired)
        elif retired:
            removed = 0
        else:
            updated, removed = active[overflow_count:], 0
        self._last_hge_batch_stats = {"bgsApplied": int(applied or 0),
                                      "signalsMerged": len(hge_rows) if hge_changed else 0,
                                      "expiredRemoved": int(removed or 0)}
        if applied or hge_changed or removed:
            self._hge_sightings = updated
            self._save_hge_cache(already_partitioned=True)
            self.hgeChanged.emit()
            if self._selected_material:
                self.selectMaterial(str(self._selected_material.get("key") or ""))
        self._next_hge_expiry_epoch = self._hge_next_expiry_epoch(self._hge_sightings)
        return removed

    @Slot()
    def flushHgeObservationBatch(self, force=False):
        force = bool(force or getattr(self, "_shutdown_complete", False))
        active_hge = getattr(self, "_active_hge_observation_batch", None)
        if active_hge and getattr(self, "_shutdown_complete", False):
            self._active_hge_observation_batch = None
            if (active_hge["generation"] == self._profile_generation
                    and active_hge["path"] == str(self.hge_cache_file)
                    and active_hge["profileKey"] == self.profile_context.key):
                self._pending_bgs_snapshots = [*active_hge["snapshots"], *self._pending_bgs_snapshots]
                self._pending_hge_observations = [*active_hge["additions"], *self._pending_hge_observations]
        active = getattr(self, "_active_mining_observation_batch", None)
        if active:
            if not self._mining_batch_context_matches(active):
                self._active_mining_observation_batch = None
            elif getattr(self, "_shutdown_complete", False):
                # Qt completion signals may still be queued after joining a
                # worker. Reclaim its inputs for the final synchronous save;
                # its late result cannot overwrite this durable snapshot.
                self._active_mining_observation_batch = None
                self._pending_mining_candidates = [
                    *active["rows"], *self._pending_mining_candidates,
                ]
        pending_snapshots = self._pending_bgs_snapshots
        snapshots_due = bool(pending_snapshots) and (
            force or time.monotonic() - getattr(
                self, "_last_bgs_batch_monotonic", 0.0
            ) >= BGS_OBSERVATION_BATCH_SECONDS
        )
        snapshots = pending_snapshots if snapshots_due else []
        if snapshots_due:
            self._pending_bgs_snapshots = []
            self._last_bgs_batch_monotonic = time.monotonic()
        hge_rows = self._pending_hge_observations
        self._pending_hge_observations = []
        pending_mining = getattr(self, "_pending_mining_candidates", [])
        pending_powerplay = getattr(
            self, "_pending_mining_powerplay_observations", []
        )
        observation_batch_due = bool(
            pending_mining or pending_powerplay
        ) and (
            force or time.monotonic() - getattr(
                self, "_last_mining_batch_monotonic", 0.0
            ) >= MINING_OBSERVATION_BATCH_SECONDS
        )
        mining_due = (bool(pending_mining) and observation_batch_due
                      and not getattr(self, "_active_mining_observation_batch", None))
        powerplay_due = bool(pending_powerplay) and observation_batch_due
        mining_rows = pending_mining if mining_due else []
        powerplay_rows = pending_powerplay if powerplay_due else []
        if observation_batch_due:
            if mining_due:
                self._pending_mining_candidates = []
            self._pending_mining_powerplay_observations = []
            self._last_mining_batch_monotonic = time.monotonic()
        if (
            not snapshots and not hge_rows and not mining_rows
            and not powerplay_rows
            and time.time() < getattr(self, "_next_hge_expiry_epoch", 0)
        ):
            return
        hge_due = bool(snapshots or hge_rows or (
            self._hge_sightings and (force or time.time() >= getattr(self, "_next_hge_expiry_epoch", 0))))
        removed = 0
        if hge_due:
            if hasattr(self, "_network_threads_lock") and not getattr(self, "_shutdown_complete", False):
                self._dispatch_hge_observation_batch(snapshots, hge_rows)
            else:
                removed = self._apply_hge_observation_batch_sync(snapshots, hge_rows)
        if mining_rows and not self._dispatch_mining_observation_batch(mining_rows):
            existing = self._mining_catalog.get("candidates", [])
            existing = existing if isinstance(existing, list) else []
            positions = self._mining_positions_for(existing)
            merged, displaced = merge_mining_candidate_batch(
                existing, mining_rows, positions=positions,
            )
            preserved = self._archive_history(
                "mining_observations", mining_rows
            )
            preserved = self._archive_history(
                "mining_catalog", displaced,
            ) and preserved
            candidates = (
                merged if preserved else [
                    *existing, *mining_rows,
                ]
            )
            self._compact_mining_catalog_rows(candidates)
            self._mining_catalog = {
                "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "resetAt": str(self._mining_catalog.get("resetAt") or ""),
                "identityVersion": MINING_CATALOG_IDENTITY_VERSION,
                "candidates": candidates,
            }
            self._mining_catalog_revision = getattr(
                self, "_mining_catalog_revision", 0
            ) + 1
            if candidates is merged:
                self._mining_catalog_positions = positions
            else:
                self._mining_catalog_positions = mining_candidate_positions(
                    candidates
                )
            self._mining_catalog_positions_identity = id(candidates)
            self._add_mining_system_names(mining_rows)
            self._mining_rows_cache_key = None
            self._mining_find_cache_key = None
            self._mining_find_cache = []
            self._save_mining_catalog()
            self._mining_sync_status = (
                f"EDDN live · {len(mining_rows)} observations merged · "
                f"{len(self._mining_catalog['candidates'])} rings cached"
            )
            self.miningChanged.emit()
            self.stateChanged.emit()
        if powerplay_rows and self._publish_mining_powerplay(powerplay_rows):
            self.miningChanged.emit()
            self.stateChanged.emit()
        self._eddn_listener_status = (
            f"Connected · {len(self._hge_sightings)} local observations · max 24 h"
        )
        if snapshots or hge_rows or mining_rows or powerplay_rows or removed:
            self.connectionChanged.emit()


    @staticmethod
    def _hge_next_expiry_epoch(observations):
        """Find the exact next retention deadline for the idle batch timer."""
        deadlines = []
        for row in observations or []:
            if not isinstance(row, dict) or row.get("self_test"):
                continue
            try:
                observed = datetime.fromisoformat(str(
                    row.get("signal_timestamp") or row.get("received_at") or ""
                ).replace("Z", "+00:00"))
                if observed.tzinfo is None:
                    observed = observed.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
            lifetime = 86400
            reported = int(row.get("time_remaining", 0) or 0)
            if (
                str(row.get("evidence_kind") or "") in {
                    "EDDN_SIGNAL", "LOCAL_JOURNAL", "ENTERED",
                }
                and reported > 0
            ):
                lifetime = min(lifetime, reported)
            deadlines.append(observed.timestamp() + lifetime)
        now = time.time()
        if any(value <= now for value in deadlines):
            return 0
        return min(deadlines, default=float("inf"))


    @Slot(str)
    def setTraderPreference(self, value):
        value = str(value or "").casefold()
        if value not in {"confirmed", "nearest"}:
            return
        if value == self._trader_preference:
            return
        self._trader_preference = value
        self._save_ui_config()
        self.uiChanged.emit()
        self.refresh()
