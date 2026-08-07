"""Battery-alert settings: cell chemistry (LiPo/Li-Ion), cell count, and the
per-cell warning/critical voltage thresholds used by BatteryAlertMonitor.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from alerts.tts_alert import CHEMISTRY_DEFAULTS
from core import i18n


class BatterySettingsDialog(QDialog):
    def __init__(self, chemistry: str, cells: int, low_cell_voltage: float,
                 critical_cell_voltage: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("battery_dialog_title"))

        self._chemistry_group = QButtonGroup(self)
        self._lipo_radio = QRadioButton(i18n.tr("battery_chemistry_lipo"))
        self._liion_radio = QRadioButton(i18n.tr("battery_chemistry_liion"))
        self._chemistry_group.addButton(self._lipo_radio)
        self._chemistry_group.addButton(self._liion_radio)

        chem_box = QGroupBox(i18n.tr("battery_chemistry_box"))
        chem_layout = QHBoxLayout(chem_box)
        chem_layout.addWidget(self._lipo_radio)
        chem_layout.addWidget(self._liion_radio)

        form_box = QGroupBox()
        form = QFormLayout(form_box)
        self._cells_spin = QSpinBox()
        self._cells_spin.setRange(1, 24)
        self._cells_spin.setValue(cells)
        self._low_spin = QDoubleSpinBox()
        self._low_spin.setRange(0.5, 5.0)
        self._low_spin.setSingleStep(0.05)
        self._low_spin.setSuffix(" V")
        self._low_spin.setValue(low_cell_voltage)
        self._critical_spin = QDoubleSpinBox()
        self._critical_spin.setRange(0.5, 5.0)
        self._critical_spin.setSingleStep(0.05)
        self._critical_spin.setSuffix(" V")
        self._critical_spin.setValue(critical_cell_voltage)
        form.addRow(i18n.tr("battery_cells_label"), self._cells_spin)
        form.addRow(i18n.tr("battery_low_label"), self._low_spin)
        form.addRow(i18n.tr("battery_critical_label"), self._critical_spin)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(chem_box)
        layout.addWidget(form_box)
        layout.addWidget(button_box)

        self._lipo_radio.setChecked(chemistry != "liion")
        self._liion_radio.setChecked(chemistry == "liion")
        self._chemistry_group.buttonToggled.connect(self._apply_chemistry_defaults)

    def _apply_chemistry_defaults(self, button, checked) -> None:
        if not checked:
            return
        chemistry = "liion" if button is self._liion_radio else "lipo"
        low, critical = CHEMISTRY_DEFAULTS[chemistry]
        self._low_spin.setValue(low)
        self._critical_spin.setValue(critical)

    def chemistry(self) -> str:
        return "liion" if self._liion_radio.isChecked() else "lipo"

    def cells(self) -> int:
        return self._cells_spin.value()

    def low_cell_voltage(self) -> float:
        return self._low_spin.value()

    def critical_cell_voltage(self) -> float:
        return self._critical_spin.value()
