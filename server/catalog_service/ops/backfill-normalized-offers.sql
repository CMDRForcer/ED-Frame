\set ON_ERROR_STOP on

BEGIN;

INSERT INTO station_module_offers
    (market_id, module_symbol, module_id, buy_price, buy_merc_coins_price,
     observed_at, price_observed_at, availability_source, price_source,
     updated_at)
SELECT o.market_id,
       LOWER(CASE WHEN jsonb_typeof(entry.value) = 'object'
                    THEN entry.value ->> 'name'
                  ELSE entry.value #>> '{}' END),
       CASE WHEN jsonb_typeof(entry.value) = 'object'
              THEN NULLIF(entry.value ->> 'id', '')::BIGINT END,
       CASE WHEN jsonb_typeof(entry.value) = 'object'
              THEN NULLIF(entry.value ->> 'buyPrice', '')::BIGINT END,
       CASE WHEN jsonb_typeof(entry.value) = 'object'
              THEN NULLIF(entry.value ->> 'buyMercCoinsPrice', '')::BIGINT END,
       o.observed_at,
       CASE WHEN jsonb_typeof(entry.value) = 'object'
             AND NULLIF(entry.value ->> 'priceObservedAt', '') IS NOT NULL
              THEN (entry.value ->> 'priceObservedAt')::TIMESTAMPTZ
            WHEN jsonb_typeof(entry.value) = 'object'
             AND NULLIF(entry.value ->> 'buyPrice', '') IS NOT NULL
              THEN o.observed_at END,
       o.source,
       CASE WHEN jsonb_typeof(entry.value) = 'object'
              THEN NULLIF(entry.value ->> 'priceSource', '') END,
       NOW()
FROM station_outfitting o
CROSS JOIN LATERAL jsonb_array_elements(o.modules) entry(value)
WHERE jsonb_typeof(entry.value) IN ('object', 'string')
  AND NULLIF(CASE WHEN jsonb_typeof(entry.value) = 'object'
                    THEN entry.value ->> 'name'
                  ELSE entry.value #>> '{}' END, '') IS NOT NULL
ON CONFLICT (market_id, module_symbol) DO UPDATE SET
    module_id = COALESCE(EXCLUDED.module_id, station_module_offers.module_id),
    buy_price = COALESCE(EXCLUDED.buy_price, station_module_offers.buy_price),
    buy_merc_coins_price = COALESCE(
        EXCLUDED.buy_merc_coins_price,
        station_module_offers.buy_merc_coins_price
    ),
    observed_at = GREATEST(
        EXCLUDED.observed_at, station_module_offers.observed_at
    ),
    price_observed_at = COALESCE(
        EXCLUDED.price_observed_at,
        station_module_offers.price_observed_at
    ),
    availability_source = EXCLUDED.availability_source,
    price_source = COALESCE(
        EXCLUDED.price_source, station_module_offers.price_source
    ),
    updated_at = NOW();

INSERT INTO station_ship_offers
    (market_id, ship_symbol, ship_id, buy_price, observed_at,
     price_observed_at, availability_source, price_source, updated_at)
SELECT y.market_id,
       LOWER(CASE WHEN jsonb_typeof(entry.value) = 'object'
                    THEN entry.value ->> 'name'
                  ELSE entry.value #>> '{}' END),
       CASE WHEN jsonb_typeof(entry.value) = 'object'
              THEN NULLIF(entry.value ->> 'id', '')::BIGINT END,
       CASE WHEN jsonb_typeof(entry.value) = 'object'
              THEN NULLIF(entry.value ->> 'buyPrice', '')::BIGINT END,
       y.observed_at,
       CASE WHEN jsonb_typeof(entry.value) = 'object'
             AND NULLIF(entry.value ->> 'priceObservedAt', '') IS NOT NULL
              THEN (entry.value ->> 'priceObservedAt')::TIMESTAMPTZ
            WHEN jsonb_typeof(entry.value) = 'object'
             AND NULLIF(entry.value ->> 'buyPrice', '') IS NOT NULL
              THEN y.observed_at END,
       y.source,
       CASE WHEN jsonb_typeof(entry.value) = 'object'
              THEN NULLIF(entry.value ->> 'priceSource', '') END,
       NOW()
FROM station_shipyards y
CROSS JOIN LATERAL jsonb_array_elements(y.ships) entry(value)
WHERE jsonb_typeof(entry.value) IN ('object', 'string')
  AND NULLIF(CASE WHEN jsonb_typeof(entry.value) = 'object'
                    THEN entry.value ->> 'name'
                  ELSE entry.value #>> '{}' END, '') IS NOT NULL
ON CONFLICT (market_id, ship_symbol) DO UPDATE SET
    ship_id = COALESCE(EXCLUDED.ship_id, station_ship_offers.ship_id),
    buy_price = COALESCE(EXCLUDED.buy_price, station_ship_offers.buy_price),
    observed_at = GREATEST(EXCLUDED.observed_at, station_ship_offers.observed_at),
    price_observed_at = COALESCE(
        EXCLUDED.price_observed_at, station_ship_offers.price_observed_at
    ),
    availability_source = EXCLUDED.availability_source,
    price_source = COALESCE(EXCLUDED.price_source, station_ship_offers.price_source),
    updated_at = NOW();

COMMIT;

ANALYZE station_module_offers;
ANALYZE station_ship_offers;
