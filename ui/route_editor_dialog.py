"""Edit the planned route's waypoints - lat/lon come from drawing or
importing, but altitude/name/INAV-mission parameters are commonly not set
by either, so this gives a place to fill them in per point, plus buttons to
export/import the route directly as an INAV .mission JSON file.
"""
from __future__ import annotations

from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core import i18n
from core.route import Waypoint
from core.terrain import TerrainLookupError, check_terrain_clearance
from export.inav_mission import (
    MissionAction,
    MissionValidationError,
    export_inav_mission,
    import_inav_mission_json,
    validate_mission,
)

COL_INDEX, COL_LAT, COL_LON, COL_ALT, COL_NAME, COL_ACTION, COL_SPEED, COL_P1, COL_P2, COL_P3 = range(10)

# Below this clearance (metres) a waypoint is flagged as a likely terrain
# collision - a small positive buffer, not just >0, to allow for the public
# elevation API's sampling being coarser than the actual flight path.
TERRAIN_MARGIN_M = 20.0
_COLOR_COLLISION = QColor(255, 120, 120)
_COLOR_WARNING = QColor(255, 220, 130)
_COLOR_CLEAR = QColor(160, 230, 160)


class RouteEditorDialog(QDialog):
    def __init__(self, waypoints: List[Waypoint], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("routeeditor_title"))
        self.resize(760, 420)

        self._original = list(waypoints)

        self._table = QTableWidget(len(self._original), 10, self)
        self._table.setHorizontalHeaderLabels([
            "#",
            i18n.tr("routeeditor_lat"),
            i18n.tr("routeeditor_lon"),
            i18n.tr("routeeditor_alt"),
            i18n.tr("routeeditor_name"),
            i18n.tr("routeeditor_action"),
            i18n.tr("routeeditor_speed"),
            i18n.tr("routeeditor_p1"),
            i18n.tr("routeeditor_p2"),
            i18n.tr("routeeditor_p3"),
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)

        self._alt_spins: List[QDoubleSpinBox] = []
        self._name_edits: List[QLineEdit] = []
        self._action_combos: List[QComboBox] = []
        self._speed_spins: List[QDoubleSpinBox] = []
        self._p1_spins: List[QSpinBox] = []
        self._p2_spins: List[QSpinBox] = []
        self._p3_spins: List[QSpinBox] = []

        for row, wp in enumerate(self._original):
            self._add_row(row, wp)

        export_btn = QPushButton(i18n.tr("routeeditor_export_mission"))
        export_btn.clicked.connect(self._export_mission)
        import_btn = QPushButton(i18n.tr("routeeditor_import_mission"))
        import_btn.clicked.connect(self._import_mission)
        terrain_btn = QPushButton(i18n.tr("routeeditor_check_terrain"))
        terrain_btn.clicked.connect(self._check_terrain)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        mission_row = QHBoxLayout()
        mission_row.addWidget(export_btn)
        mission_row.addWidget(import_btn)
        mission_row.addWidget(terrain_btn)
        mission_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table)
        layout.addLayout(mission_row)
        layout.addWidget(button_box)

    def _add_row(self, row: int, wp: Waypoint) -> None:
        self._table.setItem(row, COL_INDEX, self._readonly_item(str(row + 1)))
        self._table.setItem(row, COL_LAT, self._readonly_item(f"{wp.lat:.6f}"))
        self._table.setItem(row, COL_LON, self._readonly_item(f"{wp.lon:.6f}"))

        alt_spin = QDoubleSpinBox()
        alt_spin.setRange(-1000.0, 10000.0)
        alt_spin.setDecimals(1)
        alt_spin.setSuffix(" m")
        alt_spin.setValue(wp.alt if wp.alt is not None else 0.0)
        self._table.setCellWidget(row, COL_ALT, alt_spin)
        self._alt_spins.append(alt_spin)

        name_edit = QLineEdit(wp.name)
        self._table.setCellWidget(row, COL_NAME, name_edit)
        self._name_edits.append(name_edit)

        action_combo = QComboBox()
        action_combo.addItems([a.value for a in MissionAction])
        idx = action_combo.findText(wp.action)
        action_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._table.setCellWidget(row, COL_ACTION, action_combo)
        self._action_combos.append(action_combo)

        speed_spin = QDoubleSpinBox()
        speed_spin.setRange(0.0, 100.0)
        speed_spin.setDecimals(1)
        speed_spin.setValue(wp.speed)
        self._table.setCellWidget(row, COL_SPEED, speed_spin)
        self._speed_spins.append(speed_spin)

        p1 = QSpinBox()
        p1.setRange(-32768, 32767)
        p1.setValue(wp.p1)
        self._table.setCellWidget(row, COL_P1, p1)
        self._p1_spins.append(p1)

        p2 = QSpinBox()
        p2.setRange(-32768, 32767)
        p2.setValue(wp.p2)
        self._table.setCellWidget(row, COL_P2, p2)
        self._p2_spins.append(p2)

        p3 = QSpinBox()
        p3.setRange(-32768, 32767)
        p3.setValue(wp.p3)
        self._table.setCellWidget(row, COL_P3, p3)
        self._p3_spins.append(p3)

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def updated_waypoints(self) -> List[Waypoint]:
        return [
            Waypoint(
                wp.lat, wp.lon, alt_spin.value(), name_edit.text(),
                action=action_combo.currentText(),
                speed=speed_spin.value(),
                p1=p1.value(), p2=p2.value(), p3=p3.value(),
            )
            for wp, alt_spin, name_edit, action_combo, speed_spin, p1, p2, p3 in zip(
                self._original, self._alt_spins, self._name_edits, self._action_combos,
                self._speed_spins, self._p1_spins, self._p2_spins, self._p3_spins,
            )
        ]

    def _reload_rows(self, waypoints: List[Waypoint]) -> None:
        self._original = list(waypoints)
        self._table.setRowCount(len(self._original))
        self._alt_spins.clear()
        self._name_edits.clear()
        self._action_combos.clear()
        self._speed_spins.clear()
        self._p1_spins.clear()
        self._p2_spins.clear()
        self._p3_spins.clear()
        for row, wp in enumerate(self._original):
            self._add_row(row, wp)

    def _export_mission(self) -> None:
        waypoints = self.updated_waypoints()
        warnings = validate_mission(waypoints)
        if warnings:
            proceed = QMessageBox.warning(
                self, i18n.tr("msgbox_mission_warning_title"), "\n".join(warnings),
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if proceed != QMessageBox.StandardButton.Ok:
                return

        path, _ = QFileDialog.getSaveFileName(self, i18n.tr("routeeditor_export_mission"), "", i18n.tr("mission_filter"))
        if not path:
            return
        try:
            export_inav_mission(waypoints, path)
        except MissionValidationError as exc:
            QMessageBox.critical(self, i18n.tr("msgbox_mission_invalid_title"), str(exc))

    def _import_mission(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, i18n.tr("routeeditor_import_mission"), "", i18n.tr("mission_filter"))
        if not path:
            return
        try:
            waypoints = import_inav_mission_json(path)
        except MissionValidationError as exc:
            QMessageBox.critical(self, i18n.tr("msgbox_mission_invalid_title"), str(exc))
            return
        self._reload_rows(waypoints)

    def _check_terrain(self) -> None:
        waypoints = self.updated_waypoints()
        self.setCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            clearances = check_terrain_clearance(waypoints)
        except TerrainLookupError as exc:
            QMessageBox.critical(self, i18n.tr("msgbox_terrain_failed_title"), str(exc))
            return
        finally:
            self.unsetCursor()

        for row, clearance in enumerate(clearances):
            if clearance < 0:
                color = _COLOR_COLLISION
            elif clearance < TERRAIN_MARGIN_M:
                color = _COLOR_WARNING
            else:
                color = _COLOR_CLEAR
            for col in (COL_INDEX, COL_LAT, COL_LON):
                item = self._table.item(row, col)
                if item is not None:
                    item.setBackground(color)
                    item.setToolTip(i18n.tr("routeeditor_terrain_tooltip", clearance=f"{clearance:.0f}"))
