"""Elevation-profile dialog: terrain vs. planned flight altitude along the
current route, fetched via core.terrain (Open-Elevation, needs internet -
same requirement as the existing "Gelände prüfen" button in the waypoint
editor). Drawn with a small custom QPainter chart, not a plotting library -
consistent with how the rest of the app's visuals (horizon gauge, dashboard,
icons) are all hand-drawn to keep the PyInstaller build lean. If the lookup
fails (no internet, API down), the dialog still opens - it just shows the
error text instead of the chart, since long-range flying often happens
without connectivity and this feature must degrade gracefully, not crash.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from core import i18n
from core.route import RouteManager
from core.terrain import TerrainLookupError, route_elevation_profile
from ui.dashboard import ACCENT, CAPTION_COLOR, PANEL_BG

TERRAIN_LINE_COLOR = QColor("#a97c50")
TERRAIN_FILL_COLOR = QColor(107, 74, 43, 140)
FLIGHT_COLOR = QColor(ACCENT)
GRID_COLOR = QColor(255, 255, 255, 30)
MARGIN_LEFT = 58
MARGIN_BOTTOM = 26
MARGIN_TOP = 12
MARGIN_RIGHT = 14


class ElevationChartWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(420, 260)
        self.setStyleSheet(f"background-color: {PANEL_BG};")
        self._distances: List[float] = []
        self._terrain: List[float] = []
        self._predicted: List[float] = []

    def set_data(self, distances: List[float], terrain: List[float], predicted: List[float]) -> None:
        self._distances = distances
        self._terrain = terrain
        self._predicted = predicted
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(PANEL_BG))

        if len(self._distances) < 2:
            painter.setPen(QColor(CAPTION_COLOR))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, i18n.tr("elevation_profile_no_data"))
            painter.end()
            return

        plot_rect = QRectF(
            MARGIN_LEFT, MARGIN_TOP,
            self.width() - MARGIN_LEFT - MARGIN_RIGHT,
            self.height() - MARGIN_TOP - MARGIN_BOTTOM,
        )

        all_y = self._terrain + self._predicted
        y_min, y_max = min(all_y), max(all_y)
        if y_max - y_min < 1.0:
            y_min, y_max = y_min - 1.0, y_max + 1.0
        y_pad = (y_max - y_min) * 0.1
        y_min -= y_pad
        y_max += y_pad
        x_max = max(self._distances) or 1.0

        def to_point(x_m: float, y_m: float) -> QPointF:
            px = plot_rect.left() + (x_m / x_max) * plot_rect.width()
            py = plot_rect.bottom() - ((y_m - y_min) / (y_max - y_min)) * plot_rect.height()
            return QPointF(px, py)

        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        for i in range(5):
            frac = i / 4
            y_val = y_min + frac * (y_max - y_min)
            py = plot_rect.bottom() - frac * plot_rect.height()
            painter.setPen(QPen(GRID_COLOR, 1))
            painter.drawLine(QPointF(plot_rect.left(), py), QPointF(plot_rect.right(), py))
            painter.setPen(QColor(CAPTION_COLOR))
            painter.drawText(
                QRectF(0, py - 8, MARGIN_LEFT - 6, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{y_val:.0f} m",
            )

        terrain_fill = QPainterPath()
        terrain_fill.moveTo(to_point(self._distances[0], y_min))
        for x_m, y_m in zip(self._distances, self._terrain):
            terrain_fill.lineTo(to_point(x_m, y_m))
        terrain_fill.lineTo(to_point(self._distances[-1], y_min))
        terrain_fill.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(TERRAIN_FILL_COLOR)
        painter.drawPath(terrain_fill)

        terrain_line = QPainterPath()
        terrain_line.moveTo(to_point(self._distances[0], self._terrain[0]))
        for x_m, y_m in zip(self._distances[1:], self._terrain[1:]):
            terrain_line.lineTo(to_point(x_m, y_m))
        painter.setPen(QPen(TERRAIN_LINE_COLOR, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(terrain_line)

        flight_line = QPainterPath()
        flight_line.moveTo(to_point(self._distances[0], self._predicted[0]))
        for x_m, y_m in zip(self._distances[1:], self._predicted[1:]):
            flight_line.lineTo(to_point(x_m, y_m))
        painter.setPen(QPen(FLIGHT_COLOR, 2.5))
        painter.drawPath(flight_line)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(FLIGHT_COLOR)
        for x_m, y_m in zip(self._distances, self._predicted):
            painter.drawEllipse(to_point(x_m, y_m), 3, 3)

        distance_text = f"{x_max / 1000:.2f} km" if x_max >= 1000 else f"{x_max:.0f} m"
        painter.setPen(QColor(CAPTION_COLOR))
        painter.drawText(
            QRectF(plot_rect.left(), self.height() - MARGIN_BOTTOM + 4, plot_rect.width(), MARGIN_BOTTOM - 4),
            Qt.AlignmentFlag.AlignCenter,
            f"{i18n.tr('elevation_profile_distance_label')}: {distance_text}",
        )
        painter.end()


class ElevationProfileDialog(QDialog):
    def __init__(
        self,
        route_manager: RouteManager,
        home: Optional[Tuple[float, float]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("elevation_profile_title"))
        self.resize(580, 400)

        self._chart = ElevationChartWidget()
        self._status_label = QLabel()
        self._status_label.setStyleSheet(f"color: {CAPTION_COLOR}; font-size: 11px;")
        self._status_label.setWordWrap(True)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(self._chart, 1)
        layout.addWidget(self._status_label)
        layout.addWidget(button_box)

        self._load(route_manager, home)

    def _load(self, route_manager: RouteManager, home: Optional[Tuple[float, float]]) -> None:
        waypoints = route_manager.waypoints()
        distances = [0.0]
        for segment in route_manager.segment_distances():
            distances.append(distances[-1] + segment)

        home_lat, home_lon = home if home is not None else (None, None)
        try:
            terrain, predicted = route_elevation_profile(waypoints, home_lat, home_lon)
        except TerrainLookupError as exc:
            self._status_label.setText(str(exc))
            return

        self._chart.set_data(distances, terrain, predicted)
        self._status_label.setText(i18n.tr("elevation_profile_hint"))
