"""Import for Austro Control's "UAS Zones" geo-awareness export (the JSON
file downloadable from Austro Control Dronespace) into NoFlyZone overlays -
Austria's airports/heliports, restricted/prohibited areas, CTRs and model-
flying areas as polygons with an authorization/restriction level.

Distinct from export/nfz_import.py's plain-GeoJSON import: this is a bare
JSON array of zone objects, each carrying its own `geometry` list (only
each entry's `horizontalProjection` is an actual GeoJSON polygon - altitude
limits and vertical reference live alongside it, but NoFlyZone has no
altitude dimension to put them in) and a `restriction` level rather than
being uniformly "no-fly". Reuses export/nfz_import.py's
polygon_rings_from_geometry() for the horizontalProjection parsing, since
that's the same GeoJSON Polygon/MultiPolygon shape.

NO_RESTRICTION zones (Modellfluggebiete: "expect more drone traffic here",
not an actual restriction) are skipped - including them as an "NFZ" would
misrepresent an informational notice as a place you can't fly. The other
three levels are real constraints of different strictness, so the label
prefix says which one - REQ_AUTHORISATION is legal to fly in with
clearance, not an outright prohibition like PROHIBITED is.
"""
from __future__ import annotations

import json
from typing import List

from core.nfz import NoFlyZone
from core.resources import resource_path
from export.nfz_import import polygon_rings_from_geometry

BUNDLED_AUSTRIA_ZONES_PARTS = ("assets", "nfz", "austria_uas_zones.json")

_RESTRICTION_LABELS = {
    "PROHIBITED": "Flugverbot",
    "REQ_AUTHORISATION": "Genehmigungspflichtig",
    "CONDITIONAL": "Flugplatzzone",
}

_EXCLUDED_RESTRICTIONS = frozenset({"NO_RESTRICTION"})


def is_acg_zone_format(data) -> bool:
    """True if `data` looks like an Austro Control UAS-zones export (a bare
    JSON array of zone objects) rather than a plain GeoJSON
    FeatureCollection/Feature - used by export/nfz_import.py's
    import_nfz_file() to auto-detect which parser a .json file needs."""
    return (
        isinstance(data, list)
        and bool(data)
        and isinstance(data[0], dict)
        and "restriction" in data[0]
        and "geometry" in data[0]
    )


def _zone_label(zone: dict) -> str:
    restriction = str(zone.get("restriction") or "").upper()
    prefix = _RESTRICTION_LABELS.get(restriction, restriction or "?")
    name = str(zone.get("message") or zone.get("name") or zone.get("identifier") or "Zone")
    return f"{prefix}: {name}"


def zones_from_acg_data(data: list) -> List[NoFlyZone]:
    zones: List[NoFlyZone] = []
    for zone in data:
        if not isinstance(zone, dict):
            continue
        restriction = str(zone.get("restriction") or "").upper()
        if restriction in _EXCLUDED_RESTRICTIONS:
            continue

        label = _zone_label(zone)
        for geometry_entry in zone.get("geometry") or []:
            horizontal = (geometry_entry or {}).get("horizontalProjection") or {}
            for points in polygon_rings_from_geometry(horizontal):
                zones.append(NoFlyZone(name=label, kind="polygon", points=points))

    return zones


def import_acg_zone_file(path: str) -> List[NoFlyZone]:
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    if not is_acg_zone_format(data):
        raise ValueError("Keine gültige Austro-Control-Zonendatei (erwartet eine JSON-Liste von Zonen).")
    zones = zones_from_acg_data(data)
    if not zones:
        raise ValueError("Keine Zonen in der Datei gefunden.")
    return zones


def load_bundled_austria_zones() -> List[NoFlyZone]:
    """The Austria-wide zone set bundled with the app (assets/nfz/) - a
    one-shot snapshot from Austro Control Dronespace, not live-fetched."""
    path = resource_path(*BUNDLED_AUSTRIA_ZONES_PARTS)
    return import_acg_zone_file(str(path))
