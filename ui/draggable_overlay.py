"""Shared drag-to-reposition behaviour for floating map overlay widgets
(HorizonWidget, RouteEditorOverlay, ...). A drag calls the parent MapWidget's
set_overlay_free() so the manual position sticks instead of snapping back
to the last preset corner on the next resize.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget


class DraggableOverlay(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            parent = self.parentWidget()
            if parent is not None and hasattr(parent, "set_overlay_free"):
                parent.set_overlay_free(self)
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        delta = event.position().toPoint() - self._drag_start
        new_pos = self.pos() + delta
        parent = self.parentWidget()
        if parent is not None:
            max_x = max(0, parent.width() - self.width())
            max_y = max(0, parent.height() - self.height())
            new_pos.setX(min(max(new_pos.x(), 0), max_x))
            new_pos.setY(min(max(new_pos.y(), 0), max_y))
        self.move(new_pos)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
