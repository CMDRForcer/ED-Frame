"""Bounded parallel Mining Finder retrieval with per-task HTTP sessions."""

from concurrent.futures import ThreadPoolExecutor
import math
import time

import requests

from .mining_finder import fetch_edframe_mining_candidates
from .mining_snapshot import MiningSnapshotStore
from .mining_market import (
    fetch_edframe_system_coordinates, fetch_edsm_system_coordinates,
    fetch_market_imports,
)
from .mining_powerplay import fetch_edframe_powerplay


def fetch_mining_refresh(query, *, origin=None, include_edframe=True,
                         session_factory=None, is_current=None, snapshot_path=None,
                         region_cache=None, prepare_sites=None, max_workers=3,
                         merit_context=None, merit_market_cache=None, site_commodity=None,
                         known_market_reader=None):
    """Retrieve independent domains concurrently without sharing a Session.

    Cursor-dependent ring pages remain sequential within their reusable
    connection. Market provider order, fallback, limits and freshness are
    deliberately unchanged. Complete regional reads may be reused briefly;
    markets always execute. Every future is joined before returning.
    """
    session_factory = session_factory or requests.Session

    def session_get(session):
        def get(*args, **kwargs):
            if is_current is not None and not is_current():
                raise RuntimeError("Mining lookup superseded or shutting down")
            return session.get(*args, **kwargs)
        return get

    result = {}
    if not origin:
        with session_factory() as session:
            get = session_get(session)
            if include_edframe:
                try:
                    origin = fetch_edframe_system_coordinates(
                        query["startSystem"], get=get,
                    )
                except Exception:
                    pass
            if not origin:
                try:
                    origin = fetch_edsm_system_coordinates(
                        query["startSystem"], get=get,
                    )
                except Exception as exc:
                    result["originError"] = str(exc)
    if origin:
        result["origin"] = origin
    coordinates = (origin or {}).get("coordinates")
    radius = max(1, query["nearbyLy"])
    site_query = {**query, "commodity": site_commodity} if site_commodity else query
    powerplay_query = {**query, '_powerplayPower': (merit_context or {}).get('power', ''),
                      '_powerplayGoal': (merit_context or {}).get('goal', '')}

    def prepare_site_result(data):
        # Prepare a complete site domain as soon as it is available, overlapping
        # slow Powerplay/market I/O. No partial publication or shared Session.
        rows = data.get("serverCandidates")
        if prepare_sites is not None and rows:
            started = time.monotonic()
            try:
                if is_current is None or is_current():
                    prepared = prepare_sites(rows)
                    if is_current is None or is_current():
                        data["preparedRings"] = prepared
            except Exception as exc:
                # The original complete raw domain remains available for the
                # normal merge/retry path; a preparation failure loses no data.
                data["ringPreparationError"] = type(exc).__name__
            data["ringPreparationSeconds"] = round(time.monotonic() - started, 3)
        return data

    def fetch_domain(kind):
        started = time.monotonic()
        cache_started = region_cache.now() if region_cache is not None else None
        data = {}
        try:
            cache_fields = {"sites": ("serverCandidates", "siteCoverage"),
                            "powerplay": ("serverPowerplay", "powerplayCoverage")}
            if region_cache is not None and kind in cache_fields:
                if is_current is not None and not is_current():
                    raise RuntimeError("Mining lookup superseded or shutting down")
                reused = region_cache.get(kind, site_query if kind == "sites" else powerplay_query, origin)
                if reused is not None:
                    if is_current is not None and not is_current():
                        raise RuntimeError("Mining lookup superseded or shutting down")
                    rows_key, coverage_key = cache_fields[kind]
                    data = {rows_key: reused[0], coverage_key: reused[1]}
                    seconds = time.monotonic() - started
                    return prepare_site_result(data), seconds
            with session_factory() as session:
                get = session_get(session)
                if kind == "sites":
                    data["siteCoverage"] = {}
                    snapshot_options = ({"snapshot_store": MiningSnapshotStore(snapshot_path)}
                                        if snapshot_path else {})
                    data["serverCandidates"] = fetch_edframe_mining_candidates(
                        query["startSystem"], get,
                        commodity=site_query["commodity"], origin=coordinates,
                        max_distance=radius, timeout=10,
                        diagnostics=data["siteCoverage"],
                        **({"max_rows": 200_000} if site_query["commodity"] == "allcommodities" else {}),
                        **snapshot_options,
                    )
                    snapshot = data["siteCoverage"].pop("_snapshot", None)
                    if snapshot_path and snapshot:
                        data["siteSnapshot"] = snapshot
                elif kind == "powerplay":
                    data["powerplayCoverage"] = {}
                    data["serverPowerplay"] = fetch_edframe_powerplay(
                        origin=coordinates, max_distance=radius,
                        get=get, diagnostics=data["powerplayCoverage"],
                        **({'merit_context': merit_context} if merit_context else {}),
                    )
                else:
                    data["providerStatus"] = {}
                    hours = max(1, query["maxMarketAgeHours"])
                    data["markets"] = fetch_market_imports(
                        query["startSystem"], query["commodity"],
                        max_distance=radius,
                        max_days_ago=max(1, min(14, math.ceil(hours / 24))),
                        get=get, landing_pad=query["landingPad"],
                        include_edframe=include_edframe,
                        provider_status=data["providerStatus"],
                        origin=origin, max_age_hours=hours,
                    )
                    data["success"] = True
            if region_cache is not None and kind in cache_fields:
                rows_key, coverage_key = cache_fields[kind]
                region_cache.put(kind, site_query if kind == "sites" else powerplay_query, origin, data[rows_key], data[coverage_key],
                                 started_at=cache_started, is_current=is_current)
        except Exception as exc:
            error_key = {"sites": "siteError", "powerplay": "powerplayError"}.get(kind)
            if error_key:
                data[error_key] = str(exc)
            else:
                data.update(success=False, error=str(exc))
        seconds = time.monotonic() - started
        return prepare_site_result(data), seconds

    domains = ["markets"]
    if include_edframe and origin:
        domains = ["sites", "powerplay", "markets"]
    timings = {}
    with ThreadPoolExecutor(max_workers=max(1, min(3, int(max_workers), len(domains))), thread_name_prefix="mining-fetch") as pool:
        futures = {kind: pool.submit(fetch_domain, kind) for kind in domains}
        for kind, future in futures.items():
            data, seconds = future.result()
            result.update(data)
            timings[kind] = round(seconds, 3)
    result["fetchTimings"] = timings
    if (merit_context and include_edframe and result.get('serverCandidates')
            and result.get('serverPowerplay') and (is_current is None or is_current())):
        from .mining_merit_markets import fill_merit_markets
        started = time.monotonic()
        known_markets = ()
        if merit_context.get('allCommodities') and known_market_reader is not None:
            try:
                known_markets = known_market_reader(result.get('origin')) or ()
            except Exception:
                pass  # Losing cache reuse must not lose the fresh public path.
        result['markets'], result['meritMarketCoverage'] = fill_merit_markets(
            result['serverCandidates'], result['serverPowerplay'], result.get('markets', []),
            query, {**merit_context, '_originCoordinates': coordinates}, session_factory=session_factory, cache=merit_market_cache,
            is_current=is_current, max_workers=min(2, max_workers), known_markets=known_markets)
        from .mining_powerplay import merge_powerplay_observations
        batch_facts = result['meritMarketCoverage'].pop('_powerplayFacts', [])
        exact_rings = result['meritMarketCoverage'].pop('_siteCandidates', [])
        if exact_rings:
            from .mining_finder import merge_mining_candidates
            result['serverCandidates'] = merge_mining_candidates([*result['serverCandidates'], *exact_rings])
            # Earlier preparation described only the regional ring domain.
            result.pop('preparedRings', None)
            prepare_site_result(result)
        if batch_facts:
            result['serverPowerplay'] = merge_powerplay_observations(
                result['serverPowerplay'], batch_facts, limit=100_000)
        timings['meritMarkets'] = round(time.monotonic() - started, 3)
        if result['meritMarketCoverage']['addedRows']:
            result['success'] = True
    return result
