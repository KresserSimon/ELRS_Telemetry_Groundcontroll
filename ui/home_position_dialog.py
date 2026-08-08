"""Dialog to set the map's startup center ("home position") - independent
of the live telemetry-derived home marker, which is always the first GPS
fix of the current session. This is only about where the map first opens,
before any fix has arrived.
"""
from __future__ import annotations

from typing import Optional, Tuple

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QPushButton,
    QVBoxLayout,
)

from core import i18n

DEFAULT_LAT = 48.1372
DEFAULT_LON = 11.5756


class HomePositionDialog(QDialog):
    def __init__(
        self,
        current: Optional[Tuple[float, float]],
        live_position: Optional[Tuple[float, float]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("home_dialog_title"))

        self._lat_spin = QDoubleSpinBox()
        self._lat_spin.setRange(-90.0, 90.0)
        self._lat_spin.setDecimals(6)
        self._lon_spin = QDoubleSpinBox()
        self._lon_spin.setRange(-180.0, 180.0)
        self._lon_spin.setDecimals(6)

        lat, lon = current if current is not None else (DEFAULT_LAT, DEFAULT_LON)
        self._lat_spin.setValue(lat)
        self._lon_spin.setValue(lon)

        form = QFormLayout()
        form.addRow(i18n.tr("home_lat_label"), self._lat_spin)
        form.addRow(i18n.tr("home_lon_label"), self._lon_spin)

        use_live_btn = QPushButton(i18n.tr("home_use_current_btn"))
        use_live_btn.setEnabled(live_position is not None)
        use_live_btn.clicked.connect(lambda: self._use_live(live_position))

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(use_live_btn)
        layout.addWidget(button_box)

    def _use_live(self, live_position: Optional[Tuple[float, float]]) -> None:
        if live_position is None:
            return
        lat, lon = live_position
        self._lat_spin.setValue(lat)
        self._lon_spin.setValue(lon)

    def home_position(self) -> Tuple[float, float]:
        return self._lat_spin.value(), self._lon_spin.value()
