"""Planned route (waypoints drawn on the map or imported) - independent of
the live telemetry track recorded by TrackRecorder.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class Waypoint:
    lat: float
    lon: float
    alt: Optional[float] = None
    name: str = ""


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
