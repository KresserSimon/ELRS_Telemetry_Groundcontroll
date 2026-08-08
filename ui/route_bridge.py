"""QWebChannel bridge object: receives route-drawing and map-context-menu
click events from the Leaflet page's JavaScript and re-emits them as Qt
signals for MainWindow.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class RouteBridge(QObject):
    waypoint_added = pyqtSignal(float, float)
    waypoint_removed = pyqtSignal(int)
    waypoint_added_typed = pyqtSignal(float, float, str)
    home_position_picked = pyqtSignal(float, float)
    view_action_triggered = pyqtSignal(str)

    @pyqtSlot(float, float)
    def waypoint_clicked(self, lat: float, lon: float) -> None:
        self.waypoint_added.emit(lat, lon)

    @pyqtSlot(int)
    def waypoint_marker_clicked(self, index: int) -> None:
        self.waypoint_removed.emit(index)

    @pyqtSlot(float, float, str)
    def waypoint_clicked_typed(self, lat: float, lon: float, kind: str) -> None:
        self.waypoint_added_typed.emit(lat, lon, kind)

    @pyqtSlot(float, float)
    def pick_home_position(self, lat: float, lon: float) -> None:
        self.home_position_picked.emit(lat, lon)

    @pyqtSlot(str)
    def view_action(self, action: str) -> None:
        self.view_action_triggered.emit(action)
