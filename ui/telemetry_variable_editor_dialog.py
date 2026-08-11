"""Shows telemetry variables auto-detected beyond the fixed TelemetryState
schema (see core/telemetry_catalog.py and docs/feature_plan.md's
"Telemetrie-Variablen-Editor") - live values while a connection is active,
with a user-editable display name and a delete/restore toggle.
"""
from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core import i18n
from core.telemetry_catalog import TelemetryVariableCatalog

_COL_KEY, _COL_VALUE, _COL_NAME, _COL_ACTION = range(4)
_REFRESH_INTERVAL_MS = 500


def _readonly_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class TelemetryVariableEditorDialog(QDialog):
    def __init__(self, catalog: TelemetryVariableCatalog, parent=None) -> None:
        super().__init__(parent)
        self._catalog = catalog
        self.setWindowTitle(i18n.tr("varedit_dialog_title"))
        self.resize(560, 360)

        self._hint_label = QLabel(i18n.tr("varedit_hint"))
        self._hint_label.setWordWrap(True)

        self._show_hidden_check = QCheckBox(i18n.tr("varedit_show_hidden"))
        self._show_hidden_check.toggled.connect(self._rebuild_rows)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels([
            i18n.tr("varedit_col_key"),
            i18n.tr("varedit_col_value"),
            i18n.tr("varedit_col_name"),
            "",
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.horizontalHeader().setSectionResizeMode(_COL_KEY, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(_COL_VALUE, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(_COL_ACTION, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemChanged.connect(self._on_item_changed)

        self._empty_label = QLabel(i18n.tr("varedit_empty"))
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self._hint_label)
        layout.addWidget(self._show_hidden_check)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._empty_label)
        layout.addWidget(button_box)

        self._suppress_item_changed = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(_REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._refresh_values)
        self._refresh_timer.start()

        self._rebuild_rows()

    def closeEvent(self, event) -> None:
        self._refresh_timer.stop()
        super().closeEvent(event)

    def _rebuild_rows(self) -> None:
        variables = self._catalog.variables(include_hidden=self._show_hidden_check.isChecked())
        self._empty_label.setVisible(not variables)
        self._table.setVisible(bool(variables))

        self._suppress_item_changed = True
        self._table.setRowCount(len(variables))
        for row, variable in enumerate(variables):
            self._table.setItem(row, _COL_KEY, _readonly_item(variable.key))
            self._table.setItem(row, _COL_VALUE, _readonly_item(f"{variable.last_value:g}"))
            name_item = QTableWidgetItem(variable.display_name)
            name_item.setData(Qt.ItemDataRole.UserRole, variable.key)
            self._table.setItem(row, _COL_NAME, name_item)

            button = QPushButton(
                i18n.tr("varedit_restore_btn") if variable.hidden else i18n.tr("varedit_delete_btn")
            )
            button.clicked.connect(lambda _checked, key=variable.key, hidden=variable.hidden: self._toggle_hidden(key, hidden))
            self._table.setCellWidget(row, _COL_ACTION, button)
        self._suppress_item_changed = False

    def _refresh_values(self) -> None:
        # Only the live-value column needs updating on a timer - names/
        # hidden state only change via direct user action (_rebuild_rows
        # already handles those immediately).
        include_hidden = self._show_hidden_check.isChecked()
        by_key = {v.key: v for v in self._catalog.variables(include_hidden=include_hidden)}
        for row in range(self._table.rowCount()):
            key_item = self._table.item(row, _COL_KEY)
            if key_item is None:
                continue
            variable = by_key.get(key_item.text())
            if variable is not None:
                self._table.item(row, _COL_VALUE).setText(f"{variable.last_value:g}")

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suppress_item_changed or item.column() != _COL_NAME:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key is not None:
            self._catalog.set_display_name(key, item.text())

    def _toggle_hidden(self, key: str, currently_hidden: bool) -> None:
        self._catalog.set_hidden(key, not currently_hidden)
        self._rebuild_rows()
