"""Exact statistics queries that reuse existing catalog indexes."""

# Seek the next distinct commodity through markets_search_idx instead of
# sorting millions of market rows. Both MIN and COUNT ignore NULL, preserving
# COUNT(DISTINCT commodity) semantics for empty and future catalogs as well.
COMMODITY_COUNT_SQL = """
WITH RECURSIVE observed_commodities(commodity) AS (
    SELECT MIN(commodity) FROM markets
    UNION ALL
    SELECT (
        SELECT MIN(m.commodity)
        FROM markets m
        WHERE m.commodity > previous.commodity
    )
    FROM observed_commodities previous
    WHERE previous.commodity IS NOT NULL
)
SELECT COUNT(commodity) AS value FROM observed_commodities
"""
