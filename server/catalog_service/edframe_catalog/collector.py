from __future__ import annotations

import logging
import os
import signal
import time

import zmq

from ed_companion.integrations.eddn import EddnRelayDecodeError, decode_relay_frame

from .database import (
    connection, ensure_schema, record_state, upsert_batch,
    upsert_state_find_batch,
)
from .projection import (
    project_markets,
    project_sites,
    project_stations,
    project_system,
    project_state_bgs_snapshot,
    project_state_signals,
    projected_systems,
    schema_name,
    utc_now,
)


LOG = logging.getLogger("edframe.catalog.collector")
RUNNING = True


def _stop(_signum, _frame) -> None:
    global RUNNING
    RUNNING = False


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    ensure_schema()

    relay = os.environ.get("EDDN_RELAY_URL", "tcp://eddn.edcd.io:9500")
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.setsockopt(zmq.SUBSCRIBE, b"")
    socket.setsockopt(zmq.RCVTIMEO, 1000)
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect(relay)
    LOG.info("connected to %s", relay)

    try:
        with connection() as conn:
            while RUNNING:
                try:
                    raw = socket.recv()
                except zmq.Again:
                    continue
                received_at = utc_now()
                try:
                    payload = decode_relay_frame(raw)
                    schema = schema_name(payload)
                    system = project_system(payload)
                    markets = project_markets(payload, received_at)
                    sites = project_sites(payload, received_at)
                    stations = project_stations(payload, received_at)
                    systems = projected_systems(
                        system, markets, sites, stations,
                    )
                    projected = upsert_batch(
                        conn,
                        systems,
                        stations,
                        markets,
                        sites,
                    )
                    snapshot = project_state_bgs_snapshot(payload, received_at)
                    signals = project_state_signals(payload, received_at)
                    projected += upsert_state_find_batch(
                        conn,
                        [snapshot] if snapshot else [],
                        signals,
                    )
                    record_state(
                        conn,
                        schema=schema,
                        received_at=received_at,
                        projected=projected,
                    )
                    conn.commit()
                except (EddnRelayDecodeError, ValueError, TypeError) as exc:
                    conn.rollback()
                    LOG.warning("rejected relay frame: %s", exc)
                    record_state(
                        conn,
                        schema="invalid",
                        received_at=received_at,
                        errors=1,
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    LOG.exception("collector iteration failed")
                    time.sleep(1)
    finally:
        socket.close()
        context.term()
        LOG.info("collector stopped")


if __name__ == "__main__":
    main()

