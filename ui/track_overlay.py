"""Draggable map overlay for the flown-GPS-track recorder: start/pause and
export, live on the map instead of buried in the File menu only. Export
just asks MainWindow to run the format-choice popup - this widget owns no
file I/O itself, matching how the other overlays (route editor, ...) leave
policy decisions to MainWindow and only display + request.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from core import i18n
from ui import icons
from ui.draggable_overlay import DraggableOverlay

PANEL_BG = "rgba(18, 22, 28, 235)"
BORDER = "#0d1117"


class TrackOverlay(DraggableOverlay):
    start_pause_clicked = pyqtSignal()
    export_clicked = pyqtSignal()

    MIN_WIDTH = 160
    MIN_HEIGHT = 90

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"TrackOverlay {{ background-color: {PANEL_BG}; "
            f"border: 1px solid {BORDER}; border-radius: 10px; }}"
        )
        self.resize(210, 110)

        self._recording = False
        self._point_count = 0

        self._title_label = QLabel()
        self._title_label.setStyleSheet("color: #ffffff; font-weight: 700; font-size: 12px; background: transparent;")
        self._title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: #c7cfda; font-size: 10px; background: transparent;")
        self._status_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        icon_size = QSize(icons.BUTTON_SIZE, icons.BUTTON_SIZE)

        self._toggle_btn = QPushButton()
        self._toggle_btn.setIconSize(icon_size)
        self._toggle_btn.clicked.connect(self.start_pause_clicked)
        self._export_btn = QPushButton()
        self._export_btn.setIcon(QIcon(icons.export_icon()))
        self._export_btn.setIconSize(icon_size)
        self._export_btn.clicked.connect(self.export_clicked)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._toggle_btn)
        btn_row.addWidget(self._export_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        layout.addWidget(self._title_label)
        layout.addWidget(self._status_label)
        layout.addLayout(btn_row)

        i18n.on_language_changed(self.retranslate)
        self.retranslate()

    def set_state(self, recording: bool, point_count: int) -> None:
        self._recording = recording
        self._point_count = point_count
        self.retranslate()

    def update_count(self, point_count: int) -> None:
        self._point_count = point_count
        self._update_status_text()

    def retranslate(self) -> None:
        self._title_label.setText(i18n.tr("track_title"))
        self._update_status_text()
        self._toggle_btn.setText(i18n.tr("track_pause_btn" if self._recording else "track_start_btn"))
        self._toggle_btn.setIcon(QIcon(icons.pause_icon() if self._recording else icons.play_icon()))
        self._export_btn.setText(i18n.tr("track_export_btn"))

    def _update_status_text(self) -> None:
        status_key = "track_status_recording" if self._recording else "track_status_paused"
        self._status_label.setText(i18n.tr(status_key, count=self._point_count))
