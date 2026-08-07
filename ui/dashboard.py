"""Telemetry dashboard bar: GPS / link quality / battery / connection status."""
from __future__ import annotations

import math

from PyQt6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core import i18n
from core.telemetry_state import TelemetryState
from ui import icons

_NA = "--"


def _value_label() -> QLabel:
    lbl = QLabel(_NA)
    lbl.setStyleSheet("font-weight: 600; font-size: 13px;")
    return lbl


def _icon_label(pixmap) -> QLabel:
    lbl = QLabel()
    lbl.setPixmap(pixmap)
    lbl.setFixedSize(icons.SIZE, icons.SIZE)
    return lbl


class _Field(QWidget):
    def __init__(self, caption_key: str) -> None:
        super().__init__()
        self._caption_key = caption_key
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)
        self.caption_label = QLabel(i18n.tr(caption_key))
        self.caption_label.setStyleSheet("color: #9aa4b2; font-size: 10px;")
        self.value = _value_label()
        layout.addWidget(self.caption_label)
        layout.addWidget(self.value)

    def set_text(self, text: str) -> None:
        self.value.setText(text)

    def retranslate(self) -> None:
        self.caption_label.setText(i18n.tr(self._caption_key))


class Dashboard(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._fields: list[_Field] = []
        self._group_boxes: list[tuple[QGroupBox, str]] = []
        self._connected = False

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(12)

        self.gps_lat = _Field("dash_lat")
        self.gps_lon = _Field("dash_lon")
        self.gps_alt = _Field("dash_alt")
        self.gps_sats = _Field("dash_sats")
        root.addWidget(self._group("dash_gps", [self.gps_lat, self.gps_lon, self.gps_alt, self.gps_sats],
                                    icons.gps_icon()))

        self.mode = _Field("dash_flight_mode")
        root.addWidget(self._group("dash_status", [self.mode], icons.drone_icon()))

        self.rssi = _Field("dash_rssi")
        self.lq = _Field("dash_lq")
        self.snr = _Field("dash_snr")
        self.tx_power = _Field("dash_tx_power")
        self.link_icon_label = _icon_label(icons.signal_icon(-1))
        root.addWidget(self._group("dash_link", [self.rssi, self.lq, self.snr, self.tx_power],
                                    icon_label=self.link_icon_label))

        self.voltage = _Field("dash_voltage")
        self.remaining = _Field("dash_remaining")
        self.battery_icon_label = _icon_label(icons.battery_icon(None))
        root.addWidget(self._group("dash_battery", [self.voltage, self.remaining],
                                    icon_label=self.battery_icon_label))

        self.conn_icon_label = _icon_label(icons.status_led_icon(False))
        self.conn_text = QLabel()
        self.conn_text.setStyleSheet("font-weight: 600; font-size: 13px;")
        conn_row = QHBoxLayout()
        conn_row.setSpacing(6)
        conn_row.addWidget(self.conn_icon_label)
        conn_row.addWidget(self.conn_text)
        conn_wrap = QWidget()
        conn_wrap.setLayout(conn_row)
        conn_box = QVBoxLayout()
        conn_box.addWidget(conn_wrap)
        conn_group = QGroupBox()
        conn_group.setLayout(conn_box)
        self._group_boxes.append((conn_group, "dash_connection"))
        root.addWidget(conn_group)

        root.addStretch(1)
        self.set_connection_status(False)
        self.retranslate()

        i18n.on_language_changed(self.retranslate)

    def _group(self, title_key: str, fields: list, icon_pixmap=None, icon_label: QLabel = None) -> QGroupBox:
        box = QGroupBox()
        self._group_boxes.append((box, title_key))
        layout = QHBoxLayout(box)
        layout.setSpacing(10)
        if icon_label is None and icon_pixmap is not None:
            icon_label = _icon_label(icon_pixmap)
        if icon_label is not None:
            layout.addWidget(icon_label)
        for f in fields:
            layout.addWidget(f)
            self._fields.append(f)
        return box

    def retranslate(self) -> None:
        for box, key in self._group_boxes:
            box.setTitle(i18n.tr(key))
        for field in self._fields:
            field.retranslate()
        self.conn_text.setText(i18n.tr("dash_connected" if self._connected else "dash_disconnected"))

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

        link_level = -1 if state.link_quality is None else max(0, min(4, math.ceil(state.link_quality / 25)))
        self.link_icon_label.setPixmap(icons.signal_icon(link_level))

        self.voltage.set_text(f"{state.battery_voltage:.2f}" if state.battery_voltage is not None else _NA)
        self.remaining.set_text(str(state.battery_remaining) if state.battery_remaining is not None else _NA)
        self.battery_icon_label.setPixmap(icons.battery_icon(state.battery_remaining))

        self.set_connection_status(state.connected)

    def set_connection_status(self, connected: bool) -> None:
        self._connected = connected
        self.conn_icon_label.setPixmap(icons.status_led_icon(connected))
        self.conn_text.setText(i18n.tr("dash_connected" if connected else "dash_disconnected"))
