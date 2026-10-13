"""Explicit, validated API startup for deployments without schema changes."""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
import re

from .database import connection, ensure_schema

_LOG = logging.getLogger(__name__)
VERIFIED_SCHEMA_ENV = "EDFRAME_VERIFIED_SCHEMA_SHA256"


def prepare_api_schema():
    expected = os.environ.get(VERIFIED_SCHEMA_ENV, "")
    if not expected:
        ensure_schema()
        return

    # The operator supplies this only after verifying an unchanged installed
    # schema. A changed bundle or missing relation fails without issuing DDL.
    schema = Path(__file__).with_name("schema.sql").read_bytes()
    if hashlib.sha256(schema).hexdigest() != expected:
        raise RuntimeError("Verified schema fingerprint does not match this API bundle")
    text = schema.decode("utf-8")
    tables = re.findall(r"CREATE TABLE IF NOT EXISTS ([a-z_]+)", text)
    indexes = re.findall(r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS ([a-z_]+)", text)
    relations = sorted(set(tables + indexes))
    if not tables or not indexes:
        raise RuntimeError("Verified schema bundle contains no table/index contract")
    with connection() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout = '2s'")
        rows = conn.execute(
            "SELECT name, to_regclass('public.' || name) IS NOT NULL AS present "
            "FROM unnest(%s::text[]) name",
            (relations,),
        ).fetchall()
    missing = [row["name"] for row in rows if not row["present"]]
    if len(rows) != len(relations) or missing:
        raise RuntimeError("Verified schema is missing relations: " + ", ".join(missing))
    _LOG.info("Verified existing API schema; no startup DDL required")
