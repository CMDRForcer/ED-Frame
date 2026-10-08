# Mining Finder: foreground priority and background ring batches

Source-only implementation of audit items 1 and 2. No server deployment,
commit, push or packaged release in this task. BGS prediction and retention
logic, eligibility, provider fallback, query limits and freshness remain intact.

## Changes

- Explicit commodity searches preempt a background warm request immediately.
  Unknown-origin multi-commodity searches also take priority. A known-origin
  multi-commodity search can already use the retained catalog and verify its
  displayed routes, so it need not restart warming. A running foreground
  request retains its latest-followup queue.
- Cancel by request identity, without marking a durable warm target failed or
  completed. An already-running HTTP request cannot be forcibly interrupted;
  subsequent pages, persistence and publication reject the canceled identity.
- Incoming regional/live ring batches and current-system refreshes use a
  tracked merge worker. It owns compacted row copies and an identity-index
  snapshot, and archives incoming and displaced observations before publication.
- The Qt completion slot publishes prepared data and queues the existing
  background JSON saver. New observations accumulate while a merge is active.
  A concurrent catalog revision triggers a rebase against the latest catalog;
  profile, generation, path and reset guards prevent stale resurrection.
- Archive failures retain both previous and incoming rows in the active
  catalog. Unexpected merge failures requeue inputs. Shutdown reclaims any
  unhandled in-flight batch for the existing final synchronous durable save;
  late Qt completions cannot overwrite it.

## Local measurement

Synthetic remerge of 24,447 ring records with real SQLite history, not a live
private-profile GUI benchmark. HTTP retrieval, QML rendering and catalog JSON
disk write are excluded. The isolated history database recorded 24,447 incoming
observations and 24,447 displaced catalog records; 24,447 rings remained active.

| Phase | Seconds |
| --- | ---: |
| Dispatch tracked worker | 0.006193 |
| Merge, compaction and real SQLite history (background) | 1.411 |
| Publish prepared result (save queued/mocked) | 0.000568 |

This relocates work rather than proving a faster total network download.
The prior complete public-region retrieval varied between roughly 20 and
30 seconds. Full retrieval/delta or spatial-server work remains a separate
optimization, as do broad cache invalidation and UI-side market-store reads.

## Verification

Tests cover priority, stale cancellation/completion, worker thread identity,
slow history without blocking the next UI batch tick, private snapshots,
archive failure, real history preservation, incoming observations while busy,
catalog rebasing, profile/generation/path/reset guards, retry and shutdown.
The complete app suite includes real offscreen QML load and injected-error
smoke checks; server regressions and repository hygiene are checked separately.

Final verification: all 985 app tests and 88 server tests passed. Repository
hygiene and `git diff --check` passed. No production/server settings changed.
