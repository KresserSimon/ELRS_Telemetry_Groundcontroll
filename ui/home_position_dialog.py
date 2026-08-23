"""Dialog to set the map's startup center ("home position") - independent
of the live telemetry-derived home marker, which is always the first GPS
fix of the current session. This is only about where the map first opens,
before any fix has arrived.
"""
from __future__ import annotations

from typing import Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core import i18n
from core.ip_geolocation import IpGeolocationError, lookup_ip_location

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

        use_ip_btn = QPushButton(i18n.tr("home_use_ip_btn"))
        use_ip_btn.clicked.connect(self._use_ip_location)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(use_live_btn)
        layout.addWidget(use_ip_btn)
        layout.addWidget(button_box)

    def _use_live(self, live_position: Optional[Tuple[float, float]]) -> None:
        if live_position is None:
            return
        lat, lon = live_position
        self._lat_spin.setValue(lat)
        self._lon_spin.setValue(lon)

    def _use_ip_location(self) -> None:
        # City-level accuracy (a few km) - good enough to pick the right
        # map region, not a substitute for a real GPS fix. Synchronous
        # on purpose: this is a single quick request triggered by an
        # explicit button click, same pattern as the OpenAIP zone fetch.
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            lat, lon = lookup_ip_location()
        except IpGeolocationError as exc:
            self.unsetCursor()
            QMessageBox.warning(
                self,
                i18n.tr("msgbox_ip_geolocation_failed_title"),
                i18n.tr("msgbox_ip_geolocation_failed_body", error=str(exc)),
            )
            return
        self.unsetCursor()
        self._lat_spin.setValue(lat)
        self._lon_spin.setValue(lon)

    def home_position(self) -> Tuple[float, float]:
        return self._lat_spin.value(), self._lon_spin.value()
