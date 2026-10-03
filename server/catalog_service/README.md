# ED-Frame central catalog service

This service continuously consumes the public EDDN relay and stores the
anonymous public catalog facts ED-Frame can reuse:

- public system name/address/coordinates from `journal/1`;
- public station metadata keyed by Market ID, including type, directly
  observed landing-pad capacity, distance, services, economies, faction and
  carrier access when the source message supplies those fields;
- public ring and hotspot observations projected through ED-Frame's existing
  mining evidence contract;
- complete public `commodity/3` rows for every commodity: mean, buy and sell
  prices, stock, demand, brackets, status flags, observation time and receipt
  time.
- current public BGS snapshots and supported FSS signal observations used by
  State Finds. BGS snapshots are retained for 24 hours; signals retain their
  reported lifetime and are never extended by the server.

Missing source fields remain `null`; the collector does not infer landing-pad
size or other station properties from names or station types. Sparse newer
station messages retain richer facts already observed. Schema changes are
idempotent and do not clear existing tables or rows.

It does not accept or store Commander names, FIDs, private groups, cargo,
Journal files, builds, wishlists, credentials or tokens. PostgreSQL is reachable
only by the private Compose network. The public surface is a read-only HTTPS API.

## Production deployment

1. Copy `.env.example` to `.env`, set a long random database password and the
   public DNS name.
2. Ensure the DNS A/AAAA records point at the host.
3. Run `docker compose up -d --build`.
4. Verify `/healthz` and `/v1/status` over HTTPS.

Persistent volumes hold PostgreSQL and Caddy certificates. The collector can be
restarted or upgraded without clearing the catalog. The database should also be
exported regularly with `pg_dump`; a provider VM snapshot is not a substitute
for an application-level database backup.

The files in `ops/` provide a verified daily custom-format `pg_dump` with
14-day retention and conservative weekly removal of market observations older
than 90 days. Expired signals and BGS snapshots older than 24 hours are also
removed. Mining evidence and system geography are deliberately retained.

## API

- `GET /healthz`
- `GET /v1/status`
- `GET /v1/systems/suggest?q=Cube`
- `GET /v1/stations/search?system=Cubeo&landing_pad=L`
- `GET /v1/markets/search?commodity=platinum`
- `GET /v1/sites/search?commodity=platinum`
- `GET /v1/sync/markets`
- `GET /v1/sync/state-finds`

Market and site search accept optional `x`, `y`, `z` and `max_distance`
parameters. This keeps route-radius filtering on the server while preserving
the same read-only, anonymous contract.

`/v1/status` exposes separate catalog counts plus freshness and completeness
metrics for market details, station metadata, coordinates and mining evidence.

