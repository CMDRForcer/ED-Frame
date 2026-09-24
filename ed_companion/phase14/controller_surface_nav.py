"""Saved surface waypoints and live compass data for the Nav page."""

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Property, Signal, Slot

from ed_companion.navigation.material_farms import (
    farm_entry_key, material_farm_rows, sanitize_farm_overrides,
)
from ed_companion.surface_nav import parse_coordinate, surface_guidance
from .state import journal_dir, read_json


class SurfaceNavMixin:
    surfaceNavChanged = Signal()

    surfaceNav = Property(
        "QVariantMap", lambda self: self._surface_nav, notify=surfaceNavChanged,
    )

    def _init_surface_nav(self):
        self.surface_nav_file = self.config_dir / "surface_nav_targets.json"
        reference_dir = getattr(
            self, "_reference_data_dir", Path(__file__).resolve().parents[2] / "ed_data",
        )
        self._farm_catalog = read_json(reference_dir / "raw_materials_database.json", {})
        self.material_farm_edits_file = self.config_dir / "material_farm_edits.json"
        self._farm_edits = sanitize_farm_overrides(
            self._farm_catalog, self._read_local_json(self.material_farm_edits_file, {}),
        )
        saved = self._read_local_json(self.surface_nav_file, {})
        saved = saved if isinstance(saved, dict) else {}
        targets = []
        saved_targets = saved.get("targets")
        for row in saved_targets if isinstance(saved_targets, list) else []:
            if not isinstance(row, dict):
                continue
            try:
                latitude = parse_coordinate(row.get("latitude"), 90)
                longitude = parse_coordinate(row.get("longitude"), 180)
            except ValueError:
                continue
            if not row.get("id") or not row.get("body") or not row.get("system"):
                continue
            target = {
                "id": str(row["id"]), "name": str(row.get("name") or "Waypoint"),
                "system": str(row["system"]), "body": str(row["body"]),
                "latitude": latitude, "longitude": longitude,
            }
            if row.get("catalogId"):
                target["catalogId"] = str(row["catalogId"])
            if row.get("catalogMaterialKey"):
                target["catalogMaterialKey"] = str(row["catalogMaterialKey"])
            targets.append(target)
        active_id = str(saved.get("activeId") or "")
        if not any(row["id"] == active_id for row in targets):
            active_id = ""
        self._surface_nav = {
            "targets": targets, "activeId": active_id, "position": {},
            "guidance": {}, "message": "", "farmSites": [],
            "farmMaterials": [], "farmAllMaterials": [], "farmDeletedSites": [],
            "originSystem": "", "originKnown": False,
        }
        self._poll_surface_nav()

    def _set_surface_nav_message(self, message):
        self._surface_nav = {**self._surface_nav, "message": message}
        self.surfaceNavChanged.emit()

    def _save_surface_nav(self, targets, active_id):
        payload = {"targets": targets, "activeId": active_id}
        if not self._persist_json(self.surface_nav_file, payload, "Surface Nav targets"):
            self._set_surface_nav_message("nav.error_save")
            return False
        self._surface_nav = {
            **self._surface_nav, "targets": targets, "activeId": active_id,
            "message": "",
        }
        self._poll_surface_nav()
        self.surfaceNavChanged.emit()
        return True

    @Slot(str, str, str, result=bool)
    def saveSurfaceTarget(self, name, latitude_text, longitude_text):
        try:
            latitude = parse_coordinate(latitude_text, 90)
            longitude = parse_coordinate(longitude_text, 180)
        except ValueError:
            self._set_surface_nav_message("nav.error_coordinate")
            return False
        status = read_json(journal_dir() / "Status.json", {})
        status = status if isinstance(status, dict) else {}
        body = str(status.get("BodyName") or "").strip()
        system = str(self._state.get("system") or "").strip()
        if not body or not system or system == "Unknown":
            self._set_surface_nav_message("nav.error_body")
            return False
        targets = list(self._surface_nav["targets"])
        row = {
            "id": uuid4().hex, "name": str(name).strip() or f"Waypoint {len(targets) + 1}",
            "system": system, "body": body,
            "latitude": latitude, "longitude": longitude,
        }
        targets.append(row)
        return self._save_surface_nav(targets, row["id"])

    @Slot(str, result=bool)
    def activateSurfaceTarget(self, target_id):
        if not any(row["id"] == target_id for row in self._surface_nav["targets"]):
            return False
        return self._save_surface_nav(self._surface_nav["targets"], target_id)

    @Slot(str, str, result=bool)
    def activateMaterialFarmSite(self, site_id, material_key):
        site = next((row for row in self._surface_nav["farmSites"]
                     if row["siteId"] == site_id
                     and row["sourceMaterialKey"] == material_key), None)
        if site is None or site["latitude"] is None or site["longitude"] is None:
            self._set_surface_nav_message("nav.error_site_coordinates")
            return False
        existing = next((row for row in self._surface_nav["targets"]
                         if row.get("catalogId") == site_id
                         and row.get("catalogMaterialKey", material_key) == material_key), None)
        if existing:
            refreshed = {
                **existing, "system": site["system"],
                "body": f"{site['system']} {site['body']}",
                "latitude": site["latitude"], "longitude": site["longitude"],
                "catalogMaterialKey": material_key,
            }
            targets = [refreshed if row["id"] == existing["id"] else row
                       for row in self._surface_nav["targets"]]
            return self._save_surface_nav(targets, existing["id"])
        target = {
            "id": uuid4().hex,
            "name": f"{site['materialName']} · {site['system']} {site['body']}",
            "system": site["system"],
            "body": f"{site['system']} {site['body']}",
            "latitude": site["latitude"], "longitude": site["longitude"],
            "catalogId": site_id,
            "catalogMaterialKey": material_key,
        }
        return self._save_surface_nav(
            [*self._surface_nav["targets"], target], target["id"],
        )

    def _save_material_farm_edits(self, edits):
        if not self._persist_json(self.material_farm_edits_file, edits, "Material farm edits"):
            self._set_surface_nav_message("nav.error_farm_save")
            return False
        self._farm_edits = edits
        self._poll_surface_nav()
        self._set_surface_nav_message("")
        return True

    @Slot(str, str, str, str, str, str, str, str, result=bool)
    def editMaterialFarmSite(self, site_id, source_material_key, material_key,
                             system, body, latitude_text, longitude_text, method):
        key = farm_entry_key(site_id, source_material_key)
        site = next((row for row in self._surface_nav["farmSites"]
                     if row["siteId"] == site_id
                     and row["sourceMaterialKey"] == source_material_key), None)
        materials = self._farm_catalog.get("materials", {})
        if site is None or not isinstance(materials.get(material_key), dict):
            self._set_surface_nav_message("nav.error_farm_details")
            return False
        system, body, method = (str(value).strip() for value in (system, body, method))
        if (not system or not body or len(system) > 100 or len(body) > 100
                or len(method) > 500):
            self._set_surface_nav_message("nav.error_farm_details")
            return False
        if not str(latitude_text).strip() and not str(longitude_text).strip():
            latitude = longitude = None
        else:
            try:
                latitude = parse_coordinate(latitude_text, 90)
                longitude = parse_coordinate(longitude_text, 180)
            except ValueError:
                self._set_surface_nav_message("nav.error_coordinate")
                return False
        edits = {**self._farm_edits, key: {
            "materialKey": material_key, "system": system, "body": body,
            "latitude": latitude, "longitude": longitude, "method": method,
        }}
        return self._save_material_farm_edits(edits)

    @Slot(str, str, result=bool)
    def removeMaterialFarmSite(self, site_id, source_material_key):
        key = farm_entry_key(site_id, source_material_key)
        if not any(row["siteId"] == site_id
                   and row["sourceMaterialKey"] == source_material_key
                   for row in self._surface_nav["farmSites"]):
            return False
        return self._save_material_farm_edits({**self._farm_edits, key: {"deleted": True}})

    @Slot(str, str, result=bool)
    def restoreMaterialFarmSite(self, site_id, source_material_key):
        key = farm_entry_key(site_id, source_material_key)
        if key not in self._farm_edits:
            return False
        edits = dict(self._farm_edits)
        edits.pop(key)
        return self._save_material_farm_edits(edits)

    @Slot(str, str, result=bool)
    def renameSurfaceTarget(self, target_id, name):
        new_name = str(name).strip()
        if not new_name or len(new_name) > 80:
            self._set_surface_nav_message("nav.error_name")
            return False
        targets = [
            {**row, "name": new_name} if row["id"] == target_id else row
            for row in self._surface_nav["targets"]
        ]
        if not any(row["id"] == target_id for row in targets):
            return False
        return self._save_surface_nav(targets, self._surface_nav["activeId"])

    @Slot(str, result=bool)
    def removeSurfaceTarget(self, target_id):
        targets = [row for row in self._surface_nav["targets"] if row["id"] != target_id]
        if len(targets) == len(self._surface_nav["targets"]):
            return False
        active_id = "" if self._surface_nav["activeId"] == target_id else self._surface_nav["activeId"]
        return self._save_surface_nav(targets, active_id)

    @Slot(result=bool)
    def saveCurrentSurfacePosition(self):
        position = self._surface_nav.get("position") or {}
        if not position:
            self._set_surface_nav_message("nav.error_position")
            return False
        return self.saveSurfaceTarget(
            "", str(position["latitude"]), str(position["longitude"]),
        )

    def _poll_surface_nav(self):
        status = read_json(journal_dir() / "Status.json", {})
        status = status if isinstance(status, dict) else {}
        position = {}
        try:
            latitude = parse_coordinate(status.get("Latitude"), 90)
            longitude = parse_coordinate(status.get("Longitude"), 180)
            body = str(status.get("BodyName") or "").strip()
            if body:
                position = {
                    "latitude": latitude, "longitude": longitude, "body": body,
                    "system": str(self._state.get("system") or ""),
                }
        except ValueError:
            pass
        target = next((row for row in self._surface_nav["targets"]
                       if row["id"] == self._surface_nav["activeId"]), None)
        current_system = str(self._state.get("system") or "").strip()
        current_position = self._state.get("currentPosition")
        all_farm_sites, farm_materials = material_farm_rows(
            self._farm_catalog, current_position, current_system,
            self._farm_edits, include_deleted=True,
        )
        farm_sites = [row for row in all_farm_sites if not row["deleted"]]
        deleted_farm_sites = [row for row in all_farm_sites if row["deleted"]]
        catalog_materials = self._farm_catalog.get("materials", {})
        all_farm_materials = sorted(
            ({"key": key, "name": str(value.get("name") or key)}
             for key, value in catalog_materials.items()
             if isinstance(value, dict)),
            key=lambda row: row["name"].casefold(),
        ) if isinstance(catalog_materials, dict) else []
        origin_known = any(row["distanceLy"] is not None for row in farm_sites)
        guidance = {}
        if target and position:
            if (target["system"].casefold() != position["system"].casefold()
                    or target["body"].casefold() != position["body"].casefold()):
                guidance = {"wrongBody": True}
            else:
                guidance = surface_guidance(status, target)
        if (position != self._surface_nav["position"]
                or guidance != self._surface_nav["guidance"]
                or farm_sites != self._surface_nav["farmSites"]
                or deleted_farm_sites != self._surface_nav["farmDeletedSites"]
                or current_system != self._surface_nav["originSystem"]
                or origin_known != self._surface_nav["originKnown"]):
            self._surface_nav = {
                **self._surface_nav, "position": position, "guidance": guidance,
                "farmSites": farm_sites, "farmMaterials": farm_materials,
                "farmAllMaterials": all_farm_materials,
                "farmDeletedSites": deleted_farm_sites,
                "originSystem": current_system, "originKnown": origin_known,
            }
            self.surfaceNavChanged.emit()
