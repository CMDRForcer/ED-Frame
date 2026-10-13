import hashlib
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from edframe_catalog import startup


class ApiStartupTests(unittest.TestCase):
    def setUp(self):
        self.schema = Path(startup.__file__).with_name("schema.sql").read_bytes()
        self.fingerprint = hashlib.sha256(self.schema).hexdigest()
        self.conn = MagicMock()
        self.factory = MagicMock()
        self.factory.return_value.__enter__.return_value = self.conn
        self.conn.execute.return_value.fetchall.return_value = []

    def test_default_startup_still_initializes_schema(self):
        with patch.dict(startup.os.environ, {}, clear=True), patch.object(startup, "ensure_schema") as initialize:
            startup.prepare_api_schema()
        initialize.assert_called_once_with()

    def test_verified_bundle_checks_installed_relations_without_ddl(self):
        def execute(sql, params=None):
            cursor = MagicMock()
            if params:
                cursor.fetchall.return_value = [{"name": name, "present": True} for name in params[0]]
            return cursor
        self.conn.execute.side_effect = execute
        with patch.dict(startup.os.environ, {startup.VERIFIED_SCHEMA_ENV:self.fingerprint}), patch.object(startup, "connection", self.factory), patch.object(startup, "ensure_schema") as initialize:
            startup.prepare_api_schema()
        initialize.assert_not_called()
        statements = [str(c.args[0]) for c in self.conn.execute.call_args_list]
        self.assertIn("SET TRANSACTION READ ONLY", statements)
        self.assertFalse(any("CREATE" in sql or "ALTER" in sql or "UPDATE" in sql for sql in statements))

    def test_different_bundle_fails_before_connecting_or_writing(self):
        with patch.dict(startup.os.environ, {startup.VERIFIED_SCHEMA_ENV:"invalid"}), patch.object(startup, "connection", self.factory), patch.object(startup, "ensure_schema") as initialize:
            with self.assertRaisesRegex(RuntimeError, "fingerprint"):
                startup.prepare_api_schema()
        self.factory.assert_not_called()
        initialize.assert_not_called()

    def test_missing_database_relation_rejects_verified_mode_without_ddl(self):
        self.conn.execute.return_value.fetchall.return_value = [{"name":"markets", "present":False}]
        with patch.dict(startup.os.environ, {startup.VERIFIED_SCHEMA_ENV:self.fingerprint}), patch.object(startup, "connection", self.factory), patch.object(startup, "ensure_schema") as initialize:
            with self.assertRaisesRegex(RuntimeError, "missing relations.*markets"):
                startup.prepare_api_schema()
        initialize.assert_not_called()

    def test_database_failure_never_falls_back_to_schema_writes(self):
        self.factory.side_effect = RuntimeError("database unavailable")
        with patch.dict(startup.os.environ, {startup.VERIFIED_SCHEMA_ENV:self.fingerprint}), patch.object(startup, "connection", self.factory), patch.object(startup, "ensure_schema") as initialize:
            with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                startup.prepare_api_schema()
        initialize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
