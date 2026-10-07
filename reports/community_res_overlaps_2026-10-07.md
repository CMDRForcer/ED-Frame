# Community RES/hotspot baseline

Frozen upstream CSV bundled in ed_data/community_res_overlaps.json, with original
data, attribution and upstream README MIT notice. No ongoing third-party query.
Snapshot revision b5680d18c84c21c088027c04fec5a9bf56dab31c; source file modification
2025-01-05T15:02:03Z. Imported 2026-10-07; verification date remains null.

The API exposes all reports at /v1/mining/overlaps, optionally filtered by system
or commodity, and attaches matching reports to existing /v1/sites/search rows.
System and normalized full ring names must match. Multiple source rows are
preserved, not arbitrarily selected or promoted based on import date.

Other commodities (including Painite, Tritium, LTD and Bromellite) retain their
identity. Where the upstream column does not explicitly name a commodity, its
Platinum context is marked commodityExplicit=false. Reported percentages without
sample counts are NOT ingested as Prospector measurements or high-yield proof.
Known incorrect historical entries remain historical, not verified suggestions.

App projection and merge preserve source URL, row, revision and timestamps.
Community overlap reports do NOT populate confirmed RES fields, change scores,
create live sightings or alter BGS. UI flags community reports as undated.

This is a historical baseline, not a current verification campaign or a guarantee
of permission from every third-party contributor. Upstream project credits
EDTools; attribution is retained rather than hidden.

Deployed 2026-10-07 around 15:31 UTC. Public catalog returns 91 reports:
60 Platinum, 21 Painite, 4 Tritium, 3 LTD, 3 Bromellite; 80 normalized rings.
Read-only production matching found 42 stored rows across 30 exact named rings.
The remaining baseline rings are available through /v1/mining/overlaps, but are
not invented as coordinate-bearing candidates in the existing sites query.
API health is OK. 72 server tests and 147 app/contract/QML smoke tests passed.
Backup: /opt/edframe-deploy-backups/overlaps-20261007-01/api.py;
rollback image: edframe-catalog-api:before-overlaps-20261007-01.
Only API restarted. No database migration or collector restart.
Local application changes are not yet committed or released.
