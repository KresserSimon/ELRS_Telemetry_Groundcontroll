"""Shared drag-to-reposition and drag-to-resize behaviour for floating map
overlay widgets (HorizonWidget, RouteEditorOverlay, TrackOverlay, ...).

Dragging the widget body calls the parent MapWidget's set_overlay_free() so
the manual position sticks instead of snapping back to the last preset
corner on the next resize. Resizing is done from a small grip in the
bottom-right corner - a separate child widget rather than a hit-test zone
on the overlay itself, since the overlay is otherwise packed edge-to-edge
with interactive children (tables, buttons) that would swallow the mouse
press before it ever reached a zone check.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class _ResizeGrip(QWidget):
    SIZE = 14

    def __init__(self, overlay: "DraggableOverlay") -> None:
        super().__init__(overlay)
        self._overlay = overlay
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self._drag_start = None
        self._start_size = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._start_size = self._overlay.size()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        delta = event.globalPosition().toPoint() - self._drag_start
        self._overlay.request_resize(
            self._start_size.width() + delta.x(),
            self._start_size.height() + delta.y(),
        )
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            event.accept()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(255, 255, 255, 140))
        pen.setWidth(1)
        painter.setPen(pen)
        s = self.SIZE
        for offset in (3, 7, 11):
            painter.drawLine(s - offset, s - 1, s - 1, s - offset)
        painter.end()


class _CloseButton(QWidget):
    SIZE = 14

    def __init__(self, overlay: "DraggableOverlay") -> None:
        super().__init__(overlay)
        self._overlay = overlay
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # Accept (don't propagate) so the overlay body's own drag
            # handler never sees this press as the start of a window-move.
            event.accept()
            self._overlay.close_overlay()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(255, 255, 255, 170))
        pen.setWidth(1.4)
        painter.setPen(pen)
        m, s = 3, self.SIZE
        painter.drawLine(m, m, s - m, s - m)
        painter.drawLine(s - m, m, m, s - m)
        painter.end()


class DraggableOverlay(QWidget):
    # Subclasses may override to change how small/large a drag-resize can go.
    MIN_WIDTH = 120
    MIN_HEIGHT = 70

    # Emitted when the user clicks the close (x) button - MainWindow
    # connects this per-overlay to uncheck the matching "show ... " menu
    # action, so the overlay stays reachable again afterwards.
    closed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start = None
        self._docked = False
        self._resize_grip = _ResizeGrip(self)
        self._close_button = _CloseButton(self)

    def set_docked(self, docked: bool) -> None:
        """Toggle between floating-on-the-map behaviour (drag to move,
        drag the corner grip to resize) and being embedded in a fixed slot
        elsewhere (e.g. the telemetry dashboard), where a parent layout -
        not the user's mouse - controls position and size. The close
        button keeps working either way; only dragging and the resize
        grip are floating-only."""
        self._docked = docked
        self._resize_grip.setVisible(not docked)
        self.setCursor(Qt.CursorShape.ArrowCursor if docked else Qt.CursorShape.OpenHandCursor)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_grip.move(self.width() - _ResizeGrip.SIZE, self.height() - _ResizeGrip.SIZE)
        self._close_button.move(self.width() - _CloseButton.SIZE - 4, 4)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Both are created before subclasses add their own content in
        # their __init__, so without this they'd end up underneath
        # whatever they add - raise them back to the top once everything
        # exists and the widget is actually about to be shown.
        self._resize_grip.raise_()
        self._close_button.raise_()

    def close_overlay(self) -> None:
        self.setVisible(False)
        self.closed.emit()

    def request_resize(self, width: int, height: int) -> None:
        """Apply a user-driven resize from the corner grip. Subclasses with
        non-default resize semantics (e.g. a square gauge that must scale
        both dimensions together) should override this instead of touching
        the grip itself."""
        width = max(self.MIN_WIDTH, width)
        height = max(self.MIN_HEIGHT, height)
        parent = self.parentWidget()
        if parent is not None:
            width = min(width, max(self.MIN_WIDTH, parent.width() - self.x()))
            height = min(height, max(self.MIN_HEIGHT, parent.height() - self.y()))
        self.resize(width, height)
        self._notify_parent_resized()

    def _notify_parent_resized(self) -> None:
        parent = self.parentWidget()
        if parent is not None and hasattr(parent, "reposition_overlays"):
            parent.reposition_overlays()

    def mousePressEvent(self, event) -> None:
        if self._docked:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            parent = self.parentWidget()
            if parent is not None and hasattr(parent, "set_overlay_free"):
                parent.set_overlay_free(self)
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._docked or self._drag_start is None or not (event.buttons() & Qt.MouseButton.LeftButton):
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
        if self._docked:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
