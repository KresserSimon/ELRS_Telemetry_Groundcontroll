"""Draggable map overlay that IS the waypoint editor - not a separate modal
dialog. The route summary (waypoint count / total distance) sits above an
always-live table of every waypoint's lat/lon/alt/name and INAV mission
parameters. Edits apply immediately to the shared RouteManager, the same
"live view onto shared state" model every other overlay (artificial
horizon, ...) already uses, rather than an edit-then-OK dialog flow.
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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
from ui.draggable_overlay import DraggableOverlay

COL_INDEX, COL_LAT, COL_LON, COL_ALT, COL_NAME, COL_ACTION, COL_SPEED, COL_P1, COL_P2, COL_P3 = range(10)

# Below this clearance (metres) a waypoint is flagged as a likely terrain
# collision - a small positive buffer, not just >0, to allow for the public
# elevation API's sampling being coarser than the actual flight path.
TERRAIN_MARGIN_M = 20.0
_COLOR_COLLISION = QColor(255, 120, 120)
_COLOR_WARNING = QColor(255, 220, 130)
_COLOR_CLEAR = QColor(160, 230, 160)

PANEL_BG = "rgba(18, 22, 28, 235)"
BORDER = "#0d1117"


def format_distance(meters: float) -> str:
    if meters >= 1000:
        return f"{meters / 1000:.2f} km"
    return f"{meters:.0f} m"


class RouteEditorOverlay(DraggableOverlay):
    """waypoints_edited fires whenever the user edits a field in place;
    MainWindow applies it straight back to RouteManager."""

    waypoints_edited = pyqtSignal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"RouteEditorOverlay {{ background-color: {PANEL_BG}; "
            f"border: 1px solid {BORDER}; border-radius: 10px; }}"
        )
        self.setFixedWidth(660)
        self.setMaximumHeight(360)

        self._waypoints: List[Waypoint] = []
        self._waypoint_count = 0
        self._total_distance = 0.0
        # True while a commit initiated by this widget round-trips back
        # through MainWindow -> RouteManager -> set_waypoints(): the table
        # already shows the edited value verbatim, so skip rebuilding it
        # (which would tear down the very widget the user is still editing).
        self._self_originated = False
        self._building = False

        self._alt_spins: List[QDoubleSpinBox] = []
        self._name_edits: List[QLineEdit] = []
        self._action_combos: List[QComboBox] = []
        self._speed_spins: List[QDoubleSpinBox] = []
        self._p1_spins: List[QSpinBox] = []
        self._p2_spins: List[QSpinBox] = []
        self._p3_spins: List[QSpinBox] = []

        self._header_label = QLabel()
        self._header_label.setStyleSheet(
            "color: #ffffff; font-weight: 700; font-size: 12px; background: transparent; padding: 8px 10px 0 10px;"
        )
        # Let clicks on the (non-interactive) header fall through to this
        # widget's own mousePressEvent so it stays the drag handle.
        self._header_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._summary_label = QLabel()
        self._summary_label.setStyleSheet(
            "color: #c7cfda; font-size: 11px; background: transparent; padding: 0 10px 6px 10px;"
        )
        self._summary_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._table = QTableWidget(0, 10, self)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)

        export_btn = QPushButton()
        export_btn.clicked.connect(self._export_mission)
        import_btn = QPushButton()
        import_btn.clicked.connect(self._import_mission)
        terrain_btn = QPushButton()
        terrain_btn.clicked.connect(self._check_terrain)
        self._export_btn, self._import_btn, self._terrain_btn = export_btn, import_btn, terrain_btn

        button_row = QHBoxLayout()
        button_row.setContentsMargins(10, 4, 10, 8)
        button_row.addWidget(export_btn)
        button_row.addWidget(import_btn)
        button_row.addWidget(terrain_btn)
        button_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header_label)
        layout.addWidget(self._summary_label)
        layout.addWidget(self._table, 1)
        layout.addLayout(button_row)

        i18n.on_language_changed(self.retranslate)
        self.retranslate()

    # ------------------------------------------------------------- display

    def set_waypoints(self, waypoints: List[Waypoint], segment_distances: Optional[List[float]] = None) -> None:
        self._waypoints = list(waypoints)
        self._waypoint_count = len(self._waypoints)
        self._total_distance = sum(segment_distances) if segment_distances else 0.0
        self._update_summary()

        if self._self_originated:
            self._self_originated = False
            return
        self._rebuild_table()

    def _update_summary(self) -> None:
        self._summary_label.setText(
            i18n.tr("routeoverlay_summary", count=self._waypoint_count, distance=format_distance(self._total_distance))
        )

    def retranslate(self) -> None:
        self._header_label.setText(i18n.tr("routeeditor_title"))
        self._update_summary()
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
        self._export_btn.setText(i18n.tr("routeeditor_export_mission"))
        self._import_btn.setText(i18n.tr("routeeditor_import_mission"))
        self._terrain_btn.setText(i18n.tr("routeeditor_check_terrain"))

    # ---------------------------------------------------------------- table

    def _rebuild_table(self) -> None:
        self._building = True
        try:
            self._table.setRowCount(len(self._waypoints))
            self._alt_spins.clear()
            self._name_edits.clear()
            self._action_combos.clear()
            self._speed_spins.clear()
            self._p1_spins.clear()
            self._p2_spins.clear()
            self._p3_spins.clear()
            for row, wp in enumerate(self._waypoints):
                self._add_row(row, wp)
            self._table.resizeColumnsToContents()
        finally:
            self._building = False

    def _add_row(self, row: int, wp: Waypoint) -> None:
        self._table.setItem(row, COL_INDEX, self._readonly_item(str(row + 1)))
        self._table.setItem(row, COL_LAT, self._readonly_item(f"{wp.lat:.6f}"))
        self._table.setItem(row, COL_LON, self._readonly_item(f"{wp.lon:.6f}"))

        alt_spin = QDoubleSpinBox()
        alt_spin.setRange(-1000.0, 10000.0)
        alt_spin.setDecimals(1)
        alt_spin.setSuffix(" m")
        alt_spin.setValue(wp.alt if wp.alt is not None else 0.0)
        alt_spin.valueChanged.connect(self._commit)
        self._table.setCellWidget(row, COL_ALT, alt_spin)
        self._alt_spins.append(alt_spin)

        name_edit = QLineEdit(wp.name)
        name_edit.editingFinished.connect(self._commit)
        self._table.setCellWidget(row, COL_NAME, name_edit)
        self._name_edits.append(name_edit)

        action_combo = QComboBox()
        action_combo.addItems([a.value for a in MissionAction])
        idx = action_combo.findText(wp.action)
        action_combo.setCurrentIndex(idx if idx >= 0 else 0)
        action_combo.currentIndexChanged.connect(self._commit)
        self._table.setCellWidget(row, COL_ACTION, action_combo)
        self._action_combos.append(action_combo)

        speed_spin = QDoubleSpinBox()
        speed_spin.setRange(0.0, 100.0)
        speed_spin.setDecimals(1)
        speed_spin.setValue(wp.speed)
        speed_spin.valueChanged.connect(self._commit)
        self._table.setCellWidget(row, COL_SPEED, speed_spin)
        self._speed_spins.append(speed_spin)

        p1 = QSpinBox()
        p1.setRange(-32768, 32767)
        p1.setValue(wp.p1)
        p1.valueChanged.connect(self._commit)
        self._table.setCellWidget(row, COL_P1, p1)
        self._p1_spins.append(p1)

        p2 = QSpinBox()
        p2.setRange(-32768, 32767)
        p2.setValue(wp.p2)
        p2.valueChanged.connect(self._commit)
        self._table.setCellWidget(row, COL_P2, p2)
        self._p2_spins.append(p2)

        p3 = QSpinBox()
        p3.setRange(-32768, 32767)
        p3.setValue(wp.p3)
        p3.valueChanged.connect(self._commit)
        self._table.setCellWidget(row, COL_P3, p3)
        self._p3_spins.append(p3)

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _read_table(self) -> List[Waypoint]:
        return [
            Waypoint(
                wp.lat, wp.lon, alt_spin.value(), name_edit.text(),
                action=action_combo.currentText(),
                speed=speed_spin.value(),
                p1=p1.value(), p2=p2.value(), p3=p3.value(),
            )
            for wp, alt_spin, name_edit, action_combo, speed_spin, p1, p2, p3 in zip(
                self._waypoints, self._alt_spins, self._name_edits, self._action_combos,
                self._speed_spins, self._p1_spins, self._p2_spins, self._p3_spins,
            )
        ]

    def _commit(self) -> None:
        if self._building:
            return
        self._self_originated = True
        try:
            self.waypoints_edited.emit(self._read_table())
        finally:
            self._self_originated = False

    # ------------------------------------------------------------- mission

    def _export_mission(self) -> None:
        waypoints = self._read_table() if self._waypoints else []
        if not waypoints:
            QMessageBox.warning(self, i18n.tr("msgbox_no_route_title"), i18n.tr("msgbox_no_route_body"))
            return

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
        # A structural replace, not a field tweak - let set_waypoints() (via
        # MainWindow -> RouteManager) rebuild the table from scratch.
        self.waypoints_edited.emit(waypoints)

    def _check_terrain(self) -> None:
        if not self._waypoints:
            QMessageBox.warning(self, i18n.tr("msgbox_no_route_title"), i18n.tr("msgbox_no_route_body"))
            return
        waypoints = self._read_table()
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
