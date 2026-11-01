# Frontier market refresh — local test build, 2026-11-01

The Frontier refresh action now reads `/profile`, `/shipyard` and `/market`
in one background request bundle. There is no additional polling timer.
A failed station document leaves the successful Commander profile usable.
Rate limits stop subsequent requests in the bundle; `Retry-After` is respected
without occupying a worker throughout a long server cooldown.

Public `commodity/3` messages use only allowlisted market fields and explicit
`CAPI-Live-market` provenance. Publication requires enabled Frontier consent,
matching Journal Commander and station, a docked Commander, a recent response
and enabled EDDN uploads. Newer Journal/queued observations take precedence.
Withdrawal, profile changes and watchdog expiry invalidate late results.

A missing/null commodity list or an incomplete row rejects the entire market
document. An explicit empty list can clear removed carrier orders. Zero stock
does not remove valid purchase orders. Equivalent economic contents already
queued/accepted within five minutes are not uploaded again; changed quantities
and later freshness confirmations can be sent.

The live test exposed a signal backlog ahead of fresh markets. Station inventory
messages now take priority over exploration/signal messages, retaining FIFO
within each group. Signal events remain queued; consent, profile isolation,
retry deadlines and the existing send interval are unchanged. Six regressions
cover priority selection and these delivery guards.

Connections → Frontier CAPI shows read/queued/sending/retry/accepted states,
goods with sell stock, goods with purchase demand and the observation time.
Acceptance means an EDDN gateway receipt, not confirmed ingestion by Inara
or a Discord bot. The guides and all four interface catalogs were updated.

Validation:

- Full app suite before the priority follow-up: 1,502 tests passed. Final
  targeted suite including the queue priority change: 146 tests passed.
- 24 added regressions cover identity, missing and empty inventories, partial
  responses, zero-stock purchase orders, duplicate suppression, queue delivery,
  consent withdrawal, late responses and rate limits.
- Source QML smoke: all 33 areas passed. A synthetic German status card was
  rendered and inspected; its populated quantity labels were also checked.
- The packaged Windows application also passed all 33 QML smoke areas in an
  isolated profile with public uploads disabled.
- A fake HTTP gateway verifies the compressed public payload and receipt flow.
  No live Frontier request or additional public upload was performed by this QA.

The initial packaged smoke result is retained beside the local Windows test
build; that first ZIP predates the queue-priority follow-up. The complete
implementation, including the priority and throughput changes, is included in
app 1.0.13. No server deployment is needed.
