"""Pure projection helpers for the Shipyard & Outfitting finder.

The UI deliberately consumes a small, honest projection: availability is
separate from price confidence and unknown coordinates/prices stay unknown.
"""

from __future__ import annotations

import math
import re
import json
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Iterable


# Frontier naval ranks are zero-based in the Journal Rank event.  Only hulls
# with a documented naval-rank purchase gate belong here; normal availability
# and temporary early-access entitlements must not be guessed.
SHIP_RANK_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "federation_dropship": {
        "field": "Federation", "minimum": 3, "rankName": "Midshipman",
    },
    "federation_dropship_mkii": {
        "field": "Federation", "minimum": 5,
        "rankName": "Chief Petty Officer",
    },
    "federation_gunship": {
        "field": "Federation", "minimum": 7, "rankName": "Ensign",
    },
    "federation_corvette": {
        "field": "Federation", "minimum": 12,
        "rankName": "Rear Admiral",
    },
    "empire_courier": {
        "field": "Empire", "minimum": 3, "rankName": "Master",
    },
    "empire_trader": {
        "field": "Empire", "minimum": 7, "rankName": "Baron",
    },
    "cutter": {
        "field": "Empire", "minimum": 12, "rankName": "Duke",
    },
}


MODULE_GROUP_LABELS = {
    "HARDPOINTS": "HARDPOINTS",
    "UTILITY": "UTILITY MOUNTS",
    "CORE": "CORE INTERNAL",
    "OPTIONAL": "OPTIONAL INTERNAL",
}

# Acquisition is separate from physical fit and station inventory. No legacy
# Powerplay rank/timer rule is used: the current reward track needs its own
# evidence before a player's purchase entitlement can be confirmed.
POWERPLAY_MODULE_FAMILIES = frozenset({
    "ADVANCED PLASMA ACCELERATOR", "CONCORD CANNON",
    "CYTOSCRAMBLER BURST LASER", "ENFORCER CANNON",
    "IMPERIAL HAMMER RAIL GUN", "MINING LANCE BEAM LASER",
    "PACIFIER FRAG-CANNON", "PACK-HOUND MISSILE RACK",
    "PRISMATIC SHIELD GENERATOR", "PULSE DISRUPTOR LASER",
    "RETRIBUTOR BEAM LASER", "ROCKET PROPELLED FSD DISRUPTER",
})
HUMAN_BROKER_FAMILIES = frozenset({
    "ENZYME MISSILE RACK", "META ALLOY HULL REINFORCEMENT PACKAGE",
    "REMOTE RELEASE FLECHETTE LAUNCHER", "SHOCK CANNON",
})


def evaluate_module_access(item: Any) -> dict[str, Any]:
    """Describe acquisition without treating availability/ownership as unlocks."""
    row = item if isinstance(item, dict) else {}
    name = str(row.get("displayName") or row.get("moduleFamily") or "").upper()
    route, status, reason = "STANDARD", "STANDARD PURCHASE", "Normal outfitting purchase; station stock and access still apply"
    tone, rank = "OPEN", 0
    if not name:
        route, status = "UNKNOWN", "ACQUISITION UNKNOWN"
        reason = "Module identity is unavailable; purchase requirements cannot be verified"
    elif name in POWERPLAY_MODULE_FAMILIES:
        route, status = "POWERPLAY", "POWERPLAY · UNLOCK UNKNOWN"
        reason = "Powerplay reward unlock required; your module entitlement is not verified"
    elif ("GUARDIAN" in name or name in HUMAN_BROKER_FAMILIES
          or name == "ANTI-CORROSION CARGO RACK" and str(row.get("moduleClass")) in {"2", "4"}):
        route, status = "TECH_BROKER", "TECH BROKER · UNLOCK UNKNOWN"
        broker = "Guardian" if "GUARDIAN" in name else "Human"
        reason = f"{broker} Technology Broker acquisition required; unlock/material recipe and variant must be checked"
    elif name == "ENHANCED PERFORMANCE THRUSTERS":
        route, status = "SPECIAL_VENDOR", "ENGINEER OUTFITTING"
        reason = "Sold through engineer outfitting; engineer access and station stock must be checked"
    elif name in {"BASIC DISCOVERY SCANNER", "INTERMEDIATE DISCOVERY SCANNER", "ADVANCED DISCOVERY SCANNER"}:
        route, status = "LEGACY", "LEGACY · NOT NORMAL STOCK"
        reason = "Legacy discovery scanner catalog identity; do not assume current outfitting availability"
        tone, rank = "LOCKED", 3
    elif name.startswith("MK II ") or any(marker in name for marker in (
        "PRE-ENGINEERED", "MODIFIED", "NANITE", "VOLLEY REPEATER",
    )):
        route, status = "SPECIAL", "SPECIAL · ACQUISITION UNKNOWN"
        reason = "Special variant; acquisition route and entitlement are not verified"
    if route != "STANDARD" and tone != "LOCKED":
        tone, rank = "UNKNOWN", 2
    return {
        "acquisitionRoute": route, "purchaseStatus": status,
        "purchaseTone": tone, "purchaseReason": reason, "purchaseRank": rank,
    }

_CORE_INTERNAL_SYMBOLS = (
    "_powerplant_", "_guardianpowerplant_",
    "_engine_", "_hyperdrive_", "_lifesupport_",
    "_powerdistributor_", "_guardianpowerdistributor_",
    "_sensors_", "_radar_", "_fueltank_", "_armour_",
)

MODULE_DEPARTMENT_ORDER = {
    "HARDPOINTS": ("LASERS", "KINETIC", "EXPLOSIVE", "EXPERIMENTAL", "MINING"),
    "UTILITY": ("DEFENCE", "SCANNERS", "SUPPORT"),
    "CORE": ("POWER", "PROPULSION", "NAVIGATION", "SUPPORT"),
    "OPTIONAL": ("CARGO", "PROTECTION", "LIMPETS", "PASSENGER", "EXPLORATION", "SUPPORT"),
}


def _module_group(symbol: str, module_class: str) -> str:
    value = str(symbol or "").casefold()
    if value.startswith("hpt_"):
        return "UTILITY" if str(module_class or "") == "0" else "HARDPOINTS"
    if any(marker in value for marker in _CORE_INTERNAL_SYMBOLS):
        return "CORE"
    return "OPTIONAL"


def _family_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").casefold()).strip("-")


def _module_department(symbol: str, name: str, group: str) -> str:
    value = f"{symbol} {name}".casefold()
    if group == "HARDPOINTS":
        if any(marker in value for marker in (
            "mining", "abrasion", "seismic", "subsurface", "pulse wave",
        )):
            return "MINING"
        if "laser" in value:
            return "LASERS"
        if any(marker in value for marker in (
            "multicannon", "multi-cannon", "cannon", "fragment", "slugshot",
        )):
            return "KINETIC"
        if any(marker in value for marker in (
            "missile", "rocket", "torpedo", "mine", "flak",
        )):
            return "EXPLOSIVE"
        return "EXPERIMENTAL"
    if group == "UTILITY":
        if any(marker in value for marker in (
            "chaff", "heatsink", "heat sink", "pointdefence", "point defence",
            "ecm", "shieldbooster", "shield booster",
        )):
            return "DEFENCE"
        if any(marker in value for marker in ("scanner", "warrant", "wake")):
            return "SCANNERS"
        return "SUPPORT"
    if group == "CORE":
        if any(marker in value for marker in ("powerplant", "power plant", "powerdistributor", "power distributor")):
            return "POWER"
        if any(marker in value for marker in ("engine", "thruster")):
            return "PROPULSION"
        if any(marker in value for marker in ("hyperdrive", "frame shift", "sensor", "radar")):
            return "NAVIGATION"
        return "SUPPORT"
    if any(marker in value for marker in ("cargorack", "cargo rack", "refinery")):
        return "CARGO"
    if any(marker in value for marker in (
        "shield", "reinforcement", "cellbank", "cell bank", "guardian",
    )):
        return "PROTECTION"
    if any(marker in value for marker in ("dronecontrol", "limpet")):
        return "LIMPETS"
    if any(marker in value for marker in ("passenger", "cabin")):
        return "PASSENGER"
    if any(marker in value for marker in (
        "fuelscoop", "fuel scoop", "detailedsurface", "discovery",
        "vehiclehangar", "vehicle hangar", "autofieldmaintenance",
    )):
        return "EXPLORATION"
    return "SUPPORT"


def _module_core_slot(symbol: str) -> str:
    value = str(symbol or "").casefold()
    rules = (
        ("PowerPlant", ("_powerplant_", "_guardianpowerplant_")),
        ("MainEngines", ("_engine_",)),
        ("FrameShiftDrive", ("_hyperdrive_",)),
        ("LifeSupport", ("_lifesupport_",)),
        ("PowerDistributor", ("_powerdistributor_", "_guardianpowerdistributor_")),
        ("Radar", ("_sensors_", "_radar_")),
        ("FuelTank", ("_fueltank_",)),
        ("Armour", ("_armour_",)),
    )
    return next((slot for slot, markers in rules if any(marker in value for marker in markers)), "")


def _module_schematic_kind(symbol: str, name: str) -> str:
    value = f"{symbol} {name}".casefold()
    rules = (
        ("FRAGMENT", ("fragment", "slugshot")),
        ("MULTI_CANNON", ("multicannon", "multi cannon")),
        ("CANNON", ("cannon",)),
        ("RAIL_PLASMA", ("railgun", "plasma", "guardian_gauss")),
        ("LASER", ("laser",)),
        ("MISSILE", ("missile", "torpedo", "flak", "rocket")),
        ("FSD", ("frameshiftdrive", "frame shift drive", "fsd")),
        ("POWER", ("powerplant", "power plant", "powerdistributor")),
        ("THRUSTER", ("thruster",)),
        ("SHIELD", ("shieldgenerator", "shield generator", "shieldbooster")),
        ("SCANNER", ("scanner", "detailedsurface", "killwarrant", "wake")),
        ("CARGO", ("cargorack", "cargo rack", "refinery", "limpet")),
        ("UTILITY", ("chaff", "heatsink", "pointdefence", "ecm")),
    )
    for kind, needles in rules:
        if any(needle in value for needle in needles):
            return kind
    return "INTERNAL"


def build_module_catalog(payload: Any, *, include_hull_armour: bool = False) -> list[dict[str, Any]]:
    modules = payload.get("modules", {}) if isinstance(payload, dict) else {}
    if include_hull_armour:
        modules = dict(modules)
        names = {"grade1": ("LIGHTWEIGHT ALLOYS", "1C"), "grade2": ("REINFORCED ALLOYS", "1B"),
                 "grade3": ("MILITARY GRADE COMPOSITE", "1A"), "mirrored": ("MIRRORED SURFACE COMPOSITE", "1A"),
                 "reactive": ("REACTIVE SURFACE COMPOSITE", "1A")}
        for symbol in module_fit_reference().get("modules", {}):
            if "_armour_" in symbol and symbol.split("_armour_")[-1] in names:
                modules.setdefault(symbol, names[symbol.split("_armour_")[-1]])
    rows = []
    for symbol, value in modules.items():
        if not isinstance(value, (list, tuple)) or not value:
            continue
        folded_symbol = str(symbol).casefold()
        mount = (
            "FIXED" if "_fixed_" in folded_symbol else
            "GIMBALLED" if "_gimbal_" in folded_symbol else
            "TURRETED" if "_turret_" in folded_symbol else ""
        )
        size_rating = str(value[1] if len(value) > 1 else "").strip()
        module_class_match = re.match(r"\d+", size_rating)
        module_rating_match = re.search(r"[A-Z]$", size_rating.upper())
        module_class = module_class_match[0] if module_class_match else ""
        display_name = str(value[0] or symbol).strip()
        module_group = _module_group(folded_symbol, module_class)
        module_department = _module_department(
            folded_symbol, display_name, module_group,
        )
        row = {
            "symbol": folded_symbol,
            "displayName": display_name,
            "sizeRating": size_rating,
            "mount": mount,
            "moduleClass": module_class,
            "moduleRating": module_rating_match[0] if module_rating_match else "",
            "moduleGroup": module_group,
            "moduleGroupLabel": MODULE_GROUP_LABELS[module_group],
            "moduleDepartment": module_department,
            "moduleFamily": display_name,
            "moduleFamilyKey": _family_key(display_name),
            "moduleCoreSlot": _module_core_slot(folded_symbol),
            "schematicKind": _module_schematic_kind(
                folded_symbol, display_name,
            ),
            "kind": "MODULES",
        }
        row.update(evaluate_module_access(row))
        rows.append(row)
    return sorted(rows, key=lambda row: (
        row["displayName"].casefold(), row["sizeRating"], row["symbol"],
    ))


def build_module_families(
    catalog: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return one truthful shop-category tile per module family."""
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for source in catalog:
        row = source if isinstance(source, dict) else {}
        group = str(row.get("moduleGroup") or "OPTIONAL")
        key = str(row.get("moduleFamilyKey") or "")
        if not key:
            continue
        identity = (group, key)
        family = grouped.setdefault(identity, {
            "moduleGroup": group,
            "moduleGroupLabel": str(
                row.get("moduleGroupLabel") or MODULE_GROUP_LABELS.get(group, group)
            ),
            "moduleFamily": str(row.get("moduleFamily") or row.get("displayName") or ""),
            "moduleFamilyKey": key,
            "moduleDepartment": str(row.get("moduleDepartment") or "SUPPORT"),
            "schematicKind": str(row.get("schematicKind") or "INTERNAL"),
            "variantCount": 0,
            "classes": set(),
            "mounts": set(),
            "fitStates": set(),
            "compatibleVariantCount": 0,
            "purchaseStates": set(),
            "purchaseReasons": set(),
        })
        family["variantCount"] += 1
        family["purchaseStates"].add(str(row.get("purchaseStatus") or "ACQUISITION UNKNOWN"))
        family["purchaseReasons"].add(str(row.get("purchaseReason") or ""))
        if row.get("moduleClass"):
            family["classes"].add(str(row["moduleClass"]))
        if row.get("mount"):
            family["mounts"].add(str(row["mount"]))
        fit_status = str(row.get("currentShipFitStatus") or "UNKNOWN")
        family["fitStates"].add(fit_status)
        if fit_status == "FITS":
            family["compatibleVariantCount"] += 1
    result = []
    group_order = {"HARDPOINTS": 0, "UTILITY": 1, "CORE": 2, "OPTIONAL": 3}
    for family in grouped.values():
        classes = sorted(family.pop("classes"), key=lambda item: int(item))
        mounts = sorted(family.pop("mounts"))
        fit_states = family.pop("fitStates")
        purchase_states = family.pop("purchaseStates")
        purchase_reasons = family.pop("purchaseReasons")
        family["purchaseStatus"] = next(iter(purchase_states)) if len(purchase_states) == 1 else "VARIANT REQUIREMENTS DIFFER"
        family["purchaseReason"] = " · ".join(sorted(reason for reason in purchase_reasons if reason))
        family["purchaseTone"] = "OPEN" if purchase_states == {"STANDARD PURCHASE"} else "UNKNOWN"
        family["classLabel"] = "CLASS " + ("–".join(
            [classes[0], classes[-1]] if len(classes) > 1 else classes
        ) if classes else "—")
        family["mountLabel"] = " · ".join(mounts)
        family["currentShipFitStatus"] = (
            "FITS" if "FITS" in fit_states else
            "UNKNOWN" if "UNKNOWN" in fit_states else "INCOMPATIBLE"
        )
        result.append(family)
    return sorted(result, key=lambda row: (
        group_order.get(str(row["moduleGroup"]), 9),
        str(row["moduleFamily"]).casefold(),
    ))


@lru_cache(maxsize=1)
def module_fit_reference() -> dict[str, Any]:
    """Small bundled reference, loaded once; missing data never implies a fit."""
    try:
        data = json.loads((Path(__file__).resolve().parents[2] / "ed_data" / "module_fit_reference.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def module_catalog_with_ship_fit(
    catalog: Iterable[dict[str, Any]], ship_slots: Any,
    ship_symbol: str = "", reference: Any = None, ship_stats: Any = None,
) -> list[dict[str, Any]]:
    """Annotate modules without hiding uncertain compatibility evidence."""
    slots = [dict(row) for row in (ship_slots or []) if isinstance(row, dict)]
    reference = reference if isinstance(reference, dict) else module_fit_reference()
    stats = reference.get("modules", {})
    ship_symbol = str(ship_symbol or "").casefold()
    hull_mass = reference.get("ships", {}).get(ship_symbol, {}).get("hullMass")
    ship_stats = ship_stats if isinstance(ship_stats, dict) else {}
    catalog = [{**row, "referencePrice": stats.get(str(row.get("symbol") or "").casefold(), {}).get("cost"),
                "referencePriceSource": reference.get("rulesSource", "") if "_armour_" in str(row.get("symbol") or "").casefold() else reference.get("source", ""),
                "powerDrawMW": stats.get(str(row.get("symbol") or "").casefold(), {}).get("power")}
               for row in catalog if isinstance(row, dict)]
    if not slots:
        return [{
            **dict(row),
            "fitsCurrentShip": True,
            "currentShipFitStatus": "UNKNOWN",
            "currentShipFitReason": "Current ship slot layout is unavailable",
        } for row in catalog if isinstance(row, dict)]

    group_names = {
        "HARDPOINTS": "HARDPOINTS",
        "UTILITY": "UTILITY MOUNTS",
        "CORE": "CORE INTERNALS",
        "OPTIONAL": "OPTIONAL INTERNALS",
    }
    result = []
    for source in catalog:
        if not isinstance(source, dict):
            continue
        row = dict(source)
        symbol = str(row.get("symbol") or "").casefold()
        spec = stats.get(symbol, {})
        group = str(row.get("moduleGroup") or "OPTIONAL")
        core_slot = str(row.get("moduleCoreSlot") or "")
        target_group = group_names.get(group, "OPTIONAL INTERNALS")
        candidates = [
            slot for slot in slots
            if str(slot.get("group") or "") == target_group
        ]
        if group == "CORE":
            core_slot = str(row.get("moduleCoreSlot") or "")
            if not core_slot:
                row.update({
                    "fitsCurrentShip": True,
                    "currentShipFitStatus": "UNKNOWN",
                    "currentShipFitReason": "Core slot family could not be verified",
                })
                result.append(row)
                continue
            candidates = [
                slot for slot in candidates
                if str(slot.get("slot") or "") == core_slot
            ]
        try:
            module_size = int(row.get("moduleClass"))
        except (TypeError, ValueError):
            module_size = None
        if module_size is None:
            row.update({
                "fitsCurrentShip": True,
                "currentShipFitStatus": "UNKNOWN",
                "currentShipFitReason": "Module class is unavailable",
            })
        else:
            slot_fits = {}
            for slot in candidates:
                size = int(slot.get("slotSize") or 0)
                restriction = str(slot.get("restriction") or "").casefold()
                family = str(row.get("moduleFamily") or row.get("displayName") or "").upper()
                status, reason = "FITS", "Slot type and class match; power and mass limits not verified"
                if module_size > size and core_slot != "Armour":
                    status, reason = "INCOMPATIBLE", "Module exceeds slot class"
                elif group == "CORE" and core_slot in {"LifeSupport", "Radar"} and module_size != size:
                    status, reason = "INCOMPATIBLE", "Life support and sensors require the exact slot class"
                elif restriction == "military" and not any(name in family for name in (
                    "HULL REINFORCEMENT", "MODULE REINFORCEMENT", "SHIELD CELL BANK", "GUARDIAN SHIELD REINFORCEMENT",
                )):
                    status, reason = "INCOMPATIBLE", "Military slot accepts reinforcement packages and shield cell banks only"
                elif restriction == "planetaryapproachsuite":
                    status, reason = "INCOMPATIBLE", "Reserved planetary approach suite slot"
                elif restriction and restriction != "military":
                    status, reason = "UNKNOWN", "Slot restriction has not been verified: " + restriction
                elif spec.get("noUndersize") and module_size != size:
                    status, reason = "INCOMPATIBLE", "This module requires the exact slot class"
                if status != "INCOMPATIBLE":
                    if core_slot == "Armour":
                        status = "FITS" if ship_symbol and symbol.split("_armour_")[0] == ship_symbol else "INCOMPATIBLE" if ship_symbol else "UNKNOWN"
                        reason = "Armour is specific to this hull" if status == "FITS" else "Armour belongs to another hull" if ship_symbol else "Hull identity unavailable"
                    elif "allowedShips" in spec:
                        known_ship = ship_symbol in reference.get("ships", {})
                        if ship_symbol in spec["allowedShips"]:
                            if status == "FITS":
                                reason = "Hull-specific module allowed"
                        else:
                            status = "INCOMPATIBLE" if known_ship else "UNKNOWN"
                            reason = "Module not approved for this hull" if known_ship else "Hull rule reference unavailable"
                    elif any(name in family for name in ("FIGHTER HANGAR", "LUXURY", "MK II")) and not spec:
                        status, reason = "UNKNOWN", "Ship-specific compatibility requires additional evidence"
                    limit = spec.get("limit")
                    if limit and status != "INCOMPATIBLE":
                        others = [s for s in slots if str(s.get("slot")) != str(slot.get("slot"))]
                        count = sum(stats.get(str(s.get("moduleId") or "").casefold(), {}).get("limit") == limit for s in others)
                        maximum = reference.get("limits", {}).get(limit)
                        if maximum is None or any(not s.get("empty") and str(s.get("moduleId") or "").casefold() not in stats for s in others):
                            status, reason = "UNKNOWN", "Installation count cannot be verified"
                        elif any(stats.get(str(s.get("moduleId") or "").casefold(), {}).get("unlimit") == limit for s in slots):
                            status, reason = "UNKNOWN", "Experimental weapon stabiliser limit needs verification"
                        elif count >= maximum:
                            status, reason = "INCOMPATIBLE", f"Installation limit reached ({maximum}); replace the existing module"
                    if symbol and not spec and status == "FITS":
                        status, reason = "UNKNOWN", "Module-specific rule reference unavailable"
                    if status != "INCOMPATIBLE" and ("SHIELD GENERATOR" in family or core_slot == "MainEngines"):
                        max_mass = spec.get("maxmass")
                        if hull_mass is None or max_mass is None:
                            status, reason = "UNKNOWN", "Mass limit reference unavailable"
                        elif hull_mass > max_mass:
                            status, reason = "INCOMPATIBLE", f"Hull mass {hull_mass:g} t exceeds module limit {max_mass:g} t"
                        elif core_slot == "MainEngines":
                            status, reason = "UNKNOWN", f"Hull below {max_mass:g} t limit; full loadout, engineering, fuel and cargo mass still need verification"
                            old_spec = stats.get(str(slot.get("moduleId") or "").casefold(), {})
                            snapshot = ship_stats.get("modules", {})
                            snapshot_matches = bool(snapshot) and all(str(s.get("moduleId") or "").casefold() == str(snapshot.get(str(s.get("slot") or ""), "")).casefold() for s in slots)
                            fuel = ship_stats.get("fuelCapacity")
                            if isinstance(fuel, dict):
                                fuel = sum(fuel.values()) if all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in fuel.values()) else None
                            values = [ship_stats.get("unladenMass"), ship_stats.get("cargoCapacity"), fuel, old_spec.get("mass"), spec.get("mass")]
                            if snapshot_matches and not slot.get("engineered") and all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in values):
                                laden_mass = values[0] + values[1] + values[2] - values[3] + values[4]
                                status = "FITS" if laden_mass <= max_mass else "INCOMPATIBLE"
                                reason = f"Fully laden replacement mass {laden_mass:g} / {max_mass:g} t (Journal loadout; standard replacement)"
                        elif status == "FITS":
                            reason = f"Slot and hull mass verified ({hull_mass:g} / {max_mass:g} t)"
                power_warning = "Power budget not verified"
                installed = [s for s in slots if not s.get("empty") and str(s.get("slot")) != str(slot.get("slot"))]
                if spec.get("power") is not None and all(stats.get(str(s.get("moduleId") or "").casefold(), {}).get("power") is not None and not s.get("engineered") for s in installed):
                    reactor = spec if core_slot == "PowerPlant" else next((stats.get(str(s.get("moduleId") or "").casefold(), {}) for s in installed if s.get("slot") == "PowerPlant"), {})
                    capacity = reactor.get("pgen")
                    if capacity is not None:
                        demand = sum(stats[str(s["moduleId"]).casefold()].get("power", 0) for s in installed) + spec.get("power", 0)
                        power_warning = f"Reference deployed draw {demand:g} / {capacity:g} MW" + ("; OVER BUDGET" if demand > capacity else "") + "; cargo hatch, module priorities and engineering not included"
                slot_fits[str(slot.get("slot") or "")] = {"status": status, "reason": reason, "powerWarning": power_warning}
            fits = any(value["status"] != "INCOMPATIBLE" for value in slot_fits.values())
            status = "FITS" if any(value["status"] == "FITS" for value in slot_fits.values()) else "UNKNOWN" if fits else "INCOMPATIBLE"
            row.update({
                "currentShipSlotFits": slot_fits,
                "fitsCurrentShip": fits,
                "currentShipFitStatus": status,
                "currentShipFitReason": (
                    next((value["reason"] for value in slot_fits.values() if value["status"] == status),
                         f"No compatible {target_group.lower()} slot on the current ship")
                ),
                "powerWarning": "Power budget not verified" + (f"; reference draw {row['powerDrawMW']:g} MW" if row.get("powerDrawMW") is not None else "; module power draw unknown"),
            })
        result.append(row)
    return result


def build_ship_catalog(
    payload: Any, reference_prices: Any = None,
) -> list[dict[str, Any]]:
    price_rows = (
        reference_prices.get("ships", {})
        if isinstance(reference_prices, dict) else {}
    )
    rows = []
    for source in payload if isinstance(payload, list) else []:
        if not isinstance(source, dict):
            continue
        symbol = str(source.get("symbol") or "").strip()
        name = str(source.get("name") or symbol).strip()
        if not symbol or not name:
            continue
        price_row = price_rows.get(symbol.casefold())
        price_row = price_row if isinstance(price_row, dict) else {}
        reference_price = _integer(price_row.get("referencePrice"))
        row = {
            "symbol": symbol.casefold(),
            "assetSymbol": symbol,
            "schematicSource": f"assets/ships/{symbol}.svg",
            "displayName": name,
            "manufacturer": str(source.get("manufacturer") or "").strip(),
            "size": str(source.get("size") or "").strip().upper(),
            "maximumSpeed": source.get("maximumSpeed"),
            "boost": source.get("boost"),
            "kind": "SHIPS",
        }
        if reference_price is not None and reference_price > 0:
            row.update({
                "referencePrice": reference_price,
                "referencePriceSource": str(
                    price_row.get("source") or "ED-Frame reference catalog"
                ),
                "referencePriceCapturedAt": str(
                    reference_prices.get("capturedAt") or ""
                ),
            })
        rows.append(row)
    # Elite's purchase carousel presents affordable hulls before expensive
    # ones.  The global catalog has no station context yet, so use the
    # explicit reference price; unknown prices remain visible at the end.
    return sorted(rows, key=lambda row: (
        0 if _integer(row.get("referencePrice")) is not None else 1,
        _integer(row.get("referencePrice")) or 0,
        row["displayName"].casefold(),
    ))


def catalog_suggestions(
    catalog: Iterable[dict[str, Any]], query: str, *, limit: int = 12,
) -> list[dict[str, Any]]:
    term = str(query or "").strip().casefold()
    if not term:
        return [dict(row) for row in list(catalog)[:max(1, int(limit))]]
    ranked = []
    for row in catalog:
        name = str(row.get("displayName") or "").casefold()
        symbol = str(row.get("symbol") or "").casefold()
        manufacturer = str(row.get("manufacturer") or "").casefold()
        if term not in name and term not in symbol and term not in manufacturer:
            continue
        score = 0 if name.startswith(term) else 1 if term in name else 2
        ranked.append((score, name, symbol, dict(row)))
    return [entry[-1] for entry in sorted(ranked)[:max(1, int(limit))]]


def _coordinates(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _pad_rank(value: Any) -> int:
    normalized = str(value or "").strip().casefold()
    if normalized in {"l", "large"}:
        return 3
    if normalized in {"m", "medium"}:
        return 2
    if normalized in {"s", "small"}:
        return 1
    return 0


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_permit_rules(engineers: Any) -> dict[str, dict[str, Any]]:
    """Project the small, sourced permit subset from the unlock catalog."""
    rules: dict[str, dict[str, Any]] = {}
    for record in (engineers or {}).values() if isinstance(engineers, dict) else []:
        if not isinstance(record, dict):
            continue
        permit = record.get("permit")
        if not isinstance(permit, dict):
            continue
        system = str(permit.get("system") or record.get("system") or "").strip()
        if not system:
            continue
        rules[system.casefold()] = {
            "system": system,
            "name": str(permit.get("name") or f"{system} permit"),
            "method": str(permit.get("method") or "Permit evidence required"),
            "rule": dict(permit.get("rule") or {}),
        }
    return rules


def _overview_ranks(overview: Any) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    rows = overview.get("ranks", []) if isinstance(overview, dict) else []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "")
        result[key] = _integer(row.get("rank")) if row.get("known") else None
    return result


def evaluate_ship_access(
    item: Any, commander_overview: Any,
) -> dict[str, Any]:
    """Return the known naval-rank purchase gate for one hull."""
    source = item if isinstance(item, dict) else {}
    symbol = str(source.get("symbol") or "").strip().casefold()
    rule = SHIP_RANK_REQUIREMENTS.get(symbol)
    if not rule:
        return {
            "purchaseStatus": "OPEN",
            "purchaseTone": "OPEN",
            "purchaseReason": "No known naval-rank purchase requirement",
            "purchaseRank": 0,
        }
    field = str(rule["field"])
    minimum = int(rule["minimum"])
    rank_name = str(rule["rankName"])
    value = _overview_ranks(commander_overview).get(field)
    requirement = f"Requires {field} {rank_name} (rank {minimum})"
    if value is None:
        return {
            "purchaseStatus": "RANK UNCONFIRMED",
            "purchaseTone": "UNKNOWN",
            "purchaseReason": f"{requirement}; Journal rank is unavailable",
            "purchaseRank": 2,
            "requiredRank": minimum,
            "requiredRankName": rank_name,
            "requiredRankField": field,
        }
    if value < minimum:
        return {
            "purchaseStatus": "RANK REQUIRED",
            "purchaseTone": "LOCKED",
            "purchaseReason": f"{requirement}; Journal shows rank {value}",
            "purchaseRank": 3,
            "requiredRank": minimum,
            "requiredRankName": rank_name,
            "requiredRankField": field,
            "commanderRank": value,
        }
    return {
        "purchaseStatus": "RANK CONFIRMED",
        "purchaseTone": "CONFIRMED",
        "purchaseReason": f"Journal {field} rank {value} satisfies {rank_name}",
        "purchaseRank": 0,
        "requiredRank": minimum,
        "requiredRankName": rank_name,
        "requiredRankField": field,
        "commanderRank": value,
    }


def ship_catalog_with_access(
    catalog: Iterable[dict[str, Any]], commander_overview: Any,
) -> list[dict[str, Any]]:
    """Decorate and order hulls like the purchase carousel.

    Available hulls come first, unconfirmed rank access follows, and hulls
    proven to be rank-locked for the current commander sit at the far right.
    Price remains the ordering inside each access group.
    """
    decorated = [
        {**dict(row), **evaluate_ship_access(row, commander_overview)}
        for row in catalog if isinstance(row, dict)
    ]
    access_order = {"OPEN": 0, "CONFIRMED": 0, "UNKNOWN": 1, "LOCKED": 2}
    return sorted(decorated, key=lambda row: (
        access_order.get(str(row.get("purchaseTone") or "UNKNOWN"), 1),
        0 if _integer(row.get("referencePrice")) is not None else 1,
        _integer(row.get("referencePrice")) or 0,
        str(row.get("displayName") or row.get("symbol") or "").casefold(),
    ))


def _observed_age(value: str) -> tuple[int | None, str]:
    text = str(value or "").strip()
    if not text:
        return None, "AGE UNKNOWN"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        minutes = max(0, int(
            (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc))
            .total_seconds() // 60
        ))
    except (TypeError, ValueError, OverflowError):
        return None, "AGE UNKNOWN"
    if minutes < 60:
        return minutes, f"{minutes} MIN OLD"
    hours = minutes // 60
    if hours < 48:
        return minutes, f"{hours} H OLD"
    return minutes, f"{hours // 24} D OLD"


def evaluate_station_access(
    system: str, commander_overview: Any, permit_rules: Any,
) -> dict[str, Any]:
    """Describe access without treating missing Journal proof as denial."""
    name = str(system or "").strip()
    overview = commander_overview if isinstance(commander_overview, dict) else {}
    permits = {
        str(value).strip().casefold()
        for value in overview.get("permits", [])
        if str(value).strip()
    }
    visited = {
        str(value).strip().casefold()
        for value in overview.get("visitedSystems", [])
        if str(value).strip()
    }
    rule = (
        permit_rules.get(name.casefold())
        if isinstance(permit_rules, dict) else None
    )
    if not isinstance(rule, dict):
        return {
            "accessStatus": "OPEN",
            "accessTone": "OPEN",
            "accessReason": "No known permit restriction",
            "accessRank": 1,
        }
    permit_name = str(rule.get("name") or "Permit")
    if name.casefold() in visited:
        return {
            "accessStatus": "CONFIRMED",
            "accessTone": "CONFIRMED",
            "accessReason": f"Journal confirms a visit to {name}",
            "accessRank": 0,
        }
    if name.casefold() in permits or permit_name.casefold() in permits:
        return {
            "accessStatus": "CONFIRMED",
            "accessTone": "CONFIRMED",
            "accessReason": f"Journal confirms {permit_name}",
            "accessRank": 0,
        }
    ranks = _overview_ranks(overview)
    condition = rule.get("rule")
    condition = condition if isinstance(condition, dict) else {}
    condition_type = str(condition.get("type") or "")
    minimum = _integer(condition.get("minimum")) or 0
    if condition_type == "rank":
        field = str(condition.get("field") or "")
        value = ranks.get(field)
        if value is not None and value >= minimum:
            return {
                "accessStatus": "CONFIRMED",
                "accessTone": "CONFIRMED",
                "accessReason": f"{field} rank {value} satisfies {permit_name}",
                "accessRank": 0,
            }
        if value is not None:
            return {
                "accessStatus": "PERMIT MISSING",
                "accessTone": "LOCKED",
                "accessReason": f"{permit_name} requires {field} rank {minimum}; Journal shows {value}",
                "accessRank": 3,
            }
    elif condition_type == "anyRank":
        fields = [str(value) for value in condition.get("fields", [])]
        known = [ranks.get(field) for field in fields if ranks.get(field) is not None]
        if any(value >= minimum for value in known):
            return {
                "accessStatus": "CONFIRMED",
                "accessTone": "CONFIRMED",
                "accessReason": f"Elite career rank satisfies {permit_name}",
                "accessRank": 0,
            }
        if len(known) == len(fields) and fields:
            return {
                "accessStatus": "PERMIT MISSING",
                "accessTone": "LOCKED",
                "accessReason": f"{permit_name} requires Elite rank in one recognised career",
                "accessRank": 3,
            }
    return {
        # A permit-gated destination without positive Journal proof must not
        # look travel-safe.  Red here means "do not recommend", while the
        # wording remains honest that absence of proof is not proof of absence.
        "accessStatus": "PERMIT NOT CONFIRMED",
        "accessTone": "LOCKED",
        "accessReason": (
            f"No Journal proof for {permit_name} · "
            + str(rule.get("method") or "permit evidence required")
        ),
        "accessRank": 3,
    }
def rank_station_offers(
    rows: Iterable[dict[str, Any]], *, kind: str,
    origin_coordinates: Any = None, max_distance_ly: int = 0,
    pad_filter: str = "ANY", item: dict[str, Any] | None = None,
    commander_overview: Any = None, permit_rules: Any = None,
    price_rules: Any = None,
    access_filter: str = "SAFE + UNKNOWN",
) -> list[dict[str, Any]]:
    """Filter, enrich and rank station offers without inventing facts."""
    kind = str(kind or "MODULES").upper()
    origin = _coordinates(origin_coordinates)
    requested_pad = _pad_rank(pad_filter)
    if kind == "SHIPS":
        requested_pad = max(requested_pad, _pad_rank((item or {}).get("size")))
    distance_limit = max(0, int(max_distance_ly or 0))
    projected: list[dict[str, Any]] = []
    for source in rows:
        if not isinstance(source, dict):
            continue
        station = str(source.get("station") or "").strip()
        system = str(source.get("system") or "").strip()
        if not station or not system:
            continue
        available_pad = _pad_rank(source.get("landingPadSize"))
        if requested_pad and available_pad and available_pad < requested_pad:
            continue
        coordinates = _coordinates(source.get("coordinates"))
        distance = None
        if origin is not None and coordinates is not None:
            distance = round(math.sqrt(sum(
                (left - right) ** 2 for left, right in zip(origin, coordinates)
            )), 1)
        if distance_limit and (distance is None or distance > distance_limit):
            continue
        offer_key = "moduleOffer" if kind == "MODULES" else "shipOffer"
        offer = source.get(offer_key)
        offer = dict(offer) if isinstance(offer, dict) else {}
        price = _integer(offer.get("buyPrice", source.get("buyPrice")))
        confidence = str(offer.get("priceConfidence") or "").upper()
        price_type = str(offer.get("priceType") or "").upper()
        price_observed_at = str(offer.get("priceObservedAt") or "").strip()
        price_source = str(
            offer.get("priceSource") or source.get("priceSource")
            or source.get("source") or ""
        )
        price_rule_label = ""
        price_adjustment_bps = 0
        reference_price = _integer((item or {}).get("referencePrice"))
        if kind == "SHIPS":
            # Shipyard.json can contain the Commander's active hull/trade-in
            # value and EDDN only proves availability.  A station-specific
            # exact price therefore overrides the deterministic catalog only
            # when it came from an actual, opt-in ShipyardBuy Journal event.
            purchase_confirmed = (
                price is not None
                and "shipyardbuy" in price_source.casefold().replace(" ", "")
            )
            rules = (
                price_rules.get("rules", [])
                if isinstance(price_rules, dict) else price_rules
            )
            matching_rule = None
            for candidate in rules or []:
                if not isinstance(candidate, dict):
                    continue
                rule_system = str(candidate.get("system") or "").strip()
                rule_station = str(candidate.get("station") or "").strip()
                if (
                    (not rule_system or rule_system.casefold() == system.casefold())
                    and (not rule_station or rule_station.casefold() == station.casefold())
                ):
                    matching_rule = candidate
                    break
            if matching_rule is not None:
                price_adjustment_bps = _integer(
                    matching_rule.get("priceAdjustmentBps")
                ) or 0
                price_rule_label = str(
                    matching_rule.get("label") or "Station price rule"
                ).strip()
            if purchase_confirmed:
                price_status = "PURCHASE CONFIRMED"
            elif reference_price is not None:
                factor = max(0, 10_000 + price_adjustment_bps)
                price = (reference_price * factor + 5_000) // 10_000
                if matching_rule is not None:
                    price_status = "DISCOUNTED" if price_adjustment_bps < 0 else "STATION RULE"
                    price_source = price_rule_label
                else:
                    price_status = "REFERENCE"
                    price_source = str(
                        (item or {}).get("referencePriceSource")
                        or "ED-Frame fixed ship reference catalog"
                    )
                price_observed_at = ""
            else:
                # Newly released hulls remain honestly unknown until the
                # bundled reference catalog is updated.  Availability is kept.
                price = None
                price_status = "UNKNOWN"
                price_source = ""
                price_observed_at = ""
        elif price is None:
            price_status = "UNKNOWN"
        elif (
            kind == "MODULES" or price_type == "OBSERVED"
            or confidence == "OBSERVED" or price_observed_at
        ):
            price_status = "OBSERVED"
        elif price_type == "INFERRED":
            price_status = "ESTIMATED"
        else:
            price_status = "UNKNOWN" if kind == "SHIPS" else "REFERENCE"
        observed_at = str(
            price_observed_at
            or source.get("outfittingObservedAt" if kind == "MODULES" else "shipyardObservedAt")
            or source.get("observedAt") or ""
        )
        arrival = source.get("distanceToArrivalLs")
        system_access = evaluate_station_access(
            system, commander_overview, permit_rules,
        )
        ship_access = (
            evaluate_ship_access(item, commander_overview)
            if kind == "SHIPS" else evaluate_module_access(item)
        )
        if int(ship_access["purchaseRank"]) > int(system_access["accessRank"]):
            access = {
                "accessStatus": ship_access["purchaseStatus"],
                "accessTone": ship_access["purchaseTone"],
                "accessReason": ship_access["purchaseReason"],
                "accessRank": ship_access["purchaseRank"],
            }
        else:
            access = dict(system_access)
        if (
            str(access_filter or "").upper()
            in {"CONFIRMED ONLY", "ACCESSIBLE ONLY"}
            and access["accessRank"] > 1
        ):
            continue
        age_minutes, age_label = _observed_age(observed_at)
        pad_label = str(source.get("landingPadSize") or "UNKNOWN").upper()
        distance_label = (
            f"{distance:.1f} LY" if distance is not None else "LY UNKNOWN"
        )
        arrival_number = _integer(arrival)
        arrival_label = (
            f"{arrival_number:,} LS" if arrival_number is not None
            else "ARRIVAL UNKNOWN"
        )
        access_label = (
            "SAFE" if access["accessRank"] <= 1 else access["accessStatus"]
        )
        recommendation = " · ".join((
            access_label, f"{pad_label}-PAD", age_label,
            distance_label, arrival_label,
        ))
        projected.append({
            "marketId": source.get("marketId"),
            "system": system,
            "station": station,
            "stationType": str(source.get("stationType") or "UNKNOWN"),
            "landingPadSize": str(source.get("landingPadSize") or "UNKNOWN").upper(),
            "distanceLy": distance,
            "distanceKnown": distance is not None,
            "distanceToArrivalLs": arrival,
            "price": price,
            "priceKnown": price is not None,
            "priceStatus": price_status,
            "priceSource": price_source,
            "referencePrice": reference_price,
            "priceAdjustmentBps": price_adjustment_bps,
            "priceRuleLabel": price_rule_label,
            "observedAt": observed_at,
            "dataAgeMinutes": age_minutes,
            "dataAgeLabel": age_label,
            "systemAccessStatus": system_access["accessStatus"],
            "systemAccessReason": system_access["accessReason"],
            **ship_access,
            **access,
            "reason": "Availability observed"
                      + (f" · {price_status.lower()} price" if price_status != "UNKNOWN" else " · price unknown"),
            "recommendationReason": recommendation,
        })
    projected.sort(key=lambda row: (
        row["accessRank"],
        0 if row["priceStatus"] in {"OBSERVED", "PURCHASE CONFIRMED"} else
        1 if row["priceStatus"] in {"ESTIMATED", "DISCOUNTED", "STATION RULE"} else
        2 if row["priceKnown"] else 3,
        row["price"] if row["priceKnown"] else 10**18,
        row["distanceLy"] if row["distanceKnown"] else 10**9,
        float(row["distanceToArrivalLs"] or 10**12),
        row["system"].casefold(), row["station"].casefold(),
    ))
    return projected
