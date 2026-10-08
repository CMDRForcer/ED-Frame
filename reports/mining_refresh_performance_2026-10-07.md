# Mining refresh: connection reuse, concurrency and background persistence

Implemented after release 1.5.39. Source changes only; no server deployment,
release, BGS changes or catalog eligibility changes in this task.

## Design

- Resolve an unknown origin first, retaining the ED-Frame/EDSM fallback.
- Run three independent tasks at most: rings, regional Powerplay, markets.
  Each owns and closes its own requests.Session; no Session is shared between
  threads. Cursor-dependent ring pages still run sequentially in that session.
- Keep the market provider order and fallback, query parameters, page limits,
  age checks, and projection/merge semantics unchanged. One domain's failure
  does not discard successful results from another domain.
- Join all domain tasks inside the existing tracked network worker. Check
  profile/request/shutdown state before subsequent HTTP requests so an obsolete
  lookup does not continue paging after a switch, reset or shutdown.
- Save the returned markets to SQLite, retry/warming metadata, the market JSON
  snapshot and newly resolved coordinate snapshot before emitting completion.
  This work is off the Qt thread. The completion slot publishes memory and
  starts the existing throttled background backup.
- Capture the exact profile store and paths before dispatch. Validate request,
  profile, generation and path inside the existing reset serialization lock.
  Reset invalidates the request before taking the same lock. A preceding write
  is cleared by reset; a queued obsolete write is rejected.
- Report persistence failure separately: usable network results still display.

## Live measurement

Public live queries only, no private profile cache. Shanteneri, 250 LY,
Platinum, maximum market age 1 hour, large pad, minimum demand 5,000 t.

The new full parallel retrieval took **19.658 seconds**:

| Domain | Time | Rows |
| --- | ---: | ---: |
| Rings | 19.657 s | 24,447 merged rings / 25 pages |
| Regional Powerplay | 0.381 s | 640 projected public rows |
| Markets with provider fallback | 0.840 s | 1,027 merged markets |

Ring coverage was `bounded=false`; BZ Ceti remained included. ED-Frame returned
200 markets, Ardent returned 1,000, EDData was not needed. No domain errors.

Prior ring-only retrieval measured 24.99 seconds with separate requests; the
new measurement includes all three network domains. These are sequential
live samples, not a controlled speedup guarantee or GUI time-to-first-render
benchmark. The network is still the dominant cost. Freshness and service load
can change timing and row counts.

Background persistence is verified with real worker-thread tests, separate
from this network-only measurement. SQLite retention/pruning policy and BGS
prediction rules were not changed. Other Journal-ingestion and catalog-sync
paths were not redesigned by this focused refresh change.

## Verification

- 970 app tests and 88 server tests passed; repository hygiene and diff checks
  passed. Thirteen new refresh tests cover concurrent starts, session ownership
  and closure, per-domain failures, fallback, cancellation, worker-only writes,
  profile/path/generation guards, reset, coordinate persistence and save errors.
- Isolated offscreen source startup smoke test: PASS, including Mining Finder,
  all pages and dialogs. No user's active profile was used.
