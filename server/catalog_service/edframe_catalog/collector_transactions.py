"""Bounded retries for PostgreSQL transactions known to have aborted."""
from __future__ import annotations

import logging
import random
import time

from psycopg.errors import DeadlockDetected, SerializationFailure

LOG = logging.getLogger("edframe.catalog.collector")
MAX_ATTEMPTS = 4


def retry_transaction(conn, operation, *, schema, received_at):
    for attempt in range(MAX_ATTEMPTS):
        try:
            result = operation()
        except (DeadlockDetected, SerializationFailure) as exc:
            # Roll back every projection and telemetry write before replaying
            # the entire same frame. Never replay an uncertain connection/COMMIT.
            conn.rollback()
            if attempt + 1 == MAX_ATTEMPTS:
                raise
            delay = min(0.05 * 2 ** attempt, 0.2) + random.uniform(0, 0.025)
            LOG.warning(
                "retrying aborted collector transaction schema=%s received_at=%s sqlstate=%s attempt=%s/%s delay_ms=%.1f",
                schema, received_at, exc.sqlstate, attempt + 2, MAX_ATTEMPTS, delay * 1000,
            )
            time.sleep(delay)
        else:
            if attempt:
                LOG.info("collector transaction recovered schema=%s received_at=%s attempts=%s", schema, received_at, attempt + 1)
            return result
