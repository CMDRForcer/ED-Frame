# Mining Finder data contract

Status: implemented read-only contract for QML, navigation and the
profile-bound runtime catalog. It never initiates uploads.

## Evidence shown to users

- `LOCAL_CONFIRMED`: the Commander's own Journal directly observed the fact.
- `LIVE_REPORTED`: a schema-valid public EDDN event was received live. It is a
  report, not a guarantee that a hotspot or deposit still exists.
- `CATALOG_CANDIDATE`: searchable Spansh body/ring data with its source update
  time. It is suitable for finding destinations, not confirming current yield.

Location evidence does not expire. When its last confirmation exceeds ED-Frame's
display policy (24 hours for live reports and 30 days for local/catalog
observations), it remains searchable with its original evidence and receives
`RECHECK_RECOMMENDED`. A missing timestamp becomes
`CONFIRMATION_TIME_UNKNOWN`. Neither state claims that a ring disappeared.

The UI must never label a destination or yield as guaranteed.

Powerplay control is assessed independently of ring and market ages. Supporting
control/state/participant observations up to 48 hours old can confirm route-rule
compatibility. Explicit dated control up to 14 days old can suggest a compatible
route as `POWERPLAY_PROVISIONAL` / `LAST_KNOWN`; it never becomes `VERIFIED` or
increments the verified-merit count. Older, undated, invalid or presence-only
facts cannot earn a provisional merit score. Newer control observations replace
older control, and download/cache times never renew observation times.

Merit searches supplement regional price-ranked markets with exact system
checks for compatible Powerplay routes. Server 0.9.3 accepts up to 200 exact
systems per public batch. The app dispatches at most eight sequential batches
(1,600 systems) within a 20-second dispatch budget, with 2/12-second connect/read
timeouts. Each batch also returns original-dated Powerplay facts and up to
5,000 retained rings for those systems. Partial ring reads remain marked partial.
Eligible regional Powerplay systems with known coordinates can receive exact
ring data even when a bounded regional ring page omitted them. Optional Power
and goal filters apply before regional Powerplay pagination; cache keys include
both filters. Older servers retain the 64-pair foreground fallback, using at
most two concurrent connections (one on constrained resource profiles). Current
and last-known routes remain separate in ranking. Successful empty results are
cached for ten minutes, populated results for five; failed/cancelled checks are
not cached as absence. Deferred displayed market checks continue in six-target
blocks only while the Mining page is visible and idle. Query/profile changes
discard old deferred queues.

ALL COMMODITIES fetches the full ring-type scope independently of the concrete
commodity used for market warming. Its regional read budget is 200,000 raw rows
(concrete commodity reads retain 50,000), and reaching any client/server bound
remains explicitly partial. Legacy cursor continuation remains compatible with
the server's 100,000 numeric-offset validation. Regional cache entries keep
their separate ALL/concrete scope and existing memory limits.

The targeted ALL supplement checks concrete method-compatible commodities and
reuses qualifying local market rows in its network worker. Existing local rows
are only selection input; they are not republished/re-ingested as new downloads.
ALL merit results keep current/last-known eligibility first, compare actual
sale value next, and show the best route per mining system before additional
rings from those systems. This changes the broad result ordering deliberately;
concrete-commodity searches keep their existing ordering.

## Source responsibilities

### Local Frontier Journal

`Scan` supplies body/ring structure and reported reserve level.
`SAASignalsFound` supplies SAA signal types and counts for a body or ring.
`ProspectedAsteroid` is a direct sample of one asteroid: materials/proportions,
content, remaining percentage and an optional motherlode material.
`MiningRefined`, `Cargo` and `MarketSell` describe actual collection, current
cargo and sale results. `LaunchSRV`/`DockSRV` bound an observed Rhino session.

A prospector sample proves only that asteroid. A hotspot or reserve label does
not prove a particular yield.

### EDDN

Only ED-Frame's already-supported `journal/1` `Scan` and `SAASignalsFound` events
are candidates. Existing allowlists, private-field stripping and schema
validation remain mandatory before queueing and sending. `ProspectedAsteroid`,
`MiningRefined`, cargo and sales remain local and are not added to EDDN.

### Spansh

The documented `/dump/{id64}` response is the catalog contract because its
`system.bodies[].rings[]` records contain ring type and optional signal data;
the smaller `/system/{id64}` response does not carry this ring detail. ED-Frame
projects only system identity/coordinates, body name/arrival distance/reserve,
ring name/type and the ring signal map/update time. Missing properties stay
unknown rather than receiving inferred defaults.

### INARA

INARA remains a Commander synchronization integration. Its API is not treated
as a bulk galaxy/mining search service and is outside the finder data path.

## Rhino boundary

ED-Frame has observed Rhino session boundaries plus refined cargo and engineering
material events. No Rhino-specific deposit taxonomy, range, yield, vehicle
capacity or new Frontier identifier is inferred here. New fields must first be
observed in a redacted Journal sample and covered by a fixture.

## Runtime verification

The controller, modular Mining page and profile-bound market store use this
contract. Deferred planner work resumes after pending public inputs finish even
when the Mining page has been recreated during navigation. Successful empty
background market responses do not invalidate an unchanged plan. Public-data
comparison and populated-store UI measurements are recorded in the release
validation reports; bounded reads never imply complete galaxy coverage.
