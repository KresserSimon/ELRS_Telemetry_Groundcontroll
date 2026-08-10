"""Draggable map overlay showing the frozen last-known position once
telemetry cuts out ("Modell-verloren-Modus", see
core/lost_model_monitor.py) - export/copy just ask MainWindow to do the
actual I/O, matching every other overlay's "display + request" split
(compare ui/track_overlay.py).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from core import i18n
from ui.draggable_overlay import DraggableOverlay

PANEL_BG = "rgba(18, 22, 28, 235)"
BORDER = "#e74c3c"


class LostModelOverlay(DraggableOverlay):
    export_gpx_clicked = pyqtSignal()
    copy_coords_clicked = pyqtSignal()

    MIN_WIDTH = 210
    MIN_HEIGHT = 150

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"LostModelOverlay {{ background-color: {PANEL_BG}; "
            f"border: 2px solid {BORDER}; border-radius: 10px; }}"
        )
        self.resize(230, 160)

        self._active = False
        self._lat = 0.0
        self._lon = 0.0
        self._distance_m = None
        self._bearing_deg = None
        self._lost_seconds = 0.0

        self._title_label = QLabel()
        self._title_label.setStyleSheet("color: #ff6b60; font-weight: 700; font-size: 12px; background: transparent;")
        self._title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._info_label = QLabel()
        self._info_label.setStyleSheet("color: #e8e8e8; font-size: 10px; background: transparent;")
        self._info_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._info_label.setWordWrap(True)

        self._export_btn = QPushButton()
        self._export_btn.clicked.connect(self.export_gpx_clicked)
        self._copy_btn = QPushButton()
        self._copy_btn.clicked.connect(self.copy_coords_clicked)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._export_btn)
        btn_row.addWidget(self._copy_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        layout.addWidget(self._title_label)
        layout.addWidget(self._info_label)
        layout.addLayout(btn_row)

        i18n.on_language_changed(self.retranslate)
        self.retranslate()

    def set_inactive(self) -> None:
        self._active = False
        self.retranslate()

    def update_info(self, lat: float, lon: float, distance_m, bearing_deg, lost_seconds: float) -> None:
        self._active = True
        self._lat = lat
        self._lon = lon
        self._distance_m = distance_m
        self._bearing_deg = bearing_deg
        self._lost_seconds = lost_seconds
        self.retranslate()

    def has_frozen_position(self) -> bool:
        return self._active

    def frozen_position(self):
        return (self._lat, self._lon) if self._active else None

    def retranslate(self) -> None:
        self._title_label.setText(i18n.tr("lostmodel_title"))
        if not self._active:
            self._info_label.setText(i18n.tr("lostmodel_inactive"))
        else:
            dist_str = f"{self._distance_m:.0f} m" if self._distance_m is not None else "--"
            bearing_str = f"{self._bearing_deg:.0f}°" if self._bearing_deg is not None else "--"
            self._info_label.setText(i18n.tr(
                "lostmodel_info",
                lat=f"{self._lat:.6f}", lon=f"{self._lon:.6f}",
                distance=dist_str, bearing=bearing_str,
                seconds=f"{self._lost_seconds:.0f}",
            ))
        self._export_btn.setText(i18n.tr("lostmodel_export_gpx_btn"))
        self._copy_btn.setText(i18n.tr("lostmodel_copy_btn"))
