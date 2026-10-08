# Domain-specific cache invalidation — audit item 3

Source-only change. No commit, push, server deployment or new Windows release.
The preceding uncommitted refresh/priority/background-merge work is preserved.

## Mining

- Ring projection keys no longer contain the global state object identity or
  the identity of an equivalent freshly allocated local-candidate list.
- Journal-state workers build a deterministic local-candidate content digest.
  UI getters compare that small token, not a large local/regional JSON dump.
  Unsigned legacy/imported states retain a content-comparison fallback.
  Worker-produced candidate snapshots are immutable; new observations produce
  a new digest, including same-count yield/hotspot/provenance changes.
- Profile/generation, position/system, catalog identity/revision/reset and
  hourly projection freshness remain keys. A valid worker result is accepted
  even if unrelated credits/materials changed while it was building.
- The UI has its own revision, including prepared-projection publication,
  market/Powerplay revision, negative verification outcomes, refined
  commodities, ship/selection, module identifiers, cargo and vehicle readiness.
  Readiness now explicitly depends on this revision in QML.
- Minute UI/filter freshness continues even without Journal events. The
  expensive full-ring projection still uses its existing hourly cadence.
  Freshness calculations and ranking/eligibility rules are not changed.

## Fleet and other domains

- Fleet caches depend on actual fleet content, profile, ship definitions,
  image directory, mapping and file metadata, not global state revision.
- Full-state, credit and fast-location invalidation retain this keyed fleet
  projection while clearing other existing broad-state caches as before.
- Unrelated state publications skip fleet notifications. Private dependency
  snapshots detect in-place fleet changes even without a previous-state dict;
  initial publication still notifies. Image appearance/removal also invalidates.
- Finance and BGS caches/rules remain conservative and unchanged. No blanket
  retention of caches whose full dependencies have not been established.

## Local measurement

Synthetic catalog with 24,447 regional rings plus one local ring. This is
Python projection/cache code with mocked signals, not interactive Qt timing
or a private-profile/network benchmark. One first projection took 0.186558 s.
Across 100 subsequent state replacements changing only credits, all 24,448
ring rows and the fleet projection were reused:

- Ring projection builds: **1 total**, not another build per state replacement.
- Fleet model notifications during the 100 unrelated publications: **0**.
- All 100 refresh/cache checks: **0.007517 s** (mean **0.0752 ms**).

These figures show eliminated redundant work, not a guaranteed end-to-end
search speedup. Server transfer and UI-side market-store reads remain separate
performance opportunities.

## Checks

Regression tests cover equal replacement, nested/same-sized changes, immutable
worker digest use without large UI copies, position/system/profile/reset,
catalog/market/verification changes, loadout/ship/vehicle/commodity changes,
minute/hour freshness, prepared-row publication, in-flight worker acceptance,
fleet/image/catalog dependencies and selective retention of only safe caches.

Verification: all 999 app tests and 88 server tests passed. The final fleet
notification refinement also passed 25 targeted tests and a fresh real
offscreen QML smoke run (PASS, 29.896 s). Repository hygiene and
`git diff --check` passed. No installed EXE or production service changed.
