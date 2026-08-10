"""Heimkehr-Energiebudget settings: the assumed return-flight speed (used
whenever groundspeed is near zero, e.g. hovering - see
core/energy_budget.py's estimate()) and the reserve-ampel thresholds.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QVBoxLayout

from core import i18n


class EnergyBudgetSettingsDialog(QDialog):
    def __init__(
        self,
        speed_assumption_ms: float,
        yellow_threshold_pct: float,
        green_threshold_pct: float,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("energy_dialog_title"))

        form = QFormLayout()
        self._speed_spin = QDoubleSpinBox()
        self._speed_spin.setRange(0.5, 50.0)
        self._speed_spin.setSingleStep(0.5)
        self._speed_spin.setSuffix(" m/s")
        self._speed_spin.setValue(speed_assumption_ms)
        self._yellow_spin = QDoubleSpinBox()
        self._yellow_spin.setRange(1.0, 90.0)
        self._yellow_spin.setSingleStep(1.0)
        self._yellow_spin.setSuffix(" %")
        self._yellow_spin.setValue(yellow_threshold_pct)
        self._green_spin = QDoubleSpinBox()
        self._green_spin.setRange(2.0, 95.0)
        self._green_spin.setSingleStep(1.0)
        self._green_spin.setSuffix(" %")
        self._green_spin.setValue(green_threshold_pct)
        form.addRow(i18n.tr("energy_speed_assumption_label"), self._speed_spin)
        form.addRow(i18n.tr("energy_yellow_threshold_label"), self._yellow_spin)
        form.addRow(i18n.tr("energy_green_threshold_label"), self._green_spin)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(button_box)

    def _on_accept(self) -> None:
        # Green must stay the safer (higher-reserve) threshold, or the
        # ampel logic in core/energy_budget.py's estimate() would never
        # show yellow - a >= check against an inverted pair always lands
        # on green.
        if self._green_spin.value() < self._yellow_spin.value():
            self._green_spin.setValue(self._yellow_spin.value())
        self.accept()

    def speed_assumption_ms(self) -> float:
        return self._speed_spin.value()

    def yellow_threshold_pct(self) -> float:
        return self._yellow_spin.value()

    def green_threshold_pct(self) -> float:
        return self._green_spin.value()
