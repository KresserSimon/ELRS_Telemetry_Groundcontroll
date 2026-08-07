"""No-fly-zone (NFZ) overlay data: polygons or circles marking restricted
areas on the map. Purely a display aid, imported from a file (GeoJSON/CSV) -
not fetched from any live airspace API.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class NoFlyZone:
    name: str
    kind: str  # "polygon" | "circle"
    points: List[Tuple[float, float]] = field(default_factory=list)  # [(lat, lon), ...], polygon
    center: Optional[Tuple[float, float]] = None  # (lat, lon), circle
    radius_m: Optional[float] = None  # circle


class NoFlyZoneManager(QObject):
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._zones: List[NoFlyZone] = []

    def zones(self) -> List[NoFlyZone]:
        return list(self._zones)

    def __len__(self) -> int:
        return len(self._zones)

    def set_all(self, zones: List[NoFlyZone]) -> None:
        self._zones = list(zones)
        self.changed.emit()

    def clear(self) -> None:
        if self._zones:
            self._zones.clear()
            self.changed.emit()
