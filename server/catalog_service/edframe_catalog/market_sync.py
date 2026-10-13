"""Indexed market sync pages with the existing station-enrichment contract."""
from __future__ import annotations

# Every market belongs to exactly one ordered stream: its own receipt when it
# is at least as new as the station, otherwise the newer station receipt.
# Taking at most N keys from each stream is sufficient for the first N combined
# keys. Only that small page joins full station/system metadata.
# LATERAL keeps station-only changes ordered through stations_received_idx and
# the markets primary key; no scan/sort of the complete enriched catalog.
_QUERY = """
WITH market_changes AS MATERIALIZED (
    SELECT m.received_at AS sync_at, m.market_id, m.commodity
    FROM markets m
    LEFT JOIN stations st ON st.market_id = m.market_id
    WHERE (m.received_at, m.market_id, m.commodity)
          > (%(cursor_at)s, %(cursor_market_id)s, %(cursor_commodity)s)
      AND (st.received_at IS NULL OR m.received_at >= st.received_at)
      {commodity_filter}
    ORDER BY m.received_at, m.market_id, m.commodity
    LIMIT %(batch_size)s
), station_changes AS MATERIALIZED (
    SELECT st.received_at AS sync_at, st.market_id, m.commodity
    FROM stations st
    CROSS JOIN LATERAL (
        SELECT m.commodity
        FROM markets m
        WHERE m.market_id = st.market_id
          AND m.received_at < st.received_at
          AND (st.received_at, st.market_id, m.commodity)
              > (%(cursor_at)s, %(cursor_market_id)s, %(cursor_commodity)s)
          {commodity_filter}
        ORDER BY m.commodity
        LIMIT %(batch_size)s
    ) m
    WHERE (st.received_at, st.market_id)
          >= (%(cursor_at)s, %(cursor_market_id)s)
    ORDER BY st.received_at, st.market_id, m.commodity
    LIMIT %(batch_size)s
), page AS MATERIALIZED (
    SELECT *
    FROM (
        SELECT * FROM market_changes
        UNION ALL
        SELECT * FROM station_changes
    ) candidates
    ORDER BY sync_at, market_id, commodity
    LIMIT %(batch_size)s
), changed AS (

    SELECT m.market_id, m.commodity,
           COALESCE(NULLIF(st.station_name, ''), m.station_name)
               AS station_name,
           COALESCE(NULLIF(st.system_name, ''), m.system_name)
               AS system_name,
           m.mean_price, m.buy_price, m.stock, m.stock_bracket,
           m.sell_price, m.demand, m.demand_bracket,
           m.status_flags, m.observed_at, m.received_at,
           s.x, s.y, s.z, m.source,
           st.station_type, st.system_address,
           st.landing_pad_size, st.distance_to_arrival_ls,
           st.services, st.economies, st.primary_economy,
           st.government, st.controlling_faction,
           st.fleet_carrier, st.carrier_docking_access,
           st.prohibited,
           GREATEST(
               m.received_at,
               COALESCE(st.received_at, m.received_at)
           ) AS sync_at
    FROM page p
    JOIN markets m
      ON (m.market_id, m.commodity) = (p.market_id, p.commodity)
    LEFT JOIN systems s
      ON LOWER(s.name) = LOWER(m.system_name)
    LEFT JOIN stations st ON st.market_id = m.market_id
)
SELECT market_id AS "marketId", commodity,
       station_name AS station, system_name AS system,
       mean_price AS "meanPrice", buy_price AS "buyPrice",
       stock, stock_bracket AS "stockBracket",
       sell_price AS "sellPrice", demand,
       demand_bracket AS "demandBracket",
       status_flags AS "statusFlags",
       observed_at AS "observedAt", received_at AS "receivedAt",
       x, y, z, source,
       station_type AS "stationType",
       system_address AS "systemAddress",
       landing_pad_size AS "landingPadSize",
       distance_to_arrival_ls AS "distanceToArrivalLs",
       services, economies, primary_economy AS "primaryEconomy",
       government, controlling_faction AS "controllingFaction",
       fleet_carrier AS "fleetCarrier",
       carrier_docking_access AS "carrierDockingAccess",
       prohibited, sync_at AS "syncAt"
FROM changed
ORDER BY sync_at, market_id, commodity
LIMIT %(batch_size)s
"""


def market_sync_query(
    cursor_at, cursor_market_id, cursor_commodity, commodities, batch_size,
):
    """Build a page without changing cursor format, fields or timestamp meaning.

    batch_size includes the endpoint's extra row used to determine hasMore.
    Query structure depends only on whether a filter exists; symbols are bound
    values. Both streams see the same PostgreSQL statement snapshot.
    """
    commodity_filter = (
        "AND m.commodity = ANY(%(commodities)s)" if commodities else ""
    )
    return _QUERY.format(commodity_filter=commodity_filter), {
        "cursor_at": cursor_at,
        "cursor_market_id": cursor_market_id,
        "cursor_commodity": cursor_commodity,
        "commodities": list(commodities),
        "batch_size": batch_size,
    }
