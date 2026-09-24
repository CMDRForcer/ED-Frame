"""Repeatable integrity checks for ship-engineering material references.

The live Journal is the authority for what Elite actually consumed.  These
helpers keep the comparison with the planned recipe deterministic and turn a
bounded list of local observations into a UI-safe, non-blocking summary.
"""

from __future__ import annotations

from typing import Any


def material_key(value: Any) -> str:
    return "".join(character for character in str(value or "").casefold() if character.isalnum())


def ingredient_totals(
    rows: object, *quantity_fields: str,
) -> dict[str, int]:
    """Return canonical material quantities from blueprint or Journal rows."""

    fields = quantity_fields or ("Count", "Size", "Quantity")
    totals: dict[str, int] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = material_key(row.get("Material") or row.get("Name"))
        if not key:
            continue
        quantity = 0
        for field in fields:
            if row.get(field) is None:
                continue
            try:
                quantity = max(0, int(row.get(field) or 0))
            except (TypeError, ValueError):
                quantity = 0
            break
        if quantity:
            totals[key] = totals.get(key, 0) + quantity
    return totals


def compare_ingredient_costs(
    expected_rows: object, observed_rows: object,
) -> dict[str, Any]:
    """Compare a planned recipe with the cost recorded by ``EngineerCraft``."""

    expected = ingredient_totals(expected_rows, "Size", "Count", "Quantity")
    observed = ingredient_totals(observed_rows, "Count", "Size", "Quantity")
    keys = sorted(set(expected).union(observed))
    differences = {
        key: {
            "expected": expected.get(key, 0),
            "observed": observed.get(key, 0),
            "delta": observed.get(key, 0) - expected.get(key, 0),
        }
        for key in keys
        if expected.get(key, 0) != observed.get(key, 0)
    }
    return {
        "matches": not differences,
        "expected": expected,
        "observed": observed,
        "differences": differences,
    }


def material_monitor_snapshot(
    rows: object, ship_id: object = "", ship: object = "",
) -> dict[str, Any]:
    """Summarize local craft observations for one selected physical ship.

    A warning here is informational: it reports that Journal evidence changed
    the plan, but it never blocks travel or another craft.
    """

    wanted_id = str(ship_id or "")
    wanted_ship = str(ship or "")
    selected = [
        dict(row) for row in (rows or [])
        if isinstance(row, dict)
        and (
            (wanted_id and str(row.get("shipId") or "") == wanted_id)
            or (
                not wanted_id and wanted_ship
                and str(row.get("ship") or "") == wanted_ship
            )
        )
    ]
    adaptations = [
        row for row in selected
        if row.get("recipeChanged") or row.get("rollBudgetExtended")
    ]
    reductions = [row for row in selected if row.get("requirementReduced")]
    latest = dict(selected[-1]) if selected else {}
    latest_issue = dict(adaptations[-1]) if adaptations else {}
    latest_reduction = dict(reductions[-1]) if reductions else {}
    return {
        "status": (
            "ADAPTED" if adaptations else
            "VERIFIED" if selected else
            "WAITING"
        ),
        "blocking": False,
        "observedCount": len(selected),
        "verifiedCount": len(selected) - len(adaptations),
        "adaptationCount": len(adaptations),
        "recipeChangeCount": sum(
            bool(row.get("recipeChanged")) for row in selected
        ),
        "rollBudgetExtensionCount": sum(
            bool(row.get("rollBudgetExtended")) for row in selected
        ),
        "requirementReductionCount": len(reductions),
        "releasedMaterialUnits": sum(
            int(row.get("releasedMaterialUnits", 0) or 0)
            for row in reductions
        ),
        "latest": latest,
        "latestIssue": latest_issue,
        "latestReduction": latest_reduction,
    }
