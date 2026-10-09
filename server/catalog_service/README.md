# ED-Frame central catalog service

This service continuously consumes the public EDDN relay and stores the
anonymous public catalog facts ED-Frame can reuse:

- public system name/address/coordinates from `journal/1`;
- public station metadata keyed by Market ID, including type, directly
  observed landing-pad capacity, distance, services, economies, faction and
  carrier access when the source message supplies those fields;
- public ring and hotspot observations projected through ED-Frame's existing
  mining evidence contract;
- explicit public Powerplay state, presence and control from `journal/1`,
  retained as one latest anonymous snapshot per system. Presence never implies
  control. The regional Mining API serves observations up to 24 hours old by
  default; old snapshots remain stored rather than being deleted by age;
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
  `Outfitting.json` and `Shipyard.json` snapshots. These retain item ID, exact
  observed price, source and observation
  time; later availability-only EDDN messages preserve matching prices;
- normalized station-module and station-ship offer tables for indexed Finder
  lookups, alongside the lossless complete-inventory JSON snapshots;
- versioned public reference catalogs for module display name, class/rating and
  power draw plus ship manufacturer, size and loadout geometry;
- current public BGS snapshots and supported FSS signal observations used by
  State Finds. The latest snapshot per system is retained durably but served
  as current only for 24 hours; signals retain their reported lifetime and are
  never extended by the server.
- per-schema EDDN telemetry in one-hour buckets: received and used messages,
  projected rows, ignored messages, errors, compressed relay bytes and last
  receipt time. Raw relay frames are never retained. `/v1/status` exposes the
  rolling latest 24 buckets; buckets older than eight days are removed.

Ship prices use three explicit confidence levels. A direct `Shipyard.json`
price is `OBSERVED` for that station and hull. The most common current
non-carrier observation becomes the gradual global `BASE_PRICE`; an early
discounted value is automatically displaced when ordinary-price observations
become the consensus. Other hulls at the same station may use the median
observed discount as `INFERRED`, with one supporting hull marked provisional
and two matching hulls confirmed. Elite's public 2.5% personal rebate is
removed before storage; no Commander rank or identity is accepted.

Missing source fields remain `null`; the collector does not infer landing-pad
size or other station properties from names or station types. Sparse newer
station messages retain richer facts already observed. Schema changes are
idempotent and do not clear existing tables or rows.

It does not accept or store Commander names, FIDs, private groups, cargo,
Journal files or paths, builds, wishlists, credentials or tokens. PostgreSQL is
reachable only by the private Compose network. The public surface is read-only
except for bounded, rate-limited yield and station-price observation endpoints.
In the current desktop app, the ED-Frame community connection is enabled by
default for new profiles. Its Connections switch controls catalog access and
supported anonymous contributions together; an explicit disabled setting is
preserved. Commander identities, raw Journal files and private builds remain
outside this public service contract.

## Conditional Mining snapshots (source-only until deployed)

The protocol is disabled by default (`EDFRAME_MINING_SNAPSHOT_PROTOCOL=0`),
including after an unrelated API deployment. Disabled mode treats protocol
hints as ordinary fresh regional paging, including continuations, without
hash work. In-flight frozen cursors cannot survive disabling/restarting the
page store; clients discard those partial pages and retry fresh. Set `1` only after explicitly installing
the transactional revision markers and approving rollout.

`GET /v1/sites/search` optionally accepts `snapshot_protocol=1` on bounded,
paginated system/region queries. Initial requests may send `known_revision`
only when holding a complete local snapshot. A matching regional revision
returns `notModified: true`, empty row arrays and `snapshotComplete: true`.
This confirms identity, not a new observation or extended lifetime.

Changed initial requests freeze the complete bounded projection in ONE short
repeatable-read, read-only PostgreSQL transaction: ring selection/order,
source timestamps, yield aggregates, fallback metadata and community references.
The transaction ends before publication. Rows are streamed in 5,000-row chunks,
not retained as 50,000 Python objects or an open transaction between requests.
Responses include `revision`, `snapshotStatic` and diagnostic `snapshotAt`;
source observation timestamps are unchanged. Every continuation sends the same
`snapshot_revision`/`snapshot_static`, offset and opaque `f1.<token>.<offset>` cursor.
It reads the frozen projection ONLY, without another PostgreSQL query or live
counter check. Collector writes cannot reshuffle these pages or restart a search.
The next search checks live counters and immediately sees new commits, even
before the frozen page TTL expires. Insert/delete and change/revert invalidate
that next search too. Intermediate pages are `snapshotComplete: false` until
the final page; a bounded/truncated projection NEVER claims complete coverage.

The two API workers share a container-local SQLite page store (default
`/tmp/edframe-mining-pages.sqlite3`; optionally `EDFRAME_MINING_PAGES_PATH`).
It contains only public projections and is not a durable catalog volume.
Limits: one builder, 20-second build budget, 50,000 rows plus one truncation
sentinel, eight entries, three-minute page lifetime, 8 MiB compressed and
64 MiB raw per entry, 8 MiB raw per chunk and 2 MiB raw reference metadata.
SQLite is limited to 96 MiB; rollback journal rather than WAL keeps auxiliary
disk usage bounded (database plus worst-case journal under roughly 192 MiB).
Expired/aborted entries reclaim pages; unexpired entries are NOT evicted to
admit a new search. Busy/full/oversize/timed-out builds return 503 and clients
use fresh legacy paging. Missing/expired/corrupt/query-mismatched cursors or a
rolling projection change return 409; clients discard partial rows and retry.
TTL is only an availability limit, never proof that data is unchanged.

Tradeoff: the initial response waits for materialization of the bounded search
instead of sending a live first page early. Later pages are cheap and consistent;
total search time and first-response latency must both be measured before rollout.
The protocol's default-off gate and existing non-protocol path are retained.

The digest covers regional membership/expiry, site fields/deletions, both
yield tables, same-system fallback metadata, imported references and their
public system positions. Bundled/code changes invalidate revisions. This
requires an **explicit migration**; it is not installed by ordinary startup.
Existing clients and non-protocol queries remain unchanged.

Migration procedure (approved maintenance window, verified DB backup first):

1. Keep `EDFRAME_MINING_SNAPSHOT_PROTOCOL=0`; stop collector and API writes.
2. Run the matching API image's operator command:
   `python -m edframe_catalog.mining_epochs --install`.
   The command uses one transaction, source-table write locks and bounded
   timeouts. Failure rolls everything back. No source records are deleted.
3. It creates five small tables: state/generation, cell/system counters, historical
   128-LY cell footprints, and reference names; it backfills existing positions
   and installs 20 statement-level DML/TRUNCATE triggers atomically.
4. Restart services with matching code. Approve/enable the protocol only after
   checking real paging and concurrent collector throughput.
5. After restoring a DB backup, **before serving conditional queries**, run
   `python -m edframe_catalog.mining_epochs --install --rotate-after-restore`.
   Otherwise restored counters might reuse previously issued revisions.

Never prune footprints/counters, disable the triggers, or change replication
trigger handling while the protocol is enabled. These rows retain deletion and
movement evidence. Reinstallation preserves them and the database generation.
New bundled reference names require rerunning installation; unseeded names,
missing tables or an unready migration return 503 rather than unverifiable reuse.

Each proof reads a few conservative grid-cell counters plus reference counters, not
full mining JSON or yield histories. Changes outside those cells do not normally
invalidate the region; unknown positions invalidate conservatively. Same-system
metadata/yields and both old/new positions are included. An indexed global
oldest eligible observation guards rolling-age expiry, including without any
write. It can invalidate an unrelated region but cannot overlook an aged-out row.

App snapshots are bounded to eight compressed entries and 64 MiB of retained
payload per Commander profile. They are persisted on tracked workers, with
checksum validation, profile/reset fences and unchanged source timestamps.
The app reads a small revision hint first and only decompresses the old payload
after an unchanged response. The hint alone never proves usable rows: checksum
failure, eviction or a concurrent replacement retries fresh paging without it.
Regions above 500 LY keep the existing legacy client path until separately
evaluated. Protocol failures also fall back to fresh paging;
repeated paging conflicts produce explicitly provisional, non-cacheable rows.

`ops/benchmark-mining-revision.py` is a read-only SQL probe; append it after
`edframe_catalog/mining_revision.py`, set Python's package context to
`edframe_catalog`, and stream it to the running API Python process. It does
not install files, change data/schema or deploy the protocol. Deployment
requires the matching app and server code; no client speedup is claimed for
the currently published Windows release.

`ops/verify-mining-revision-cost.py` compares historical content-proof variants
in the same read-only transaction. The optimized historical proof binds the regional
system-name set, then fingerprints all original dependencies in that same
repeatable-read snapshot. Small spheres (up to 100 LY) use the existing GiST
box prefilter; broad spheres retain the cheaper exact-sphere scan. No hash
domain was narrowed to only the requested commodity or current page.
`ops/verify-mining-revision-handler.py` compares every returned ring/reference
and its order with the deployed handler, then tests conditional confirmation.

The old full-content prototype was rejected: the 2026-10-09 250-LY probe took
27.7 seconds with proofs vs 15.8 without; unchanged confirmation took 5.0 seconds.
These are sequential in-process SQL/handler samples, not installed-app timings.
It is retained only as `mining_content_revision` for diagnostics, not called by
the API and never used as a missing-migration fallback.
`ops/verify-mining-epochs.py` tests real triggers, MVCC, rollback, concurrent
commits, deletes, movement and expiry in a generated isolated schema; optional
benchmarks copy only public data and remove that exact schema in `finally`.
With `api` and `pages` source inputs it also compares frozen/legacy HTTP row
projections and ordering, concurrent updates, next-search invalidation, page
latencies, cross-instance continuation without PG, and capacity failures.
Sources execute only in the isolated child process; no installed API code,
public tables, production schema or service settings are changed.
Do not automatically deploy/enable a general rollout without confirming
collector write overhead and cold paging under live churn. See
`reports/server_revalidation_2026-10-09.md` in the repository root.

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
- `GET /v1/mining/powerplay?x=0&y=0&z=0&max_distance=100`
- Powerplay responses include `hasMore`/`nextCursor`; continue with `cursor` to
  read beyond the first 200 systems. Repeated `system=Cubeo&system=...` query
  parameters select up to 200 exact systems using the identity index, independent
  of radius (response `selection: systems`). The 24-hour default freshness and
  explicit-control requirement are unchanged; no database migration is needed.
- Exact-system queries may opt into `include_coverage=true`. The bounded
  `coverage` array labels each requested system `CURRENT`, `STALE` or `MISSING`
  and includes the original last observation time where known. It does not
  transfer old facts into `results` or extend freshness. Regional queries never
  perform a historical galaxy-wide lookup for this option.
- Explicit `Unoccupied` snapshots are retained even when `Powers` is empty or
  absent. Such rows use an empty `power` and `UNOCCUPIED` relationship; no Power
  or controller is invented. Consumers must accept these system-wide facts.
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

### Regional State Finds

`GET /v1/sync/state-finds` optionally accepts `x`, `y`, `z` together and
`max_distance` (default 250 LY, maximum 2000 LY). Both BGS snapshots (24-hour
window) and unexpired signals are filtered through known system coordinates.
Missing coordinates are excluded, not interpreted as zero distance.
The response echoes `region: {origin: [x,y,z], radiusLy: ...}`.
Clients must reset their cursor whenever this region changes. Omitting all
coordinates preserves the global endpoint for older clients.
Regional coverage is not complete galaxy coverage or proof of an active HGE.

### Regional station services

`GET /v1/stations/nearby` requires `x/y/z` and `service` (a public
StationServices identifier). `max_distance` defaults to 100 LY (max 2000);
`landing_pad` is the required ship pad: S accepts S/M/L, M accepts M/L,
L accepts L. Unknown pads are excluded when a requirement is specified.
Fleet Carriers are excluded by default. Results are ordered by LY distance,
arrival LS, then MarketID; at most 200 rows with `hasMore` for truncation.
The API echoes the region and returns observation timestamps and docking
metadata, not guaranteed commander-specific access or trader/broker subtypes.

### Commodity catalog and station quotes

`GET /v1/catalog/commodities` lists every symbol currently present in `markets`,
including rare/new/special commodities. An indexed recursive walk avoids a
full-table DISTINCT over millions of rows. Names/categories are a small client
reference. The normal trading UI filters out unknown, salvage, nonmarketable,
mission-reward and mining-only cargo. Rare purchases have their own category.
The complete API/database inventory is retained for other consumers.

`GET /v1/markets/commodity-offers` requires `commodity`, `direction=BUY|SELL`
and `x/y/z`. BUY uses `buy_price/stock` ascending; SELL uses
`sell_price/demand` descending. Nonpositive prices and insufficient quantities
are excluded; there is no mean-price or reference-price fallback.
`max_distance` defaults to 100 LY (max 2000), `min_quantity` to 1 (max 1M),
`max_age_hours` to 24 (max 2160). Pad compatibility and carrier exclusion
follow the station-services endpoint. Up to 200 rows (`hasMore`), with region,
timestamp, source, access metadata and all raw price/quantity fields.
The app requests at most 100 rows manually. No new tables, history retention,
background commodity polling or third-party live market requests are added.
