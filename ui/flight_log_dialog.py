"""Configure which telemetry fields to log and at what interval."""
from __future__ import annotations

from typing import List

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from core import i18n
from export.flight_logger import ALL_FIELDS

FIELD_LABEL_KEYS = {
    "timestamp": "logfield_timestamp",
    "lat": "logfield_lat",
    "lon": "logfield_lon",
    "alt": "logfield_alt",
    "satellites": "logfield_satellites",
    "gps_fix": "logfield_gps_fix",
    "heading": "logfield_heading",
    "roll": "logfield_roll",
    "pitch": "logfield_pitch",
    "flight_mode": "logfield_flight_mode",
    "battery_voltage": "logfield_battery_voltage",
    "battery_remaining": "logfield_battery_remaining",
    "battery_current": "logfield_battery_current",
    "battery_capacity_used": "logfield_battery_capacity_used",
    "cell_voltages": "logfield_cell_voltages",
    "rssi": "logfield_rssi",
    "link_quality": "logfield_link_quality",
    "snr": "logfield_snr",
    "tx_power": "logfield_tx_power",
    "vario": "logfield_vario",
    "baro_altitude": "logfield_baro_altitude",
    "rpm": "logfield_rpm",
    "temperature": "logfield_temperature",
    "groundspeed": "logfield_groundspeed",
    "airspeed": "logfield_airspeed",
    "connected": "logfield_connected",
}


class FlightLogSettingsDialog(QDialog):
    def __init__(self, selected_fields: List[str], interval_s: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("logdialog_title"))

        self._checkboxes = {}
        fields_box = QGroupBox(i18n.tr("logdialog_fields"))
        grid = QGridLayout(fields_box)
        cols = 3
        for idx, field in enumerate(ALL_FIELDS):
            cb = QCheckBox(i18n.tr(FIELD_LABEL_KEYS[field]))
            cb.setChecked(field in selected_fields)
            self._checkboxes[field] = cb
            grid.addWidget(cb, idx // cols, idx % cols)

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel(i18n.tr("logdialog_interval")))
        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setRange(0.1, 60.0)
        self._interval_spin.setSingleStep(0.1)
        self._interval_spin.setSuffix(" s")
        self._interval_spin.setValue(interval_s)
        interval_row.addWidget(self._interval_spin)
        interval_row.addStretch(1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(fields_box)
        layout.addLayout(interval_row)
        layout.addWidget(button_box)

    def selected_fields(self) -> List[str]:
        return [f for f in ALL_FIELDS if self._checkboxes[f].isChecked()]

    def interval_s(self) -> float:
        return self._interval_spin.value()
