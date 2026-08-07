"""Telemetry dashboard bar: GPS / link quality / battery / connection status."""
from __future__ import annotations

from PyQt6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.telemetry_state import TelemetryState

_NA = "--"


def _value_label() -> QLabel:
    lbl = QLabel(_NA)
    lbl.setStyleSheet("font-weight: 600; font-size: 13px;")
    return lbl


class _Field(QWidget):
    def __init__(self, caption: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)
        cap = QLabel(caption)
        cap.setStyleSheet("color: #9aa4b2; font-size: 10px;")
        self.value = _value_label()
        layout.addWidget(cap)
        layout.addWidget(self.value)

    def set_text(self, text: str) -> None:
        self.value.setText(text)


class Dashboard(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(12)

        self.gps_lat = _Field("Lat")
        self.gps_lon = _Field("Lon")
        self.gps_alt = _Field("Alt (m)")
        self.gps_sats = _Field("Sats")
        root.addWidget(self._group("GPS", [self.gps_lat, self.gps_lon, self.gps_alt, self.gps_sats]))

        self.mode = _Field("Flight Mode")
        root.addWidget(self._group("Status", [self.mode]))

        self.rssi = _Field("RSSI (dBm)")
        self.lq = _Field("LQ (%)")
        self.snr = _Field("SNR (dB)")
        self.tx_power = _Field("TX Power (mW)")
        root.addWidget(self._group("Link", [self.rssi, self.lq, self.snr, self.tx_power]))

        self.voltage = _Field("Voltage (V)")
        self.remaining = _Field("Remaining (%)")
        root.addWidget(self._group("Battery", [self.voltage, self.remaining]))

        self.conn_dot = QLabel("●")
        self.conn_text = QLabel("Getrennt")
        conn_box = QVBoxLayout()
        conn_row = QHBoxLayout()
        conn_row.addWidget(self.conn_dot)
        conn_row.addWidget(self.conn_text)
        conn_wrap = QWidget()
        conn_wrap.setLayout(conn_row)
        conn_box.addWidget(conn_wrap)
        conn_group = QGroupBox("Verbindung")
        conn_group.setLayout(conn_box)
        root.addWidget(conn_group)

        root.addStretch(1)
        self.set_connection_status(False)

    @staticmethod
    def _group(title: str, fields: list) -> QGroupBox:
        box = QGroupBox(title)
        layout = QHBoxLayout(box)
        layout.setSpacing(10)
        for f in fields:
            layout.addWidget(f)
        return box

    def update_state(self, state: TelemetryState) -> None:
        self.gps_lat.set_text(f"{state.lat:.6f}" if state.lat is not None else _NA)
        self.gps_lon.set_text(f"{state.lon:.6f}" if state.lon is not None else _NA)
        self.gps_alt.set_text(f"{state.alt:.1f}" if state.alt is not None else _NA)
        self.gps_sats.set_text(str(state.satellites) if state.satellites is not None else _NA)

        self.mode.set_text(state.flight_mode or _NA)

        self.rssi.set_text(str(state.rssi) if state.rssi is not None else _NA)
        self.lq.set_text(str(state.link_quality) if state.link_quality is not None else _NA)
        self.snr.set_text(f"{state.snr:.1f}" if state.snr is not None else _NA)
        self.tx_power.set_text(str(state.tx_power) if state.tx_power is not None else _NA)

        self.voltage.set_text(f"{state.battery_voltage:.2f}" if state.battery_voltage is not None else _NA)
        self.remaining.set_text(str(state.battery_remaining) if state.battery_remaining is not None else _NA)

        self.set_connection_status(state.connected)

    def set_connection_status(self, connected: bool) -> None:
        color = "#2ecc71" if connected else "#e74c3c"
        self.conn_dot.setStyleSheet(f"color: {color}; font-size: 16px;")
        self.conn_text.setText("Verbunden" if connected else "Getrennt")
