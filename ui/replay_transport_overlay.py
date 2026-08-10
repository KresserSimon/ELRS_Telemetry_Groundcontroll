"""Draggable map overlay: transport controls (play/pause/speed/scrub) for
an active Log-Replay session (telemetry/replay_worker.py) - see
docs/feature_plan.md's "Log-Replay". Owns no I/O/threading itself, matches
every other overlay's "display + request" split; MainWindow drives the
actual ReplayWorker in response to this widget's signals.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout

from core import i18n
from ui.draggable_overlay import DraggableOverlay

PANEL_BG = "rgba(18, 22, 28, 235)"
BORDER = "#0d1117"
SPEED_OPTIONS = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
DEFAULT_SPEED = 1.0


class ReplayTransportOverlay(DraggableOverlay):
    play_pause_clicked = pyqtSignal()
    speed_changed = pyqtSignal(float)
    seek_requested = pyqtSignal(int)
    summary_requested = pyqtSignal()

    MIN_WIDTH = 260
    MIN_HEIGHT = 110

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"ReplayTransportOverlay {{ background-color: {PANEL_BG}; "
            f"border: 1px solid {BORDER}; border-radius: 10px; }}"
        )
        self.resize(320, 130)

        self._playing = False
        # Suppresses set_progress() fighting the user's own drag - while
        # true, incoming progress updates from the worker are ignored for
        # slider positioning (still shown in the status text).
        self._seeking = False

        self._title_label = QLabel()
        self._title_label.setStyleSheet("color: #ffffff; font-weight: 700; font-size: 12px; background: transparent;")
        self._title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: #c7cfda; font-size: 10px; background: transparent;")
        self._status_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._play_btn = QPushButton()
        self._play_btn.clicked.connect(self.play_pause_clicked)

        self._speed_combo = QComboBox()
        for speed in SPEED_OPTIONS:
            self._speed_combo.addItem(f"{speed:g}x", speed)
        self._speed_combo.setCurrentIndex(SPEED_OPTIONS.index(DEFAULT_SPEED))
        self._speed_combo.currentIndexChanged.connect(
            lambda idx: self.speed_changed.emit(self._speed_combo.itemData(idx))
        )

        self._summary_btn = QPushButton()
        self._summary_btn.clicked.connect(self.summary_requested)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._play_btn)
        btn_row.addWidget(self._speed_combo)
        btn_row.addWidget(self._summary_btn)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.sliderPressed.connect(self._on_slider_pressed)
        self._slider.sliderReleased.connect(self._on_slider_released)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        layout.addWidget(self._title_label)
        layout.addWidget(self._status_label)
        layout.addWidget(self._slider)
        layout.addLayout(btn_row)

        i18n.on_language_changed(self.retranslate)
        self.retranslate()

    def _on_slider_pressed(self) -> None:
        self._seeking = True

    def _on_slider_released(self) -> None:
        self._seeking = False
        self.seek_requested.emit(self._slider.value())

    def set_progress(self, index: int, total: int) -> None:
        if not self._seeking:
            self._slider.blockSignals(True)
            self._slider.setRange(0, max(0, total - 1))
            self._slider.setValue(index)
            self._slider.blockSignals(False)
        self._status_label.setText(i18n.tr("replay_progress_label", index=index + 1, total=total))

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        self.retranslate()

    def is_playing(self) -> bool:
        return self._playing

    def retranslate(self) -> None:
        self._title_label.setText(i18n.tr("replay_title"))
        self._play_btn.setText(i18n.tr("replay_pause_btn") if self._playing else i18n.tr("replay_play_btn"))
        self._summary_btn.setText(i18n.tr("replay_summary_btn"))
