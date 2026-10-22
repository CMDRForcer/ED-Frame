# Anaconda Mk II: launch support

Anaconda Mk II is now recognized as `AnacondaMkII`. Engineering and the
outfitting browser use the complete 38-slot layout, including two military
class-5 slots, eight utility mounts and the class-6 `Cargo01` slot. The
planetary approach suite is included in that count.

## Data and compatibility

- Source: https://edsy.org/eddb.js, data version `424029902`, dated
  20 October 2026. The reviewed source SHA-256 is recorded in
  `ed_data/module_fit_reference_supplement.json`.
- Cargo01 accepts cargo racks or fuel tanks. The browser exposes tanks in
  that optional slot without changing their normal core-module category.
- Mk II cargo racks have reference capacities of 96/192/384 tonnes for
  classes 6/7/8. Operational cargo capacity still comes from Journal
  Loadout; no unverified hull cargo maximum is introduced.
- Hull permissions include the Mining Volley Repeater, cargo racks and
  the supported fighter/vehicle hangars. Existing hull permissions remain.
  The precise slot-specific mining optimisation remains unverified and is
  not encoded as an invented installation restriction.
- Armour is hull-specific in the purchase browser. Standard lightweight
  alloy and Mk II ablative lightweight alloy now have different identities.
  This also corrects the same distinction on Caspian Explorer. Storing the
  ablative module restores the ordinary stock alloy, not another ablative
  module. Export does not copy engineering between these variants.
- Old generic standard-armour aliases remain valid. Legacy Caspian plans
  that lost the distinction when stored as a generic armour ID are not
  guessed to be ablative; authoritative Journal evidence/rebinding may be
  needed. No existing profile files are rewritten by this change.
- The reference exporter retains the reviewed launch supplement and unions
  its hull permissions with future upstream permissions. Existing upstream
  module power/mass fields are not frozen by copied launch overrides.

## Deliberate limitations

This is based on community reference data and official launch notes, not a
user-supplied live Mk II Journal. Unknown thermal/acceleration figures are
not imported. The ship is marked ARX early access; no standard-credit
purchase price or user entitlement is invented. A new native SVG dorsal
illustration is included for Engineering, the fleet and ship browser. It
follows the other graphics' canvas, palette, strokes and translucent facets,
with a forked bow based on the user's reference views. It is not a measured
schematic and contains no claimed hardpoint positions. No raster image or
glow is embedded. Other ships' October balancing and December Law & Disorder
are separate tasks.

## Validation

- Python 3.13.16: **237 selected regression tests passed**, including fleet
  recognition, physical slots, module restrictions, armour identities,
  storage, export/import, engineering bindings, power budgets, wishlists,
  purchase references, native SVG style/transparency, the fleet graphic path
  and the QML browser predicates/stable slot list.
- Full real-QML smoke: **34 areas passed**, exit code 0. An isolated,
  synthetic Mk II Journal exercised all 38 active physical slots and an
  installed Mk II rack in Cargo01, followed by the standard pages, overlays,
  dialogs and screenshot checks. The graphic was loaded and checked in
  Engineering, the Fleet tab and the ship browser. An additional fleet
  screenshot confirms that the final safety margins prevent bow/stern
  clipping at the card's 1.28 magnification. This is not a live-player
  Journal test. See `anaconda_mkii_fleet_2026-10-21.png`.
- Compilation, repository hygiene and `git diff --check` passed.
- The entire repository test suite and Windows packaging were not run.

Regression command (from repository root):

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest \
  tests.test_anaconda_mkii tests.test_module_purchase_display \
  tests.test_module_fit_rules tests.test_shipyard_slot_browser \
  tests.test_fleet_projection tests.test_installed_slot_engineering \
  tests.test_outfitting_accept tests.test_stable_slot_list \
  tests.test_release_contracts tests.test_shipyard_finder \
  tests.test_commander_fleet_projection tests.test_build_import_bindings \
  tests.test_wishlist_read_resilience tests.test_power_budget \
  tests.test_priority_workflow
```

Changes are local; no release or remote publication was performed.

## Shipyard selection visibility follow-up

Choosing a ship from suggestions now scrolls the horizontal catalog to its
selected card. This makes the Mk II visible despite its last position in the
49-hull catalog; late model updates also reveal the selection. A dedicated
real-QML smoke exercised chooseItem and confirmed the entire Mk II tile is
inside the ListView viewport (2 checks passed). The 25 focused browser/hull
regressions passed. Screenshot: anaconda_mkii_shipyard_2026-10-21.png.
The catalog width also accounts for UI scale; the window-space check at 115%
confirmed that the selected card ends at x=1874 inside the 1920-pixel window.
The change is local and requires an app restart after adopting these sources.

## Local Windows adoption — 21 October 2026

The supplied patch was applied without conflicts to the existing Windows
working directory on top of app 1.0.11 (commit `079af0f`). The working tree
was clean before adoption; the version and release tag were not changed.

- **238 selected regression tests passed** on Windows, including the new
  hull, armour variants, module restrictions, fleet projection and exports.
- **33 standard real-QML smoke areas passed**, followed by **3 focused
  Mk II checks** in an isolated profile with a synthetic Journal.
- The running QML controller exposed **49 unique hulls** and **38 active
  physical slots** for the Mk II. Selecting the ship revealed its final
  catalog tile and loaded its own SVG successfully.
- At **115% UI scale** in a 1920-pixel window, the selected tile ended at
  x=1874 and was fully inside its horizontal viewport.
- Python syntax, repository hygiene and whitespace checks passed.

The initial test attempt encountered restricted temporary-directory access;
using a disposable workspace-local temporary directory resolved it. The QML
inspection harness was adapted for Windows/Qt enum conversion and explicitly
loaded Segoe UI for offscreen screenshot rendering. No corresponding app
workaround was needed. Existing user profiles were not modified.

The full repository suite and Windows packaging were not rerun. These are
local source changes; an installed EXE is unchanged. Restart the source app
from this working directory to use them. No commit, push or release was made.
