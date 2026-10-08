# App performance audit — 2026-10-07

Read-only code/server investigation following the uncommitted Mining refresh
improvements. No additional product code, production API, persistent database
settings, indexes or BGS rules changed in this audit. No running ED-Frame
process was available, so this is not a live GUI or private-profile benchmark.

## Measured Mining data path

Public Shanteneri / 250-LY / Platinum queries using the new concurrent refresh:

| Phase | Seconds | Scope |
| --- | ---: | --- |
| Network retrieval | 29.421 | 24,447 merged ring records; markets + Powerplay concurrently |
| Ring domain | 29.420 | Dominant network domain |
| Powerplay domain | 0.351 | Concurrent, not added to ring time |
| Market domain | 0.973 | Concurrent, unchanged provider fallback |
| Merge same region back into existing catalog | 1.255 | 24,447 incoming records / 24,447 displaced records |
| Catalog JSON serialization | 0.155 | 28,059,989 UTF-8 bytes; disk write not included |
| Build display rows | 0.378 | 24,447 rows |
| LASER Platinum filter | 0.140 | 2,060 candidates |
| Highest-profit planner | 0.092 | 30 results |
| Powerplay-merits planner | 0.068 | 30 results |
| Shortest-route planner | 0.096 | 30 results |

The prior new-refresh sample took 19.658 seconds for the same complete region.
This variation confirms that 19.7 seconds is not a guaranteed total search
time. Tests use the real projection, merge, filter and planner functions, but
do not include GUI rendering, history archive disk I/O, route verification,
background queue delay or a mature private profile.

## Prioritized findings

1. **User lookup waits for background warming.**
   `refreshMiningMarkets` queues the new query when `_mining_market_busy` is
   true. Background and foreground tasks both fetch full ring regions.
   The user's perceived wait can therefore include the current background
   lookup plus the requested lookup. Prioritize a user request over a background
   task, using guarded cancellation and preserving the warming target for retry.

2. **Large observation merge and history still run on the Qt path.**
   `flushHgeObservationBatch` merges pending rings, calls `_archive_history`
   for observations and displaced records, compacts the entire catalog and
   merges/persists Powerplay observations. Merely remerging the repeated region
   costs 1.255 seconds before synchronous history I/O. Move Mining-specific
   merge/history work to a tracked worker, publish atomically with profile,
   generation, reset and concurrent-observation guards. Leave BGS processing
   and its prediction rules unchanged. Do not drop history to achieve speed.

3. **Unrelated state replacement invalidates Mining and other caches.**
   `_mining_rows_identity` includes `id(state)`: replacing an otherwise
   identical state dict changes the key. `miningRevision` also incorporates
   `_state_revision`, and `_publish_full_state` clears `_derived_cache` and
   emits `fleetChanged` on every full publication. Use domain-specific
   dependency revisions rather than a broad refresh identity. Preserve explicit
   time-based freshness invalidation and all dependencies (position, local
   evidence, catalog, profile, market facts, Powerplay, ship images).

4. **Full ring retrieval is repeated by every market/warming lookup.**
   Current `fetch_mining_refresh` always fetches rings, Powerplay and markets
   for a known origin. Persistent snapshots plus a server revision/delta path
   can avoid resending unchanged ring structure. Never declare a partial
   snapshot complete, reuse expired observations as fresh, or skip new yield,
   hotspot, overlap or Powerplay evidence. This requires a coherent protocol,
   not merely a longer TTL.

5. **Server regional selection lacks a spatial access path.**
   A warm 250-LY EXPLAIN selected 1,001 rows using `mining_sites_page_idx`
   after filtering out 141,588 records. The 500-LY sample filtered 69,461.
   Add and benchmark a suitable spatial index/prefilter while retaining the
   exact three-dimensional sphere and stable cursor order.

## Read-only SQL experiments: not ready to deploy

Compared original SQL, a bounding-box predicate, and a materialized regional
prefilter inside repeatable-read, read-only transactions. Every variant kept
the same ordered site identities in each tested first-page result:

| Radius | Original | Bounding box | Materialized region | Returned SQL rows |
| --- | ---: | ---: | ---: | ---: |
| 50 LY | 4.412 s | 7.741 s | 0.351 s | 275 |
| 250 LY | 3.060 s | 3.201 s | 5.728 s | 1,001 |
| 500 LY | 2.251 s | 1.741 s | 6.619 s | 1,001 |

These are sequential single samples under variable cache/load conditions,
not controlled speedup ratios. A blanket materialized prefilter regresses
larger radii. Do not deploy these substitutions without spatial indexing,
multi-page equivalence tests and representative cold/warm measurements.
EXPLAIN samples did not show a JIT node; a JIT-setting change is not established
as the cause or remedy.

## General app review

- Initial state building, state refreshes, large Mining row projection and
  catalog JSON save already run in tracked workers. Inactive CMDR sections
  already avoid finance/fleet work. Preserve these existing improvements.
- Finance history is cached against the broad `_state_revision`; it scans
  Journal events synchronously when rebuilt. A synthetic 100,000-event test
  with one LoadGame every 50 entries took 0.154 seconds; 10,000 took 0.001.
  This is a secondary optimization, not evidence of the primary Mining delay.
- Fleet cache/notifications and the broad `_derived_cache.clear()` are
  opportunities for more precise invalidation; no real-profile fleet rendering
  slowdown was measured here.
- SQLite queries such as `store.nearby` and warm-target metadata operations
  are still callable from UI paths and use the store lock. Profile them with
  a mature retained database before promising a specific gain; background
  writes alone do not prove that reads can never wait on that lock.

The preceding HTTP-session/concurrency/persistence improvements are source-only
and are not part of published Windows 1.5.39. The next packaged release must
include them before comparing the installed app against these timings.
