"""Own geofence settings: max radius and max altitude relative to the
flight-start reference - persisted per model profile (see
core/model_profiles.py) since different aircraft can plausibly need
different limits, mirroring ui/battery_settings_dialog.py's structure.

Enable/disable itself is NOT in this dialog - it's a direct, one-click menu
checkbox next to "Geofence anzeigen" (see MainWindow._build_menu()), so
turning the whole feature off never requires opening a dialog just for
that. Keeping enable/disable as a single source of truth (the menu action's
checked state) avoids two places that could drift out of sync.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QVBoxLayout

from core import i18n


class GeofenceSettingsDialog(QDialog):
    def __init__(self, radius_m: float, max_alt_m: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("geofence_dialog_title"))

        form = QFormLayout()
        self._radius_spin = QDoubleSpinBox()
        self._radius_spin.setRange(10.0, 50000.0)
        self._radius_spin.setSingleStep(10.0)
        self._radius_spin.setSuffix(" m")
        self._radius_spin.setValue(radius_m)
        self._max_alt_spin = QDoubleSpinBox()
        self._max_alt_spin.setRange(1.0, 10000.0)
        self._max_alt_spin.setSingleStep(10.0)
        self._max_alt_spin.setSuffix(" m")
        self._max_alt_spin.setValue(max_alt_m)
        form.addRow(i18n.tr("geofence_radius_label"), self._radius_spin)
        form.addRow(i18n.tr("geofence_max_alt_label"), self._max_alt_spin)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(button_box)

    def radius_m(self) -> float:
        return self._radius_spin.value()

    def max_alt_m(self) -> float:
        return self._max_alt_spin.value()
