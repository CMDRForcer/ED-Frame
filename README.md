# ED-Frame

*(formerly ED Engineering Companion / EDEC)*

**ED-Frame 1.0 — your Elite Dangerous Commander workspace, backed by our own community catalog server.**

[![Latest release](https://img.shields.io/github/v/release/CMDRForcer/ED-Frame?sort=date&label=release)](https://github.com/CMDRForcer/ED-Frame/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/CMDRForcer/ED-Frame/total?label=downloads)](https://github.com/CMDRForcer/ED-Frame/releases)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue)](LICENSE)
![Platform: Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-informational)
![Languages: EN · DE · ES · FR](https://img.shields.io/badge/languages-EN%20%C2%B7%20DE%20%C2%B7%20ES%20%C2%B7%20FR-informational)

ED-Frame is a free, open-source Windows companion for [Elite Dangerous](https://www.elitedangerous.com/) — Fleet, Routes, Analytics, Materials and Engineering in one place. It reads your local Journal and turns it into one coherent cockpit for engineering, unlocks, materials, mining, state hunting, Powerplay, Commander finances, fleet management, exploration and exobiology.

[**Download the latest ED-Frame 1.0 update**](https://github.com/CMDRForcer/ED-Frame/releases/latest) · [Website](https://cmdrforcer.github.io/) · [English guide](docs/ED-Frame-1.0-Guide-EN.md) · [Deutsche Anleitung](docs/ED-Frame-1.0-Guide-DE.md) · [Changelog](CHANGELOG.md) · [Report a bug](https://github.com/CMDRForcer/ED-Frame/issues)

**1.0.6 Powerplay update:** preserve explicit unoccupied systems for Acquire, distinguish missing and outdated evidence, and keep Powerplay observation times separate from ring and market updates. Coverage still depends on actual public observations. Historical 1.0.1–1.0.4 tags were already occupied; 1.0.5 started the maintenance updates after the new 1.0 release.

**Release numbering:** 1.0 starts the new public ED-Frame release line and succeeds the earlier EDEC/ED-Frame versions, including 1.5.43. Those older tags and downloads remain available as outdated historical releases. Use the current release link rather than choosing the largest historical version number.

![ED-Frame Commander Operations in the Orbital Dawn theme](docs/images/edec-operations.png)

## Highlights

- **One next action** — ED-Frame turns every tracked build, missing material, route and unlock into a clear answer to “what now?”
- **Your ships, your slots** — engineer the exact physical Core Internal, Optional Internal, Hardpoint and Utility slots of every known hull.
- **Journal-confirmed progress** — installed modules, grades, experimental effects, credits, fleet movements, scans and unlock evidence update automatically.
- **Engineer and Tech Broker guides** — searchable capabilities, prerequisite chains and one-time Human and Guardian unlock tracking.
- **Server-backed finders** — Mining and merit routes, commodity markets, station services, modules and ships share ED-Frame's own public catalog service.
- **Field tools** — Material routes, State Finds, live HGE assistance, exploration, a Biological Survey workspace and surface waypoint navigation.
- **Commander intelligence** — live credit ticker, assets, average CR/h, ranks, reputation, fleet and a searchable flight record.
- **Local Commander data** — ships, builds, wishlists, credentials and Journal files stay on your computer. Community connections have visible controls; Frontier CAPI and INARA require separate setup.

## Features, individually

| Feature | What it helps you do |
| --- | --- |
| **Operations** | Follow the next material, unlock, travel or crafting action for your selected build. |
| **Engineering** | Plan grades and experimental effects on your real ship's physical module slots; compare installed and planned equipment. |
| **Wishlist** | Track multiple fleet builds, missing materials and Journal-confirmed crafting progress. |
| **Engineers** | Find capabilities, follow unlock prerequisites and navigate to suitable Engineers. |
| **Technology Brokers** | Track one-time Human and Guardian unlock requirements. |
| **Materials** | Review inventory and farming guidance; protect materials reserved for tracked builds when planning trades. |
| **Mining Finder** | Compare mining sites, prices, demand, market age, pad size and evidence; plan Acquire, Reinforce or Undermine routes. |
| **Measured mining yield** | Use observed Prospector/refining evidence and supported community measurements; distinguish measured yields from hotspot or ring-type estimates. |
| **Module & Ship Finder** | Find observed station inventories and prices; inspect module fit for the current ship and slot. |
| **Commodity Finder** | Find buying stock or selling demand with distance, quantity, landing-pad and quote-age filters. |
| **Station services** | Find nearby stations providing the selected service using observed station metadata. |
| **State Finds & HGE** | Compare live sightings, remaining signal lifetime and separately labelled BGS predictions. |
| **Powerplay** | Track pledge, rank and merits from the Journal; distinguish explicit system control from power presence. |
| **CMDR & Fleet** | Review ranks, reputation, credits, assets, CR/h and known ships, including parked hulls. |
| **Missions** | Track active missions, deadlines, massacre stacks and recorded Community Goals. |
| **Exploration** | Review unsold Journal scans, noteworthy bodies and transparently estimated cartography values. |
| **Exobiology** | Track survey targets, sampling distances, completed species and observed earnings. |
| **Surface navigation** | Save planetary waypoints and follow a compass in the app or a separate overlay. |
| **Logbook** | Search flight events, session activity and your local notes. |
| **Appearance & connections** | Choose six themes and four languages; manage services, profiles, diagnostics and overlays. |

## Our own server — shared galaxy facts, local Commander state

ED-Frame now has its own **community catalog server**. It collects supported public EDDN observations and serves shared system, station, market, ring/hotspot, Powerplay and State Finds data to the app. It also supplies module and ship availability and observed purchase prices. Supported anonymous mining-yield, signal and station-price contributions help the shared catalog grow.

- **Mining:** combine site evidence with prices, demand and explicit Powerplay facts. Market confirmation and merit suitability have separate checks; missing evidence remains visible.
- **Shopping and trading:** search station services, commodity offers, module inventories and ship availability without manually maintaining station lists.
- **Freshness:** use the original observation time and age filters. A recent download does not make an old price current; an observation is not an availability, yield or merit guarantee.
- **Offline use:** keep already retained observations locally. Regional SQLite ring queries avoid loading the complete ring catalog into memory and preserve the original observations and their history.
- **Controls and privacy:** ED-Frame and EDDN community connections are enabled by default for a new profile and can be disabled in Connections. The ED-Frame connection controls catalog access and supported anonymous contributions together. The server does not accept Commander names/FIDs, raw Journal files, private builds, wishlists, credentials or tokens. Frontier CAPI and INARA remain separately configured integrations.

The server complements local Journal evidence; it does not replace it. Coverage depends on observed public activity, and gaps stay visible. [Server documentation](server/catalog_service/README.md) explains the public data contract.

## Why ED-Frame

Most build tools model a *type* of ship. ED-Frame models *your* ship — the specific hull with its ShipID, physical module slots and current `Loadout`. Then it connects that ship to the rest of your Commander state: materials, Engineer access, routes, credits, fleet, signals and scans.

That precision is the whole point:

- A plan stays attached to the **slot**, so two identical Multi-cannons never get confused.
- ED-Frame separates **observed facts**, **planned work** and **predictions** instead of presenting guesses as certainty.
- The Operations page joins the individual tools into a route: collect, trade, travel, unlock, install and craft.
- You can plan for a ship parked across the bubble **without switching to it in-game**.

Commander state comes from your local files; shared galaxy facts come from the enabled catalog sources. Missing evidence stays unknown.

## Every workspace, from top to bottom

The workspaces below share your Commander state. Sidebar entries can be rearranged to match the way you play.

### 1. Operations — the answer to “what now?”

Commander Operations is the mission-control view for the selected wishlist ship. It keeps the next best action prominent, shows material readiness and explains both **why** the action comes next and **what follows after it**. Switch between a planned ship and the current ship without changing ships in Elite.

Engineer and trader routes sit beside the active work. Copy a system name, open the relevant workspace, review missing materials, follow unlock prerequisites and watch Journal-confirmed crafts or trades advance the plan automatically. Live HGE targets and route activity remain visible without turning the page into a wall of diagnostics.

### 2. Engineering — real modules in real slots

Pick any ship ED-Frame has seen and work on its actual Core Internal, Optional Internal, Hardpoint and Utility slots. The ship panel shows speed, boost, jump range, mass, cargo capacity and how many modules can be engineered. Each slot distinguishes the installed module, current engineering and planned target.

The Power Plant panel compares **Now** with the selected ship's **Plan**, including raw MW draw, capacity and reserve before any priority shutdown. The plan projects desired module swaps and bound wishlist engineering for that same ship; unbound plans, missing power catalog entries, stock-value assumptions for replacements without a planned engineering grade, and currently switched-off modules are called out rather than treated as confirmed. It uses catalog grade effects, not exact engineering rolls, and is not a live hardpoint-deployment meter.

Search the blueprint catalog, choose grade-only, experimental-only or combined planning, and compare the benefits and trade-offs of experimental effects. The install guard stops an empty or wrong slot from looking craft-ready. Import ED-Frame, EDSY/SLEF and Coriolis builds through exact hull-slot validation, or export the selected ship's outfitting with its slot identities intact.

![Ship engineering bound to the physical slots of a fleet ship](docs/images/edec-engineering.png)

### 3. Wishlist — every build as an executable plan

The Wishlist rolls every pinned module into build progress, material readiness and a physical-slot checklist. Follow the current ship or choose another fleet hull; edit, duplicate, track or move plans without losing their slot bindings.

Each job shows grade progress, experimental status, missing materials and Journal-confirmed crafts. Conflicting, unrelated or unmatched craft events are surfaced for review instead of silently changing the wrong module. Completed engineering leaves the active workload and remains available as history.

![Wishlist with ship progress, slot-bound plans and material readiness](docs/images/edec-wishlist.png)

### 4. Engineers — discover, unlock and travel

Search the Engineer index by name, system, module or blueprint. Cards combine access state, rank, distance, capabilities and maximum grade, with one-click system copying for navigation.

The **Unlock Guide** turns a locked Engineer into an ordered chain of prerequisites, reputation or permit requirements, invitation and first visit. Journal evidence ticks off confirmed steps; gaps in older history remain visibly unknown rather than guessed.

![Guided unlock chain for a locked Engineer](docs/images/edec-engineers-unlock.png)

#### Technology Brokers

The Tech Brokers tab covers one-time Human and Guardian technology unlocks for modules, weapons and fighters. Track a selected unlock, see its prerequisites and next step, compare required inventory with what you own, and jump directly to farming guidance for anything missing. Broker systems can be copied without leaving the workflow.

![Human and Guardian Technology Broker unlock tracking](docs/images/edec-tech-brokers.png)

### 5. Materials — know what is available and what is reserved

Raw, Manufactured and Encoded inventory comes directly from the Journal, with grade caps, stock bars and surplus flags. Filter to all, missing, ready, surplus or tradeable materials. ED-Frame protects stock reserved by tracked builds, so a suggested trade never spends something the plan still needs.

Missing-material guidance lists acquisition routes, source systems and coordinates where available. Trader selection can prefer the nearest known location or one your own Journal has confirmed.

![Live material inventory with build-aware filters](docs/images/edec-materials.png)

### 6. Mining Finder — choose a target with evidence

Find rings and planetary deposits by commodity, mining method, distance, reserve quality and evidence level. Choose yield, profit, distance or Powerplay merit planning; filter market age, demand and landing-pad size. Acquire, Reinforce and Undermine routes distinguish verified markets, verified Powerplay facts and missing evidence. ED-Frame checks the active ship for the required mining equipment and separates measured yield, hotspot evidence and ring-type estimates.

Each result shows the body, ring type, hotspot or signal evidence, last confirmation, arrival distance and a copyable system. Journal observations combine with ED-Frame server data, other enabled catalog sources and retained offline knowledge. The regional SQLite ring store preserves full observations and history while reading the relevant search region.

![Mining Finder results with method, distance and evidence filters](docs/images/edec-mining-finder.png)

### 7. State Finds — hunt signals, not spreadsheets

Search for High Grade Emissions, Conflict Zones and Seeking Meds or Foods within a chosen range. Filter live reports and predictions by signal type, state or allegiance, then compare freshness, distance, remaining lifetime, faction and intensity.

HGE rows include the materials expected from the observed system state. ED-Frame labels local Journal evidence, EDDN sightings and BGS predictions distinctly, and puts the best-supported nearby candidates first.

![State Finds with live and predicted signal intelligence](docs/images/edec-state-finds.png)

### 8. Powerplay — observed data, clearly bounded

ED-Frame identifies your pledged leader and presents an offline profile and portrait alongside the values Elite has actually reported: rank, merits, pledge duration, salary and recent Powerplay cargo. In the current system it tracks controlling power, control progress and the undermining-versus-reinforcement tug of war without inventing unavailable rewards or numbers.

![Journal-driven Powerplay 2.0 overview](docs/images/edec-powerplay.png)

### 9. CMDR — profile, finances and fleet

The CMDR workspace has three focused views.

#### Overview

Ranks and progress, major- and minor-faction reputation, financial snapshots, current ship and squadron are laid out as cards you can rearrange.

![Commander ranks, reputation and financial snapshot](docs/images/edec-commander.png)

#### Credits

The balance behaves like a ticker: earnings turn green, spending turns red and total assets remain visible as a separate line. Choose the current session, 1 hour, 6 hours, 24 hours, 7 days, 30 days or all recorded history. ED-Frame shows net change, average credits per hour and exact timestamped values on hover; it never fabricates points inside an unobserved gap.

![Live Credits ticker with period selection and hover detail](docs/images/edec-credits.png)

#### Fleet

Every known ship shows its value, rebuy and location — current, transferring, stored or remote. Add your own screenshot to a ship card or keep ED-Frame's silhouette. This is the same fleet used by Engineering, so a parked hull can be planned without switching to it in-game.

![Fleet overview with per-ship value, rebuy and location](docs/images/edec-fleet.png)

### 10. Logbook — a searchable flight record

The profile-isolated Logbook summarizes jumps, distance, dockings, crafts and trades for the current and recent sessions. Search the newest-first timeline by system, station, blueprint, material or ship, filter event types and keep local notes beside the record.

![Commander logbook with session totals and a searchable event timeline](docs/images/edec-logbook.png)

### 11. Exobiology — a Biological Survey workspace

Exobiology turns FSS, DSS and organic-scan events into survey targets for the current system or every recently observed system. Confirmed genera rank ahead of candidates inferred from planetary conditions, while possible first-footfall bonuses are clearly marked as possibilities rather than promises.

Species found, lifetime earnings, remaining signals on the current body, session value and carried unsold value stay visible at a glance. During sampling, the distance assistant tells you when the colony range is clear for the next sample.

![Biological Survey with scan progress, values and landing targets](docs/images/edec-exobiology.png)

### 12. Nav — surface waypoints

Near a planet or on its surface, open **Nav → Surface Nav**, enter signed latitude and longitude in decimal degrees, and save the point under a name. You can also save your current position when Elite provides coordinates, then rename that waypoint in the saved list. Saved waypoints stay with your Commander profile and can be selected again after a restart.

The **Raw Material Farms** section below saved waypoints is collapsed by default. Open it to filter by material, sort either by straight-line distance from the Journal's current system position or by material then distance, copy a destination system, and turn a bundled-catalog entry with surface coordinates into a saved waypoint. You can edit a farm's material, system, body, coordinates and notes, or remove an outdated entry and restore the bundled original later. Edits are stored per Commander profile, separate from the bundled catalog. Unknown distances sort last; a changed system without known galactic coordinates also has unknown distance. Sites without exact surface coordinates cannot become compass waypoints. These distances are not jump-route lengths or a live guarantee of material availability.

The compass arrow points toward the active waypoint relative to your current ship, SRV or suit heading. The page also shows the bearing and the shortest distance along the body's surface. Direction needs live coordinates and heading from Elite's `Status.json`; distance additionally needs its planet radius. Elite updates coordinates more coarsely while flying, so the final approach is more precise near the surface. A waypoint on another body or in another system remains saved, but guidance resumes only when you return there.

**Show Nav Overlay** opens a separate, movable always-on-top compass with the active waypoint, relative turn, surface distance and status. Its visibility, position, opacity and scale persist independently of the Engineering overlay. Lock and click-through can be toggled from the Nav tab or the Windows tray menu. As with other desktop overlays, use Elite's borderless-windowed mode; exclusive fullscreen can cover the overlay.

### Module & Ship Finder — find equipment for your ship

Search observed module and ship inventories by origin, range and landing pad. Module selection exposes class, rating, family and known compatibility with the current hull and physical slot. Prices distinguish direct observations from inferred values; access restrictions and missing availability remain visible.

### Commodity Finder and station services

In Nav, choose BUY to compare station stock or SELL to compare demand. Filter quantity and quote age, and compare prices with distance and pad information. The station-service search finds nearby observed services. These are observations, not guaranteed stock, legality or docking access.

### Missions — deadlines and shared targets

Review active Journal missions, destination, reward and expiry. Group recorded massacre missions into stacks and review observed Community Goals in the same workspace.

### Exploration — unsold cartography

Review Journal-derived scans, valuable or noteworthy bodies and unsold exploration data. Value ranges and possible discovery bonuses are clearly presented as estimates.

### 13. Settings — appearance, data sources and diagnostics

Six themes, four interface languages, UI scaling, reduced motion and enhanced GPU visuals let the cockpit fit the display. Tray mode, Windows start-up behavior, renderer selection and Journal-folder controls are available without editing configuration files.

![Settings with the six-theme design-skin picker](docs/images/edec-themes.png)

#### Connections and diagnostics

Connections exposes controls and status for the ED-Frame catalog, EDDN, Frontier CAPI, INARA, Spansh and EDSM. ED-Frame and EDDN community services are enabled for new profiles; disabling them preserves local retained data. Frontier CAPI can supplement credits and the active ship after consent and login; INARA can synchronize supported Commander events after setup. Queues, receipts, retries and service status remain visible.

![Connection status, consent controls and delivery receipts](docs/images/edec-connections.png)

Advanced Diagnostics exposes Journal watcher health, renderer and service pipelines, copyable reports and a local log when troubleshooting is actually needed.

> All screenshots use the **Orbital Dawn** theme and synthetic demo data. They contain no real Commander profile, Journal history, service credentials, or API keys.

## Install on Windows

**Requirements:** Windows 10 or 11, and Elite Dangerous Journal files for live Commander data.

### Portable (recommended)

1. Open the [latest release](https://github.com/CMDRForcer/ED-Frame/releases/latest).
2. Under **Assets**, download `ED-Frame-<version>-Windows.zip`.
3. Extract the whole ZIP to a writable folder.
4. Run `ED-Frame.exe`, keeping the `_internal` folder beside it.

The Windows package bundles its runtime and is Explorer-compatible. A full project archive and `SHA256SUMS.txt` are published alongside it. Windows SmartScreen may warn because the executable is not code-signed.

### From source

Install Python 3, clone the repository, run `INSTALL_REQUIREMENTS.bat` once, then launch `START_APP.bat`.

Personal settings, Journal cursors, caches, plans and service credentials live outside the program directory and are never included in release archives.

## Data and privacy

Start with the current **1.0 guides** in [English](docs/ED-Frame-1.0-Guide-EN.md) or [German](docs/ED-Frame-1.0-Guide-DE.md). The older [English](docs/ED-Frame_User_Manual_Privacy_EN_1.5.5.pdf) and [German](docs/ED-Frame_User_Manual_Privacy_DE_1.5.5.pdf) PDF manuals remain historical references; they predate the current features and community defaults.

ED-Frame keeps Commander state in local files. Community services can be disabled; Frontier CAPI and INARA require separate setup:

- **ED-Frame server** — shared public catalogs and supported anonymous mining, signal and station-price observations. Enabled by default for new profiles; the Connections switch controls both catalog access and contributions. Commander identities, raw Journal files, private builds, wishlists and credentials are not accepted by this service.

- **INARA** — supported Commander events are batched, deduplicated, rate-limited, and written to local receipts before any upload. The API key is encrypted for the current Windows account with DPAPI, is never exposed back to QML, and is redacted from logs and crash reports.
- **EDDN** — supported public market, station, exploration and exobiology messages are validated and stripped of private or unsupported fields before transmission. Community upload/listener functionality is enabled by default for new profiles and has its own Connections switch.
- **Frontier Companion API** — an explicit in-app consent tick is required before the first login. Authorisation uses Frontier's PKCE OAuth flow with no client secret; only credits and the active ship are imported, and newer Journal values always stay authoritative. OAuth tokens are encrypted for the current Windows account (DPAPI) and are never written to logs.
- **Spansh** — optional read-only catalog data assists navigation and material guidance, with bundled offline fallbacks.

A build run from a source checkout identifies itself to INARA and EDDN as a development build, so ad-hoc runs are never counted as a released version.

The bundled Frontier OAuth client covers the default GitHub Pages redirect. If you run your own instance and have accepted the Frontier developer terms, set `EDEC_FRONTIER_CLIENT_ID` (and, if needed, `EDEC_FRONTIER_REDIRECT_URI`) to use your own registered client.

## Reliability

- A headless load of the real `Main.qml` in CI whose QML runtime errors fail the build, plus state-based QML interaction tests.
- Contract tests for physical slot binding, ED-Frame/EDSY/Coriolis interchange, Powerplay observation boundaries, and external-service safety limits.
- Atomic local persistence with corruption quarantine, bounded history, multi-process protection, retry backoff, and durable queues.
- Journal processing that follows recently active files without replaying known lines.
- Translation contracts that keep the EN/DE/ES/FR catalogs and their placeholders in sync.

The full test suite and a source/packaged smoke test run on every release.

## Development

```text
INSTALL_REQUIREMENTS.bat
START_APP.bat
```

See [`requirements.txt`](requirements.txt) for runtime dependencies. ED-Frame is under active development; bug reports, translations and feature suggestions are welcome through [GitHub Issues](https://github.com/CMDRForcer/ED-Frame/issues).

## License and attribution

ED-Frame is licensed under the [GNU General Public License v3.0](LICENSE) and is free to use.

ED-Frame is an independent third-party project and is not affiliated with Frontier Developments. Elite Dangerous is a trademark of Frontier Developments plc.

Exobiology reference data (`ed_data/exobiology_species.json`, `ed_data/exobiology_colony_ranges.json`) is ED-Frame's own re-expression of public game facts — spawn conditions, credit values and colony-range distances — not copied code. The colony-range distances are sourced from the [Elite Dangerous Fandom wiki](https://elite-dangerous.fandom.com/wiki/Exobiology_Sample_Values_and_Details) (CC BY-SA).
