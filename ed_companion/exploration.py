"""Journal-derived unsold cartography ledger and conservative valuation.

Frontier does not write the final per-body sale price to the scan event.  The
projection therefore keeps the evidence and reports a value range whenever a
terraforming or first-discovery bonus is not guaranteed.  It never presents a
community-derived estimate as an exact Journal fact.
"""
from __future__ import annotations

from typing import Any


_UNSELLABLE_SCAN_TYPES = frozenset({"navbeacondetail"})
_LOSS_OPTIONS = frozenset({"rebuy", "restart"})
_Q = 0.56591828
_FIRST_DISCOVERY_MULTIPLIER = 2.6
_MAPPING_MULTIPLIER = 10 / 3
_FIRST_DISCOVERY_AND_MAP_MULTIPLIER = 3.699622554
_FIRST_MAP_MULTIPLIER = 8.0956
_EFFICIENCY_MULTIPLIER = 1.25


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None


def _system_key(address: object, name: object) -> str:
    numeric = _as_int(address)
    if numeric is not None:
        return f"address:{numeric}"
    text = str(name or "").strip()
    return f"name:{text.casefold()}" if text else ""


def _body_key(event: dict[str, Any], system_name: str = "") -> str:
    system = _system_key(event.get("SystemAddress"), system_name)
    body_id = _as_int(event.get("BodyID"))
    if system and body_id is not None:
        return f"{system}:body:{body_id}"
    body_name = str(event.get("BodyName") or "").strip()
    if system and body_name:
        return f"{system}:name:{body_name.casefold()}"
    return f"body-name:{body_name.casefold()}" if body_name else ""


def _signal_rows(event: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for signal in event.get("Signals", []) or []:
        if not isinstance(signal, dict):
            continue
        symbol = str(signal.get("Type") or "")
        label = str(signal.get("Type_Localised") or symbol)
        rows.append({
            "type": symbol,
            "name": label,
            "count": max(0, _as_int(signal.get("Count")) or 0),
            "source": str(event.get("event") or ""),
        })
    rows.sort(key=lambda row: (row["name"].casefold(), row["type"]))
    return rows


def _is_terraformable(value: object) -> bool:
    return "terraform" in str(value or "").casefold()


def _star_k(star_type: str) -> float:
    if star_type in {"N", "H"}:
        return 22628
    if star_type.startswith("D"):
        return 14057
    return 1200


def _planet_value_components(
    planet_class: str, terraformable: bool,
) -> tuple[int, int, float]:
    """Return base k, terraform bonus k and conservative bonus fraction."""
    terraform = 0
    fraction = 1.0
    if planet_class == "Metal rich body":
        base = 21790
    elif planet_class == "Ammonia world":
        base = 96932
    elif planet_class == "Sudarsky class I gas giant":
        base = 1656
    elif planet_class in {"Sudarsky class II gas giant", "High metal content body"}:
        base = 9654
        if terraformable:
            terraform, fraction = 100677, 0.9
    elif planet_class == "Water world":
        base = 64831
        if terraformable:
            terraform, fraction = 116295, 0.75
    elif planet_class == "Earthlike body":
        base, terraform = 64831, 116295
        # Naturally habitable ELWs receive the full bonus.  An explicitly
        # terraformed ELW does not receive this extra component.
        fraction = 0.0 if terraformable else 1.0
    else:
        base = 300
        if terraformable:
            terraform, fraction = 93328, 0.9
    return base, terraform, fraction


def _mapping_multiplier(first_discovery: bool, first_map: bool) -> float:
    if first_discovery and first_map:
        return _FIRST_DISCOVERY_AND_MAP_MULTIPLIER
    if first_map:
        return _FIRST_MAP_MULTIPLIER
    return _MAPPING_MULTIPLIER


def _odyssey_mapped_bonus(value: float) -> float:
    return value + max(value * 0.3, 555)


def _planet_estimate(
    row: dict[str, Any], *, maximum: bool, odyssey_bonus: bool,
) -> int | None:
    mass = _as_float(row.get("massEarths"))
    if mass is None or mass < 0:
        return None
    base, terraform, minimum_fraction = _planet_value_components(
        str(row.get("planetClass") or ""),
        _is_terraformable(row.get("terraformState")),
    )
    k = base + terraform * (1.0 if maximum else minimum_fraction)
    value = max(k + k * _Q * (mass ** 0.2), 500)
    first_discovery = bool(
        maximum
        and (
            row.get("possibleFirstDiscovery")
            or not row.get("wasDiscoveredKnown")
        )
    )
    if row.get("mapped"):
        first_map = bool(
            maximum
            and (
                row.get("possibleFirstMapped")
                or not row.get("wasMappedKnown")
            )
        )
        value *= _mapping_multiplier(first_discovery, first_map)
        if odyssey_bonus:
            value = _odyssey_mapped_bonus(value)
        if row.get("efficiencyBonus"):
            value *= _EFFICIENCY_MULTIPLIER
    if first_discovery:
        value *= _FIRST_DISCOVERY_MULTIPLIER
    return round(value)


def _star_estimate(row: dict[str, Any], *, maximum: bool) -> int | None:
    mass = _as_float(row.get("stellarMass"))
    if mass is None or mass < 0:
        return None
    k = _star_k(str(row.get("starType") or ""))
    value = max(k + mass * k / 66.25, 500)
    if maximum and (
        row.get("possibleFirstDiscovery") or not row.get("wasDiscoveredKnown")
    ):
        value *= _FIRST_DISCOVERY_MULTIPLIER
    return round(value)


def _finding_label(row: dict[str, Any]) -> str:
    planet_class = str(row.get("planetClass") or "")
    star_type = str(row.get("starType") or "")
    if planet_class:
        return planet_class
    if star_type == "N":
        return "Neutron star"
    if star_type == "H":
        return "Black hole"
    if star_type.startswith("D"):
        return "White dwarf"
    if star_type:
        return f"{star_type} star"
    if row.get("bodyKind") == "belt":
        return "Belt cluster"
    return "Unknown body"


def _signal_count(row: dict[str, Any], needle: str) -> int:
    return sum(
        int(signal.get("count") or 0)
        for signal in row.get("signals", [])
        if isinstance(signal, dict)
        and needle in f"{signal.get('type', '')} {signal.get('name', '')}".casefold()
    )


def _value_and_classify(row: dict[str, Any]) -> None:
    """Add value range and display-ready classification in place."""
    tags: list[str] = []
    planet_class = str(row.get("planetClass") or "")
    star_type = str(row.get("starType") or "")
    category_tags = {
        "Earthlike body": "EARTH_LIKE",
        "Water world": "WATER_WORLD",
        "Ammonia world": "AMMONIA_WORLD",
    }
    if planet_class in category_tags:
        tags.append(category_tags[planet_class])
    if _is_terraformable(row.get("terraformState")):
        tags.append("TERRAFORMABLE")
    if star_type == "N":
        tags.append("NEUTRON_STAR")
    elif star_type == "H":
        tags.append("BLACK_HOLE")
    elif star_type.startswith("D"):
        tags.append("WHITE_DWARF")
    if row.get("possibleFirstDiscovery"):
        tags.append("POSSIBLE_FIRST_DISCOVERY")
    elif not row.get("wasDiscoveredKnown"):
        tags.append("DISCOVERY_STATUS_UNKNOWN")
    if row.get("mapped"):
        tags.append("MAPPED")
    if row.get("possibleFirstMapped"):
        tags.append("POSSIBLE_FIRST_MAPPING")
    elif row.get("mapped") and not row.get("wasMappedKnown"):
        tags.append("MAPPING_STATUS_UNKNOWN")
    if row.get("efficiencyBonus"):
        tags.append("EFFICIENCY_BONUS")
    biological = _signal_count(row, "biological")
    geological = _signal_count(row, "geological")
    if biological:
        tags.append("BIOLOGICAL_SIGNALS")
    if geological:
        tags.append("GEOLOGICAL_SIGNALS")

    minimum: int | None
    maximum: int | None
    if not row.get("hasScan"):
        minimum = maximum = None
    elif row.get("bodyKind") == "belt":
        minimum = maximum = 0
    elif row.get("bodyKind") == "star":
        minimum = _star_estimate(row, maximum=False)
        maximum = _star_estimate(row, maximum=True)
    elif row.get("bodyKind") == "planet":
        odyssey_known = bool(row.get("odysseyKnown"))
        odyssey = bool(row.get("odyssey"))
        minimum = _planet_estimate(
            row, maximum=False, odyssey_bonus=odyssey if odyssey_known else False,
        )
        maximum = _planet_estimate(
            row, maximum=True, odyssey_bonus=odyssey if odyssey_known else True,
        )
    else:
        minimum = maximum = None
    if minimum is not None and maximum is not None and minimum > maximum:
        minimum, maximum = maximum, minimum
    status = (
        "unavailable" if minimum is None or maximum is None
        else "estimated" if minimum == maximum
        else "range"
    )
    row.update({
        "findingClass": _finding_label(row),
        "tags": tags,
        "biologicalSignalCount": biological,
        "geologicalSignalCount": geological,
        "estimatedValueMin": minimum,
        "estimatedValueMax": maximum,
        "estimatedValue": minimum if minimum == maximum else None,
        "valueStatus": status,
        "highValue": bool(maximum is not None and maximum >= 100000),
        "valueBasis": "community-formula-estimate",
    })


def _sold_names(event: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Return case-folded system and body names confirmed by a sale."""
    systems: set[str] = set()
    bodies: set[str] = set()
    for value in event.get("Systems", []) or []:
        if isinstance(value, dict):
            value = value.get("SystemName") or value.get("Name")
        text = str(value or "").strip()
        if text:
            systems.add(text.casefold())
    for value in event.get("Discovered", []) or []:
        if isinstance(value, dict):
            system_name = str(value.get("SystemName") or "").strip()
            body_name = str(value.get("BodyName") or "").strip()
            if system_name:
                systems.add(system_name.casefold())
            if body_name:
                bodies.add(body_name.casefold())
        else:
            text = str(value or "").strip()
            if text:
                bodies.add(text.casefold())
    return systems, bodies


def _new_body(event: dict[str, Any], system_name: str) -> dict[str, Any]:
    address = _as_int(event.get("SystemAddress"))
    body_id = _as_int(event.get("BodyID"))
    key = _body_key(event, system_name)
    return {
        "id": key,
        "systemKey": _system_key(address, system_name),
        "systemAddress": address,
        "systemName": system_name,
        "bodyId": body_id,
        "bodyName": str(event.get("BodyName") or ""),
        "timestamp": str(event.get("timestamp") or ""),
        "hasScan": False,
        "scanType": "",
        "bodyKind": "unknown",
        "starType": "",
        "planetClass": "",
        "terraformState": "",
        "landable": False,
        "atmosphere": "",
        "atmosphereType": "",
        "volcanism": "",
        "distanceFromArrivalLs": None,
        "massEarths": None,
        "stellarMass": None,
        "odysseyKnown": False,
        "odyssey": False,
        "rings": [],
        "wasDiscoveredKnown": False,
        "wasDiscovered": False,
        "wasMappedKnown": False,
        "wasMapped": False,
        "possibleFirstDiscovery": False,
        "possibleFirstMapped": False,
        "mapped": False,
        "probesUsed": None,
        "efficiencyTarget": None,
        "efficiencyBonus": False,
        "signals": [],
        "genuses": [],
    }


def exploration_ledger(
    events: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Return unsold cartography observations and their boundary evidence.

    ``SellExplorationData`` and ``MultiSellExplorationData`` retire only the
    named systems/bodies.  A plain ``Died`` is not sufficient evidence of a
    ship loss (crew/fighter deaths use it too); an insurance ``Resurrect``
    with ``rebuy``/``restart`` is the destructive boundary.
    """
    bodies: dict[str, dict[str, Any]] = {}
    system_names: dict[int, str] = {}
    current_system_name = ""
    current_system_address: int | None = None
    last_sale: dict[str, Any] = {}
    last_loss: dict[str, Any] = {}
    current_odyssey_known = False
    current_odyssey = False

    def resolve_system_name(event: dict[str, Any]) -> str:
        address = _as_int(event.get("SystemAddress"))
        explicit = str(event.get("StarSystem") or "").strip()
        if explicit and address is not None:
            system_names[address] = explicit
        if explicit:
            return explicit
        if address is not None and system_names.get(address):
            return system_names[address]
        if address is None or address == current_system_address:
            return current_system_name
        return ""

    def body_for(event: dict[str, Any]) -> dict[str, Any] | None:
        system_name = resolve_system_name(event)
        key = _body_key(event, system_name)
        if not key:
            return None
        row = bodies.get(key)
        if row is None:
            row = _new_body(event, system_name)
            bodies[key] = row
        elif system_name and not row["systemName"]:
            row["systemName"] = system_name
            row["systemKey"] = _system_key(row["systemAddress"], system_name)
        row["timestamp"] = max(
            str(row.get("timestamp") or ""), str(event.get("timestamp") or "")
        )
        return row

    for event in events or []:
        if not isinstance(event, dict):
            continue
        name = str(event.get("event") or "")
        if name == "Fileheader":
            if "Odyssey" in event:
                current_odyssey_known = True
                current_odyssey = bool(event.get("Odyssey"))
            else:
                version = str(event.get("gameversion") or "")
                major = _as_int(version.split(".", 1)[0])
                if major is not None:
                    current_odyssey_known = True
                    current_odyssey = major >= 4
        if event.get("StarSystem"):
            current_system_name = str(event["StarSystem"])
        event_address = _as_int(event.get("SystemAddress"))
        if event_address is not None:
            current_system_address = event_address
            if current_system_name:
                system_names[event_address] = current_system_name

        if name == "Scan":
            scan_type = str(event.get("ScanType") or "")
            if scan_type.casefold() in _UNSELLABLE_SCAN_TYPES:
                continue
            row = body_for(event)
            if row is None:
                continue
            star_type = str(event.get("StarType") or "")
            planet_class = str(event.get("PlanetClass") or "")
            rings = []
            for ring in event.get("Rings", []) or []:
                if not isinstance(ring, dict):
                    continue
                rings.append({
                    "name": str(ring.get("Name") or ""),
                    "ringClass": str(ring.get("RingClass") or ""),
                    "massMt": _as_float(ring.get("MassMT")),
                    "innerRad": _as_float(ring.get("InnerRad")),
                    "outerRad": _as_float(ring.get("OuterRad")),
                })
            row.update({
                "hasScan": True,
                "scanType": scan_type,
                "bodyKind": (
                    "star" if star_type else "planet" if planet_class
                    else "belt" if "Belt Cluster" in str(event.get("BodyName") or "")
                    else "unknown"
                ),
                "starType": star_type,
                "planetClass": planet_class,
                "terraformState": str(event.get("TerraformState") or ""),
                "landable": bool(event.get("Landable", False)),
                "atmosphere": str(event.get("Atmosphere") or ""),
                "atmosphereType": str(event.get("AtmosphereType") or ""),
                "volcanism": str(event.get("Volcanism") or ""),
                "distanceFromArrivalLs": _as_float(
                    event.get("DistanceFromArrivalLS")
                ),
                "massEarths": _as_float(event.get("MassEM")),
                "stellarMass": _as_float(event.get("StellarMass")),
                "odysseyKnown": current_odyssey_known,
                "odyssey": current_odyssey,
                "rings": rings,
                "wasDiscoveredKnown": "WasDiscovered" in event,
                "wasDiscovered": bool(event.get("WasDiscovered", False)),
                "wasMappedKnown": "WasMapped" in event,
                "wasMapped": bool(event.get("WasMapped", False)),
                "possibleFirstDiscovery": (
                    "WasDiscovered" in event
                    and not bool(event.get("WasDiscovered"))
                ),
            })
            if row.get("mapped"):
                row["possibleFirstMapped"] = bool(
                    row.get("wasMappedKnown") and not row.get("wasMapped")
                )
        elif name == "SAAScanComplete":
            row = body_for(event)
            if row is None:
                continue
            probes = _as_int(event.get("ProbesUsed"))
            target = _as_int(event.get("EfficiencyTarget"))
            row.update({
                "mapped": True,
                "probesUsed": probes,
                "efficiencyTarget": target,
                "efficiencyBonus": bool(
                    probes is not None and target is not None
                    and target > 0 and probes <= target
                ),
            })
            row["possibleFirstMapped"] = bool(
                row.get("wasMappedKnown") and not row.get("wasMapped")
            )
        elif name in {"FSSBodySignals", "SAASignalsFound"}:
            row = body_for(event)
            if row is None:
                continue
            by_key = {
                (signal["type"], signal["source"]): signal
                for signal in row.get("signals", [])
                if isinstance(signal, dict)
            }
            for signal in _signal_rows(event):
                by_key[(signal["type"], signal["source"])] = signal
            row["signals"] = sorted(
                by_key.values(),
                key=lambda signal: (
                    signal["name"].casefold(), signal["source"], signal["type"]
                ),
            )
            genuses = []
            for genus in event.get("Genuses", []) or []:
                if not isinstance(genus, dict):
                    continue
                genuses.append({
                    "genus": str(genus.get("Genus") or ""),
                    "name": str(
                        genus.get("Genus_Localised") or genus.get("Genus") or ""
                    ),
                })
            if genuses:
                row["genuses"] = genuses
        elif name in {"SellExplorationData", "MultiSellExplorationData"}:
            sold_systems, sold_bodies = _sold_names(event)
            bodies = {
                key: row for key, row in bodies.items()
                if str(row.get("systemName") or "").casefold() not in sold_systems
                and str(row.get("bodyName") or "").casefold() not in sold_bodies
            }
            last_sale = {
                "timestamp": str(event.get("timestamp") or ""),
                "event": name,
                "baseValue": _as_int(event.get("BaseValue")),
                "bonus": _as_int(event.get("Bonus")),
                "totalEarnings": _as_int(event.get("TotalEarnings")),
                "systemCount": len(sold_systems),
            }
        elif name == "Resurrect":
            option = str(event.get("Option") or "").casefold()
            if option in _LOSS_OPTIONS or bool(event.get("Bankrupt")):
                bodies = {}
                last_loss = {
                    "timestamp": str(event.get("timestamp") or ""),
                    "option": option,
                    "bankrupt": bool(event.get("Bankrupt")),
                }

    for row in bodies.values():
        _value_and_classify(row)

    findings = sorted(
        bodies.values(),
        key=lambda row: (
            str(row.get("systemName") or "").casefold(),
            row.get("bodyId") is None,
            row.get("bodyId") if row.get("bodyId") is not None else 0,
            str(row.get("bodyName") or "").casefold(),
        ),
    )
    grouped: dict[str, dict[str, Any]] = {}
    for row in findings:
        key = str(row.get("systemKey") or "")
        system = grouped.setdefault(key, {
            "id": key,
            "systemAddress": row.get("systemAddress"),
            "name": str(row.get("systemName") or ""),
            "lastScan": "",
            "bodyCount": 0,
            "mappedCount": 0,
            "signalBodyCount": 0,
            "possibleFirstDiscoveryCount": 0,
            "possibleFirstMappedCount": 0,
            "estimatedValueMin": 0,
            "estimatedValueMax": 0,
            "unvaluedBodyCount": 0,
        })
        system["lastScan"] = max(system["lastScan"], str(row.get("timestamp") or ""))
        system["bodyCount"] += int(bool(row.get("hasScan")))
        system["mappedCount"] += int(bool(row.get("mapped")))
        system["signalBodyCount"] += int(bool(row.get("signals")))
        system["possibleFirstDiscoveryCount"] += int(
            bool(row.get("possibleFirstDiscovery"))
        )
        system["possibleFirstMappedCount"] += int(
            bool(row.get("possibleFirstMapped"))
        )
        if row.get("estimatedValueMin") is None or row.get("estimatedValueMax") is None:
            system["unvaluedBodyCount"] += int(bool(row.get("hasScan")))
        else:
            system["estimatedValueMin"] += int(row["estimatedValueMin"])
            system["estimatedValueMax"] += int(row["estimatedValueMax"])
    systems = sorted(
        grouped.values(),
        key=lambda row: (
            str(row.get("lastScan") or ""), str(row.get("name") or "").casefold()
        ),
        reverse=True,
    )
    scanned = [row for row in findings if row.get("hasScan")]
    valued = [
        row for row in scanned
        if row.get("estimatedValueMin") is not None
        and row.get("estimatedValueMax") is not None
    ]
    value_min = sum(int(row["estimatedValueMin"]) for row in valued)
    value_max = sum(int(row["estimatedValueMax"]) for row in valued)
    unvalued = len(scanned) - len(valued)
    summary = {
        "systemCount": len([row for row in systems if row.get("bodyCount")]),
        "bodyCount": len(scanned),
        "mappedCount": sum(bool(row.get("mapped")) for row in findings),
        "signalBodyCount": sum(bool(row.get("signals")) for row in findings),
        "possibleFirstDiscoveryCount": sum(
            bool(row.get("possibleFirstDiscovery")) for row in scanned
        ),
        "possibleFirstMappedCount": sum(
            bool(row.get("possibleFirstMapped")) for row in findings
        ),
        "lastSale": last_sale,
        "lastLoss": last_loss,
        "estimatedValueMin": value_min,
        "estimatedValueMax": value_max,
        "estimatedValue": value_min if not unvalued and value_min == value_max else None,
        "valuedBodyCount": len(valued),
        "unvaluedBodyCount": unvalued,
        "valueStatus": (
            "unavailable" if unvalued and not valued
            else "partial" if unvalued
            else "estimated" if value_min == value_max
            else "range"
        ),
        "valueBasis": "community-formula-estimate",
        "fleetCarrierReductionIncluded": False,
    }
    return {"systems": systems, "findings": findings, "summary": summary}
