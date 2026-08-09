"""Dialog to configure and start/stop the antenna-tracker telemetry
output (core/tracker_output.py) - format (MAVLink/NMEA) and transport
(serial/UDP), mirroring ui/connection_dialog.py's transport toggle UI.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from core import i18n
from core.tracker_output import (
    FORMAT_MAVLINK,
    FORMAT_NMEA,
    MODE_SERIAL,
    MODE_UDP,
    TrackerOutputSender,
)
from telemetry.serial_ports import list_serial_ports

DEFAULT_UDP_PORT = 15550


class TrackerOutputDialog(QDialog):
    def __init__(self, sender: TrackerOutputSender, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("tracker_dialog_title"))
        self._sender = sender
        self._sender.error_occurred.connect(self._on_error)

        self._format_group = QButtonGroup(self)
        self._mavlink_radio = QRadioButton(i18n.tr("tracker_format_mavlink"))
        self._nmea_radio = QRadioButton(i18n.tr("tracker_format_nmea"))
        self._format_group.addButton(self._mavlink_radio)
        self._format_group.addButton(self._nmea_radio)
        self._mavlink_radio.setChecked(True)
        format_box = QGroupBox(i18n.tr("tracker_format_box"))
        format_layout = QHBoxLayout(format_box)
        format_layout.addWidget(self._mavlink_radio)
        format_layout.addWidget(self._nmea_radio)

        self._transport_group = QButtonGroup(self)
        self._udp_radio = QRadioButton(i18n.tr("conn_udp_radio"))
        self._serial_radio = QRadioButton(i18n.tr("conn_usb_radio"))
        self._transport_group.addButton(self._udp_radio)
        self._transport_group.addButton(self._serial_radio)
        self._udp_radio.setChecked(True)
        transport_box = QGroupBox(i18n.tr("conn_transport_box"))
        transport_layout = QHBoxLayout(transport_box)
        transport_layout.addWidget(self._udp_radio)
        transport_layout.addWidget(self._serial_radio)

        self._udp_group = QGroupBox(i18n.tr("conn_udp_group"))
        udp_form = QFormLayout(self._udp_group)
        self._host_edit = QLineEdit("127.0.0.1")
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(DEFAULT_UDP_PORT)
        udp_form.addRow(i18n.tr("conn_host_label"), self._host_edit)
        udp_form.addRow(i18n.tr("conn_port_label"), self._port_spin)

        self._serial_group = QGroupBox(i18n.tr("conn_usb_group"))
        serial_form = QFormLayout(self._serial_group)
        port_row = QHBoxLayout()
        self._serial_combo = QComboBox()
        self._serial_combo.setEditable(True)
        refresh_btn = QPushButton(i18n.tr("conn_refresh_btn"))
        refresh_btn.clicked.connect(self._refresh_serial_ports)
        port_row.addWidget(self._serial_combo, 1)
        port_row.addWidget(refresh_btn)
        self._baud_spin = QSpinBox()
        self._baud_spin.setRange(1200, 2_000_000)
        self._baud_spin.setValue(57600)
        serial_form.addRow(i18n.tr("conn_port_label"), port_row)
        serial_form.addRow(i18n.tr("conn_baud_label"), self._baud_spin)

        self._status_label = QLabel()

        self._start_btn = QPushButton(i18n.tr("tracker_start_btn"))
        self._stop_btn = QPushButton(i18n.tr("tracker_stop_btn"))
        self._start_btn.clicked.connect(self._on_start)
        self._stop_btn.clicked.connect(self._on_stop)
        action_row = QHBoxLayout()
        action_row.addWidget(self._start_btn)
        action_row.addWidget(self._stop_btn)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)
        button_box.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(format_box)
        layout.addWidget(transport_box)
        layout.addWidget(self._udp_group)
        layout.addWidget(self._serial_group)
        layout.addLayout(action_row)
        layout.addWidget(self._status_label)
        layout.addWidget(button_box)

        self._udp_radio.toggled.connect(self._update_transport_visibility)
        self._refresh_serial_ports()
        self._update_transport_visibility()
        self._update_status()

    def _update_transport_visibility(self) -> None:
        self._udp_group.setVisible(self._udp_radio.isChecked())
        self._serial_group.setVisible(self._serial_radio.isChecked())

    def _refresh_serial_ports(self) -> None:
        self._serial_combo.clear()
        for p in list_serial_ports():
            label = f"{p.device} - {p.description}" if p.description else p.device
            self._serial_combo.addItem(label, p.device)

    def _selected_serial_port(self) -> str:
        data = self._serial_combo.currentData()
        if data:
            return data
        return self._serial_combo.currentText().strip()

    def _update_status(self) -> None:
        if self._sender.is_active():
            self._status_label.setText(i18n.tr("tracker_status_active"))
        else:
            self._status_label.setText(i18n.tr("tracker_status_inactive"))

    def _on_start(self) -> None:
        output_format = FORMAT_MAVLINK if self._mavlink_radio.isChecked() else FORMAT_NMEA
        mode = MODE_UDP if self._udp_radio.isChecked() else MODE_SERIAL
        self._sender.start(
            mode,
            output_format,
            serial_port=self._selected_serial_port(),
            baud=self._baud_spin.value(),
            host=self._host_edit.text().strip() or "127.0.0.1",
            port=self._port_spin.value(),
        )
        self._update_status()

    def _on_stop(self) -> None:
        self._sender.stop()
        self._update_status()

    def _on_error(self, message: str) -> None:
        self._status_label.setText(message)
