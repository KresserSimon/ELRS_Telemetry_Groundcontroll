"""Artificial-horizon (attitude indicator) overlay widget.

Drawn entirely with QPainter - a solid panel background (not a transparent
top-level window) so it composites reliably as a child widget on top of the
QWebEngineView-backed map, which has its own native paint surface.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF

from ui.draggable_overlay import DraggableOverlay

BASE_PANEL_SIZE = 130
MIN_SCALE = 0.5
MAX_SCALE = 2.5
MARGIN = 9
PX_PER_DEGREE = 2.6

SKY = QColor("#3b7dd8")
GROUND = QColor("#8a5a2b")
DIM_SKY = QColor("#31404f")
DIM_GROUND = QColor("#3a352c")
MARK_COLOR = QColor("#f2f5f8")
POINTER_COLOR = QColor("#ffcc00")
BEZEL_COLOR = QColor("#0d1117")
PANEL_BG = QColor(18, 22, 28, 235)


class HorizonWidget(DraggableOverlay):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scale = 1.0
        self.setFixedSize(BASE_PANEL_SIZE, BASE_PANEL_SIZE)
        self._roll: Optional[float] = None
        self._pitch: Optional[float] = None

    def set_scale(self, scale: float) -> None:
        self._scale = max(MIN_SCALE, min(MAX_SCALE, scale))
        size = round(BASE_PANEL_SIZE * self._scale)
        self.setFixedSize(size, size)
        self.update()

    def scale(self) -> float:
        return self._scale

    def update_attitude(self, roll: Optional[float], pitch: Optional[float]) -> None:
        self._roll = roll
        self._pitch = pitch
        self.update()

    def paintEvent(self, event) -> None:
        has_data = self._roll is not None and self._pitch is not None
        roll = self._roll if has_data else 0.0
        pitch = max(-60.0, min(60.0, self._pitch)) if has_data else 0.0

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        panel_rect = QRectF(0, 0, self.width(), self.height())
        painter.setPen(QPen(BEZEL_COLOR, 1))
        painter.setBrush(PANEL_BG)
        painter.drawRoundedRect(panel_rect.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)

        cx = self.width() / 2
        cy = self.height() / 2
        radius = self.width() / 2 - MARGIN

        painter.save()
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), radius, radius)
        painter.setClipPath(clip)

        px_per_degree = PX_PER_DEGREE * self._scale

        painter.translate(cx, cy)
        painter.rotate(-roll)
        pitch_offset = pitch * px_per_degree

        big = radius * 3
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(SKY if has_data else DIM_SKY)
        painter.drawRect(QRectF(-big, -big + pitch_offset, 2 * big, big))
        painter.setBrush(GROUND if has_data else DIM_GROUND)
        painter.drawRect(QRectF(-big, pitch_offset, 2 * big, big))

        painter.setPen(QPen(MARK_COLOR, 1.5))
        painter.drawLine(QPointF(-big, pitch_offset), QPointF(big, pitch_offset))

        painter.setPen(QPen(MARK_COLOR, 1.1))
        font = painter.font()
        font.setPointSize(max(5, round(6 * self._scale)))
        painter.setFont(font)
        for deg in range(-30, 31, 10):
            if deg == 0:
                continue
            y = pitch_offset - deg * px_per_degree
            half_w = 13 if deg % 20 == 0 else 7
            painter.drawLine(QPointF(-half_w, y), QPointF(half_w, y))
            painter.drawText(QPointF(half_w + 2, y + 3), str(abs(deg)))

        painter.restore()

        painter.setPen(QPen(BEZEL_COLOR, 2.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        painter.save()
        painter.translate(cx, cy)
        painter.setPen(QPen(MARK_COLOR, 1.2))
        for mark_deg in (-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60):
            painter.save()
            painter.rotate(mark_deg)
            length = 8 if mark_deg in (0, -30, 30, -60, 60) else 5
            painter.drawLine(QPointF(0, -radius + 1), QPointF(0, -radius + 1 + length))
            painter.restore()

        painter.save()
        painter.rotate(-roll)
        pointer = QPolygonF([QPointF(0, -radius + 2), QPointF(-4, -radius + 10), QPointF(4, -radius + 10)])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(POINTER_COLOR)
        painter.drawPolygon(pointer)
        painter.restore()
        painter.restore()

        painter.setPen(QPen(POINTER_COLOR, 2.5))
        painter.drawLine(QPointF(cx - 18, cy), QPointF(cx - 6, cy))
        painter.drawLine(QPointF(cx + 6, cy), QPointF(cx + 18, cy))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(POINTER_COLOR)
        painter.drawEllipse(QPointF(cx, cy), 2, 2)

        if not has_data:
            painter.setPen(MARK_COLOR)
            painter.drawText(panel_rect, Qt.AlignmentFlag.AlignCenter, "N/A")

        painter.end()
