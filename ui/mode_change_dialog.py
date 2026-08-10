"""Confirmation dialog for a MAVLink flight-mode change - picking a mode and
pressing OK IS the plan's required "Klartext"-confirmation step (a plain-
language warning is shown alongside the picker, see docs/feature_plan.md's
"MAVLink-Rueckkanal"): sending this to a real flight controller changes how
it flies immediately.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QVBoxLayout

from core import i18n
from telemetry.mavlink_command import modes_for_vehicle_type


class ModeChangeDialog(QDialog):
    def __init__(self, vehicle_type: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("modechange_dialog_title"))

        warning = QLabel(i18n.tr("modechange_warning"))
        warning.setWordWrap(True)

        self._list = QListWidget()
        for key, custom_mode in modes_for_vehicle_type(vehicle_type):
            item = QListWidgetItem(i18n.tr(key))
            item.setData(1000, custom_mode)
            self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(warning)
        layout.addWidget(self._list)
        layout.addWidget(button_box)

    def selected_mode(self) -> Optional[int]:
        item = self._list.currentItem()
        if item is None:
            return None
        return item.data(1000)
