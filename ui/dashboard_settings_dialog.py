"""Pick which dashboard fields are shown - lets the user customize the
bottom telemetry bar to their own preferred layout ("their standard"),
which MainWindow then persists via core.dashboard_config.
"""
from __future__ import annotations

from typing import List, Set, Tuple

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core import i18n


class DashboardSettingsDialog(QDialog):
    def __init__(self, catalog: List[Tuple[str, List[str]]], visible_keys: Set[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("dashcfg_dialog_title"))
        self.resize(360, 440)

        self._checkboxes = {}

        container = QWidget()
        vlayout = QVBoxLayout(container)
        for group_title_key, field_keys in catalog:
            box = QGroupBox(i18n.tr(group_title_key))
            box_layout = QVBoxLayout(box)
            for field_key in field_keys:
                cb = QCheckBox(i18n.tr(field_key))
                cb.setChecked(field_key in visible_keys)
                self._checkboxes[field_key] = cb
                box_layout.addWidget(cb)
            vlayout.addWidget(box)
        vlayout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        layout.addWidget(button_box)

    def visible_fields(self) -> Set[str]:
        return {key for key, cb in self._checkboxes.items() if cb.isChecked()}
