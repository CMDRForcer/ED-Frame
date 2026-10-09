# ED-Frame 1.0.7 — prepared local candidate

This candidate is unpublished. App 1.0.7 is paired with catalog server 0.9.2.

- Broad mining searches prepare commodity/method/ring rules once per query.
  Route planning and diagnostics share the exact market read within one worker;
  the next search and verification read again.
- Background planners retain known start-system coordinates from their captured
  ring view. ALL COMMODITIES now sees regional markets when another system is
  being warmed in the background.
- The matching server supplements missing explicit Powerplay control from
  bounded, identity-checked Spansh snapshots. Current EDDN control is reused
  first; newer/equal-time EDDN observations win conflicts. Original source times
  remain unchanged and missing fields remain unknown.
- The existing community connection switch controls the new targeted lookup.
  The extension needs the matching server deployment; older servers retain the
  existing lookup/fallback behavior.

Frozen populated-store measurements cover Platinum and ALL COMMODITIES at
250/500 LY. The domain worker's returned fields and order remain identical for
all four performance comparisons. The separate free-text origin correction
intentionally restores previously omitted markets in the actual QML workflow.

Broad searches still consume substantial CPU and RAM. Timings, UI stalls,
validation and artifact identities are recorded in the
[complete measurement report](mining_complete_benchmark_2026-10-09.md).

Publication remains a separate joint step: review this candidate, deploy the
matching server with the usual backup/health checks, then publish the tested
app. No Git push, release tag or production rollout is part of this preparation.
