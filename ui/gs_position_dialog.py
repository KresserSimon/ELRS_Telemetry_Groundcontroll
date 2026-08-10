"""Dialog to manually set the pilot's own ground-station position - see
core/gs_position.py for why this is a separate concept from the map's
startup center and the flight-start "Home" reference.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QVBoxLayout

from core import i18n
from core.gs_position import GsPosition


class GsPositionDialog(QDialog):
    def __init__(self, current: Optional[GsPosition], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("gsposition_dialog_title"))

        self._lat_spin = QDoubleSpinBox()
        self._lat_spin.setRange(-90.0, 90.0)
        self._lat_spin.setDecimals(6)
        self._lon_spin = QDoubleSpinBox()
        self._lon_spin.setRange(-180.0, 180.0)
        self._lon_spin.setDecimals(6)

        self._alt_check = QCheckBox(i18n.tr("gsposition_alt_known_label"))
        self._alt_spin = QDoubleSpinBox()
        self._alt_spin.setRange(-500.0, 9000.0)
        self._alt_spin.setSuffix(" m")
        self._alt_check.toggled.connect(self._alt_spin.setEnabled)

        if current is not None:
            self._lat_spin.setValue(current.lat)
            self._lon_spin.setValue(current.lon)
            if current.alt is not None:
                self._alt_check.setChecked(True)
                self._alt_spin.setValue(current.alt)
            else:
                self._alt_check.setChecked(False)
        self._alt_spin.setEnabled(self._alt_check.isChecked())

        form = QFormLayout()
        form.addRow(i18n.tr("gsposition_lat_label"), self._lat_spin)
        form.addRow(i18n.tr("gsposition_lon_label"), self._lon_spin)
        form.addRow(self._alt_check)
        form.addRow(i18n.tr("gsposition_alt_label"), self._alt_spin)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(button_box)

    def gs_position(self) -> GsPosition:
        return GsPosition(
            lat=self._lat_spin.value(),
            lon=self._lon_spin.value(),
            alt=self._alt_spin.value() if self._alt_check.isChecked() else None,
            source="manual",
        )
