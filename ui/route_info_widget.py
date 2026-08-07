"""Draggable map overlay showing the planned route's waypoint count and
total distance. Hidden automatically when there's no route (or a single
point, for which "distance" is meaningless).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout

from core import i18n
from ui.draggable_overlay import DraggableOverlay

PANEL_BG = "rgba(18, 22, 28, 235)"
BORDER = "#0d1117"


def format_distance(meters: float) -> str:
    if meters >= 1000:
        return f"{meters / 1000:.2f} km"
    return f"{meters:.0f} m"


class RouteInfoWidget(DraggableOverlay):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"RouteInfoWidget {{ background-color: {PANEL_BG}; "
            f"border: 1px solid {BORDER}; border-radius: 10px; }}"
        )
        self.setFixedWidth(180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self._count_label = QLabel()
        self._count_label.setStyleSheet("color: #c7cfda; font-size: 10px; background: transparent;")
        self._dist_label = QLabel()
        self._dist_label.setStyleSheet("color: #ffffff; font-weight: 600; font-size: 13px; background: transparent;")

        layout.addWidget(self._count_label)
        layout.addWidget(self._dist_label)

        self._waypoint_count = 0
        self._total_distance = 0.0
        self.retranslate()

    def update_info(self, waypoint_count: int, total_distance_m: float) -> None:
        self._waypoint_count = waypoint_count
        self._total_distance = total_distance_m
        self.retranslate()

    def retranslate(self) -> None:
        self._count_label.setText(f"{i18n.tr('routeinfo_waypoints')}: {self._waypoint_count}")
        self._dist_label.setText(f"{i18n.tr('routeinfo_total_distance')}: {format_distance(self._total_distance)}")
