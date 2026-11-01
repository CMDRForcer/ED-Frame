# EDDN upload throughput — local implementation, 2026-11-01

The sender previously shared the single background lane with catalog imports.
Interactive tasks could prevent the next upload starting, and each send also
depended on the full asynchronous Journal/profile projection becoming current.
Live receipts showed a 67 ms median network call but a 19 s median acceptance
interval in the inspected 25-receipt sample.

## Final behavior

- One serial upload lane runs independently of the bounded general worker pool,
  including on two-core machines. Uploads remain serial; no CPU-specific code
  or increased network concurrency is introduced.
- Each queued message keeps its original profile/context. Before HTTP, the
  sender checks the current Journal session identity on its I/O worker. A new
  or incomplete session, different profile/root, withdrawn consent or shutdown
  pauses transmission. Normal Journal appends no longer require a full history
  and location projection before every message.
- Station inventories take priority while preserving order within each queue
  class. The 400 ms floor remains enforced; an early timer rearms the remaining
  delay instead of losing the send until the next Journal poll.
- A small, separate per-profile `eddn_delivery_receipts.sqlite3` records attempts,
  accepted receipts and retry state durably on the sender before Qt publishes
  the result. Startup reconciles these records with the existing JSON queue.
  Known accepted messages are not resent merely because the UI/snapshot had
  not caught up. Unacknowledged in-flight requests retain the existing possible
  duplicate warning after an interrupted process.
- UI updates and JSON snapshots are coalesced to roughly once per second.
  Bulk archival and archive counts run off Qt. Existing JSON message contents
  remain durable, and the Journal cursor does not advance on a failed queue save.
- Receipt cleanup happens only after archival and a durable queue snapshot.
  It compares the exact acknowledgement token, so an old archive operation
  cannot remove a later attempt or acknowledgement for the same message ID.
- HTTP 429 cooldowns are persisted independently of individual jobs. They
  survive restart and receipt cleanup. Storage errors retain records and stop
  new uploads; a received HTTP acknowledgement falls back to the JSON snapshot
  before display if the receipt database cannot be written.

Connections → EDDN → Show technical details exposes worker wait, profile check,
network, receipt-write and UI callback times. These measurements remain local.

## Validation

The isolated whole-app throughput exercise uses real Qt, scheduling, profile
checks and persistence, with a **fake gateway returning after 60 ms**. Twenty
synthetic market messages start in a roughly 1.1 MB queue while a deliberately
blocked interactive task remains active. The final measurement is retained
with the local build; this test sends no synthetic data to EDDN.

Final controlled measurement: 20 messages in 10.373 s (1.928/s), median gap
480.59 ms, maximum gap 814.13 ms. The last worker wait was 0.41 ms, profile
check 0.77 ms, receipt write 8.65 ms and Qt callback wait 0.29 ms. The blocked
interactive task was released only after all 20 uploads completed. These are
controlled test results, not a promise about live gateway response times.
The complete page exercise still recorded brief UI delays (209 ms maximum);
this change does not claim to eliminate every source of UI work.

The full app suite passed 1,527 tests before the final timer/archival refinements.
The final focused suite passed 93 tests and covers those refinements, restart recovery, failed
writes, profile fences, rate limits, archival races and the two-core scheduler.
Source and packaged QML smoke results are retained with the local test build.
The final source exercise passed all 34 areas, including throughput; the final
packaged Windows application passed all 33 standard QML smoke areas. Twenty-two
sender/scheduling regressions were added. Seven final UI checks also passed.
The DE/EN guides and all four translation catalogs include the new diagnostics.

Initially validated locally against 1.0.12, these changes are included in app
1.0.13. They need no server deployment. A source checkout can be tested using
the project's `START_APP.bat` after fully exiting the running application.
