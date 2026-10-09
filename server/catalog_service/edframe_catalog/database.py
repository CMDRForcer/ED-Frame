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
        purge_invalid_shipyard_trade_in_values(conn)
        seed_reference_catalog(conn)


def purge_invalid_shipyard_trade_in_values(
    conn: psycopg.Connection,
) -> None:
    """Remove active-ship trade-in valuations uploaded as station offers.

    Current Elite builds can emit an ``id: 0`` PriceList row containing the
    fitted current ship's 90% resale value.  Older ED-Frame clients accepted
    that row as a purchase offer.  Clean both the normalized index and source
    snapshot, then let the bundled static catalog restore the hull reference.
    """
    conn.execute(
        """
        UPDATE station_shipyards yard
        SET ships = COALESCE((
                SELECT jsonb_agg(entry.value ORDER BY entry.ordinality)
                FROM jsonb_array_elements(yard.ships)
                     WITH ORDINALITY entry(value, ordinality)
                WHERE NOT (
                    jsonb_typeof(entry.value) = 'object'
                    AND COALESCE(
                        NULLIF(entry.value ->> 'id', '')::BIGINT, 1
                    ) <= 0
                )
            ), '[]'::jsonb),
            updated_at = NOW()
        WHERE yard.source LIKE 'ED-Frame Journal · Shipyard.json%'
          AND EXISTS (
              SELECT 1
              FROM jsonb_array_elements(yard.ships) entry(value)
              WHERE jsonb_typeof(entry.value) = 'object'
                AND COALESCE(
                    NULLIF(entry.value ->> 'id', '')::BIGINT, 1
                ) <= 0
          )
        """
    )
    conn.execute(
        """
        WITH invalid AS MATERIALIZED (
            SELECT DISTINCT ship_symbol
            FROM station_ship_offers
            WHERE ship_id <= 0
              AND price_source LIKE 'ED-Frame Journal · Shipyard.json%'
        ), removed AS (
            DELETE FROM station_ship_offers offer
            USING invalid
            WHERE offer.ship_symbol = invalid.ship_symbol
              AND offer.ship_id <= 0
              AND offer.price_source LIKE
                  'ED-Frame Journal · Shipyard.json%'
            RETURNING invalid.ship_symbol
        )
        UPDATE ship_catalog catalog
        SET reference_price = NULL,
            reference_price_observed_at = NULL,
            reference_price_source = NULL,
            reference_price_samples = 0,
            updated_at = NOW()
        WHERE catalog.symbol IN (SELECT ship_symbol FROM removed)
        """
    )
    conn.execute(
        """
        DELETE FROM station_shipyards
        WHERE source LIKE 'ED-Frame Journal · Shipyard.json%'
          AND ships = '[]'::jsonb
        """
    )


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
        ship_prices_payload = json.loads(
            (data_dir / "ship_reference_prices.json").read_text(
                encoding="utf-8"
            )
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
    ship_prices = (
        ship_prices_payload.get("ships", {})
        if isinstance(ship_prices_payload, dict) else {}
    )
    price_captured_at = str(
        ship_prices_payload.get("capturedAt") or ""
    ) if isinstance(ship_prices_payload, dict) else ""
    ship_rows = []
    if isinstance(ships_payload, list):
        for ship in ships_payload:
            if not isinstance(ship, dict):
                continue
            symbol = str(ship.get("symbol") or "").strip()
            display_name = str(ship.get("name") or "").strip()
            if not symbol or not display_name:
                continue
            price_row = ship_prices.get(symbol.casefold())
            price_row = price_row if isinstance(price_row, dict) else {}
            reference_price = price_row.get("referencePrice")
            if not isinstance(reference_price, int) or reference_price <= 0:
                reference_price = None
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
                "reference_price": reference_price,
                "reference_price_observed_at": (
                    price_captured_at or None
                ),
                "reference_price_source": (
                    f"Static reference · {price_row.get('source')}"
                    if reference_price else None
                ),
            })
    if ship_rows:
        conn.execute(
            """
            INSERT INTO ship_catalog
                (symbol, display_name, manufacturer, ship_size, maximum_speed,
                 boost_speed, specifications, source, reference_price,
                 reference_price_observed_at, reference_price_source,
                 reference_price_samples, updated_at)
            SELECT symbol, display_name, manufacturer, ship_size,
                   maximum_speed, boost_speed, specifications, source,
                   reference_price, reference_price_observed_at::TIMESTAMPTZ,
                   reference_price_source, 0, NOW()
            FROM jsonb_to_recordset(%s::jsonb) AS incoming(
                symbol TEXT, display_name TEXT, manufacturer TEXT,
                ship_size TEXT, maximum_speed INTEGER, boost_speed INTEGER,
                specifications JSONB, source TEXT, reference_price BIGINT,
                reference_price_observed_at TEXT,
                reference_price_source TEXT
            )
            ON CONFLICT (symbol) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                manufacturer = EXCLUDED.manufacturer,
                ship_size = EXCLUDED.ship_size,
                maximum_speed = EXCLUDED.maximum_speed,
                boost_speed = EXCLUDED.boost_speed,
                specifications = EXCLUDED.specifications,
                source = EXCLUDED.source,
                reference_price = EXCLUDED.reference_price,
                reference_price_observed_at =
                    EXCLUDED.reference_price_observed_at,
                reference_price_source = EXCLUDED.reference_price_source,
                reference_price_samples = 0,
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
               OR (ship_catalog.reference_price,
                   ship_catalog.reference_price_observed_at,
                   ship_catalog.reference_price_source,
                   ship_catalog.reference_price_samples)
                  IS DISTINCT FROM
                  (EXCLUDED.reference_price,
                   EXCLUDED.reference_price_observed_at,
                   EXCLUDED.reference_price_source, 0)
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


def upsert_powerplay_snapshot(conn: psycopg.Connection, row: dict | None, *, allow_equal=True) -> int:
    if not row:
        return 0
    comparison = ">=" if allow_equal else ">"
    conn.execute(f"""
        INSERT INTO mining_powerplay
            (identity, system_name, system_address, x, y, z,
             observed_at, received_at, facts)
        VALUES (%(identity)s, %(system_name)s, %(system_address)s,
                %(x)s, %(y)s, %(z)s, %(observed_at)s, %(received_at)s,
                %(facts)s::jsonb)
        ON CONFLICT (identity) DO UPDATE SET
            system_name = EXCLUDED.system_name,
            system_address = COALESCE(EXCLUDED.system_address, mining_powerplay.system_address),
            x = COALESCE(EXCLUDED.x, mining_powerplay.x),
            y = COALESCE(EXCLUDED.y, mining_powerplay.y),
            z = COALESCE(EXCLUDED.z, mining_powerplay.z),
            observed_at = EXCLUDED.observed_at,
            received_at = EXCLUDED.received_at,
            facts = EXCLUDED.facts
        WHERE EXCLUDED.observed_at {comparison} mining_powerplay.observed_at
    """, row)
    return 1


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


def upsert_signal_systems(conn, rows):
    """Fill missing public coordinates without replacing existing catalog facts."""
    for row in rows:
        observation = json.loads(row["observation"])
        x, y, z = observation["star_pos"]
        conn.execute("""
            INSERT INTO systems (name, system_address, x, y, z, observed_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET
                system_address = COALESCE(systems.system_address, EXCLUDED.system_address),
                x = COALESCE(systems.x, EXCLUDED.x),
                y = COALESCE(systems.y, EXCLUDED.y),
                z = COALESCE(systems.z, EXCLUDED.z)
        """, (row["system_name"], row["system_address"], x, y, z, row["observed_at"]))


def upsert_state_sighting_batch(conn, sightings):
    count = 0
    for row in sightings:
        conn.execute("""
            INSERT INTO state_signal_sightings
                (identity, system_address, system_name, observed_at, received_at, observation)
            VALUES (%(identity)s, %(system_address)s, %(system_name)s,
                    %(observed_at)s, %(received_at)s, %(observation)s::jsonb)
            ON CONFLICT (identity) DO UPDATE SET
                observed_at = EXCLUDED.observed_at, received_at = EXCLUDED.received_at,
                observation = EXCLUDED.observation, updated_at = NOW()
            WHERE EXCLUDED.observed_at > state_signal_sightings.observed_at
        """, row)
        count += 1
    return count


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
        if row.get("station_type") or isinstance(
            row.get("fleet_carrier"), bool
        ) or bool(row.get("partial_inventory")):
            # Direct Journal observations can arrive before a matching EDDN
            # Docked/commodity message.  Retain the public station type first
            # so Fleet Carrier prices never seed the global hull reference.
            conn.execute(
                """
                INSERT INTO stations
                    (market_id, system_name, station_name, station_type,
                     fleet_carrier, observed_at, received_at, source)
                VALUES
                    (%(market_id)s, %(system_name)s, %(station_name)s,
                     %(station_type)s, %(fleet_carrier)s,
                     TIMESTAMPTZ 'epoch', %(received_at)s, %(source)s)
                ON CONFLICT (market_id) DO UPDATE SET
                    system_name = EXCLUDED.system_name,
                    station_name = EXCLUDED.station_name,
                    station_type = COALESCE(
                        NULLIF(EXCLUDED.station_type, ''), stations.station_type
                    ),
                    fleet_carrier = COALESCE(
                        EXCLUDED.fleet_carrier, stations.fleet_carrier
                    )
                """,
                row,
            )
        if kind == "SHIPYARD" and bool(row.get("partial_inventory")):
            _upsert_ship_purchase_offer(conn, row)
            projected += 1
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


def _upsert_ship_purchase_offer(
    conn: psycopg.Connection, row: dict[str, Any],
) -> None:
    """Merge one purchased hull price without replacing station inventory."""
    conn.execute(
        """
        WITH incoming AS MATERIALIZED (
            SELECT LOWER(value ->> 'name') AS symbol,
                   NULLIF(value ->> 'id', '')::BIGINT AS ship_id,
                   NULLIF(value ->> 'buyPrice', '')::BIGINT AS buy_price,
                   COALESCE(
                       NULLIF(value ->> 'priceObservedAt', '')::timestamptz,
                       %(observed_at)s::timestamptz
                   ) AS price_observed_at,
                   COALESCE(
                       NULLIF(value ->> 'priceSource', ''), %(source)s
                   ) AS price_source,
                   NULLIF(value ->> 'displayName', '') AS display_name
            FROM jsonb_array_elements(%(items)s::jsonb) entry(value)
            WHERE jsonb_typeof(value) = 'object'
              AND NULLIF(value ->> 'name', '') IS NOT NULL
              AND NULLIF(value ->> 'buyPrice', '') IS NOT NULL
        ), discovered AS (
            INSERT INTO ship_catalog
                (symbol, display_name, specifications, source, updated_at)
            SELECT symbol,
                   COALESCE(display_name, INITCAP(REPLACE(symbol, '_', ' '))),
                   '{}'::jsonb, 'ED-Frame ShipyardBuy discovery', NOW()
            FROM incoming
            ON CONFLICT (symbol) DO NOTHING
            RETURNING symbol
        )
        INSERT INTO station_ship_offers
            (market_id, ship_symbol, ship_id, buy_price, observed_at,
             price_observed_at, availability_source, price_source, updated_at)
        SELECT %(market_id)s, symbol, ship_id, buy_price,
               %(observed_at)s::timestamptz, price_observed_at,
               'ED-Frame Journal · ShipyardBuy', price_source, NOW()
        FROM incoming
        ON CONFLICT (market_id, ship_symbol) DO UPDATE SET
            ship_id = COALESCE(
                EXCLUDED.ship_id, station_ship_offers.ship_id
            ),
            buy_price = CASE
              WHEN station_ship_offers.price_observed_at IS NULL
                OR EXCLUDED.price_observed_at >=
                   station_ship_offers.price_observed_at
              THEN EXCLUDED.buy_price
              ELSE station_ship_offers.buy_price END,
            price_observed_at = GREATEST(
                EXCLUDED.price_observed_at,
                station_ship_offers.price_observed_at
            ),
            price_source = CASE
              WHEN station_ship_offers.price_observed_at IS NULL
                OR EXCLUDED.price_observed_at >=
                   station_ship_offers.price_observed_at
              THEN EXCLUDED.price_source
              ELSE station_ship_offers.price_source END,
            updated_at = NOW()
        """,
        row,
    )


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
    if kind == "SHIPYARD":
        conn.execute(
            """
            WITH incoming AS MATERIALIZED (
                SELECT LOWER(
                           CASE
                             WHEN jsonb_typeof(value) = 'object'
                               THEN value ->> 'name'
                             WHEN jsonb_typeof(value) = 'string'
                               THEN value #>> '{}'
                             ELSE NULL
                           END
                       ) AS symbol,
                       NULLIF(
                           CASE WHEN jsonb_typeof(value) = 'object'
                                  THEN value ->> 'displayName'
                                ELSE NULL END,
                           ''
                       ) AS display_name
                FROM jsonb_array_elements(%(items)s::jsonb) entry(value)
                WHERE jsonb_typeof(value) IN ('object', 'string')
            )
            INSERT INTO ship_catalog
                (symbol, display_name, specifications, source, updated_at)
            SELECT symbol,
                   COALESCE(
                       display_name,
                       INITCAP(REPLACE(symbol, '_', ' '))
                   ),
                   '{}'::jsonb,
                   'ED-Frame automatic ship discovery',
                   NOW()
            FROM incoming
            WHERE NULLIF(symbol, '') IS NOT NULL
            ON CONFLICT (symbol) DO NOTHING
            """,
            row,
        )


def refresh_ship_reference_prices(
    conn: psycopg.Connection, *, market_id: int | None = None,
) -> None:
    """Learn one global default per hull from current non-carrier observations.

    The most frequently observed price wins.  A tie prefers the higher value,
    which lets an early discounted observation be corrected once an ordinary
    station reports the list price.  Exact station observations always remain
    authoritative for their own market.
    """
    conn.execute(
        """
        WITH affected AS MATERIALIZED (
            SELECT DISTINCT ship_symbol
            FROM station_ship_offers
            WHERE buy_price IS NOT NULL
              AND (%(market_id)s::BIGINT IS NULL OR market_id = %(market_id)s)
        ), candidates AS MATERIALIZED (
            SELECT o.ship_symbol, o.buy_price,
                   COUNT(*)::INTEGER AS samples,
                   MAX(o.price_observed_at) AS last_observed_at
            FROM station_ship_offers o
            JOIN affected a ON a.ship_symbol = o.ship_symbol
            LEFT JOIN stations s ON s.market_id = o.market_id
            WHERE o.buy_price IS NOT NULL
              AND o.buy_price > 0
              AND s.fleet_carrier IS NOT TRUE
            GROUP BY o.ship_symbol, o.buy_price
        ), ranked AS MATERIALIZED (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY ship_symbol
                ORDER BY samples DESC, buy_price DESC, last_observed_at DESC
            ) AS preference
            FROM candidates
        )
        UPDATE ship_catalog catalog
        SET reference_price = ranked.buy_price,
            reference_price_observed_at = ranked.last_observed_at,
            reference_price_source = 'ED-Frame observed station consensus',
            reference_price_samples = ranked.samples,
            updated_at = NOW()
        FROM ranked
        WHERE ranked.preference = 1
          AND catalog.symbol = ranked.ship_symbol
          AND (catalog.reference_price, catalog.reference_price_observed_at,
               catalog.reference_price_samples)
              IS DISTINCT FROM
              (ranked.buy_price, ranked.last_observed_at, ranked.samples)
        """,
        {"market_id": market_id},
    )


def record_state(
    conn: psycopg.Connection,
    *,
    schema: str,
    received_at: str,
    messages: int = 1,
    projected: int = 0,
    errors: int = 0,
    message_bytes: int = 0,
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
    used_messages = messages if projected > 0 and errors == 0 else 0
    ignored_messages = messages if projected == 0 and errors == 0 else 0
    conn.execute(
        """
        INSERT INTO collector_schema_metrics_hourly
            (bucket_start, schema, messages_total, used_messages_total,
             projected_rows_total, ignored_messages_total, errors_total,
             bytes_total, last_received_at)
        VALUES
            (date_trunc('hour', %(received_at)s::timestamptz), %(schema)s,
             %(messages)s, %(used_messages)s, %(projected)s,
             %(ignored_messages)s, %(errors)s, %(message_bytes)s,
             %(received_at)s)
        ON CONFLICT (bucket_start, schema) DO UPDATE SET
            messages_total =
                collector_schema_metrics_hourly.messages_total
                + EXCLUDED.messages_total,
            used_messages_total =
                collector_schema_metrics_hourly.used_messages_total
                + EXCLUDED.used_messages_total,
            projected_rows_total =
                collector_schema_metrics_hourly.projected_rows_total
                + EXCLUDED.projected_rows_total,
            ignored_messages_total =
                collector_schema_metrics_hourly.ignored_messages_total
                + EXCLUDED.ignored_messages_total,
            errors_total =
                collector_schema_metrics_hourly.errors_total
                + EXCLUDED.errors_total,
            bytes_total =
                collector_schema_metrics_hourly.bytes_total
                + EXCLUDED.bytes_total,
            last_received_at = GREATEST(
                collector_schema_metrics_hourly.last_received_at,
                EXCLUDED.last_received_at
            )
        """,
        {
            "received_at": received_at,
            "schema": str(schema or "unknown"),
            "messages": max(0, int(messages)),
            "used_messages": max(0, int(used_messages)),
            "projected": max(0, int(projected)),
            "ignored_messages": max(0, int(ignored_messages)),
            "errors": max(0, int(errors)),
            "message_bytes": max(0, int(message_bytes)),
        },
    )
