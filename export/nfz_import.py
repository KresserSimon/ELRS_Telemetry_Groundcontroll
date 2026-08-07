"""No-fly-zone import from GeoJSON (polygons/multi-polygons) or CSV
(circular zones: name, lat, lon, radius).
"""
from __future__ import annotations

import csv
import json
import os
from typing import Dict, List, Optional

from core.nfz import NoFlyZone

_LAT_KEYS = ("lat", "latitude", "y")
_LON_KEYS = ("lon", "lng", "long", "longitude", "x")
_RADIUS_M_KEYS = ("radius_m", "radiusm", "radius")
_RADIUS_KM_KEYS = ("radius_km", "radiuskm")
_NAME_KEYS = ("name", "label", "zone", "title")

DEFAULT_RADIUS_M = 500.0


def import_nfz_file(path: str) -> List[NoFlyZone]:
    if os.path.splitext(path)[1].lower() == ".csv":
        return import_nfz_csv(path)
    return import_nfz_geojson(path)


def import_nfz_geojson(path: str) -> List[NoFlyZone]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", []) if isinstance(data, dict) else []
    if not features and isinstance(data, dict) and data.get("type") == "Feature":
        features = [data]

    zones: List[NoFlyZone] = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        props = feature.get("properties") or {}
        gtype = geometry.get("type")
        coords = geometry.get("coordinates")
        if coords is None:
            continue

        if gtype == "Polygon":
            rings = [coords[0]]
        elif gtype == "MultiPolygon":
            rings = [poly[0] for poly in coords]
        else:
            continue

        for ring in rings:
            name = str(props.get("name") or props.get("Name") or f"Zone {len(zones) + 1}")
            points = [(pt[1], pt[0]) for pt in ring]  # GeoJSON coordinates are [lon, lat]
            zones.append(NoFlyZone(name=name, kind="polygon", points=points))

    if not zones:
        raise ValueError("Keine Polygon-Zonen in der GeoJSON-Datei gefunden.")
    return zones


def import_nfz_csv(path: str) -> List[NoFlyZone]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("Leere CSV-Datei.")

        lowered = {name: name.strip().lower() for name in reader.fieldnames}
        lat_col = _column_for(lowered, _LAT_KEYS)
        lon_col = _column_for(lowered, _LON_KEYS)
        if lat_col is None or lon_col is None:
            raise ValueError("Keine lat/lon-Spalten in der CSV-Datei gefunden.")
        radius_m_col = _column_for(lowered, _RADIUS_M_KEYS)
        radius_km_col = _column_for(lowered, _RADIUS_KM_KEYS)
        name_col = _column_for(lowered, _NAME_KEYS)

        zones: List[NoFlyZone] = []
        for row in reader:
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
            except (TypeError, ValueError, KeyError):
                continue

            radius_m = None
            if radius_m_col:
                try:
                    radius_m = float(row[radius_m_col])
                except (TypeError, ValueError):
                    radius_m = None
            elif radius_km_col:
                try:
                    radius_m = float(row[radius_km_col]) * 1000.0
                except (TypeError, ValueError):
                    radius_m = None
            if radius_m is None:
                radius_m = DEFAULT_RADIUS_M

            name = (row.get(name_col) or "").strip() if name_col else ""
            zones.append(NoFlyZone(name=name or f"Zone {len(zones) + 1}", kind="circle",
                                    center=(lat, lon), radius_m=radius_m))

    if not zones:
        raise ValueError("Keine gueltigen Zonen in der CSV-Datei gefunden.")
    return zones


def _column_for(lowered: Dict[str, str], candidates) -> Optional[str]:
    for original, lower in lowered.items():
        if lower in candidates:
            return original
    return None
