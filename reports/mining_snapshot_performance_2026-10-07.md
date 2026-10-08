# Mining snapshot revalidation — 2026-10-07

Point 4 of the performance audit. Implementation is source-only: no commit,
push, executable release, server deployment, restart, DDL or production data
mutation in this turn. BGS predictions remain unchanged.

## Implemented contract

- Persist complete projected regional snapshots separately from the merged
  historical Mining catalog. A historical collection is not a coverage proof.
- Query/server/projection-bound keys; checksum-validated compressed payloads,
  eight retained entries and at most 64 MiB retained payload per profile.
- One conditional request when unchanged. Never change source `observedAt`
  or `learnedAt` because a snapshot was retrieved/revalidated.
- Server fingerprint covers regional membership/expiry, ring fields and
  deletions, both yield tables, same-system metadata fallback, imported overlap
  references and public reference-system positions. Bundled code/reference
  versions are also dependencies. Invalidation is deliberately conservative.
- First/final pages establish an identical complete-domain content revision,
  including PostgreSQL tuple versions to detect changes followed by reverts.
  Each page uses a repeatable-read transaction and checks the static projection
  version. Intermediate pages remain provisional. A changed final proof gives
  HTTP 409; the client discards that attempted mixed snapshot and retries once.
- Repeated conflicts retain fresh legacy-path results but explicitly mark
  them provisional/bounded, never complete or cacheable. Protocol failures
  fall back to ordinary fresh paging. Regions above 500 LY deliberately retain
  ordinary paging because their revision cost has not been optimized.
- Snapshot saves run on the captured request's tracked worker under the
  existing profile/generation/path/reset lock. Ring success can be persisted
  even if market providers fail. Reset clears the proof cache. Corruption loses
  only the optimization, not the fresh data path.
- Markets and Powerplay still execute independently on every normal refresh.
  Unchanged snapshots still supply the complete local rows to the lossless
  background merge/history path; that CPU/history work is not removed.

## Measurements

Synthetic fixture, real app projection/merge and persistent SQLite snapshot,
24,447 unique rings. No HTTP latency, server SQL or GUI rendering included:

| Quantity | Result |
| --- | ---: |
| Initial mocked HTTP pages | 25 |
| Unchanged mocked HTTP confirmations after store reopen | 1 |
| Initial projection/merge | 0.355110 s |
| Snapshot serialization/compression/save | 0.167809 s |
| Snapshot load/decompression + mocked confirmation | 0.179332 s |
| SQLite fixture file | 180,224 bytes |
| Rows before/after reuse | Exactly equal, all 24,447 retained |

This highly repetitive synthetic fixture compresses better than real data;
its size is not a forecast for users. Reproduce with
`tools/benchmark_mining_snapshot.py`.

Final proposed SQL was streamed into the running production API Python
process and measured inside explicit **READ ONLY / REPEATABLE READ**
transactions. No source file was installed. Each statement had a 15-second
diagnostic timeout. Both digest readings in each transaction matched:

| Shanteneri radius | First digest | Repeat digest |
| --- | ---: | ---: |
| 50 LY | 1.1358 s | 0.6605 s |
| 250 LY | 5.3263 s | 5.1579 s |
| 500 LY | 9.8790 s | 9.6263 s |

Earlier discarded variants exceeded the diagnostic timeout or hashed the
entire reference-metadata table. Final SQL restricts dependencies to the
relevant system-name set and hashes only metadata fields used by the API.
Full content checks happen at the start/end, not on every intermediate page.

These are variable-load sequential SQL samples, not end-to-end HTTP or GUI
speedups. A cache miss/change still transfers every page and adds two revision
checks for multi-page regions. The first lookup is **not** guaranteed faster.
The benefit targets repeated unchanged regions; actual installed-app timing
requires the matching server deployment and a packaged app. A row-level delta
stream is not implemented.

The proposed `search_sites` handler was also executed ephemerally in a separate
production API-container Python process, without registering a public route,
invoking its lifespan, installing source or mutating data. Real retained 50-LY
data yielded **275 distinct sites across 3 pages**, a proven complete final
page, followed by an unchanged response containing **zero site rows**. The
full in-process handler sequence took **4.6439 s**; the conditional confirmation
took **0.6548 s**. The probe used a constant ephemeral projection-version tag;
it is not a deployment or an end-to-end installed-app timing.

## Verification

Coverage includes conditional reuse across store reopen, unchanged observation
times, changed yield/hotspot/overlap contents, version-bound paging, retry and
provisional fallback, page-cap non-completeness, corrupt/partial/missing cache,
scope/server binding, bounded storage, corrupt-cache reset recovery, reused
diagnostics, server overload and large-radius fallback, independent fresh
market/Powerplay fetching, and stale profile/request save guards.

The full app suite also exercises the real offscreen QML application startup,
page/dialog navigation, benign diagnostics and an injected runtime error.

Final verification: **1,016 app tests and 97 server tests passed**;
`git diff --check` and the repository hygiene check passed. Disposable test
SQLite files left by an earlier failed fixture were removed; no real profile
or retained application data was deleted.

## Remaining performance opportunity

Point 5: spatial access paths for the exact 3-D region selection. The server
still scans the regional scope for its digest. Representative cold/warm and
multi-page-equivalence checks are required before choosing/deploying an index.
Avoid a blanket query-plan substitution that regresses larger radii.
