# Missing community ring references

Read-only live audit: 80 normalized baseline rings, 30 matching actual stored
mining ring observations, 50 missing. Of those 50, 28 have known system positions;
22 do not. An attempted one-time EDSM lookup resolved none of the 22 (HTTP errors).
The failure ledger is ed_data/community_res_system_positions.json; no failed
response is accepted as coordinates. No third-party polling is introduced.

The API's explicit include_community_overlaps option now includes historical
reference candidates anchored to existing public system coordinates. Those are
CATALOG_CANDIDATE / COMMUNITY_REFERENCE_ONLY, not new observed rings. Their ring
type, reserve, body ID, observation time, hotspots and measured yield remain
unknown or empty. Position provenance is kept separately from ring evidence.
No mining_sites rows are written. Existing observations are not overwritten.

References obey system, commodity, radius and total result limits, and known
returned rings are not duplicated. References get slots before normal rows in
the explicitly opted-in bounded query, so a full ordinary page does not hide
them. App projection preserves the association status and UI says RING UNCONFIRMED.

Expected usable baseline coverage: 30 observed-ring matches plus 28 coordinate-
anchored historical references, not 58 verified overlaps. Twenty-two remain
unlocated and cannot be placed honestly in the regional search.

75 server tests, 146 app/contract tests and 3 QML smoke tests passed. BGS untouched.
Deployed with API-only restart around 15:50 UTC. Live read-only verification:
30 observed-ring matches + 28 additional anchored references = 58 usable,
22 unresolved. No coordinates for the remaining systems were found in other
mining observations either. Public search for HIP 7799 now returns its historical
A 3 A Ring reference, with ringType/observedAt null and CATALOG_CANDIDATE evidence.
Health endpoint returned OK. Backup directory:
/opt/edframe-deploy-backups/ring-coverage-20261007-01
Rollback image: edframe-catalog-api:before-ring-coverage-20261007-01.
App changes remain uncommitted and unreleased.
