from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row


def connection():
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "edframe_catalog"),
        user=os.environ.get("POSTGRES_USER", "edframe_catalog"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        row_factory=dict_row,
    )


def ensure_schema() -> None:
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with connection() as conn:
        conn.execute(schema)


def upsert_batch(
    conn: psycopg.Connection,
    systems: Iterable[dict[str, Any]],
    stations: Iterable[dict[str, Any]],
    markets: Iterable[dict[str, Any]],
    sites: Iterable[dict[str, Any]],
) -> int:
    projected = 0
    for row in systems:
        conn.execute(
            """
            INSERT INTO systems
                (name, system_address, x, y, z, observed_at, updated_at)
            VALUES
                (%(name)s, %(system_address)s, %(x)s, %(y)s, %(z)s,
                 %(observed_at)s, NOW())
            ON CONFLICT (name) DO UPDATE SET
                system_address = COALESCE(EXCLUDED.system_address, systems.system_address),
                x = COALESCE(EXCLUDED.x, systems.x),
                y = COALESCE(EXCLUDED.y, systems.y),
                z = COALESCE(EXCLUDED.z, systems.z),
                observed_at = GREATEST(EXCLUDED.observed_at, systems.observed_at),
                updated_at = NOW()
            """,
            row,
        )
        projected += 1
    for row in stations:
        conn.execute(
            """
            INSERT INTO stations
                (market_id, system_name, station_name, system_address,
                 station_type, landing_pad_size, distance_to_arrival_ls,
                 services, economies, primary_economy, government,
                 controlling_faction, fleet_carrier, carrier_docking_access,
                 prohibited, observed_at, received_at, source)
            VALUES
                (%(market_id)s, %(system_name)s, %(station_name)s,
                 %(system_address)s, %(station_type)s, %(landing_pad_size)s,
                 %(distance_to_arrival_ls)s, %(services)s::jsonb,
                 %(economies)s::jsonb, %(primary_economy)s, %(government)s,
                 %(controlling_faction)s, %(fleet_carrier)s,
                 %(carrier_docking_access)s, %(prohibited)s::jsonb,
                 %(observed_at)s, %(received_at)s, %(source)s)
            ON CONFLICT (market_id) DO UPDATE SET
                system_name = EXCLUDED.system_name,
                station_name = EXCLUDED.station_name,
                system_address = COALESCE(
                    EXCLUDED.system_address, stations.system_address
                ),
                station_type = COALESCE(
                    NULLIF(EXCLUDED.station_type, ''), stations.station_type
                ),
                landing_pad_size = COALESCE(
                    NULLIF(EXCLUDED.landing_pad_size, ''),
                    stations.landing_pad_size
                ),
                distance_to_arrival_ls = COALESCE(
                    EXCLUDED.distance_to_arrival_ls,
                    stations.distance_to_arrival_ls
                ),
                services = COALESCE(EXCLUDED.services, stations.services),
                economies = COALESCE(EXCLUDED.economies, stations.economies),
                primary_economy = COALESCE(
                    NULLIF(EXCLUDED.primary_economy, ''),
                    stations.primary_economy
                ),
                government = COALESCE(
                    NULLIF(EXCLUDED.government, ''), stations.government
                ),
                controlling_faction = COALESCE(
                    NULLIF(EXCLUDED.controlling_faction, ''),
                    stations.controlling_faction
                ),
                fleet_carrier = COALESCE(
                    EXCLUDED.fleet_carrier, stations.fleet_carrier
                ),
                carrier_docking_access = COALESCE(
                    NULLIF(EXCLUDED.carrier_docking_access, ''),
                    stations.carrier_docking_access
                ),
                prohibited = COALESCE(EXCLUDED.prohibited, stations.prohibited),
                observed_at = EXCLUDED.observed_at,
                received_at = EXCLUDED.received_at,
                source = EXCLUDED.source
            WHERE EXCLUDED.observed_at >= stations.observed_at
            """,
            {
                **row,
                "services": (
                    None if row.get("services") is None
                    else json.dumps(row["services"])
                ),
                "economies": (
                    None if row.get("economies") is None
                    else json.dumps(row["economies"])
                ),
                "prohibited": (
                    None if row.get("prohibited") is None
                    else json.dumps(row["prohibited"])
                ),
            },
        )
        projected += 1
    for row in markets:
        conn.execute(
            """
            INSERT INTO markets
                (market_id, commodity, station_name, system_name, mean_price,
                 buy_price, stock, stock_bracket, sell_price, demand,
                 demand_bracket, status_flags, observed_at, received_at)
            VALUES
                (%(market_id)s, %(commodity)s, %(station_name)s, %(system_name)s,
                 %(mean_price)s, %(buy_price)s, %(stock)s, %(stock_bracket)s,
                 %(sell_price)s, %(demand)s, %(demand_bracket)s,
                 %(status_flags)s::jsonb, %(observed_at)s, %(received_at)s)
            ON CONFLICT (market_id, commodity) DO UPDATE SET
                station_name = EXCLUDED.station_name,
                system_name = EXCLUDED.system_name,
                mean_price = EXCLUDED.mean_price,
                buy_price = EXCLUDED.buy_price,
                stock = EXCLUDED.stock,
                stock_bracket = EXCLUDED.stock_bracket,
                sell_price = EXCLUDED.sell_price,
                demand = EXCLUDED.demand,
                demand_bracket = EXCLUDED.demand_bracket,
                status_flags = EXCLUDED.status_flags,
                observed_at = EXCLUDED.observed_at,
                received_at = EXCLUDED.received_at
            WHERE EXCLUDED.observed_at >= markets.observed_at
            """,
            {
                **row,
                "status_flags": json.dumps(row.get("status_flags") or []),
            },
        )
        projected += 1
    for row in sites:
        conn.execute(
            """
            INSERT INTO mining_sites
                (identity, system_address, system_name, x, y, z, body_id,
                 body_name, ring_name, ring_type, reserve_level,
                 distance_to_arrival_ls, hotspots, evidence, source,
                 observed_at, received_at)
            VALUES
                (%(identity)s, %(system_address)s, %(system_name)s, %(x)s,
                 %(y)s, %(z)s, %(body_id)s, %(body_name)s, %(ring_name)s,
                 %(ring_type)s, %(reserve_level)s, %(distance_to_arrival_ls)s,
                 %(hotspots)s::jsonb, %(evidence)s, %(source)s,
                 %(observed_at)s, %(received_at)s)
            ON CONFLICT (identity) DO UPDATE SET
                x = COALESCE(EXCLUDED.x, mining_sites.x),
                y = COALESCE(EXCLUDED.y, mining_sites.y),
                z = COALESCE(EXCLUDED.z, mining_sites.z),
                ring_type = COALESCE(NULLIF(EXCLUDED.ring_type, ''), mining_sites.ring_type),
                reserve_level = COALESCE(NULLIF(EXCLUDED.reserve_level, ''), mining_sites.reserve_level),
                distance_to_arrival_ls = COALESCE(
                    EXCLUDED.distance_to_arrival_ls,
                    mining_sites.distance_to_arrival_ls
                ),
                hotspots = CASE
                    WHEN EXCLUDED.hotspots <> '[]'::jsonb THEN EXCLUDED.hotspots
                    ELSE mining_sites.hotspots
                END,
                evidence = EXCLUDED.evidence,
                source = EXCLUDED.source,
                observed_at = EXCLUDED.observed_at,
                received_at = EXCLUDED.received_at
            WHERE EXCLUDED.observed_at >= mining_sites.observed_at
            """,
            row,
        )
        projected += 1
    return projected


def upsert_state_find_batch(
    conn: psycopg.Connection,
    snapshots: Iterable[dict[str, Any]],
    signals: Iterable[dict[str, Any]],
) -> int:
    projected = 0
    for row in snapshots:
        conn.execute(
            """
            INSERT INTO state_bgs_snapshots
                (identity, system_address, system_name, observed_at,
                 received_at, snapshot, updated_at)
            VALUES
                (%(identity)s, %(system_address)s, %(system_name)s,
                 %(observed_at)s, %(received_at)s, %(snapshot)s::jsonb, NOW())
            ON CONFLICT (identity) DO UPDATE SET
                system_address = EXCLUDED.system_address,
                system_name = EXCLUDED.system_name,
                observed_at = EXCLUDED.observed_at,
                received_at = EXCLUDED.received_at,
                snapshot = EXCLUDED.snapshot,
                updated_at = NOW()
            WHERE EXCLUDED.observed_at >= state_bgs_snapshots.observed_at
            """,
            row,
        )
        projected += 1
    for row in signals:
        conn.execute(
            """
            INSERT INTO state_signals
                (identity, system_address, system_name, observed_at,
                 received_at, expires_at, observation, updated_at)
            VALUES
                (%(identity)s, %(system_address)s, %(system_name)s,
                 %(observed_at)s, %(received_at)s, %(expires_at)s,
                 %(observation)s::jsonb, NOW())
            ON CONFLICT (identity) DO UPDATE SET
                received_at = GREATEST(
                    EXCLUDED.received_at, state_signals.received_at
                ),
                expires_at = GREATEST(
                    EXCLUDED.expires_at, state_signals.expires_at
                ),
                observation = EXCLUDED.observation,
                updated_at = NOW()
            WHERE EXCLUDED.observed_at >= state_signals.observed_at
            """,
            row,
        )
        projected += 1
    return projected


def upsert_station_offer_batch(
    conn: psycopg.Connection,
    offers: Iterable[dict[str, Any]],
) -> int:
    """Replace one station's complete offer list when its observation is newer."""
    projected = 0
    for row in offers:
        kind = str(row.get("kind") or "").upper()
        if kind == "OUTFITTING":
            table, items_column = "station_outfitting", "modules"
        elif kind == "SHIPYARD":
            table, items_column = "station_shipyards", "ships"
        else:
            continue
        conn.execute(
            f"""
            INSERT INTO {table}
                (market_id, system_name, station_name, {items_column},
                 horizons, odyssey, observed_at, received_at, source,
                 updated_at)
            VALUES
                (%(market_id)s, %(system_name)s, %(station_name)s,
                 %(items)s::jsonb, %(horizons)s, %(odyssey)s,
                 %(observed_at)s, %(received_at)s, %(source)s, NOW())
            ON CONFLICT (market_id) DO UPDATE SET
                system_name = EXCLUDED.system_name,
                station_name = EXCLUDED.station_name,
                {items_column} = EXCLUDED.{items_column},
                horizons = EXCLUDED.horizons,
                odyssey = EXCLUDED.odyssey,
                observed_at = EXCLUDED.observed_at,
                received_at = EXCLUDED.received_at,
                source = EXCLUDED.source,
                updated_at = NOW()
            WHERE EXCLUDED.observed_at >= {table}.observed_at
            """,
            row,
        )
        projected += 1
    return projected


def record_state(
    conn: psycopg.Connection,
    *,
    schema: str,
    received_at: str,
    messages: int = 1,
    projected: int = 0,
    errors: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO collector_state
            (source, last_received_at, last_schema, messages_total,
             projected_total, errors_total)
        VALUES ('EDDN', %(received_at)s, %(schema)s, %(messages)s,
                %(projected)s, %(errors)s)
        ON CONFLICT (source) DO UPDATE SET
            last_received_at = EXCLUDED.last_received_at,
            last_schema = EXCLUDED.last_schema,
            messages_total = collector_state.messages_total + EXCLUDED.messages_total,
            projected_total = collector_state.projected_total + EXCLUDED.projected_total,
            errors_total = collector_state.errors_total + EXCLUDED.errors_total,
            updated_at = NOW()
        """,
        {
            "received_at": received_at,
            "schema": schema,
            "messages": messages,
            "projected": projected,
            "errors": errors,
        },
    )

