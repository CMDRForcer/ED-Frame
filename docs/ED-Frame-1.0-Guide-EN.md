# ED-Frame 1.0 — getting started and features

Updated for the 1.0.5 Powerplay maintenance release.

ED-Frame is a free, open-source Windows companion for Elite Dangerous. Your local Journal drives your Commander workspace; ED-Frame's own community server supplements it with shared public galaxy observations.

## Install and upgrade

1. Download the Windows ZIP from the [latest ED-Frame release](https://github.com/CMDRForcer/ED-Frame/releases/latest).
2. Extract the complete archive into a new, writable folder.
3. Run `ED-Frame.exe` with `_internal` beside it. Python is bundled.
4. Select your Elite Dangerous Journal folder if it is not detected automatically.
5. Review **Connections**, then select the workspace for your next activity.

Use Windows 10 or 11. Personal settings, credentials, builds and retained data live under `%LOCALAPPDATA%\ED-Frame`, outside the portable folder. Reuse your existing profile; do not copy it into the application archive. The new 1.0 release line succeeds the older EDEC/ED-Frame builds, including 1.5.43, even though those historical numbers are larger. Download the current release rather than sorting old tags numerically. The executable is not code-signed; Windows may show a SmartScreen warning.

## Features, one at a time

- **Operations:** follow the next collection, trade, unlock, travel or crafting action for a tracked build.
- **Engineering:** plan grades and experimental effects on the actual physical slots of each known ship. Compare installed equipment with your plan, including power draw estimates.
- **Wishlist:** track several fleet builds, material readiness and Journal-confirmed craft progress.
- **Engineers:** search capabilities, follow unlock prerequisites and find suitable destinations.
- **Technology Brokers:** track one-time Human and Guardian unlock requirements.
- **Materials:** inspect inventory, farming guidance and trades that respect materials reserved by builds.
- **Mining Finder:** choose commodity, method, origin and radius; compare site evidence, market price, demand, quote age and pad size. Plan Acquire, Reinforce and Undermine routes.
- **Measured mining yield:** distinguish Prospector/refining measurements from hotspot reports and ring-type estimates. A measured sample is not a yield guarantee.
- **Module & Ship Finder:** search observed station inventories and prices. Review current-hull and physical-slot compatibility; distinguish observed and inferred prices.
- **Commodity Finder:** use BUY for station stock or SELL for demand. Filter quote age, quantity, pad and distance.
- **Station services:** find nearby observed services from Nav.
- **State Finds & HGE:** compare sightings, reported signal lifetime and separately labelled BGS predictions.
- **Powerplay:** review pledged power, rank, merits and explicit system control from observed data.
- **CMDR & Fleet:** inspect ranks, reputation, credits, assets, CR/h and your known ships. Plan a parked hull without switching ships in-game.
- **Missions:** review deadlines, destinations, rewards, massacre stacks and recorded Community Goals.
- **Exploration:** inspect unsold Journal scans, noteworthy bodies and clearly estimated cartography values.
- **Exobiology:** track survey targets, sample distances, completed species and observed earnings.
- **Surface navigation:** save planetary waypoints and use the compass or separate always-on-top overlay. Live guidance requires Elite's coordinates and heading; surface distance also needs body radius.
- **Logbook:** search flight events and keep local notes.
- **Appearance:** choose six themes, four interface languages, scaling, overlays and diagnostics.

## The ED-Frame community server

The server continuously processes supported public EDDN observations. It supplies systems, stations, commodity markets, module/ship inventories, rings/hotspots, Powerplay facts and State Finds observations. Supported anonymous mining-yield, signal and station-price contributions extend that shared knowledge.

**Freshness is based on the source observation.** A newly downloaded old quote is still old. Mining Finder separates market confirmation from Powerplay suitability. A missing controller, price, demand or pad observation stays visibly missing. A verified market/Powerplay route does not prove a measured yield or promise the merits you will receive in-game.

Powerplay confirmation requires observations within 24 hours, assessed separately from the market-age filter. Older control/state facts remain stored and show as outdated. Explicit unoccupied systems can support Acquire targets without a selected-Power presence row. Exact server checks distinguish systems not yet observed from systems whose last observation is too old; another refresh cannot create an unreported observation.

Retained observations remain available locally when a service is unavailable or disabled. The ring store reads the relevant region from SQLite and preserves original observations and their history. Offline data cannot provide unseen live updates.

## Connections and privacy

- **ED-Frame community connection:** enabled by default for new profiles. The switch in Connections controls catalog access and supported anonymous contributions together. Disabling it preserves retained local data.
- **EDDN:** public upload/listener functionality is enabled by default for new profiles and has its own Connections switch. Supported messages are schema-checked and exclude private/unsupported fields.
- **Frontier CAPI:** separate consent and Frontier login are required. It supplements supported credits and active-ship information; newer Journal evidence remains authoritative.
- **INARA:** requires your own setup and API key. It can transmit supported Commander events to INARA when enabled.
- **Spansh and EDSM:** supply public catalog data through their respective connection/refresh controls.

The **ED-Frame server** does not accept Commander names/FIDs, raw Journal files or paths, private builds, wishlists, credentials or tokens. This boundary applies to the ED-Frame public service; INARA has its own Commander-data integration. Windows DPAPI protects supported local credentials. Disabling ED-Frame and EDDN does not automatically disable separately configured services; review each connection if you want local-only operation.

The enclosed **1.5.5 PDF manuals are historical references** and predate these features and community defaults. Use this guide and the [current README](https://github.com/CMDRForcer/ED-Frame#readme) for 1.0.

[Report a problem](https://github.com/CMDRForcer/ED-Frame/issues) · [Source and license](https://github.com/CMDRForcer/ED-Frame) · [Website](https://cmdrforcer.github.io/)
