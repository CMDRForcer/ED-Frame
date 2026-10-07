# Bulk mining-ring source assessment — 2026-10-07

## Selected source

- Official populated-system dump: https://downloads.spansh.co.uk/galaxy_populated.json.gz
- Official schema: https://docs.spansh.co.uk/galaxy.schema.json
- Download catalogue: https://spansh.co.uk/dumps
- Scope: known populated systems, not all explored or undiscovered galaxy systems.
- Ring names/types, parent reserve levels and separately dated ring signal counts are available.
- Counts alone do not establish spatial hotspot overlap, RES presence or measured yield.

## Canonn findings

- https://github.com/canonn-science/CAPIv2-Strapi documents rings alongside its science-site APIs; its software licence is not a blanket dataset licence.
- https://github.com/canonn-science/VideoAnalysis/blob/main/DESIGN.md explicitly obtains ring/body data from Spansh for its ring-rotation project.
- No suitable complete, verified RES/hotspot-overlap bulk source was established in this check. This is not a claim that Canonn holds no other relevant research.
- No Canonn dataset was copied or exported.

## Import safeguards

`server/catalog_service/ops/import-spansh-rings.py` separates extraction from application.
Full streamed gzip traversal validates the CRC; compressed source and compact snapshot receive SHA-256 hashes.
Application requires the matching completed manifest. No partial extraction is applied.
The original mining-site table is backed up before importing.
Missing ring identities are added only when the exact system/ring pair is absent; existing site IDs, data and prospector ownership are not overwritten.
All source ring snapshots and provenance are retained separately in `ring_reference_metadata`.
Missing metadata can be enriched by exact ring/system match, with enum normalization and conflicting values left unknown.
Old hotspot timestamps are not freshened by newer body metadata or the import date.
No market, BGS or Powerplay tables are imported.
No recurring third-party queries or schedule is created.

## Operational scope

- Source download is about 4.53 GB compressed, streamed without retaining the full decompressed galaxy.
- Server preflight: about 19 GB free disk and 3.8 GB RAM; streamed parsing and COPY keep memory bounded.
- Pre-import mining sites: 548,820 total (includes non-ring candidates; not a ring-coverage count).
- Backup: `/opt/edframe-deploy-backups/bulk-rings-20261007-01/mining-sites-before.dump`, archive listing verified.
- Final source/row counts and hash are recorded by the generated snapshot manifest and application log, not estimated here.

## Completed import

- Full compressed dump: 4,527,353,407 bytes; SHA-256 `9f59d5ba9afb01eb1903ff667a92f2c21c72369b5a6104c067d295355f2feb49`.
- 151,862 source systems; 303,460 projected ring rows; 303,447 unique exact system/ring pairs after deduplication.
- 284,879 new mining-site rows inserted; no existing mining-site rows overwritten.
- Snapshot and manifest retained under `/opt/edframe-catalog-data/imports/rings-20261007/`.
- API metadata enrichment deployed against the retained ring-reference table.
- Optional `include_ring_candidates=true` searches compatible known ring types without claiming a commodity hotspot; the updated app request opts in. Existing method/commodity eligibility checks remain downstream.
- Asteroid belts are excluded from the ring-type fallback.
- Live example: BZ Ceti 5 A Ring is now present as Metallic/Common and CATALOG_CANDIDATE. Its known Monazite hotspot is not relabelled as Platinum.
- The existing released client can consume newly imported actual hotspot records; the additional opt-in ring-type search requires the updated app code.
- Tests: 86 server tests and 218 Mining app tests passed.
- BGS, market and Powerplay data flows were not modified.
