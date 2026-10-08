# Catalog synchronization responsiveness

## Cause confirmed in code

The network request already ran on a worker, but some completion callbacks
still performed persistence on the Qt GUI thread. Even a small source-status
write waited behind the market store's writer lock during a large import.
Other blocking paths included warm-target writes when starting a search, local
Market.json ingestion, verification market imports and the State Finds page
merge, historical/overflow archive and durable JSON/cursor writes.

Thus "background network sync" did not mean background processing end to end.
Ordinary SQLite/WAL reads and the stable Mining results publication from the
preceding performance work remain in place.

## Changes

- Source-status writes and search warm-target persistence use tracked workers
  with original-store, profile-generation and store-reset fences.
  Warm-target upserts preserve newer explicit search settings even if an older
  worker finishes later; usage counts remain cumulative and companion defaults
  cannot erase previously recorded explicit intent.
- Catalog completion uses the worker's retained count rather than issuing an
  additional GUI-thread count query. An empty warm queue still starts a concrete
  commodity for an all-commodities search while its queue is being persisted.
- Locally opened station markets are ingested off-thread, independently of EDDN.
  Only a successful completion increments the displayed market revision. Failed
  writes allow the same retained Market.json version to be retried; an older
  failed completion cannot reset the fingerprint of a newer file.
- Verification market ingestion precedes its GUI publication on the original
  verification worker. Ring additions use the existing lossless observation
  merge worker instead of merging the large ring catalog in the completion slot.
- State Finds processing captures the original archive and paths, merges and
  archives off-thread, saves facts before the resumable cursor, and publishes
  only a complete prepared snapshot. New Journal observations or superseding
  queued saves trigger a rebase of the fetched page instead of an overwrite.
  Stale profile/location completions release busy state without publication;
  rejected shutdown dispatches and failed saves explicitly retain/retry data.

The BGS/evidence classification and expiry rules are unchanged. No existing
profile files were migrated, compacted or deleted, and no installed application
was replaced. The screenshot identifies installed version 1.5.39; these source
changes still require build/install validation to be exercised in that app.

## Verification

Twenty-four dedicated regression tests pass. They exercise real background
threads and a disposable SQLite store, blocked writer locks, deferred GUI
callbacks, profile/reset/opt-out fences, concurrent Journal and queued-save
rebases, original-path protection, durable facts-before-cursor ordering, injected
cache/cursor/archive/market failures, retry fingerprints and verification/ring
dispatch behavior. A real Qt event loop continues its 10-ms heartbeat while the
State Finds storage worker waits behind a deliberately held file lock.

Complete app validation passed **1,066 tests in 105.193 seconds**, including
offscreen QML page/dialog checks and the heartbeat/path/queued-save guards.
After the final warm-target ordering guard, the dedicated suite passed **24
tests in 1.003 seconds** and all **28 market-store tests in 1.886 seconds**.
`git diff --check`, repository hygiene and new-file secret-pattern checks passed.
Injected storage/corruption warnings refer only to disposable test fixtures.

These are controlled regression checks, not a claimed live latency/RAM benchmark
of the user's installed executable. Build/install and live sync validation remain
the next verification step. Existing data-folder size is unchanged by design.
