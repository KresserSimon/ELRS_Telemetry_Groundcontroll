"""QWebChannel bridge object: receives route-drawing click events from the
Leaflet page's JavaScript and re-emits them as Qt signals for MainWindow.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class RouteBridge(QObject):
    waypoint_added = pyqtSignal(float, float)
    waypoint_removed = pyqtSignal(int)

    @pyqtSlot(float, float)
    def waypoint_clicked(self, lat: float, lon: float) -> None:
        self.waypoint_added.emit(lat, lon)

    @pyqtSlot(int)
    def waypoint_marker_clicked(self, index: int) -> None:
        self.waypoint_removed.emit(index)
