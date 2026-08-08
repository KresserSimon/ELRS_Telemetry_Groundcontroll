"""Small fixed (non-draggable) icon buttons overlaid on the map, Google-Maps
style: unlike the other overlays (horizon, route editor, track recorder)
these always sit in the same map corner - a one-tap toggle doesn't need to
be draggable, and staying put is exactly what makes them quick to find.

Both are dumb display+click widgets: MainWindow owns the actual auto-center
/heading-mode state and calls set_locked()/set_heading_up() to reflect it,
the same "display + request, don't own policy" split every other overlay
in this app already follows.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QPushButton

from core import i18n

_SIZE = 36
_BG = QColor(30, 34, 40, 235)
_BG_ACTIVE = QColor(46, 204, 113, 235)
_FG_INACTIVE = QColor("#e6e6e6")
_FG_ACTIVE = QColor("#14181c")


class _MapIconButton(QPushButton):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(_SIZE, _SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("border: none; background: transparent;")
        self._active = False

    def _set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(_BG_ACTIVE if self._active else _BG))
        painter.drawEllipse(1, 1, _SIZE - 2, _SIZE - 2)
        self._paint_icon(painter, _FG_ACTIVE if self._active else _FG_INACTIVE)
        painter.end()

    def _paint_icon(self, painter: QPainter, color: QColor) -> None:
        raise NotImplementedError


class LockButton(_MapIconButton):
    """Google-Maps-style "recenter/lock" toggle for map auto-center."""

    def set_locked(self, locked: bool) -> None:
        self._set_active(locked)
        self.setToolTip(i18n.tr("maplock_on" if locked else "maplock_off"))

    def _paint_icon(self, painter: QPainter, color: QColor) -> None:
        pen = QPen(color)
        pen.setWidthF(2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        c = _SIZE / 2
        r = 7.0
        painter.drawEllipse(QPointF(c, c), r, r)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            painter.drawLine(
                QPointF(c + dx * (r + 6), c + dy * (r + 6)),
                QPointF(c + dx * (r + 1), c + dy * (r + 1)),
            )
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(c, c), 2.2, 2.2)


class HeadingModeButton(_MapIconButton):
    """Toggles the map between north-up (fixed) and heading-up (the whole
    map rotates so the drone's current heading always points to the top of
    the screen)."""

    def set_heading_up(self, heading_up: bool) -> None:
        self._set_active(heading_up)
        self.setToolTip(i18n.tr("mapheading_up" if heading_up else "mapheading_north"))

    def _paint_icon(self, painter: QPainter, color: QColor) -> None:
        c = _SIZE / 2
        if self._active:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            arrow = QPolygonF([
                QPointF(c, c - 9), QPointF(c - 6.5, c + 7), QPointF(c, c + 3), QPointF(c + 6.5, c + 7),
            ])
            painter.drawPolygon(arrow)
        else:
            pen = QPen(color)
            pen.setWidthF(2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(QPointF(c - 5, c + 8), QPointF(c - 5, c - 8))
            painter.drawLine(QPointF(c - 5, c - 8), QPointF(c + 5, c + 8))
            painter.drawLine(QPointF(c + 5, c + 8), QPointF(c + 5, c - 8))
