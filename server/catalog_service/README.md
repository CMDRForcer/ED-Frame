# ED-Frame central catalog service

This service continuously consumes the public EDDN relay and stores the
anonymous public catalog facts ED-Frame can reuse:

- public system name/address/coordinates from `journal/1`;
- public station metadata keyed by Market ID, including type, directly
  observed landing-pad capacity, distance, services, economies, faction and
  carrier access when the source message supplies those fields;
- public ring and hotspot observations projected through ED-Frame's existing
  mining evidence contract;
- opt-in, anonymous `ProspectedAsteroid` material percentages from ED-Frame,
  de-duplicated by site, timestamp and material payload so measured yield can
  gradually replace hotspot/reserve estimates for every mining commodity;
- complete public `commodity/3` rows for every commodity: mean, buy and sell
  prices, stock, demand, brackets, status flags, observation time and receipt
  time.
- complete public `outfitting/2`, priced `outfitting/3` and `shipyard/2`
  inventories, keyed by Market ID and atomically replaced only by an equally
  new or newer observation. Version 3 retains the observed `BuyPrice` and
  `BuyMercCoinsPrice`; version 2 remains a compatible availability fallback;
- opt-in, anonymous module and ship purchase prices from ED-Frame
  `Outfitting.json` and `Shipyard.json`
  snapshots. These retain item ID, exact observed price, source and observation
  time; later availability-only EDDN messages preserve matching prices;
- normalized station-module and station-ship offer tables for indexed Finder
  lookups, alongside the lossless complete-inventory JSON snapshots;
- versioned public reference catalogs for module display name, class/rating and
  power draw plus ship manufacturer, size and loadout geometry;
- current public BGS snapshots and supported FSS signal observations used by
  State Finds. BGS snapshots are retained for 24 hours; signals retain their
  reported lifetime and are never extended by the server.

Missing source fields remain `null`; the collector does not infer landing-pad
size or other station properties from names or station types. Sparse newer
station messages retain richer facts already observed. Schema changes are
idempotent and do not clear existing tables or rows.

It does not accept or store Commander names, FIDs, private groups, cargo,
Journal files or paths, builds, wishlists, credentials or tokens. PostgreSQL is
reachable only by the private Compose network. The public surface is read-only
except for bounded, rate-limited yield and station-price observation endpoints.
Both sharing options are disabled by default in ED-Frame and require explicit
consent.

## Production deployment

1. Copy `.env.example` to `.env`, set a long random database password and the
   public DNS name.
2. Ensure the DNS A/AAAA records point at the host.
3. Run `docker compose up -d --build`.
4. Verify `/healthz` and `/v1/status` over HTTPS.
5. After the first deployment containing normalized offer tables, backfill the
   retained inventories once:
   `docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < ops/backfill-normalized-offers.sql`.

Persistent volumes hold PostgreSQL and Caddy certificates. The collector can be
restarted or upgraded without clearing the catalog. The database should also be
exported regularly with `pg_dump`; a provider VM snapshot is not a substitute
for an application-level database backup.

The files in `ops/` provide a verified daily custom-format `pg_dump` with
14-day retention. Weekly maintenance retains every last-known catalog fact,
including old markets and current-per-system BGS snapshots. Freshness is a
query concern and never a deletion rule. Only signals carrying an explicit,
elapsed expiry are removed. PostgreSQL statistics are refreshed weekly and the
maintenance unit reports warnings at 70% disk use and a critical failure at
85%, without deleting durable data. Container logs are bounded to three 20 MB
files per service. Mining evidence and system geography are retained.

## API

- `GET /healthz`
- `GET /v1/status`
- `GET /v1/systems/suggest?q=Cube`
- `GET /v1/stations/search?system=Cubeo&landing_pad=L`
- `GET /v1/station-offers/search?module=int_fuelscoop_size8_class5`
- `GET /v1/station-offers/search?ship=anaconda`
- `GET /v1/catalog/modules/suggest?q=beam`
- `GET /v1/catalog/ships/suggest?q=ana`
- `GET /v1/markets/search?commodity=platinum`
- `GET /v1/sites/search?commodity=platinum`
- `GET /v1/sync/markets`
- `GET /v1/sync/station-offers`
- `GET /v1/sync/state-finds`
- `POST /v1/station-offers/observations` (maximum 20 anonymous observations)
- `POST /v1/yields/observations` (maximum 100 anonymous observations per batch)

Market and site search accept optional `x`, `y`, `z` and `max_distance`
parameters. This keeps route-radius filtering on the server while preserving
the same read-only, anonymous contract.

`/v1/status` exposes separate catalog counts plus freshness and completeness
metrics for market details, station metadata, coordinates and mining evidence.
