"""Records the flown GPS track and exports it to GPX 1.1, KML 2.2, or CSV."""
from __future__ import annotations

import csv
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from core.telemetry_state import TelemetryState


@dataclass
class TrackPoint:
    lat: float
    lon: float
    alt: Optional[float]
    timestamp: float


class TrackRecorder:
    def __init__(self) -> None:
        self._points: List[TrackPoint] = []

    def clear(self) -> None:
        self._points.clear()

    def add_point(self, state: TelemetryState) -> None:
        if not state.has_gps_fix():
            return
        self._points.append(TrackPoint(state.lat, state.lon, state.alt, state.timestamp))

    def __len__(self) -> int:
        return len(self._points)

    def export_gpx(self, path: str) -> None:
        gpx = ET.Element("gpx", {
            "version": "1.1",
            "creator": "ELRS Ground Station",
            "xmlns": "http://www.topografix.com/GPX/1/1",
        })
        trk = ET.SubElement(gpx, "trk")
        ET.SubElement(trk, "name").text = "ELRS Flight Path"
        trkseg = ET.SubElement(trk, "trkseg")

        for p in self._points:
            trkpt = ET.SubElement(trkseg, "trkpt", {"lat": f"{p.lat:.7f}", "lon": f"{p.lon:.7f}"})
            if p.alt is not None:
                ET.SubElement(trkpt, "ele").text = f"{p.alt:.1f}"
            ET.SubElement(trkpt, "time").text = self._iso_time(p.timestamp)

        self._write_pretty(gpx, path)

    def export_kml(self, path: str) -> None:
        kml = ET.Element("kml", {"xmlns": "http://www.opengis.net/kml/2.2"})
        document = ET.SubElement(kml, "Document")
        ET.SubElement(document, "name").text = "ELRS Flight Path"

        style = ET.SubElement(document, "Style", {"id": "trackStyle"})
        line_style = ET.SubElement(style, "LineStyle")
        ET.SubElement(line_style, "color").text = "ff0080ff"
        ET.SubElement(line_style, "width").text = "3"

        placemark = ET.SubElement(document, "Placemark")
        ET.SubElement(placemark, "name").text = "Flight Track"
        ET.SubElement(placemark, "styleUrl").text = "#trackStyle"
        linestring = ET.SubElement(placemark, "LineString")
        ET.SubElement(linestring, "altitudeMode").text = "relativeToGround"
        ET.SubElement(linestring, "tessellate").text = "1"

        coords = " ".join(
            f"{p.lon:.7f},{p.lat:.7f},{(p.alt or 0.0):.1f}" for p in self._points
        )
        ET.SubElement(linestring, "coordinates").text = coords

        self._write_pretty(kml, path)

    def export_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "lat", "lon", "alt"])
            for p in self._points:
                writer.writerow([
                    self._iso_time(p.timestamp),
                    f"{p.lat:.7f}",
                    f"{p.lon:.7f}",
                    f"{p.alt:.1f}" if p.alt is not None else "",
                ])

    @staticmethod
    def _iso_time(ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _write_pretty(root: ET.Element, path: str) -> None:
        raw = ET.tostring(root, encoding="utf-8")
        pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")
        Path(path).write_bytes(pretty)
