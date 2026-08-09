"""Live altitude-over-time chart, drawn as a small draggable/resizable map
overlay that fills in as telemetry arrives during a flight (real or demo) -
the "how high have I actually been" companion to the static, distance-based
elevation profile in ui/elevation_profile_dialog.py (which shows terrain
vs. a *planned* route, not what was actually flown). Native QPainter chart,
no plotting library, matching the rest of the app's hand-drawn visuals.
"""
from __future__ import annotations

from typing import List, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core import i18n
from ui.dashboard import ACCENT, CAPTION_COLOR, PANEL_BG
from ui.draggable_overlay import DraggableOverlay

LINE_COLOR = QColor(ACCENT)
FILL_COLOR = QColor(61, 219, 201, 60)
GRID_COLOR = QColor(255, 255, 255, 30)
MARGIN_LEFT = 38
MARGIN_BOTTOM = 28
MARGIN_TOP = 16
MARGIN_RIGHT = 6

# X-axis time unit: display divisor (seconds per unit) + i18n key for the
# unit suffix shown in the axis title and tick labels.
TIME_UNITS = {"s": (1, "altitude_track_unit_s"), "min": (60, "altitude_track_unit_min"), "h": (3600, "altitude_track_unit_h")}
DEFAULT_TIME_UNIT = "s"

# Keeps memory bounded across a very long flight - once over the cap, every
# other sample is dropped, halving resolution but keeping the full time
# span visible instead of scrolling the earliest part away.
MAX_SAMPLES = 1200


class AltitudeChartWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {PANEL_BG};")
        self._samples: List[Tuple[float, float]] = []  # (elapsed_s, alt_m)
        self._time_unit = DEFAULT_TIME_UNIT

    def add_sample(self, elapsed_s: float, alt_m: float) -> None:
        self._samples.append((elapsed_s, alt_m))
        if len(self._samples) > MAX_SAMPLES:
            self._samples = self._samples[::2]
        self.update()

    def set_time_unit(self, unit: str) -> None:
        if unit not in TIME_UNITS:
            return
        self._time_unit = unit
        self.update()

    def clear(self) -> None:
        self._samples = []
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(PANEL_BG))

        if len(self._samples) < 2:
            painter.setPen(QColor(CAPTION_COLOR))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, i18n.tr("altitude_track_no_data"))
            painter.end()
            return

        plot_rect = QRectF(
            MARGIN_LEFT, MARGIN_TOP,
            self.width() - MARGIN_LEFT - MARGIN_RIGHT,
            self.height() - MARGIN_TOP - MARGIN_BOTTOM,
        )

        times = [s[0] for s in self._samples]
        alts = [s[1] for s in self._samples]
        t_min, t_max = times[0], times[-1]
        if t_max - t_min < 1.0:
            t_max = t_min + 1.0
        # The Y axis always starts at 0m rather than the lowest sample, so
        # altitude is read as "height above ground/home", not zoomed into a
        # narrow, misleadingly-flat-looking band around whatever altitudes
        # happened to be flown.
        y_min = 0.0
        y_max = max(max(alts), 1.0) * 1.1

        def to_point(t: float, alt: float) -> QPointF:
            px = plot_rect.left() + ((t - t_min) / (t_max - t_min)) * plot_rect.width()
            py = plot_rect.bottom() - ((alt - y_min) / (y_max - y_min)) * plot_rect.height()
            return QPointF(px, py)

        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)
        for i in range(4):
            frac = i / 3
            y_val = y_min + frac * (y_max - y_min)
            py = plot_rect.bottom() - frac * plot_rect.height()
            painter.setPen(QPen(GRID_COLOR, 1))
            painter.drawLine(QPointF(plot_rect.left(), py), QPointF(plot_rect.right(), py))
            painter.setPen(QColor(CAPTION_COLOR))
            painter.drawText(
                QRectF(0, py - 7, MARGIN_LEFT - 4, 14),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{y_val:.0f}",
            )
        painter.drawText(
            QRectF(0, 0, self.width(), MARGIN_TOP),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"  {i18n.tr('altitude_track_axis_y')}",
        )

        fill_path = QPainterPath()
        fill_path.moveTo(to_point(times[0], y_min))
        for t, alt in zip(times, alts):
            fill_path.lineTo(to_point(t, alt))
        fill_path.lineTo(to_point(times[-1], y_min))
        fill_path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(FILL_COLOR)
        painter.drawPath(fill_path)

        line_path = QPainterPath()
        line_path.moveTo(to_point(times[0], alts[0]))
        for t, alt in zip(times[1:], alts[1:]):
            line_path.lineTo(to_point(t, alt))
        painter.setPen(QPen(LINE_COLOR, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(line_path)

        divisor, unit_key = TIME_UNITS[self._time_unit]
        unit_label = i18n.tr(unit_key)
        for i in range(4):
            frac = i / 3
            t_val = t_min + frac * (t_max - t_min)
            px = plot_rect.left() + frac * plot_rect.width()
            painter.setPen(QColor(CAPTION_COLOR))
            painter.drawText(
                QRectF(px - 20, plot_rect.bottom() + 2, 40, 12),
                Qt.AlignmentFlag.AlignCenter,
                f"{t_val / divisor:.1f}",
            )
        painter.drawText(
            QRectF(plot_rect.left(), self.height() - 14, plot_rect.width(), 14),
            Qt.AlignmentFlag.AlignCenter,
            i18n.tr("altitude_track_axis_x", unit=unit_label),
        )
        painter.end()


class AltitudeTrackOverlay(DraggableOverlay):
    MIN_WIDTH = 160
    MIN_HEIGHT = 90

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"AltitudeTrackOverlay {{ background-color: {PANEL_BG}; "
            f"border: 1px solid #0d1117; border-radius: 10px; }}"
        )
        self.resize(220, 130)

        self._title_label = QLabel()
        self._title_label.setStyleSheet("color: #ffffff; font-weight: 700; font-size: 12px; background: transparent;")
        self._title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._chart = AltitudeChartWidget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        layout.addWidget(self._title_label)
        layout.addWidget(self._chart, 1)

        i18n.on_language_changed(self.retranslate)
        self.retranslate()

    def add_sample(self, elapsed_s: float, alt_m: float) -> None:
        self._chart.add_sample(elapsed_s, alt_m)

    def reset(self) -> None:
        self._chart.clear()

    def set_time_unit(self, unit: str) -> None:
        self._chart.set_time_unit(unit)

    def time_unit(self) -> str:
        return self._chart._time_unit

    def retranslate(self) -> None:
        self._title_label.setText(i18n.tr("altitude_track_title"))
