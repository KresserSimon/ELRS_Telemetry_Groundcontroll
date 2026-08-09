"""Small QPainter-drawn icons for the dashboard.

Drawn in code rather than loaded from image files so PyInstaller doesn't need
to bundle/locate extra data files - the whole icon set is self-contained.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF

STROKE = QColor("#c7cfda")
ACCENT = QColor("#3ba7ff")
GOOD = QColor("#2ecc71")
WARN = QColor("#f1c40f")
BAD = QColor("#e74c3c")
DIM = QColor("#4a5361")

SIZE = 22


def _canvas(size: int = SIZE) -> tuple[QPixmap, QPainter]:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pm, p


# Button-scale icons (Start/Pause/Export etc.) are drawn smaller than the
# 22px dashboard field icons, matching typical QPushButton icon proportions
# next to a text label.
BUTTON_SIZE = 15


def play_icon() -> QPixmap:
    """A right-pointing triangle - "start recording"."""
    pm, p = _canvas(BUTTON_SIZE)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(GOOD)
    s = BUTTON_SIZE
    p.drawPolygon(QPolygonF([QPointF(s * 0.28, s * 0.15), QPointF(s * 0.28, s * 0.85), QPointF(s * 0.85, s * 0.5)]))
    p.end()
    return pm


def pause_icon() -> QPixmap:
    """Two vertical bars - "pause recording"."""
    pm, p = _canvas(BUTTON_SIZE)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(WARN)
    s = BUTTON_SIZE
    bar_w = s * 0.22
    p.drawRoundedRect(QRectF(s * 0.22, s * 0.15, bar_w, s * 0.7), 1, 1)
    p.drawRoundedRect(QRectF(s * 0.56, s * 0.15, bar_w, s * 0.7), 1, 1)
    p.end()
    return pm


def export_icon() -> QPixmap:
    """A downward arrow into a tray - "export/save"."""
    pm, p = _canvas(BUTTON_SIZE)
    s = BUTTON_SIZE
    p.setPen(QPen(ACCENT, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawLine(QPointF(s * 0.5, s * 0.08), QPointF(s * 0.5, s * 0.62))
    p.drawLine(QPointF(s * 0.28, s * 0.42), QPointF(s * 0.5, s * 0.66))
    p.drawLine(QPointF(s * 0.72, s * 0.42), QPointF(s * 0.5, s * 0.66))
    p.drawLine(QPointF(s * 0.12, s * 0.88), QPointF(s * 0.88, s * 0.88))
    p.end()
    return pm


def gps_icon() -> QPixmap:
    pm, p = _canvas()
    p.setPen(QPen(STROKE, 1.2))
    p.setBrush(ACCENT)

    # Overlapping triangle + circle reads as a classic map pin without
    # needing exact path-union math for a 22px icon.
    triangle = QPolygonF([QPointF(11, 21), QPointF(6.5, 11), QPointF(15.5, 11)])
    p.drawPolygon(triangle)
    p.drawEllipse(QRectF(4, 1, 14, 14))

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#0d1117"))
    p.drawEllipse(QRectF(8, 5, 6, 6))
    p.end()
    return pm


def drone_icon() -> QPixmap:
    pm, p = _canvas()
    pen = QPen(STROKE, 1.8)
    p.setPen(pen)
    p.drawLine(6, 6, 16, 16)
    p.drawLine(16, 6, 6, 16)

    p.setPen(QPen(STROKE, 0.8))
    p.setBrush(ACCENT)
    for x, y in ((6, 6), (16, 6), (6, 16), (16, 16)):
        p.drawEllipse(QRectF(x - 2.6, y - 2.6, 5.2, 5.2))
    p.end()
    return pm


def signal_icon(level: int = 0) -> QPixmap:
    """level: -1 = unknown, 0..4 = number of lit bars."""
    pm, p = _canvas()
    p.setPen(Qt.PenStyle.NoPen)
    bar_count = 4
    bar_w = 3.2
    gap = 1.6
    base_y = 19
    start_x = 2
    for i in range(bar_count):
        h = 4 + i * 4
        x = start_x + i * (bar_w + gap)
        lit = level >= 0 and i < level
        p.setBrush(ACCENT if lit else DIM)
        p.drawRoundedRect(QRectF(x, base_y - h, bar_w, h), 1, 1)
    p.end()
    return pm


def compass_icon() -> QPixmap:
    pm, p = _canvas()
    p.setPen(QPen(STROKE, 1.3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(2, 2, 18, 18))

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(ACCENT)
    p.drawPolygon(QPolygonF([QPointF(11, 4), QPointF(13.5, 11), QPointF(11, 9.5)]))
    p.setBrush(DIM)
    p.drawPolygon(QPolygonF([QPointF(11, 18), QPointF(8.5, 11), QPointF(11, 12.5)]))

    p.setBrush(STROKE)
    p.drawEllipse(QRectF(9.5, 9.5, 3, 3))
    p.end()
    return pm


def battery_icon(percent: Optional[int]) -> QPixmap:
    pm, p = _canvas()
    body = QRectF(2, 6, 16, 10)
    p.setPen(QPen(STROKE, 1.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(body, 2, 2)
    p.drawRect(QRectF(18.5, 9, 1.8, 4))

    if percent is not None:
        pct = max(0, min(100, percent))
        color = GOOD if pct > 50 else (WARN if pct > 20 else BAD)
        inner = body.adjusted(1.6, 1.6, -1.6, -1.6)
        fill_w = inner.width() * (pct / 100.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(inner.left(), inner.top(), fill_w, inner.height()), 1, 1)

    p.end()
    return pm


def sensor_icon() -> QPixmap:
    pm, p = _canvas()
    p.setPen(QPen(STROKE, 1.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(2, 3, 18, 18), 20 * 16, 320 * 16)

    p.setPen(QPen(ACCENT, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(11, 12), QPointF(16, 7))

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(STROKE)
    p.drawEllipse(QRectF(9, 10, 4, 4))
    p.end()
    return pm


def status_led_icon(connected: bool) -> QPixmap:
    pm, p = _canvas()
    color = GOOD if connected else BAD
    p.setPen(QPen(color.darker(140), 1.2))
    p.setBrush(color)
    p.drawEllipse(QRectF(6, 6, 10, 10))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(color, 1.0, Qt.PenStyle.SolidLine))
    p.setOpacity(0.35)
    p.drawEllipse(QRectF(3, 3, 16, 16))
    p.end()
    return pm
