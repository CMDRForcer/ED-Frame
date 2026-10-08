# App responsiveness and local footprint — 2026-10-07

## Scope and data preservation

Implementation following the app-wide responsiveness complaint. The user
explicitly chose code-only improvements and retention of existing files.
No installed app was replaced, no production deployment was performed, and
no existing profile history, catalog, recovery image or crash report was
deleted, migrated or retrospectively compressed. Measurements read files;
tests used disposable workspace profiles. No Commander identities or raw
profile records are included here. BGS prediction rules are unchanged.

## What occupied disk

The initial inventory was approximately 4,704 MiB. Dominant profile files:

| File | Initial size, MiB | Purpose |
| --- | ---: | --- |
| mining_market_catalog.sqlite3 | 1,520 | Current markets, station offers and retained market observations |
| mining_market_catalog.backup.sqlite3 | 1,494 | Full uncompressed recovery snapshot |
| data_history.sqlite3 | 1,407 | Historical observations and displaced records |
| mining_finder_catalog.json | 225 | Retained public ring knowledge |
| mining_powerplay_catalog.json | 39 | Powerplay system links |

Later read-only SQLite snapshots showed 150,000 current market rows, 500,000
market-history rows and 1,228,388 archive records. Ring observations dominated
archive payloads. The archive file grew to about 1,493 MiB while investigating;
these are different-time observations, not fixed-size assertions. Images/QML
cache were only about 2 MiB. Free database pages were negligible: deleting
temporary files alone would not solve the multi-GB footprint.

Retaining a full offline public catalog, historical observations and a second
full recovery image explains the size. This is not a necessary minimum for a
server-supported app, but switching to a smaller regional working set would
be a separate architectural change. This change does not silently reduce
coverage, delete old observations or drop offline functionality.

## Blocking and duplicate memory removed

- SQLite read helpers formerly took the importer's Python writer lock and
  opened write-configured connections. Healthy WAL readers now read the last
  committed snapshot independently. A regression test holds both the Python
  lock and an uncommitted SQLite transaction while counts/metadata stay below
  250 ms. Explicit reset/recovery still waits safely for active readers.
- All atomic JSON files formerly shared one write lock. A background large
  Mining save could stall a tiny UI settings save. Locks now belong to each
  resolved target path; writes to the same path remain serialized and atomic.
- Page switches debounce settings persistence for 400 ms. Normal QML page
  loaders incubate asynchronously; inactive pages still unload. The shared,
  lean Mining source view survives leaving and returning to the page.
- Full-record JSON decoding produced long interpreter stalls and separate
  repeated strings. Record-sized streaming decoding shares selected repeated
  strings within one load and yields regularly, without global intern pools.
- Full display dictionaries for every retained ring are no longer kept in a
  second permanent view. Rows remain shared until a result needs derived
  labels. A no-local-delta view also avoids building a throwaway identity map.
- Filtering, route evaluation and market diagnostics execute on a tracked
  worker, not in QML binding getters. Only one planner runs at a time; profile,
  source, market and query guards prevent publishing obsolete results.
- Powerplay catalog/observation saves also use queued, chunked snapshots.
  Old derived-cache revisions are evicted per domain; coordinate and crash
  report lookups reuse bounded caches rather than repeating disk scans.

## Read-only isolated measurements

Each variant ran in a fresh Python process against the existing local public
ring JSON. These are catalog-path measurements, not the whole app's RAM or
live rendered tab timings. The file changed slightly between the last runs.

| Measurement | Previous full decode/view | New streaming/shared view |
| --- | ---: | ---: |
| Rings | 279,448 | 279,618 |
| JSON load RSS increase | 733.8 MiB | 510.7 MiB |
| Longest 5-ms background heartbeat gap during load | 1.370 s | 0.151 s |
| JSON load wall time | 1.621 s | 3.110 s |
| Additional display-view RSS | 270.0 MiB | 3.6 MiB |
| Display-view preparation | 2.438 s | 0.007 s |
| Process RSS after display-view preparation | 1,063.9 MiB | 574.6 MiB |

Streaming intentionally trades some background load throughput for shorter
interpreter stalls and less memory. Approximately 46% lower RSS in this
isolated catalog/view sample is not a guarantee of a 46% reduction in total
installed-app memory. Garbage collection still caused a roughly 150-ms gap;
the full retained catalog still occupies about 500 MiB.

Reproduce with `tools/profile_local_responsiveness.py PROFILE --json-only
--views` and `--json-only --stream --views --lean`. The tool never constructs
a writable store against the profile. SQLite diagnostics use normal read-only
WAL snapshots rather than immutable mode that would ignore pending WAL data.

## Future disk growth, without rewriting existing files

New history/market-history payloads can be stored as versioned lossless zlib
blobs. Existing textual JSON records remain readable/exportable. Re-fetching
identical Mining facts no longer manufactures new archive identities merely
because retrieval time or derived distance changed. Actual observation time,
provenance and fact changes remain identity inputs. The latest complete payload
is retained, including retrieval metadata.

New market recovery images are full gzip snapshots, verified by full
decompression and SHA-256 comparison before atomic replacement. Existing raw
legacy backups remain available and untouched. Recovery accepts either format;
reset generations fence snapshots still in flight. Creating a new gzip image
can initially add disk use while the old raw backup is deliberately retained.
This change does not promise an immediate reduction of the existing folder.

## Verification and remaining work

Regression tests cover concurrent WAL reads, independent file writes, corrupt
JSON protection, exact compressed-history export, compressed/legacy recovery,
failed replacement, reset-versus-backup races, shared row identity, query/profile
fences and route equivalence across planner modes. Full-suite and offscreen QML
results: **1,039 app tests passed** in 106.750 seconds, including synchronous
and production-asynchronous offscreen QML page/dialog tests; **97 server tests
passed**. `git diff --check`, tracked-file repository hygiene and new-source/
report secret-pattern checks passed. Fault-injection warnings in test output
refer only to disposable fixtures, not damage found in the actual profile.

The smoke runner explicitly waits for active Loader readiness rather than
editing a partially incubated object. It also ignores retained old page
creation contexts while recognizing independently reparented popup dialogs.
The production-async test checks real page/dialog loads and restored controls,
not just QML source text.

Remaining: build/install validation and a live tab/RAM comparison with the user's
normal workload. A lazily queried regional ring store would further reduce the
remaining large in-memory catalog, but is not implemented here. Existing folder
size remains by the user's explicit choice.

## Follow-up: Mining results disappearing during refresh

The result panels used the planner/market busy state as a visibility condition,
even when a complete same-query result was available. Background source,
verification and minute-freshness updates therefore repeatedly swapped the
populated page for its loading/empty view. QVariant-list conversion also created
fresh QML arrays for unchanged rows.

The page now coalesces notifications before requesting/publishing results,
compares complete snapshots and keeps populated panels visible. The alternatives
use a keyed ListModel with insert/move/set/remove updates rather than a reset;
the selected ring and top visible row offset are retained across changed results.
Failed same-query plans retain the last complete result, while new queries and
profile generations cannot reuse it. A genuinely empty completed result still
shows the empty view. Freshness, source updates and verification remain enabled.

The real-QML fixture covers the reported Platinum + RES / Hazardous settings,
busy transitions, unchanged snapshots, updated prices, reordering, removed
selection, new-query isolation, Powerplay section changes and empty results.
Twenty immediate notifications produce one plan request, not twenty. It also
checks no model reset for same-query updates and no repeated verification loop.
Backend tests cover unchanged snapshot identity and failed-refresh retention.

Updated full app suite: **1,043 tests passed** in 105.771 seconds; the final
isolated QML test also passed with a disposable local app-data directory.
No user data was removed/rewritten and no installed build was replaced.

## Follow-up: catalog synchronization (2026-10-08)

Remaining GUI-thread writer-lock waits, local market imports, verification
market persistence and State Finds page merge/archive/save were moved to tracked
workers. Concurrent Journal/queued-save rebases and durable facts-before-cursor
ordering preserve data; stale requests release busy state without publication.
See `catalog_sync_responsiveness_2026-10-08.md` for the detailed cause and tests.
Full app validation: 1,066 tests passed, plus final targeted ordering/storage
checks. The installed 1.5.39 executable remains unchanged.
