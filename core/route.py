"""Planned route (waypoints drawn on the map or imported) - independent of
the live telemetry track recorded by TrackRecorder.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from core import i18n
from core.geo import haversine_distance_m


@dataclass
class Waypoint:
    lat: float
    lon: float
    alt: Optional[float] = None
    name: str = ""

    # INAV mission fields (export/inav_mission.py). Default to a plain
    # WAYPOINT with no extra parameters so every existing GPX/CSV/XML
    # import path - none of which know about these - keeps working unchanged.
    action: str = "WAYPOINT"
    speed: float = 0.0
    p1: int = 0
    p2: int = 0
    p3: int = 0


class RouteManager(QObject):
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._waypoints: List[Waypoint] = []

    def waypoints(self) -> List[Waypoint]:
        return list(self._waypoints)

    def __len__(self) -> int:
        return len(self._waypoints)

    def add(self, lat: float, lon: float, alt: Optional[float] = None, name: str = "") -> None:
        self._waypoints.append(Waypoint(lat, lon, alt, name))
        self.changed.emit()

    def add_typed(self, lat: float, lon: float, kind: str) -> None:
        """Add a point picked from the map's right-click "Wegpunkt / Startpunkt
        / Endpunkt" menu, feeding straight into this same list - the point
        shows up as just another editable row in RouteEditorOverlay.

        'start' inserts at the front of the list (defines where the route
        begins); 'end' appends with an RTH action so a route planned this way
        already satisfies validate_mission()'s "must end in RTH/HOLD/LAND"
        check without extra manual editing.
        """
        if kind == "start":
            self._waypoints.insert(0, Waypoint(lat, lon, name=i18n.tr("mapctx_start")))
        elif kind == "end":
            self._waypoints.append(Waypoint(lat, lon, name=i18n.tr("mapctx_end"), action="RTH"))
        else:
            self._waypoints.append(Waypoint(lat, lon))
        self.changed.emit()

    def remove_at(self, index: int) -> None:
        if 0 <= index < len(self._waypoints):
            del self._waypoints[index]
            self.changed.emit()

    def remove_last(self) -> None:
        if self._waypoints:
            self._waypoints.pop()
            self.changed.emit()

    def clear(self) -> None:
        if self._waypoints:
            self._waypoints.clear()
            self.changed.emit()

    def set_all(self, waypoints: List[Waypoint]) -> None:
        self._waypoints = list(waypoints)
        self.changed.emit()

    def remove_many(self, indices: List[int]) -> None:
        for index in sorted(set(indices), reverse=True):
            if 0 <= index < len(self._waypoints):
                del self._waypoints[index]
        self.changed.emit()

    def update_position(self, index: int, lat: float, lon: float) -> None:
        if 0 <= index < len(self._waypoints):
            self._waypoints[index].lat = lat
            self._waypoints[index].lon = lon
            self.changed.emit()

    def reorder(self, from_index: int, to_index: int) -> None:
        """Move the waypoint at from_index so it ends up at to_index,
        shifting everything between - the semantics QTableWidget's
        InternalMove drag-and-drop expects, and the same "insert" meaning
        list.insert() uses (to_index is where the item lands *after* the
        move, not a raw list-splice offset)."""
        if not (0 <= from_index < len(self._waypoints)) or not (0 <= to_index < len(self._waypoints)):
            return
        if from_index == to_index:
            return
        wp = self._waypoints.pop(from_index)
        self._waypoints.insert(to_index, wp)
        self.changed.emit()

    def insert_between(self, index: int) -> None:
        """Insert a new waypoint at the midpoint of the segment starting at
        index (between waypoints[index] and waypoints[index + 1])."""
        if not (0 <= index < len(self._waypoints) - 1):
            return
        a, b = self._waypoints[index], self._waypoints[index + 1]
        mid_lat = (a.lat + b.lat) / 2
        mid_lon = (a.lon + b.lon) / 2
        mid_alt = None
        if a.alt is not None and b.alt is not None:
            mid_alt = (a.alt + b.alt) / 2
        self._waypoints.insert(index + 1, Waypoint(mid_lat, mid_lon, mid_alt))
        self.changed.emit()

    def reverse(self) -> None:
        if len(self._waypoints) > 1:
            self._waypoints.reverse()
            self.changed.emit()

    def set_altitude_many(self, indices: List[int], alt: float) -> None:
        for index in indices:
            if 0 <= index < len(self._waypoints):
                self._waypoints[index].alt = alt
        if indices:
            self.changed.emit()

    def set_speed_many(self, indices: List[int], speed: float) -> None:
        for index in indices:
            if 0 <= index < len(self._waypoints):
                self._waypoints[index].speed = speed
        if indices:
            self.changed.emit()

    def segment_distances(self) -> List[float]:
        """Great-circle distance (metres) between each consecutive waypoint pair."""
        return [
            haversine_distance_m(a.lat, a.lon, b.lat, b.lon)
            for a, b in zip(self._waypoints, self._waypoints[1:])
        ]

    def total_distance(self) -> float:
        return sum(self.segment_distances())
