"""Draggable map overlay showing incoming MAVLink STATUSTEXT messages
(Prearm/EKF/mode-change reasons, etc.) instead of silently discarding
them - see telemetry/mavlink_worker.py's status_text_received signal.
Severity-colored rows, a minimum-severity filter, and a copy-all button,
matching ui/track_overlay.py's "display + request" split (this widget owns
no I/O beyond the clipboard).
"""
from __future__ import annotations

from typing import List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from core import i18n
from ui.draggable_overlay import DraggableOverlay

PANEL_BG = "rgba(18, 22, 28, 235)"
BORDER = "#0d1117"
MAX_MESSAGES = 500
DEFAULT_MIN_SEVERITY = 6  # Info and more severe, excludes Debug spam by default

# MAV_SEVERITY: 0=EMERGENCY most severe .. 7=DEBUG least severe.
_SEVERITY_COLORS = {
    0: "#ff3b30", 1: "#ff3b30", 2: "#ff3b30", 3: "#ff3b30",
    4: "#f1c40f",
    5: "#3ba7ff", 6: "#3ba7ff",
    7: "#8a93a3",
}
# The three filter steps offered - deliberately simple (not all 8 MAV_SEVERITY
# levels individually) since this is a quick noise filter, not a precise log tool.
_FILTER_LEVELS = ((4, "statustext_filter_warning"), (6, "statustext_filter_info"), (7, "statustext_filter_all"))


class StatusTextConsole(DraggableOverlay):
    MIN_WIDTH = 260
    MIN_HEIGHT = 160

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"StatusTextConsole {{ background-color: {PANEL_BG}; "
            f"border: 1px solid {BORDER}; border-radius: 10px; }}"
        )
        self.resize(340, 220)

        self._messages: List[Tuple[int, str]] = []  # (severity, text), newest last
        self._min_severity_to_show = DEFAULT_MIN_SEVERITY

        self._title_label = QLabel()
        self._title_label.setStyleSheet("color: #ffffff; font-weight: 700; font-size: 12px; background: transparent;")
        self._title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._filter_combo = QComboBox()
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)

        self._list = QListWidget()
        self._list.setStyleSheet("QListWidget { background: transparent; border: none; font-size: 10px; }")

        self._copy_btn = QPushButton()
        self._copy_btn.clicked.connect(self._copy_all)
        self._clear_btn = QPushButton()
        self._clear_btn.clicked.connect(self.clear_messages)

        top_row = QHBoxLayout()
        top_row.addWidget(self._title_label)
        top_row.addStretch(1)
        top_row.addWidget(self._filter_combo)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._copy_btn)
        btn_row.addWidget(self._clear_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        layout.addLayout(top_row)
        layout.addWidget(self._list, 1)
        layout.addLayout(btn_row)

        i18n.on_language_changed(self.retranslate)
        self.retranslate()

    def add_message(self, severity: int, text: str) -> None:
        self._messages.append((severity, text))
        if len(self._messages) > MAX_MESSAGES:
            self._messages = self._messages[-MAX_MESSAGES:]
        if severity <= self._min_severity_to_show:
            self._append_row(severity, text)

    def clear_messages(self) -> None:
        self._messages = []
        self._list.clear()

    def message_count(self) -> int:
        return len(self._messages)

    def _append_row(self, severity: int, text: str) -> None:
        item = QListWidgetItem(text)
        item.setForeground(QColor(_SEVERITY_COLORS.get(severity, "#e8e8e8")))
        self._list.addItem(item)
        self._list.scrollToBottom()
        while self._list.count() > MAX_MESSAGES:
            self._list.takeItem(0)

    def _on_filter_changed(self, index: int) -> None:
        data = self._filter_combo.itemData(index)
        if data is None:
            return
        self._min_severity_to_show = data
        self._list.clear()
        for severity, text in self._messages:
            if severity <= self._min_severity_to_show:
                self._append_row(severity, text)

    def _copy_all(self) -> None:
        lines = [self._list.item(i).text() for i in range(self._list.count())]
        QApplication.clipboard().setText("\n".join(lines))

    def retranslate(self) -> None:
        self._title_label.setText(i18n.tr("statustext_title"))
        self._copy_btn.setText(i18n.tr("statustext_copy_btn"))
        self._clear_btn.setText(i18n.tr("statustext_clear_btn"))

        current = self._filter_combo.currentData()
        if current is None:
            current = self._min_severity_to_show
        self._filter_combo.blockSignals(True)
        self._filter_combo.clear()
        for severity, key in _FILTER_LEVELS:
            self._filter_combo.addItem(i18n.tr(key), severity)
        idx = self._filter_combo.findData(current)
        self._filter_combo.setCurrentIndex(idx if idx >= 0 else 1)
        self._filter_combo.blockSignals(False)
