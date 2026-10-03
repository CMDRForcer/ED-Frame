import unittest
from pathlib import Path


SERVICE = Path(__file__).resolve().parents[1]


class SchemaContractTests(unittest.TestCase):
    def test_schema_is_additive_and_idempotent(self):
        schema = (SERVICE / "edframe_catalog" / "schema.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS stations", schema)
        for column in (
            "mean_price", "buy_price", "stock", "stock_bracket",
            "demand_bracket", "status_flags",
        ):
            self.assertIn(
                f"ALTER TABLE markets ADD COLUMN IF NOT EXISTS {column}",
                schema,
            )
        self.assertNotIn("DROP TABLE", schema.upper())
        self.assertNotIn("TRUNCATE", schema.upper())
        self.assertIn("Backfilled from retained market catalog", schema)
        self.assertIn("ON CONFLICT (market_id) DO NOTHING", schema)
        self.assertIn("markets_received_idx", schema)
        self.assertIn("stations_received_idx", schema)

    def test_public_api_exposes_station_and_full_market_contract(self):
        source = (SERVICE / "edframe_catalog" / "api.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('@app.get("/v1/stations/search")', source)
        self.assertIn("LEFT JOIN stations st ON st.market_id = m.market_id", source)
        for field in (
            '"meanPrice"', '"buyPrice"', '"stockBracket"',
            '"demandBracket"', '"statusFlags"', '"receivedAt"',
        ):
            self.assertIn(field, source)
        self.assertIn('Query(pattern="^(S|M|L)$")', source)
        self.assertIn('"S": ("S", "M", "L")', source)
        self.assertIn('"M": ("M", "L")', source)
        self.assertIn('"L": ("L",)', source)
        self.assertIn("st.fleet_carrier IS NOT TRUE", source)
        self.assertIn('@app.get("/v1/sync/markets")', source)
        self.assertIn("nextCursor", source)
        self.assertIn("ORDER BY sync_at, market_id, commodity", source)


if __name__ == "__main__":
    unittest.main()
