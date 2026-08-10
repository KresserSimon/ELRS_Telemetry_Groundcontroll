"""Draggable map overlay that visually surfaces every currently-active
safety warning (battery, geofence, no-fly-zone proximity, energy budget) -
the same events that already trigger a spoken TTS warning (see
alerts/tts_alert.py, core/geofence_monitor.py, core/nfz_proximity.py,
core/energy_budget.py), now also shown on screen instead of only spoken
and left in the status bar. Only visible while at least one warning is
actually active - mirrors ui/lost_model_overlay.py's "pop up only for a
real event" behavior, not a permanently-shown placeholder.
"""
from __future__ import annotations

from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout

from core import i18n
from ui.draggable_overlay import DraggableOverlay

PANEL_BG = "rgba(40, 18, 18, 235)"
BORDER = "#e74c3c"


class WarningBanner(DraggableOverlay):
    MIN_WIDTH = 200
    MIN_HEIGHT = 40

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"WarningBanner {{ background-color: {PANEL_BG}; "
            f"border: 2px solid {BORDER}; border-radius: 10px; }}"
        )

        self._title_label = QLabel()
        self._title_label.setStyleSheet("color: #ff6b60; font-weight: 700; font-size: 12px; background: transparent;")
        self._title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._messages_label = QLabel()
        self._messages_label.setStyleSheet("color: #ffe8e6; font-size: 11px; background: transparent;")
        self._messages_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._messages_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        layout.addWidget(self._title_label)
        layout.addWidget(self._messages_label)

        self.adjustSize()
        i18n.on_language_changed(self.retranslate)
        self.retranslate()

    def set_messages(self, messages: List[str]) -> None:
        self._messages_label.setText("\n".join(messages))
        self.adjustSize()

    def retranslate(self) -> None:
        self._title_label.setText(i18n.tr("warning_banner_title"))
