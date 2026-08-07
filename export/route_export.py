"""Route (planned waypoint list) export to GPX or CSV - the counterpart to
route_import.py. Independent of track_export.py, which exports the actually
*flown* GPS track rather than the planned route.
"""
from __future__ import annotations

import csv
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

from core.route import Waypoint


def export_route_gpx(waypoints: List[Waypoint], path: str) -> None:
    gpx = ET.Element("gpx", {
        "version": "1.1",
        "creator": "ELRS Ground Station",
        "xmlns": "http://www.topografix.com/GPX/1/1",
    })
    rte = ET.SubElement(gpx, "rte")
    ET.SubElement(rte, "name").text = "ELRS Ground Station Route"

    for i, wp in enumerate(waypoints):
        rtept = ET.SubElement(rte, "rtept", {"lat": f"{wp.lat:.7f}", "lon": f"{wp.lon:.7f}"})
        if wp.alt is not None:
            ET.SubElement(rtept, "ele").text = f"{wp.alt:.1f}"
        ET.SubElement(rtept, "name").text = wp.name or f"WP{i + 1}"

    raw = ET.tostring(gpx, encoding="utf-8")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")
    Path(path).write_bytes(pretty)


def export_route_csv(waypoints: List[Waypoint], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "lat", "lon", "alt"])
        for i, wp in enumerate(waypoints):
            writer.writerow([
                wp.name or f"WP{i + 1}",
                f"{wp.lat:.7f}",
                f"{wp.lon:.7f}",
                f"{wp.alt:.1f}" if wp.alt is not None else "",
            ])
