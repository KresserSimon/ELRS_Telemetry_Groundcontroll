"""Route (waypoint list) import from GPX, iNav .mission, generic XML, and CSV.

import_route_file() is the single entry point the UI calls; it picks a parser
by file extension and falls back to content-sniffing for ambiguous/unknown
extensions so "Route importieren..." can offer one open-file dialog instead
of one menu item per format.
"""
from __future__ import annotations

import csv
import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from core.route import Waypoint

_LAT_KEYS = ("lat", "latitude", "y")
_LON_KEYS = ("lon", "lng", "long", "longitude", "x")
_ALT_KEYS = ("alt", "altitude", "ele", "elevation", "z")
_NAME_KEYS = ("name", "label", "wp", "waypoint", "title")


def import_route_file(path: str) -> List[Waypoint]:
    ext = os.path.splitext(path)[1].lower()

    if ext == ".csv":
        return import_csv(path)
    if ext == ".mission":
        return import_inav_mission(path)
    if ext == ".gpx":
        return import_gpx(path)

    # .xml or unrecognized extension: sniff the content.
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"Datei ist kein gueltiges XML: {exc}") from exc

    if _local_tag(root.tag) == "gpx":
        return import_gpx(path)
    if root.find(".//missionitem") is not None or _local_tag(root.tag) in ("mission", "missions"):
        return import_inav_mission(path)
    return import_generic_xml(path)


def _local_tag(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _first(mapping: Dict[str, str], keys) -> Optional[str]:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _to_waypoint(lat_str, lon_str, alt_str=None, name: str = "") -> Optional[Waypoint]:
    try:
        lat = float(lat_str)
        lon = float(lon_str)
    except (TypeError, ValueError):
        return None
    if lat == 0.0 and lon == 0.0:
        return None
    alt = None
    if alt_str not in (None, ""):
        try:
            alt = float(alt_str)
        except (TypeError, ValueError):
            alt = None
    return Waypoint(lat, lon, alt, (name or "").strip())


# ------------------------------------------------------------------- GPX

def import_gpx(path: str) -> List[Waypoint]:
    root = ET.parse(path).getroot()
    ns = root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else ""

    def tag(name: str) -> str:
        return f"{{{ns}}}{name}" if ns else name

    source = root.findall(f".//{tag('rte')}/{tag('rtept')}")
    if not source:
        source = root.findall(f".//{tag('trk')}/{tag('trkseg')}/{tag('trkpt')}")
    if not source:
        source = root.findall(tag("wpt"))

    waypoints: List[Waypoint] = []
    for pt in source:
        ele_el = pt.find(tag("ele"))
        name_el = pt.find(tag("name"))
        wp = _to_waypoint(
            pt.get("lat"),
            pt.get("lon"),
            ele_el.text if ele_el is not None else None,
            name_el.text if name_el is not None and name_el.text else "",
        )
        if wp:
            waypoints.append(wp)

    if not waypoints:
        raise ValueError("Keine Wegpunkte in der GPX-Datei gefunden.")
    return waypoints


# ------------------------------------------------------------ iNav .mission
#
# "MW XML" format used by mwp / iNav Configurator / ezgui: a <mission> (or,
# since iNav 4.0, a <missions> wrapper with several <mission> children) of
# <missionitem no=".." action="WAYPOINT" lat=".." lon=".." alt=".." .../>
# elements. lat/lon are plain decimal degrees, alt is integer metres.

def import_inav_mission(path: str) -> List[Waypoint]:
    root = ET.parse(path).getroot()
    items = root.findall(".//missionitem")

    def item_no(el) -> float:
        try:
            return float(el.get("no", "0"))
        except ValueError:
            return 0.0

    items.sort(key=item_no)

    waypoints: List[Waypoint] = []
    for item in items:
        wp = _to_waypoint(item.get("lat"), item.get("lon"), item.get("alt"))
        if wp:
            waypoints.append(wp)

    if not waypoints:
        raise ValueError("Keine Wegpunkte in der .mission-Datei gefunden.")
    return waypoints


# --------------------------------------------------------------- generic XML
#
# Best-effort fallback for arbitrary XML waypoint dumps: scans every element
# for lat/lon either as attributes or as same-level child element text.

def import_generic_xml(path: str) -> List[Waypoint]:
    root = ET.parse(path).getroot()
    waypoints: List[Waypoint] = []

    for elem in root.iter():
        attrs = {_local_tag(k).lower(): v for k, v in elem.attrib.items()}
        lat = _first(attrs, _LAT_KEYS)
        lon = _first(attrs, _LON_KEYS)
        if lat is not None and lon is not None:
            wp = _to_waypoint(lat, lon, _first(attrs, _ALT_KEYS), _first(attrs, _NAME_KEYS) or "")
            if wp:
                waypoints.append(wp)
            continue

        children = {_local_tag(c.tag).lower(): (c.text or "").strip() for c in elem}
        lat = _first(children, _LAT_KEYS)
        lon = _first(children, _LON_KEYS)
        if lat is not None and lon is not None:
            wp = _to_waypoint(lat, lon, _first(children, _ALT_KEYS), _first(children, _NAME_KEYS) or "")
            if wp:
                waypoints.append(wp)

    if not waypoints:
        raise ValueError("Keine erkennbaren Lat/Lon-Wegpunkte in der XML-Datei gefunden.")
    return waypoints


# -------------------------------------------------------------------- CSV

def import_csv(path: str) -> List[Waypoint]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("Leere CSV-Datei.")

        lowered = {name: name.strip().lower() for name in reader.fieldnames}
        lat_col = _column_for(lowered, _LAT_KEYS)
        lon_col = _column_for(lowered, _LON_KEYS)
        if lat_col is None or lon_col is None:
            raise ValueError("Keine lat/lon-Spalten in der CSV-Datei gefunden.")
        alt_col = _column_for(lowered, _ALT_KEYS)
        name_col = _column_for(lowered, _NAME_KEYS)

        waypoints: List[Waypoint] = []
        for row in reader:
            wp = _to_waypoint(
                row.get(lat_col),
                row.get(lon_col),
                row.get(alt_col) if alt_col else None,
                row.get(name_col) if name_col else "",
            )
            if wp:
                waypoints.append(wp)

    if not waypoints:
        raise ValueError("Keine gueltigen Wegpunkte in der CSV-Datei gefunden.")
    return waypoints


def _column_for(lowered: Dict[str, str], candidates) -> Optional[str]:
    for original, lower in lowered.items():
        if lower in candidates:
            return original
    return None
