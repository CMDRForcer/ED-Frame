"""Exact, bounded market batches; no regional price top-list truncation."""
from datetime import datetime, timezone
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ed_companion.navigation.mining_commodities import MINING_COMMODITIES
from ed_companion.navigation.mining_planner import _powerplay_index, _merit_status
from .database import connection


class MarketTarget(BaseModel):
    model_config = ConfigDict(extra='forbid')
    system: str = Field(min_length=1, max_length=100)
    commodities: list[str] = Field(min_length=1, max_length=40)

    @field_validator('system')
    @classmethod
    def system_name(cls, value):
        value = value.strip().casefold()
        if not value:
            raise ValueError('Empty system')
        return value


class MeritMarketQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    targets: list[MarketTarget] = Field(min_length=1, max_length=200)
    power: str = Field(min_length=3, max_length=100)
    goal: Literal['REINFORCE', 'UNDERMINE', 'ACQUIRE']
    method: Literal['LASER', 'CORE', 'SUBSURFACE', 'RHINO SURFACE']
    opposingPower: str = Field(default='ANY', max_length=100)
    minDemand: int = Field(default=0, ge=0, le=1000000000000)
    maxAgeHours: int = Field(default=48, ge=1, le=2160)
    landingPad: Literal['ANY', 'S', 'M', 'L'] = 'ANY'

    @field_validator('targets')
    @classmethod
    def unique_targets(cls, targets):
        if len({target.system for target in targets}) != len(targets):
            raise ValueError('Duplicate system')
        for target in targets:
            if any(symbol not in MINING_COMMODITIES for symbol in target.commodities):
                raise ValueError('Unknown mining commodity')
        return targets


def search_merit_markets(query: MeritMarketQuery):
    now = datetime.now(timezone.utc)
    names = [target.system for target in query.targets]
    with connection() as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        conn.execute("SET LOCAL statement_timeout='10s'")
        conn.execute("SET LOCAL lock_timeout='2s'")
        snapshots = conn.execute(
            'SELECT facts FROM mining_powerplay WHERE identity = ANY(%s)', (names,)
        ).fetchall()
        facts = [fact for snapshot in snapshots for fact in snapshot['facts']]
        index = _powerplay_index(facts)
        targets, coverage = [], []
        for target in query.targets:
            symbols = sorted({symbol for symbol in target.commodities
                              if query.method in MINING_COMMODITIES[symbol]['methods']})
            status, score, _distance = _merit_status(
                {'system': target.system}, {'system': target.system}, query.power,
                query.goal, query.opposingPower, index, now=now)
            # Acquisition depends on a separate mining source and distance.
            # Unknown evidence stays explicitly unknown; the app verifies routes.
            eligible = (score is None or score > 0 or query.goal == 'ACQUIRE')
            if symbols and eligible:
                targets.append({'system': target.system, 'commodities': symbols})
            coverage.append({'system': target.system, 'status': status,
                             'commodities': symbols, 'queried': bool(symbols and eligible)})
        if not targets:
            return {'protocol': 1, 'results': [], 'coverage': coverage, 'hasMore': False,
                    'powerplay': facts}
        accepted = {'ANY': ['S', 'M', 'L', None], 'S': ['S', 'M', 'L'],
                    'M': ['M', 'L'], 'L': ['L']}[query.landingPad]
        pad_clause = '' if query.landingPad == 'ANY' else 'AND st.landing_pad_size = ANY(%s)'
        values = [json.dumps(targets), query.minDemand, query.maxAgeHours]
        if pad_clause:
            values.append(accepted)
        rows = conn.execute(f'''
            WITH targets AS (
                SELECT * FROM jsonb_to_recordset(%s::jsonb)
                    AS t(system text, commodities jsonb)
            ), offers AS (
                SELECT DISTINCT ON (LOWER(m.system_name), m.commodity)
                    m.market_id AS "marketId", m.commodity, m.system_name AS system,
                    COALESCE(NULLIF(st.station_name, ''), m.station_name) AS station,
                    m.sell_price AS "sellPrice", m.demand, m.buy_price AS "buyPrice",
                    m.mean_price AS "meanPrice", m.stock,
                    m.observed_at AS "observedAt", m.received_at AS "receivedAt", m.source,
                    st.system_address AS "systemAddress", st.station_type AS "stationType",
                    st.landing_pad_size AS "landingPadSize",
                    st.distance_to_arrival_ls AS "distanceToArrivalLs",
                    st.fleet_carrier AS "fleetCarrier", st.services, st.economies,
                    st.carrier_docking_access AS "carrierDockingAccess", st.prohibited
                FROM targets t JOIN markets m ON LOWER(m.system_name) = t.system
                LEFT JOIN stations st ON st.market_id = m.market_id
                WHERE t.commodities ? m.commodity AND m.sell_price > 0
                  AND m.demand >= %s AND m.observed_at >= NOW() - (%s * INTERVAL '1 hour')
                  AND m.observed_at <= NOW() + INTERVAL '5 minutes'
                  AND st.fleet_carrier IS NOT TRUE {pad_clause}
                ORDER BY LOWER(m.system_name), m.commodity, m.sell_price DESC,
                         m.demand DESC, m.observed_at DESC, m.market_id
            )
            SELECT o.*, s.x, s.y, s.z FROM offers o
            LEFT JOIN LATERAL (
                SELECT x,y,z FROM systems WHERE LOWER(name) = LOWER(o.system)
                ORDER BY observed_at DESC NULLS LAST, name LIMIT 1
            ) s ON TRUE
            ORDER BY LOWER(o.system), o.commodity
        ''', values).fetchall()
        # Recover rings for exact eligible systems even when a broad regional
        # snapshot stopped before them. Use the established public projection.
        from .api import _mining_sites_sql
        from .mining_metadata import enrich_ring_metadata
        ring_rows = conn.execute(_mining_sites_sql([
            'LOWER(ms.system_name) = ANY(%s)',
            "ms.observed_at >= NOW() - INTERVAL '3650 days'"
        ]), ([target['system'] for target in targets], 5001, 0)).fetchall()
        ring_has_more = len(ring_rows) > 5000
        rings = enrich_ring_metadata(conn, ring_rows[:5000])
    return {'protocol': 1, 'results': rows, 'coverage': coverage, 'hasMore': False,
            'powerplay': facts, 'rings': rings, 'ringHasMore': ring_has_more}
