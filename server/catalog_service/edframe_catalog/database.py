from __future__ import annotations

import json
import os
from pathlib import Path
import re
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
        # Uvicorn starts two workers and the collector starts independently.
        # Serialise their idempotent DDL/backfill transaction so concurrent
        # startup cannot deadlock while acquiring table and index locks.
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (45444652414,))
        conn.execute(schema)
        seed_reference_catalog(conn)


def _reference_data_dir() -> Path | None:
    resolved = Path(__file__).resolve()
    candidates = [Path("/app/ed_data"), resolved.parents[1] / "ed_data"]
    if len(resolved.parents) > 3:
        candidates.append(resolved.parents[3] / "ed_data")
    return next((path for path in candidates if path.is_dir()), None)


def seed_reference_catalog(conn: psycopg.Connection) -> None:
    """Upsert the small public module/ship identity catalog shipped by ED-Frame."""
    data_dir = _reference_data_dir()
    if data_dir is None:
        return
    try:
        display_payload = json.loads(
            (data_dir / "module_display.json").read_text(encoding="utf-8")
        )
        power_payload = json.loads(
            (data_dir / "module_power.json").read_text(encoding="utf-8")
        )
        ships_payload = json.loads(
            (data_dir / "ships.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValueError, TypeError):
        return
    display_modules = display_payload.get("modules", {})
    power_modules = power_payload.get("modules", {})
    module_rows = []
    if isinstance(display_modules, dict):
        for raw_symbol, raw_display in display_modules.items():
            if (
                not isinstance(raw_display, list) or len(raw_display) < 2
                or not str(raw_symbol).strip() or not str(raw_display[0]).strip()
            ):
                continue
            size_rating = str(raw_display[1] or "").strip().upper()
            match = re.fullmatch(r"(\d+)([A-Z])", size_rating)
            power = power_modules.get(raw_symbol, {})
            module_rows.append({
                "symbol": str(raw_symbol).strip().casefold(),
                "display_name": str(raw_display[0]).strip(),
                "module_class": int(match.group(1)) if match else None,
                "rating": match.group(2) if match else None,
                "size_rating": size_rating or None,
                "power_draw_mw": (
                    power.get("powerDrawMW")
                    if isinstance(power, dict) else None
                ),
                "source": str(display_payload.get("source") or "ED-Frame"),
            })
    if module_rows:
        conn.execute(
            """
            INSERT INTO module_catalog
                (symbol, display_name, module_class, rating, size_rating,
                 power_draw_mw, source, updated_at)
            SELECT symbol, display_name, module_class, rating, size_rating,
                   power_draw_mw, source, NOW()
            FROM jsonb_to_recordset(%s::jsonb) AS incoming(
                symbol TEXT, display_name TEXT, module_class SMALLINT,
                rating TEXT, size_rating TEXT, power_draw_mw DOUBLE PRECISION,
                source TEXT
            )
            ON CONFLICT (symbol) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                module_class = EXCLUDED.module_class,
                rating = EXCLUDED.rating,
                size_rating = EXCLUDED.size_rating,
                power_draw_mw = EXCLUDED.power_draw_mw,
                source = EXCLUDED.source,
                updated_at = NOW()
            WHERE (module_catalog.display_name, module_catalog.module_class,
                   module_catalog.rating, module_catalog.size_rating,
                   module_catalog.power_draw_mw, module_catalog.source)
                  IS DISTINCT FROM
                  (EXCLUDED.display_name, EXCLUDED.module_class,
                   EXCLUDED.rating, EXCLUDED.size_rating,
                   EXCLUDED.power_draw_mw, EXCLUDED.source)
            """,
            (json.dumps(module_rows),),
        )
    ship_rows = []
    if isinstance(ships_payload, list):
        for ship in ships_payload:
            if not isinstance(ship, dict):
                continue
            symbol = str(ship.get("symbol") or "").strip()
            display_name = str(ship.get("name") or "").strip()
            if not symbol or not display_name:
                continue
            ship_rows.append({
                "symbol": symbol.casefold(),
                "display_name": display_name,
                "manufacturer": ship.get("manufacturer"),
                "ship_size": ship.get("size"),
                "maximum_speed": ship.get("maximumSpeed"),
                "boost_speed": ship.get("boost"),
                "specifications": {
                    key: ship[key] for key in (
                        "core", "hardpoints", "utility", "optional"
                    ) if key in ship
                },
                "source": "ED-Frame ship reference catalog",
            })
    if ship_rows:
        conn.execute(
            """
            INSERT INTO ship_catalog
                (symbol, display_name, manufacturer, ship_size, maximum_speed,
                 boost_speed, specifications, source, updated_at)
            SELECT symbol, display_name, manufacturer, ship_size,
                   maximum_speed, boost_speed, specifications, source, NOW()
            FROM jsonb_to_recordset(%s::jsonb) AS incoming(
                symbol TEXT, display_name TEXT, manufacturer TEXT,
                ship_size TEXT, maximum_speed INTEGER, boost_speed INTEGER,
                specifications JSONB, source TEXT
            )
            ON CONFLICT (symbol) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                manufacturer = EXCLUDED.manufacturer,
                ship_size = EXCLUDED.ship_size,
                maximum_speed = EXCLUDED.maximum_speed,
                boost_speed = EXCLUDED.boost_speed,
                specifications = EXCLUDED.specifications,
                source = EXCLUDED.source,
                updated_at = NOW()
            WHERE (ship_catalog.display_name, ship_catalog.manufacturer,
                   ship_catalog.ship_size, ship_catalog.maximum_speed,
                   ship_catalog.boost_speed, ship_catalog.specifications,
                   ship_catalog.source)
                  IS DISTINCT FROM
                  (EXCLUDED.display_name, EXCLUDED.manufacturer,
                   EXCLUDED.ship_size, EXCLUDED.maximum_speed,
                   EXCLUDED.boost_speed, EXCLUDED.specifications,
                   EXCLUDED.source)
            """,
            (json.dumps(ship_rows),),
        )


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


def upsert_yield_observations(
    conn: psycopg.Connection,
    observations: Iterable[dict[str, Any]],
) -> int:
    """Retain de-duplicated anonymous Journal prospector observations."""
    projected = 0
    for row in observations:
        conn.execute(
            """
            INSERT INTO mining_sites
                (identity, system_address, system_name, x, y, z, body_id,
                 body_name, ring_name, ring_type, reserve_level,
                 distance_to_arrival_ls, hotspots, evidence, source,
                 observed_at, received_at)
            VALUES
                (%(site_identity)s, %(system_address)s, %(system_name)s,
                 %(x)s, %(y)s, %(z)s, %(body_id)s, %(body_name)s,
                 %(ring_name)s, %(ring_type)s, %(reserve_level)s,
                 %(distance_to_arrival_ls)s, '[]'::jsonb, 'LIVE_REPORTED',
                 'ED-Frame community yield', %(observed_at)s,
                 %(received_at)s)
            ON CONFLICT (identity) DO UPDATE SET
                system_address = COALESCE(
                    EXCLUDED.system_address, mining_sites.system_address
                ),
                x = COALESCE(EXCLUDED.x, mining_sites.x),
                y = COALESCE(EXCLUDED.y, mining_sites.y),
                z = COALESCE(EXCLUDED.z, mining_sites.z),
                body_id = COALESCE(EXCLUDED.body_id, mining_sites.body_id),
                body_name = COALESCE(
                    NULLIF(EXCLUDED.body_name, ''), mining_sites.body_name
                ),
                ring_type = COALESCE(
                    NULLIF(EXCLUDED.ring_type, ''), mining_sites.ring_type
                ),
                reserve_level = COALESCE(
                    NULLIF(EXCLUDED.reserve_level, ''),
                    mining_sites.reserve_level
                ),
                distance_to_arrival_ls = COALESCE(
                    EXCLUDED.distance_to_arrival_ls,
                    mining_sites.distance_to_arrival_ls
                ),
                observed_at = GREATEST(
                    EXCLUDED.observed_at, mining_sites.observed_at
                ),
                received_at = GREATEST(
                    EXCLUDED.received_at, mining_sites.received_at
                )
            """,
            row,
        )
        conn.execute(
            """
            INSERT INTO mining_yield_samples
                (sample_id, site_identity, system_address, system_name,
                 ring_name, body_id, observed_at, received_at, source)
            VALUES
                (%(sample_id)s, %(site_identity)s, %(system_address)s,
                 %(system_name)s, %(ring_name)s, %(body_id)s,
                 %(observed_at)s, %(received_at)s, %(source)s)
            ON CONFLICT (sample_id) DO NOTHING
            """,
            row,
        )
        for commodity, proportion in (row.get("materials") or {}).items():
            conn.execute(
                """
                INSERT INTO mining_yield_materials
                    (sample_id, commodity, proportion)
                VALUES (%s, %s, %s)
                ON CONFLICT (sample_id, commodity) DO NOTHING
                """,
                (row["sample_id"], commodity, proportion),
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
            items_update = """
                CASE
                  WHEN EXCLUDED.source = 'EDDN outfitting/2' THEN (
                    SELECT COALESCE(
                      jsonb_agg(
                        COALESCE(
                          (
                            SELECT retained.value
                            FROM jsonb_array_elements(
                              station_outfitting.modules
                            ) retained(value)
                            WHERE jsonb_typeof(retained.value) = 'object'
                              AND LOWER(retained.value ->> 'name') = LOWER(
                                incoming.value #>> '{}'
                              )
                            LIMIT 1
                          ),
                          incoming.value
                        ) ORDER BY incoming.ordinality
                      ),
                      '[]'::jsonb
                    )
                    FROM jsonb_array_elements(EXCLUDED.modules)
                      WITH ORDINALITY incoming(value, ordinality)
                  )
                  ELSE EXCLUDED.modules
                END
            """
        elif kind == "SHIPYARD":
            table, items_column = "station_shipyards", "ships"
            items_update = """
                CASE
                  WHEN EXCLUDED.source = 'EDDN shipyard/2' THEN (
                    SELECT COALESCE(
                      jsonb_agg(
                        COALESCE(
                          (
                            SELECT retained.value
                            FROM jsonb_array_elements(
                              station_shipyards.ships
                            ) retained(value)
                            WHERE jsonb_typeof(retained.value) = 'object'
                              AND LOWER(retained.value ->> 'name') = LOWER(
                                incoming.value #>> '{}'
                              )
                            LIMIT 1
                          ),
                          incoming.value
                        ) ORDER BY incoming.ordinality
                      ),
                      '[]'::jsonb
                    )
                    FROM jsonb_array_elements(EXCLUDED.ships)
                      WITH ORDINALITY incoming(value, ordinality)
                  )
                  ELSE EXCLUDED.ships
                END
            """
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
                {items_column} = {items_update},
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
        _replace_normalized_station_offers(
            conn, row, kind=kind, parent_table=table
        )
        projected += 1
    return projected


def _replace_normalized_station_offers(
    conn: psycopg.Connection,
    row: dict[str, Any],
    *,
    kind: str,
    parent_table: str,
) -> None:
    """Keep a query-friendly projection of one accepted complete inventory."""
    if kind == "OUTFITTING":
        target = "station_module_offers"
        symbol_column = "module_symbol"
        id_column = "module_id"
        merc_select = """
            CASE WHEN jsonb_typeof(value) = 'object'
                 THEN NULLIF(value ->> 'buyMercCoinsPrice', '')::BIGINT
                 ELSE NULL END
        """
        merc_insert_columns = ", buy_merc_coins_price"
        merc_select_column = ", buy_merc_coins_price"
        merc_update = """
            buy_merc_coins_price = CASE
              WHEN EXCLUDED.buy_price IS NOT NULL
               AND (station_module_offers.price_observed_at IS NULL
                    OR EXCLUDED.price_observed_at >=
                       station_module_offers.price_observed_at)
                THEN EXCLUDED.buy_merc_coins_price
              ELSE station_module_offers.buy_merc_coins_price END,
        """
    else:
        target = "station_ship_offers"
        symbol_column = "ship_symbol"
        id_column = "ship_id"
        merc_select = "NULL::BIGINT"
        merc_insert_columns = ""
        merc_select_column = ""
        merc_update = ""
    conn.execute(
        f"""
        WITH eligible AS MATERIALIZED (
            SELECT 1
            WHERE %(observed_at)s::timestamptz >= COALESCE(
                (SELECT observed_at FROM {parent_table}
                 WHERE market_id = %(market_id)s),
                '-infinity'::timestamptz
            )
        ), incoming AS MATERIALIZED (
            SELECT LOWER(
                       CASE
                         WHEN jsonb_typeof(value) = 'object'
                           THEN value ->> 'name'
                         WHEN jsonb_typeof(value) = 'string'
                           THEN value #>> '{{}}'
                         ELSE NULL
                       END
                   ) AS symbol,
                   CASE WHEN jsonb_typeof(value) = 'object'
                        THEN NULLIF(value ->> 'id', '')::BIGINT
                        ELSE NULL END AS item_id,
                   CASE WHEN jsonb_typeof(value) = 'object'
                        THEN NULLIF(value ->> 'buyPrice', '')::BIGINT
                        ELSE NULL END AS buy_price,
                   {merc_select} AS buy_merc_coins_price,
                   CASE WHEN jsonb_typeof(value) = 'object'
                         AND NULLIF(value ->> 'priceObservedAt', '') IS NOT NULL
                        THEN (value ->> 'priceObservedAt')::timestamptz
                        WHEN jsonb_typeof(value) = 'object'
                         AND NULLIF(value ->> 'buyPrice', '') IS NOT NULL
                        THEN %(observed_at)s::timestamptz
                        ELSE NULL END AS price_observed_at,
                   CASE WHEN jsonb_typeof(value) = 'object'
                        THEN NULLIF(value ->> 'priceSource', '')
                        ELSE NULL END AS price_source
            FROM eligible,
                 jsonb_array_elements(%(items)s::jsonb) entry(value)
            WHERE jsonb_typeof(value) IN ('object', 'string')
              AND NULLIF(
                    CASE WHEN jsonb_typeof(value) = 'object'
                           THEN value ->> 'name'
                         ELSE value #>> '{{}}' END,
                    ''
                  ) IS NOT NULL
        ), removed AS (
            DELETE FROM {target} current
            WHERE current.market_id = %(market_id)s
              AND EXISTS (SELECT 1 FROM eligible)
              AND NOT EXISTS (
                  SELECT 1 FROM incoming
                  WHERE incoming.symbol = current.{symbol_column}
              )
            RETURNING 1
        )
        INSERT INTO {target}
            (market_id, {symbol_column}, {id_column}, buy_price
             {merc_insert_columns}, observed_at, price_observed_at,
             availability_source, price_source, updated_at)
        SELECT %(market_id)s, symbol, item_id, buy_price
               {merc_select_column}, %(observed_at)s::timestamptz,
               price_observed_at, %(source)s, price_source, NOW()
        FROM incoming
        ON CONFLICT (market_id, {symbol_column}) DO UPDATE SET
            {id_column} = COALESCE(EXCLUDED.{id_column}, {target}.{id_column}),
            buy_price = CASE
              WHEN EXCLUDED.buy_price IS NOT NULL
               AND ({target}.price_observed_at IS NULL
                    OR EXCLUDED.price_observed_at >= {target}.price_observed_at)
                THEN EXCLUDED.buy_price
              ELSE {target}.buy_price END,
            {merc_update}
            observed_at = EXCLUDED.observed_at,
            price_observed_at = CASE
              WHEN EXCLUDED.buy_price IS NOT NULL
               AND ({target}.price_observed_at IS NULL
                    OR EXCLUDED.price_observed_at >= {target}.price_observed_at)
                THEN EXCLUDED.price_observed_at
              ELSE {target}.price_observed_at END,
            availability_source = EXCLUDED.availability_source,
            price_source = CASE
              WHEN EXCLUDED.buy_price IS NOT NULL
               AND ({target}.price_observed_at IS NULL
                    OR EXCLUDED.price_observed_at >= {target}.price_observed_at)
                THEN EXCLUDED.price_source
              ELSE {target}.price_source END,
            updated_at = NOW()
        """,
        row,
    )


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
