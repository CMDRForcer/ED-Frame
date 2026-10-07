# Mining ring metadata verification — 2026-10-07

## Cause

Scan uses the parent body's ID; SAASignalsFound uses the ring body's ID.
The existing mining-site identity therefore separates metadata and hotspots for
the same named ring. No IDs or stored observations were rewritten.

## Change

The mining-sites API fills missing ring type and reserve level from existing
observations matching system and exact ring name. Conflicting non-null system
addresses are excluded. Conflicting field values remain unknown. Existing values
are preserved; added fields include source and observation-time evidence.
Yield samples, hotspot counts, BGS predictions and ranking logic are unchanged.

## Verification

- 68 server unit tests passed, including four new metadata tests.
- Production verification used SELECT only in a read-only transaction.
- 738 Platinum hotspot entries examined.
- 529 entries gained ring type: 121 Metallic, 408 Metal Rich.
- 209 remain unknown; 503 entries have reserve metadata after enrichment.
- Body IDs unchanged; enrichment took 0.200 seconds for this batch.

Metal Rich must not be treated as Metallic or as proof of laser-minable Platinum.
This fixes associations using existing data, not the remaining coverage gap.

## Delivery state

Deployed with user approval on 2026-10-07 at approximately 15:17 UTC.
Only API was rebuilt/restarted; database and collector were not restarted.
Public /healthz returned OK and the API container became healthy.
Public /v1/sites/search for HIP 63988 Platinum returned Metal Rich,
PristineResources, unchanged body ID 41 and Scan provenance timestamps.
Backup: /opt/edframe-deploy-backups/ring-metadata-20261007-01/api.py;
rollback image: edframe-catalog-api:before-ring-metadata-20261007-01.
No database migration or bulk import was performed.
