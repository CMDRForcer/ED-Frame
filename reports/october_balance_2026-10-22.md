# October 2026 ship data and release validation

Release **1.0.12** combines the previously local Anaconda Mk II implementation
with the remaining October ship balancing.

## Reviewed changes

Source facts: [Frontier's October 20 announcement](https://steamcommunity.com/app/359320/announcements/)
and [EDSY's reference dataset](https://edsy.org/eddb.js), data version 424029902.
The downloaded snapshot's SHA-256 is
`071f3c63bab630b0db33e7d77061c1dcd7c0d06426c507ab52bf87e9a1c99da2`.
No downloaded JavaScript is executed or included in the distribution; only
reviewed game-data facts are retained in the dated supplement.

- Type-6, Type-7, Imperial Clipper and Federal Dropship gain their announced
  optional slot under a distinct Slot00 identity. Existing physical slot names
  retain their installed modules and partial wishlist bindings. Sorted positions
  are not interpreted as legacy aliases on those rebalanced hulls.
- The Asp Scout has three utility mounts. The Clipper has a class-5 fuel tank.
- Hull masses: Asp Scout 140 t, Dropship 500 t, Clipper 350 t, Type-7 300 t,
  Mandalay 190 t and Caspian Explorer 825 t. Fit-reference masses and structures
  are consistent with the physical catalog and retained by future exports.
- Standard-reference speeds/boost are updated, including Asp Scout 270/360,
  Viper Mk IV 280/360 and Dropship 200/300 m/s. These retain the existing EDSY
  stock-reference convention. Raw flight parameters in the official notes have
  a different baseline and are not substituted directly.
- Finite shield, thermal and flight references cover the ten affected ships.
  Unknown/NaN values are omitted. Approximate published Mandalay/Caspian ranges
  are descriptive reference fields; Journal-derived operational range, mass and
  cargo capacity remain authoritative.
- The browser shows the updated hull/base-shield reference and approximate range
  separately from operational values, with labels in all four languages.
- Reserved PlanetaryApproachSuite identities are retained or corrected on the
  affected hulls, with explicit backward aliases where needed. Existing military
  slot restrictions and Anaconda Mk II Cargo01 restrictions remain intact.

The Type-7 EDSY snapshot contains an additional class-6 entry and inconsistent
slot names beyond Frontier's announced class-7 addition. This conflict is not
imported. The previous verified physical layout receives exactly one new class-7
slot; no additional unverified capacity is claimed.

## Validation

- Complete application run: **1,477 tests passed**. After the final reserved-slot
  adjustment, **34 focused hull, fit, armour and QML predicate regressions passed**.
  The release workflow repeats the complete suite against the final commit.
- **221 server tests passed**.
- The final Windows portable passed **35 real smoke areas**, including all main
  pages, dialogs, mining in a child process and shared background compute work.
- Six additional real-QML checks passed: updated ship selection, scroll reachability
  of the reference text, all 49 hulls, all 38 Mk II slots, loaded Mk II graphic and
  full selected-card visibility at 115% scale. The harness applies the scale after
  the offscreen native window's initial resize before measuring scene coordinates.
- Native Windows updater tests passed for successful replacement and failed-start
  rollback, retaining two synthetic profiles, plan files, credentials and the shared
  installation ID. Each restored/updated app passed its 35-area smoke run.
- Manifest integrity, Python syntax, repository privacy/hygiene and whitespace
  checks passed. Local recent Journal records were inspected without copying them
  into the repository. No live Anaconda Mk II Journal was available; Mk II fixtures
  are synthetic and must not be presented as an owner's live-flight verification.

## Server adoption

Six reference JSONs were checked against the previously deployed baseline and
layered onto the existing 0.9.5 reference image. The candidate image retains the
existing API/database code hashes. An isolated database-schema test passed and
rolled back, including artificial observed-price preservation checks.

The production reference refresh completed with **49 ships / 980 modules** and
all **49 previous ship-price rows preserved**. API, collector, PostgreSQL and Caddy
kept their container IDs and start times: no production service was restarted.
The new reference image is pinned for future container recreation. Existing
backup files and images were retained. The private administrator tool and its
authentication material remain outside the public repository and release.
