"""Pick which dashboard fields are shown, in what order the groups appear,
and how many rows they wrap across - lets the user customize the bottom
telemetry bar to their own preferred layout ("their standard"), which
MainWindow then persists via core.dashboard_config.
"""
from __future__ import annotations

from typing import List, Set, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core import i18n
from core.dashboard_config import VALID_POSITIONS
from ui.dashboard import MAX_ROWS

_POSITION_LABEL_KEYS = {
    "top": "dashboard_position_top",
    "bottom": "dashboard_position_bottom",
    "left": "dashboard_position_left",
    "right": "dashboard_position_right",
}


class DashboardSettingsDialog(QDialog):
    def __init__(
        self,
        catalog: List[Tuple[str, List[str]]],
        visible_keys: Set[str],
        group_order: List[str],
        rows: int,
        position: str = "bottom",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("dashcfg_dialog_title"))
        self.resize(380, 600)

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

        order_label = QLabel(i18n.tr("dashcfg_order_label"))
        self._order_list = QListWidget()
        self._order_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._order_list.setMaximumHeight(150)
        for key in group_order:
            item = QListWidgetItem(i18n.tr(key))
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._order_list.addItem(item)

        self._rows_spin = QSpinBox()
        self._rows_spin.setRange(1, MAX_ROWS)
        self._rows_spin.setValue(max(1, min(rows, MAX_ROWS)))
        rows_row = QHBoxLayout()
        rows_row.addWidget(QLabel(i18n.tr("dashcfg_rows_label")))
        rows_row.addWidget(self._rows_spin)
        rows_row.addStretch(1)

        self._position_combo = QComboBox()
        for pos in VALID_POSITIONS:
            self._position_combo.addItem(i18n.tr(_POSITION_LABEL_KEYS[pos]), pos)
        idx = self._position_combo.findData(position if position in VALID_POSITIONS else "bottom")
        self._position_combo.setCurrentIndex(max(0, idx))
        position_row = QHBoxLayout()
        position_row.addWidget(QLabel(i18n.tr("dashcfg_position_label")))
        position_row.addWidget(self._position_combo)
        position_row.addStretch(1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addWidget(order_label)
        layout.addWidget(self._order_list)
        layout.addLayout(rows_row)
        layout.addLayout(position_row)
        layout.addWidget(button_box)

    def visible_fields(self) -> Set[str]:
        return {key for key, cb in self._checkboxes.items() if cb.isChecked()}

    def group_order(self) -> List[str]:
        return [self._order_list.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self._order_list.count())]

    def rows(self) -> int:
        return self._rows_spin.value()

    def position(self) -> str:
        return self._position_combo.currentData()
