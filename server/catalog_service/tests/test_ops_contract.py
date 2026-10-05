from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OperationsContractTests(unittest.TestCase):
    def test_maintenance_never_deletes_last_known_catalog_facts(self):
        script = (ROOT / "ops" / "catalog-maintenance.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("DELETE FROM markets", script)
        self.assertNotIn("DELETE FROM state_bgs_snapshots", script)
        self.assertNotIn("DELETE FROM mining_yield_samples", script)
        self.assertIn(
            "DELETE FROM state_signals WHERE expires_at <= NOW()", script
        )

    def test_maintenance_has_non_destructive_disk_thresholds(self):
        script = (ROOT / "ops" / "catalog-maintenance.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('"$disk_usage" -ge 70', script)
        self.assertIn('"$disk_usage" -ge 85', script)
        self.assertIn("exit 2", script)

    def test_container_logs_are_bounded(self):
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("x-logging: &bounded-logging", compose)
        self.assertEqual(compose.count("logging: *bounded-logging"), 4)
        self.assertIn('max-size: "20m"', compose)
        self.assertIn('max-file: "3"', compose)


if __name__ == "__main__":
    unittest.main()
