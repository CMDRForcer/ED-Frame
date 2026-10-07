-- One latest snapshot per system, not an indefinitely growing event archive.
CREATE TABLE IF NOT EXISTS mining_powerplay (
    identity TEXT PRIMARY KEY,
    system_name TEXT NOT NULL,
    system_address BIGINT,
    x DOUBLE PRECISION, y DOUBLE PRECISION, z DOUBLE PRECISION,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    facts JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS mining_powerplay_observed_idx ON mining_powerplay (observed_at);

CREATE TABLE IF NOT EXISTS systems (
    name TEXT PRIMARY KEY,
    system_address BIGINT,
    x DOUBLE PRECISION,
    y DOUBLE PRECISION,
    z DOUBLE PRECISION,
    observed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS systems_address_idx ON systems (system_address);
CREATE INDEX IF NOT EXISTS systems_name_lower_idx ON systems (LOWER(name));

CREATE TABLE IF NOT EXISTS stations (
    market_id BIGINT PRIMARY KEY,
    system_name TEXT NOT NULL,
    station_name TEXT NOT NULL,
    system_address BIGINT,
    station_type TEXT,
    landing_pad_size TEXT,
    distance_to_arrival_ls DOUBLE PRECISION,
    services JSONB,
    economies JSONB,
    primary_economy TEXT,
    government TEXT,
    controlling_faction TEXT,
    fleet_carrier BOOLEAN,
    carrier_docking_access TEXT,
    prohibited JSONB,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS stations_system_idx ON stations (LOWER(system_name));
CREATE INDEX IF NOT EXISTS stations_services_idx ON stations USING GIN (services);
CREATE INDEX IF NOT EXISTS stations_received_idx
    ON stations (received_at, market_id);

CREATE TABLE IF NOT EXISTS station_outfitting (
    market_id BIGINT PRIMARY KEY,
    system_name TEXT NOT NULL,
    station_name TEXT NOT NULL,
    modules JSONB NOT NULL,
    horizons BOOLEAN,
    odyssey BOOLEAN,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS station_outfitting_modules_idx
    ON station_outfitting USING GIN (modules);
CREATE INDEX IF NOT EXISTS station_outfitting_sync_idx
    ON station_outfitting (updated_at, market_id);

CREATE TABLE IF NOT EXISTS station_shipyards (
    market_id BIGINT PRIMARY KEY,
    system_name TEXT NOT NULL,
    station_name TEXT NOT NULL,
    ships JSONB NOT NULL,
    horizons BOOLEAN,
    odyssey BOOLEAN,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS station_shipyards_ships_idx
    ON station_shipyards USING GIN (ships);
CREATE INDEX IF NOT EXISTS station_shipyards_sync_idx
    ON station_shipyards (updated_at, market_id);

-- Search-optimised projections of the complete JSON inventories above.  The
-- JSON rows remain the atomic sync contract; these rows make item lookups and
-- price/freshness sorting predictable without scanning multi-million-element
-- JSON arrays for every Finder request.
CREATE TABLE IF NOT EXISTS station_module_offers (
    market_id BIGINT NOT NULL,
    module_symbol TEXT NOT NULL,
    module_id BIGINT,
    buy_price BIGINT,
    buy_merc_coins_price BIGINT,
    observed_at TIMESTAMPTZ NOT NULL,
    price_observed_at TIMESTAMPTZ,
    availability_source TEXT NOT NULL,
    price_source TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (market_id, module_symbol)
);

CREATE INDEX IF NOT EXISTS station_module_offers_search_idx
    ON station_module_offers
       (module_symbol, observed_at DESC, buy_price NULLS LAST);
CREATE INDEX IF NOT EXISTS station_module_offers_price_idx
    ON station_module_offers (module_symbol, price_observed_at DESC)
    WHERE buy_price IS NOT NULL;

CREATE TABLE IF NOT EXISTS station_ship_offers (
    market_id BIGINT NOT NULL,
    ship_symbol TEXT NOT NULL,
    ship_id BIGINT,
    buy_price BIGINT,
    observed_at TIMESTAMPTZ NOT NULL,
    price_observed_at TIMESTAMPTZ,
    availability_source TEXT NOT NULL,
    price_source TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (market_id, ship_symbol)
);

CREATE INDEX IF NOT EXISTS station_ship_offers_search_idx
    ON station_ship_offers
       (ship_symbol, observed_at DESC, buy_price NULLS LAST);
CREATE INDEX IF NOT EXISTS station_ship_offers_price_idx
    ON station_ship_offers (ship_symbol, price_observed_at DESC)
    WHERE buy_price IS NOT NULL;

-- Public reference facts are versioned with ED-Frame and intentionally do not
-- contain Commander state. Permit/rank ownership remains local to each app.
CREATE TABLE IF NOT EXISTS module_catalog (
    symbol TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    module_class SMALLINT,
    rating TEXT,
    size_rating TEXT,
    power_draw_mw DOUBLE PRECISION,
    source TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS module_catalog_name_idx
    ON module_catalog (LOWER(display_name), symbol);

CREATE TABLE IF NOT EXISTS ship_catalog (
    symbol TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    manufacturer TEXT,
    ship_size TEXT,
    maximum_speed INTEGER,
    boost_speed INTEGER,
    reference_price BIGINT,
    reference_price_observed_at TIMESTAMPTZ,
    reference_price_source TEXT,
    reference_price_samples INTEGER NOT NULL DEFAULT 0,
    specifications JSONB NOT NULL DEFAULT '{}'::jsonb,
    source TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE ship_catalog ADD COLUMN IF NOT EXISTS reference_price BIGINT;
ALTER TABLE ship_catalog
    ADD COLUMN IF NOT EXISTS reference_price_observed_at TIMESTAMPTZ;
ALTER TABLE ship_catalog ADD COLUMN IF NOT EXISTS reference_price_source TEXT;
ALTER TABLE ship_catalog
    ADD COLUMN IF NOT EXISTS reference_price_samples INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS ship_catalog_name_idx
    ON ship_catalog (LOWER(display_name), symbol);

CREATE TABLE IF NOT EXISTS markets (
    market_id BIGINT NOT NULL,
    commodity TEXT NOT NULL,
    station_name TEXT NOT NULL,
    system_name TEXT NOT NULL,
    mean_price INTEGER,
    buy_price INTEGER,
    stock BIGINT,
    stock_bracket SMALLINT,
    sell_price INTEGER NOT NULL,
    demand BIGINT NOT NULL,
    demand_bracket SMALLINT,
    status_flags JSONB,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL DEFAULT 'EDDN commodity/3',
    PRIMARY KEY (market_id, commodity)
);

-- Idempotent migration for installations created by catalog schema v1.
ALTER TABLE markets ADD COLUMN IF NOT EXISTS mean_price INTEGER;
ALTER TABLE markets ADD COLUMN IF NOT EXISTS buy_price INTEGER;
ALTER TABLE markets ADD COLUMN IF NOT EXISTS stock BIGINT;
ALTER TABLE markets ADD COLUMN IF NOT EXISTS stock_bracket SMALLINT;
ALTER TABLE markets ADD COLUMN IF NOT EXISTS demand_bracket SMALLINT;
ALTER TABLE markets ADD COLUMN IF NOT EXISTS status_flags JSONB;

CREATE INDEX IF NOT EXISTS markets_search_idx
    ON markets (commodity, observed_at DESC, sell_price DESC);
CREATE INDEX IF NOT EXISTS markets_system_idx ON markets (LOWER(system_name));
CREATE INDEX IF NOT EXISTS markets_received_idx
    ON markets (received_at, market_id, commodity);

-- Installations created before the station catalog already contain reliable
-- market-to-station mappings. Make those stations immediately available and
-- let newer EDDN station messages enrich the optional metadata over time.
INSERT INTO stations (
    market_id,
    system_name,
    station_name,
    observed_at,
    received_at,
    source
)
SELECT DISTINCT ON (market_id)
    market_id,
    system_name,
    station_name,
    observed_at,
    received_at,
    'Backfilled from retained market catalog'
FROM markets
WHERE market_id > 0
ORDER BY market_id, observed_at DESC
ON CONFLICT (market_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS mining_sites (
    identity TEXT PRIMARY KEY,
    system_address BIGINT,
    system_name TEXT NOT NULL,
    x DOUBLE PRECISION,
    y DOUBLE PRECISION,
    z DOUBLE PRECISION,
    body_id INTEGER,
    body_name TEXT,
    ring_name TEXT NOT NULL,
    ring_type TEXT,
    reserve_level TEXT,
    distance_to_arrival_ls DOUBLE PRECISION,
    hotspots JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence TEXT NOT NULL,
    source TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS ring_reference_metadata (
    system_name TEXT NOT NULL,
    ring_name TEXT NOT NULL,
    system_address BIGINT NOT NULL,
    ring_type TEXT,
    reserve_level TEXT,
    source TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    provenance JSONB NOT NULL,
    ring_snapshot JSONB NOT NULL,
    PRIMARY KEY (system_name, ring_name)
);
CREATE INDEX IF NOT EXISTS ring_reference_system_idx
    ON ring_reference_metadata (LOWER(system_name));

CREATE INDEX IF NOT EXISTS mining_sites_observed_idx
    ON mining_sites (observed_at DESC);
CREATE INDEX IF NOT EXISTS mining_sites_system_idx
    ON mining_sites (LOWER(system_name));
CREATE INDEX IF NOT EXISTS mining_sites_hotspots_idx
    ON mining_sites USING GIN (hotspots);

CREATE TABLE IF NOT EXISTS mining_yield_samples (
    sample_id TEXT PRIMARY KEY,
    site_identity TEXT NOT NULL REFERENCES mining_sites(identity) ON DELETE CASCADE,
    system_address BIGINT,
    system_name TEXT NOT NULL,
    ring_name TEXT NOT NULL,
    body_id INTEGER,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL DEFAULT 'ED-Frame Journal · ProspectedAsteroid'
);

CREATE INDEX IF NOT EXISTS mining_yield_samples_site_idx
    ON mining_yield_samples (site_identity, observed_at DESC);
CREATE INDEX IF NOT EXISTS mining_yield_samples_observed_idx
    ON mining_yield_samples (observed_at DESC);

CREATE TABLE IF NOT EXISTS mining_yield_materials (
    sample_id TEXT NOT NULL REFERENCES mining_yield_samples(sample_id)
        ON DELETE CASCADE,
    commodity TEXT NOT NULL,
    proportion DOUBLE PRECISION NOT NULL CHECK (
        proportion >= 0 AND proportion <= 100
    ),
    PRIMARY KEY (sample_id, commodity)
);

CREATE INDEX IF NOT EXISTS mining_yield_materials_commodity_idx
    ON mining_yield_materials (commodity, sample_id);

CREATE TABLE IF NOT EXISTS state_bgs_snapshots (
    identity TEXT PRIMARY KEY,
    system_address BIGINT,
    system_name TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    snapshot JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS state_bgs_sync_idx
    ON state_bgs_snapshots (updated_at, identity);
CREATE INDEX IF NOT EXISTS state_bgs_observed_idx
    ON state_bgs_snapshots (observed_at DESC);

CREATE TABLE IF NOT EXISTS state_signals (
    identity TEXT PRIMARY KEY,
    system_address BIGINT,
    system_name TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    observation JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Latest public sighting per system/type/faction/state; no invented expiry.
CREATE TABLE IF NOT EXISTS state_signal_sightings (
    identity TEXT PRIMARY KEY,
    system_address BIGINT,
    system_name TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    observation JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS state_signal_sightings_sync_idx
    ON state_signal_sightings (updated_at, identity);
CREATE INDEX IF NOT EXISTS state_signal_sightings_observed_idx
    ON state_signal_sightings (observed_at DESC);

CREATE INDEX IF NOT EXISTS state_signals_sync_idx
    ON state_signals (updated_at, identity);
CREATE INDEX IF NOT EXISTS state_signals_expiry_idx
    ON state_signals (expires_at);

CREATE TABLE IF NOT EXISTS collector_state (
    source TEXT PRIMARY KEY,
    last_received_at TIMESTAMPTZ,
    last_schema TEXT,
    messages_total BIGINT NOT NULL DEFAULT 0,
    projected_total BIGINT NOT NULL DEFAULT 0,
    errors_total BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Small, bounded operational telemetry. One row per schema and UTC hour makes
-- it possible to distinguish a quiet schema from messages that arrived but did
-- not contain a fact ED-Frame currently projects. Raw EDDN frames are never
-- retained.
CREATE TABLE IF NOT EXISTS collector_schema_metrics_hourly (
    bucket_start TIMESTAMPTZ NOT NULL,
    schema TEXT NOT NULL,
    messages_total BIGINT NOT NULL DEFAULT 0,
    used_messages_total BIGINT NOT NULL DEFAULT 0,
    projected_rows_total BIGINT NOT NULL DEFAULT 0,
    ignored_messages_total BIGINT NOT NULL DEFAULT 0,
    errors_total BIGINT NOT NULL DEFAULT 0,
    bytes_total BIGINT NOT NULL DEFAULT 0,
    last_received_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (bucket_start, schema)
);

CREATE INDEX IF NOT EXISTS collector_schema_metrics_hourly_received_idx
    ON collector_schema_metrics_hourly (last_received_at DESC, schema);
