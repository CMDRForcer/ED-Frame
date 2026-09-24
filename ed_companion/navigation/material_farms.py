"""Project the bundled raw-material farm catalog for live navigation."""

import math

from ed_companion.surface_nav import parse_coordinate


def _star_position(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        position = tuple(float(part) for part in value)
    except (TypeError, ValueError):
        return None
    return position if all(math.isfinite(part) for part in position) else None


def _surface_coordinates(value):
    parts = str(value or "").split("/")
    if len(parts) != 2:
        return None
    try:
        return (parse_coordinate(parts[0], 90), parse_coordinate(parts[1], 180))
    except ValueError:
        return None


def farm_entry_key(site_id, material_key):
    return f"{site_id}|{material_key}"


def sanitize_farm_overrides(catalog, saved):
    """Keep only valid edits for entries that still exist in the catalog."""
    sites = catalog.get("sites", {}) if isinstance(catalog, dict) else {}
    materials = catalog.get("materials", {}) if isinstance(catalog, dict) else {}
    if not isinstance(sites, dict) or not isinstance(materials, dict):
        return {}
    if not isinstance(saved, dict):
        return {}
    cleaned = {}
    for key, edit in saved.items():
        if not isinstance(key, str) or not isinstance(edit, dict) or "|" not in key:
            continue
        site_id, source_material = key.rsplit("|", 1)
        material = materials.get(source_material)
        if (site_id not in sites or not isinstance(material, dict)
                or site_id not in (material.get("site_ids") or [])):
            continue
        if edit.get("deleted") is True:
            cleaned[key] = {"deleted": True}
            continue
        material_key = str(edit.get("materialKey") or source_material)
        if not isinstance(materials.get(material_key), dict):
            continue
        system = str(edit.get("system") or "").strip()
        body = str(edit.get("body") or "").strip()
        method = str(edit.get("method") or "").strip()
        if (not system or not body or len(system) > 100 or len(body) > 100
                or len(method) > 500):
            continue
        latitude = edit.get("latitude")
        longitude = edit.get("longitude")
        if latitude is None and longitude is None:
            coordinates = None
        else:
            try:
                coordinates = (parse_coordinate(latitude, 90),
                               parse_coordinate(longitude, 180))
            except ValueError:
                continue
        cleaned[key] = {
            "materialKey": material_key, "system": system, "body": body,
            "method": method,
            "latitude": coordinates[0] if coordinates else None,
            "longitude": coordinates[1] if coordinates else None,
        }
    return cleaned


def material_farm_rows(catalog, current_position=None, current_system="",
                       overrides=None, include_deleted=False):
    """Return catalog-backed sites, with exact 3D straight-line distances only."""
    if not isinstance(catalog, dict):
        return [], []
    materials = catalog.get("materials") or {}
    sites = catalog.get("sites") or {}
    if not isinstance(materials, dict) or not isinstance(sites, dict):
        return [], []
    origin = _star_position(current_position)
    system_name = str(current_system or "").strip().casefold()
    edits = sanitize_farm_overrides(catalog, overrides)
    rows = []
    material_options = []
    for material_key, material in materials.items():
        if not isinstance(material, dict):
            continue
        material_rows = []
        for site_id in material.get("site_ids") or []:
            site = sites.get(site_id)
            if not isinstance(site, dict) or not site.get("verified"):
                continue
            system = str(site.get("system") or "").strip()
            body = str(site.get("body") or "").strip()
            if not system or not body:
                continue
            edit = edits.get(farm_entry_key(site_id, material_key), {})
            deleted = edit.get("deleted") is True
            if deleted and not include_deleted:
                continue
            effective_material_key = edit.get("materialKey", material_key)
            effective_material = materials.get(effective_material_key, material)
            system = edit.get("system", system)
            body = edit.get("body", body)
            destination = (_star_position(site.get("star_pos"))
                           if system.casefold() == str(site.get("system") or "").strip().casefold()
                           else None)
            distance = None
            if system_name and system.casefold() == system_name:
                distance = 0.0
            elif origin is not None and destination is not None:
                distance = round(math.dist(origin, destination), 1)
            coordinates = _surface_coordinates(site.get("coordinates"))
            if edit and not deleted:
                coordinates = ((edit["latitude"], edit["longitude"])
                               if edit["latitude"] is not None else None)
            material_rows.append({
                "siteId": str(site_id),
                "sourceMaterialKey": str(material_key),
                "materialKey": str(effective_material_key),
                "materialName": str(effective_material.get("name") or effective_material_key),
                "system": system,
                "body": body,
                "latitude": coordinates[0] if coordinates else None,
                "longitude": coordinates[1] if coordinates else None,
                "distanceLy": distance,
                "method": edit.get("method", str(site.get("method") or "")),
                "kind": str(site.get("kind") or ""),
                "role": str(site.get("role") or ""),
                "deleted": deleted,
                "edited": bool(edit) and not deleted,
            })
        if material_rows:
            rows.extend(material_rows)
    for key in {row["materialKey"] for row in rows if not row["deleted"]}:
        material = materials[key]
        material_options.append({
            "key": str(key), "name": str(material.get("name") or key),
        })
    material_options.sort(key=lambda row: row["name"].casefold())
    rows.sort(key=lambda row: (
        row["distanceLy"] is None,
        row["distanceLy"] if row["distanceLy"] is not None else math.inf,
        row["latitude"] is None,
        row["materialName"].casefold(), row["system"].casefold(), row["siteId"],
    ))
    return rows, material_options
