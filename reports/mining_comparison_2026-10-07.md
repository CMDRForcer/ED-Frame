# Live comparison: ED-Frame / MeritMiner

Checked 2026-10-07 around 18:04–18:09 UTC. Read-only; no application, BGS or server configuration changed.

## Scope

Shanteneri, 250 LY, Platinum, LASER / Laser Surface, all reserves and ring types, large landing pad, minimum demand 5,000 t, maximum market age 1 hour, no power restriction. MeritMiner's maximum demand was 0 (unlimited). ED-Frame used HIGHEST PROFIT, maximum demand unlimited, rings only, hotspot not required.

MeritMiner was checked through its actual search UI at https://meritminer.cc/. ED-Frame was checked using the current source app's real server projection, NavigationMixin filtering and route planner, without a private profile's retained catalog or local observations. This is not a GUI performance benchmark or an exhaustive galaxy-wide comparison.

## Results

MeritMiner returned two systems with same-system sales:

| System | Station | Price/t | Demand |
| --- | --- | ---: | ---: |
| Eta Sagittarii | Coles Orbital | 59,452 CR | 11,585 t |
| BZ Ceti | Coleman Ring | 57,520 CR | 11,092 t |

ED-Frame had exactly matching market price/demand records for both. The regional server call returned its maximum 200 ring rows; the app's filter retained 171 candidates and produced the requested 30 ranked routes. These counts are NOT comparable to two MeritMiner systems: ED-Frame can propose cross-system sales and includes ring-type-only candidates.

The top ED-Frame proposal was Zeta Octantis 3 A Ring (Metallic, Platinum hotspot) with a separate sale in LHS 2661 at 300,884 CR/t, demand 9,071 t, observation about 21 minutes old. This is a nominal price opportunity, not proof of greater profit/hour, yield, or Powerplay eligibility.

## Gaps exposed

1. **Regional truncation:** BZ Ceti was absent from the bounded regional ring response, although the exact-system endpoint returned its rings. The current import alone does not ensure all useful nearby systems reach the planner.
2. **Method/ring compatibility:** LASER Platinum filtering also retained known Metal Rich rings. The commodity catalog combines method and ring availability without a per-method ring map; a Platinum hotspot currently bypasses stricter method/ring rejection. This must be corrected before claiming superior route reliability. Metallic laser Platinum versus Metal Rich core Platinum is also documented by community mining observations: https://www.reddit.com/r/EliteMiners/comments/1jb0b5l/.
3. **BZ Ceti hotspot evidence differs:** MeritMiner shows Platinum in 5 A Ring; our exact-system response has Metallic type but only a Monazite hotspot for that ring. We can treat it as a Platinum-compatible ring candidate, not claim a confirmed Platinum hotspot from our current evidence.

## Conclusion

ED-Frame shows useful cross-system sale planning and matching fresh market records. MeritMiner's two displayed results in this test are more narrowly actionable same-system laser results. No overall winner demonstrated; fix query truncation and method-specific ring eligibility first, then repeat the same benchmark. No new verified overlap or measured yield was established by this comparison.

## Repair

- Added a method-specific Platinum ring map: laser/subsurface Metallic, core Metal Rich. Known incompatible rings are rejected even when they have a Platinum hotspot or community overlap report. Ring enums and the historical Metalic spelling normalize consistently. The ring dropdown now uses the same method-specific map.
- Regional site requests paginate in 1,000-row batches rather than stopping at 200. Exact-system requests retain 200-row pages. Community-only references travel separately on the first page, so they no longer displace real observations. Stable timestamp/identity ordering, validated increasing offsets, merged duplicate observations, and explicit partial-coverage diagnostics protect paging. A 50-page safety cap remains and is reported as bounded, not complete.
- SQL selects the page before aggregating Prospector statistics. API backup: `/opt/edframe-deploy-backups/mining-pagination-20261007/api.py`. Only API service rebuilt; no BGS, collector, or catalog rows changed.
- 223 Mining tests and 87 server tests passed. New tests cover later-page results, references, invalid cursors, safety limits, SQL paging/aggregation order, and hotspot/overlap failure to override Platinum method compatibility.
- App changes are source-only; released Windows 1.5.37 requires a future release to use them.

### Final live verification

At 18:32 UTC, the 250-LY Shanteneri search retrieved 24,447 merged ring records across 25 pages, `bounded=false`, including BZ Ceti. The real LASER Platinum filter retained 2,060 candidates, and Metal Rich rings no longer appeared in its proposals. The first full ring download took **221.87 seconds**; completeness is fixed, but this first-load latency remains an important performance limitation, not a speed improvement claim. Source-app restart is needed; no release or commit was performed.

## Subsequent performance work

Version 1.5.38 was committed as `3836c9a`, pushed, and published with Windows/source archives and checksums. Its packaged app still uses offset paging.

The subsequent source implementation uses descending timestamp/identity keyset cursors, a matching composite page index and an exact case-insensitive system/ring metadata index. Both indexes were created concurrently; only API was restarted, with backup at `/opt/edframe-deploy-backups/mining-keyset-20261007`. Existing offset clients remain supported. No local-only caching or reduced coverage was used to achieve the improvement.

At 18:46 UTC, the same Shanteneri/250-LY/Platinum live test retrieved **24,447 merged rings across 25 pages in 24.99 seconds**, `bounded=false`, including BZ Ceti. The real laser filter still retained 2,060 candidates. This is approximately 8.9x faster than 221.87 seconds; it is a measured full network retrieval, not a disk-cold benchmark or GUI time-to-first-render measurement. The new client cursor handling is not in the already published Windows 1.5.38 package.
