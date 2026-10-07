# Commodity search — 2026-10-07

## Follow-up: normal market purchases only

User requested removal of everything not purchasable in a normal station
commodity market. This supersedes the original all-symbol UI described below.
Live check: 269 selectable goods, including 142 EDCD rare-reference entries,
from 412 retained server symbols. Rare Goods is a separate translated category
and retains the underlying trade category in `tradeCategory`.

Normal recognized categories are admitted, except explicitly excluded
mining-only, mission-reward and other non-purchasable cargo. Salvage and
NonMarketable categories and unknown symbols are excluded unless a positive
rare-purchase reference applies. Absence of current stock is not used to remove
an otherwise classified market good; temporary shortages do not erase choices.
Price/stock observations continue to determine actual BUY offers.

Cross-check source for sell-only/mining and reward cargo:
[INARA commodity list](https://inara.cz/elite/commodities-list/), checked
2026-10-07; EDCD normal and rare references remain the local naming sources.
No external live query is added to the app. New unclassified goods require
reference review before admission. Historical/seasonal rare-reference entries
do not guarantee current supply; only actual quote observations produce offers.

Selection, direct requests and retained-row display use the same eligibility
rule. The reference is cached in memory, not re-read on every state update.
No server data was deleted, no API deployment or DB migration was necessary;
Mining Finder and its sell-only goods are unchanged.
11 focused commodity tests and isolated wide/narrow QML preview passed.
Final full app regression: 919 tests, PASS (including real Main.qml smoke).

Layout follow-up: text search moved to the leftmost position, followed by
category and commodity selection. Preferred widths keep refresh and numeric
quantity controls from consuming excessive space. Minimum tonnes has a visible
caption. At narrower widths the controls wrap into two/three columns. Wide and
narrow offscreen previews pass without binding/rearrangement errors; preview
also checks that search precedes category and rare/category filtering works.

## Delivered

NAV → COMMODITIES (German: WARENSUCHE), also accessible from Operations.
All 412 server symbols are selectable. Categories plus local name/symbol
filtering provide a dropdown of matching commodities; typing sends no network
requests. Catalog loads only on first opening or manual refresh. Quotes load
only when FIND OFFERS is clicked, in a network worker.

BUY uses the station's buyPrice and stock; SELL uses sellPrice and demand.
Zero/missing prices, missing quantities, invalid/stale timestamps and invalid
coordinates are not converted to offers. Price ascending for BUY, descending
for SELL; LY and arrival LS break ties. Radius, quantity, freshness, pad and
carrier filters are bounded. Rows show quote age/source, permit explanation,
carrier uncertainty and reported prohibition; none is a guarantee of docking
access or legal trade. No route-profit optimization is claimed.

The name/category references were downloaded once from EDCD/FDevIDs:
[commodity.csv](https://github.com/EDCD/FDevIDs/blob/master/commodity.csv),
[rare_commodity.csv](https://github.com/EDCD/FDevIDs/blob/master/rare_commodity.csv).
They provide labels only, never prices. 398 symbols are classified; 14 unknown
symbols remain visible under Unclassified. New EDDN commodity symbols appear
on the next catalog refresh without a static mining whitelist.

## Real server verification

API deployed with previous source/image backed up at
`/opt/edframe-deploy-backups/commodities-20261007`; only API restarted.
No migration or database/collector restart. `/healthz`: HTTP 200, status ok.
The initially tried `/health` returned 404 because that is not the health route.
The existing market table remains the sole quote store; no duplicate historical
table or automatic per-commodity polling was added.

Live calls through the actual app parser, origin Sol (0,0,0), 100 LY, 24 h,
minimum 1 T, carriers excluded, any pad:

| Commodity | Direction | Rows | HTTP + parse seconds | First observed quote |
|---|---|---:|---:|---|
| Gold | BUY | 100 | 0.551 | Berners-Lee Refinery / Chi Eridani: 4,434 CR, stock 179 T |
| Gold | SELL | 100 | 0.353 | Buchli City / Mildeptu: 66,957 CR, demand 17,997 T |
| Water | BUY | 100 | 0.479 | Scithers Hub / G 141-21: 6 CR, stock 6,087 T |
| Water | SELL | 100 | 0.292 | Rum Runner Station / Alrai Sector KH-V b2-3: 1,969 CR, demand 3,149 T |
| Platinum | BUY | 0 | 0.388 | No matching stock, not an inferred price |
| Platinum | SELL | 100 | 0.259 | Ito Landing / Erlaza: 302,844 CR, demand 4,208 T |

Nonempty calls reported hasMore; app displays that only the first 100 matches
are shown. Catalog initial HTTP call took 3.223 s, subsequent check 0.7 s or
less overall. Prior live EXPLAIN of the indexed inventory walk: approximately
65 ms for 412 symbols. These are individual observations, not a concurrency
load test or a latency guarantee.

## Verification scope

| Check | Result |
|---|---|
| Full app regression | 916 tests, PASS |
| Catalog server regression | 57 tests, PASS |
| Isolated commodity QML render, 1280 and 650 px | Exit 0, no QML runtime errors |
| Final real Main.qml smoke + button interaction contract after Operations entry | 2 tests, PASS; final preview Exit 0 |

The offscreen font-directory notice is an environment warning; an explicitly
loaded Segoe UI font was used for preview rendering.

Real: deployed API, raw station quotes, actual parser, catalog coverage,
server health. Simulated: isolated wide/narrow QML render with two explicit
fixture rows (including missing permit/carrier/prohibition). Screenshot files
are `commodities-preview.png` and `commodities-narrow.png`. Narrow hint wrapping
was corrected and checked against measured text height. No user's running app
was terminated/restarted and no real journal/profile was altered.

Tests cover all symbols including unknowns, buy/stock vs sell/demand mapping,
no mean fallback, invalid/stale/zero/missing fields, pad/carrier/radius filtering,
response direction/region confirmation, unchanged rows after failures, and
profile/location/disabled-server guards. API contracts verify indexed inventory
walking, direction-specific SQL, parameterized filters, pads and truncation.
The QML interaction guard now distinguishes reusable inline component types
from actual buttons and checks their actionable instances too.

No commit or push was requested for this step. Existing unrelated pending
changes have been preserved.
