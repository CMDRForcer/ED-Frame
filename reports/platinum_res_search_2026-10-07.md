# Platinum + RES search

New optimization PLATINUM + RES selects Platinum/LASER and lets the user filter
ANY, LOW, REGULAR, HIGH or HAZARDOUS. Applied filters are passed to the planner
through the existing optimization argument; no QML slot signature changed.

Only reports for Platinum with an explicitly recognized reported RES level
qualify. RES existence without a reported hotspot overlap does not qualify.
Community reports remain undated and unverified, with source evidence retained.
Unknown ring composition or yield is not upgraded by a historical report.
Community-only candidates are labeled COMMUNITY_OVERLAP, not HOTSPOT CONFIRMED.
Routes are sorted by existing distance score; market filters remain intact.

Server search accepts optional include_community_overlaps. It includes existing
site identities whose exact normalized ring is in the matching commodity's
community catalog, while keeping normal age, system, radius and result bounds.
No fictitious coordinates, new ring observations, BGS changes or RES scores.
Coverage is limited to baseline rings present in our server and the bounded
regional query. Remaining baseline rings still need coordinate/site coverage.

Server deployed with API-only restart. Backup directory:
/opt/edframe-deploy-backups/overlap-search-20261007-01
Rollback image: edframe-catalog-api:before-overlap-search-20261007-01.
73 server tests and 148 app/QML tests passed before the additional controller
regression test. Local application changes have not been committed or released.
