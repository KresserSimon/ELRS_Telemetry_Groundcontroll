"""Dialog for core/grid_pattern.py's zigzag survey-route generator: pick a
rectangle (two corners) or a circle (center + radius), a scan line spacing/
angle, and a survey altitude. On accept, the generated waypoints replace
the current route - same semantics as importing a route from a file.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from core import i18n
from core.grid_pattern import generate_grid_route
from core.route import Waypoint


def _latlon_spin(range_deg: float, initial: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(-range_deg, range_deg)
    spin.setDecimals(6)
    spin.setValue(initial)
    return spin


class GridPatternDialog(QDialog):
    def __init__(self, center_default: Tuple[float, float], live_position: Optional[Tuple[float, float]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("gridpattern_title"))
        self.resize(380, 420)

        self._waypoints: List[Waypoint] = []
        lat0, lon0 = center_default

        self._mode_group = QButtonGroup(self)
        self._corners_radio = QRadioButton(i18n.tr("gridpattern_mode_corners"))
        self._radius_radio = QRadioButton(i18n.tr("gridpattern_mode_radius"))
        self._mode_group.addButton(self._corners_radio)
        self._mode_group.addButton(self._radius_radio)
        self._corners_radio.setChecked(True)

        self._corners_box = QGroupBox()
        corners_form = QFormLayout(self._corners_box)
        self._lat1_spin = _latlon_spin(90.0, lat0 - 0.002)
        self._lon1_spin = _latlon_spin(180.0, lon0 - 0.003)
        self._lat2_spin = _latlon_spin(90.0, lat0 + 0.002)
        self._lon2_spin = _latlon_spin(180.0, lon0 + 0.003)
        corners_form.addRow(i18n.tr("gridpattern_corner1"), self._lat1_spin)
        corners_form.addRow("", self._lon1_spin)
        corners_form.addRow(i18n.tr("gridpattern_corner2"), self._lat2_spin)
        corners_form.addRow("", self._lon2_spin)

        self._radius_box = QGroupBox()
        radius_form = QFormLayout(self._radius_box)
        self._center_lat_spin = _latlon_spin(90.0, lat0)
        self._center_lon_spin = _latlon_spin(180.0, lon0)
        self._radius_spin = QDoubleSpinBox()
        self._radius_spin.setRange(1.0, 100000.0)
        self._radius_spin.setValue(200.0)
        self._radius_spin.setSuffix(" m")
        radius_form.addRow(i18n.tr("gridpattern_center"), self._center_lat_spin)
        radius_form.addRow("", self._center_lon_spin)
        radius_form.addRow(i18n.tr("gridpattern_radius"), self._radius_spin)

        use_live_btn = QPushButton(i18n.tr("home_use_current_btn"))
        use_live_btn.setEnabled(live_position is not None)
        use_live_btn.clicked.connect(lambda: self._use_live(live_position))

        common_form = QFormLayout()
        self._spacing_spin = QDoubleSpinBox()
        self._spacing_spin.setRange(1.0, 5000.0)
        self._spacing_spin.setValue(50.0)
        self._spacing_spin.setSuffix(" m")
        self._angle_spin = QDoubleSpinBox()
        self._angle_spin.setRange(0.0, 359.0)
        self._angle_spin.setValue(0.0)
        self._angle_spin.setSuffix(" °")
        self._altitude_spin = QDoubleSpinBox()
        self._altitude_spin.setRange(-1000.0, 10000.0)
        self._altitude_spin.setValue(50.0)
        self._altitude_spin.setSuffix(" m")
        common_form.addRow(i18n.tr("gridpattern_spacing"), self._spacing_spin)
        common_form.addRow(i18n.tr("gridpattern_angle"), self._angle_spin)
        common_form.addRow(i18n.tr("gridpattern_altitude"), self._altitude_spin)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._corners_radio)
        layout.addWidget(self._corners_box)
        layout.addWidget(self._radius_radio)
        layout.addWidget(self._radius_box)
        layout.addWidget(use_live_btn)
        layout.addLayout(common_form)
        layout.addWidget(button_box)

        self._corners_radio.toggled.connect(self._update_mode_visibility)
        self._update_mode_visibility()

    def _update_mode_visibility(self) -> None:
        self._corners_box.setVisible(self._corners_radio.isChecked())
        self._radius_box.setVisible(self._radius_radio.isChecked())

    def _use_live(self, live_position: Optional[Tuple[float, float]]) -> None:
        if live_position is None:
            return
        lat, lon = live_position
        if self._corners_radio.isChecked():
            self._lat1_spin.setValue(lat - 0.002)
            self._lon1_spin.setValue(lon - 0.003)
            self._lat2_spin.setValue(lat + 0.002)
            self._lon2_spin.setValue(lon + 0.003)
        else:
            self._center_lat_spin.setValue(lat)
            self._center_lon_spin.setValue(lon)

    def _on_accept(self) -> None:
        try:
            if self._corners_radio.isChecked():
                waypoints = generate_grid_route(
                    corners=(
                        (self._lat1_spin.value(), self._lon1_spin.value()),
                        (self._lat2_spin.value(), self._lon2_spin.value()),
                    ),
                    spacing_m=self._spacing_spin.value(),
                    angle_deg=self._angle_spin.value(),
                    altitude_m=self._altitude_spin.value(),
                )
            else:
                waypoints = generate_grid_route(
                    center=(self._center_lat_spin.value(), self._center_lon_spin.value()),
                    radius_m=self._radius_spin.value(),
                    spacing_m=self._spacing_spin.value(),
                    angle_deg=self._angle_spin.value(),
                    altitude_m=self._altitude_spin.value(),
                )
        except ValueError as exc:
            QMessageBox.critical(self, i18n.tr("gridpattern_error_title"), str(exc))
            return

        self._waypoints = waypoints
        self.accept()

    def waypoints(self) -> List[Waypoint]:
        return self._waypoints
