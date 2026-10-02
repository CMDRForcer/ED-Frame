# ED-Frame handoff (2026-10-02)

Repository: `CMDRForcer/ED-Frame`, branch `main`.

Release `1.5.28` contains the completed Nav, power-budget and Mining Finder
work described below. Preserve profile-local data and never change the
Commander name used by the INARA authentication path.

## Current user-visible result

- New Nav tab with surface compass, live Elite `Status.json` coordinates, manually saved waypoints, Save Current Position, and waypoint renaming. Waypoints are profile-scoped and persist across restarts.
- The sidebar navigation rows are more compact.
- Nav includes the existing bundled raw-material farm catalog. It filters by material and sorts by direct 3D system distance or material then distance. Unknown distances sort last. Sites with coordinates can become persistent surface waypoints; systems can be copied. Distances are straight-line light years, not jump routes.
- Farm entries can now be edited (material, system, body, coordinates, notes), hidden with confirmation, and restored to the bundled original. Per-profile changes live in `material_farm_edits.json` and survive restart without modifying the shipped catalog. A changed system has unknown distance unless it is the current system; reactivating a linked waypoint refreshes its destination. Existing saved waypoints remain separate when a farm is removed.
- Nav has a separate in-game overlay (`qml/NavOverlay.qml`) using the same active Surface Nav target and guidance. The Nav page and tray have independent show/lock/click-through actions; opacity and scale are adjustable in the overlay, and its corner can resize it. Settings are saved in `nav_overlay_settings.json`, independent from the Engineering overlay. Borderless-windowed mode is needed if exclusive fullscreen covers desktop overlays.
- On the Nav page, the order is compass → Save Coordinates → Saved Waypoints → Raw Material Farms. The farm section is collapsed by default and expands on click; its list delegates are not instantiated while collapsed.
- No extra web-sourced sites were added: external community coordinates differed from existing catalog entries and were not independently verified.
- The Engineering Power Plant panel now compares **Now** and **Plan** for whichever fleet ship is selected, not just the Python Mk II. Both show total pre-shutdown MW draw, capacity, and reserve. The plan uses desired outfitting and slot-bound grade/experimental targets. Separate grade and experimental plans for one slot are merged; conflicting or unbound targets are flagged. Unknown modules/Power Plant output, stock-value replacement assumptions, and currently switched-off modules get warnings. This is an estimate based on catalog grade effects, not exact roll or live hardpoint state.
- The Mining Finder combines targeted mining, verified sell markets and
  Powerplay-merit routes. Search controls collapse after use, start-system
  suggestions preserve free text, alternatives are selectable, belts can be
  excluded with Rings Only, and route evidence remains explicitly unknown
  when it cannot be verified.
- Mining market knowledge is stored per profile in SQLite with WAL, bounded
  history, automatic backup recovery and a one-time legacy JSON migration.
  Local `Market.json` snapshots are learned even when EDDN upload is disabled.
  Ardent and EDData are anonymous market fallbacks; EDSM resolves start-system
  coordinates. Failed refreshes retain good data and retry after 2, 5, 15 and
  30 minutes.
- A Mining Finder reset clears ring evidence, market cache, history, retry
  state and legacy market data only for the active profile. A migration marker
  and fresh empty backup prevent old data from reappearing after reset.

## Main files

- `Main.qml`: Nav integration and compact sidebar.
- `ed_companion/overlay.py`, `phase14_main.py`, `qml/NavOverlay.qml`: independent Nav overlay window, settings and tray controls.
- `qml/pages/NavPage.qml`, `qml/pages/MaterialFarmsSection.qml`: UI.
- `ed_companion/surface_nav.py`, `ed_companion/phase14/controller_surface_nav.py`, `ed_companion/navigation/material_farms.py`: math, persistence, farm projection.
- `ed_data/i18n/{de,en,es,fr}.json`: translations.
- `tests/test_surface_nav.py`, `tests/test_material_farms.py`, `tests/test_nav_page_layout.py`: feature tests.
- `ed_companion/phase14/state.py`, `state_fleet.py`, `controller_engineering.py`, `tests/test_power_budget.py`: global selected-ship power forecast.
- `ed_companion/navigation/mining_market.py`, `mining_market_store.py`,
  `mining_planner.py`, `mining_powerplay.py`: public data adapters, durable
  market storage and route scoring.
- `qml/pages/MiningFinderPage.qml`, `controller_navigation.py`,
  `controller_eddn.py`: Mining Finder UI, refresh/reset lifecycle and private
  local market ingestion.

## Verification / caveats

- Overlay/Nav/i18n/runtime and QML smoke tests pass.
- The complete Windows test suite passes: 719/719 tests. This includes DPAPI
  credential round trips, Mining source-order and restart matrices, every retry
  interval, reset/rebuild, profile isolation, bounded retention and corruption
  recovery with and without a backup.
- A live Cubeo/Platinum cycle loaded 15 public markets, reset to zero, remained
  empty after forced database corruption and rebuilt all 15 observations.
- The currently running GUI may still be the old process. Restart the app when the user wants to see these changes; avoid killing it unexpectedly while they are playing.

This note describes release `1.5.28`; later work should start from its tag or a
newer `main` commit.
