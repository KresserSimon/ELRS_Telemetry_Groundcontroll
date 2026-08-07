"""Runtime dialog to switch transport (WiFi/UDP <-> USB/seriell) and protocol
(MAVLink <-> CRSF) without restarting the app.
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
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from core import i18n
from telemetry.serial_ports import list_serial_ports

DEFAULT_UDP_PORT = {"mavlink": 14550, "crsf": 14551}
DEFAULT_BAUD = {"mavlink": 57600, "crsf": 420000}


class ConnectionSettingsDialog(QDialog):
    def __init__(self, args, parent=None, show_demo_button: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("conn_dialog_title"))
        self.demo_requested = False

        self._protocol_group = QButtonGroup(self)
        self._mavlink_radio = QRadioButton(i18n.tr("conn_mavlink"))
        self._crsf_radio = QRadioButton(i18n.tr("conn_crsf"))
        self._protocol_group.addButton(self._mavlink_radio)
        self._protocol_group.addButton(self._crsf_radio)

        self._transport_group = QButtonGroup(self)
        self._udp_radio = QRadioButton(i18n.tr("conn_udp_radio"))
        self._usb_radio = QRadioButton(i18n.tr("conn_usb_radio"))
        self._transport_group.addButton(self._udp_radio)
        self._transport_group.addButton(self._usb_radio)

        protocol_box = QGroupBox(i18n.tr("conn_protocol_box"))
        protocol_layout = QHBoxLayout(protocol_box)
        protocol_layout.addWidget(self._mavlink_radio)
        protocol_layout.addWidget(self._crsf_radio)

        transport_box = QGroupBox(i18n.tr("conn_transport_box"))
        transport_layout = QHBoxLayout(transport_box)
        transport_layout.addWidget(self._udp_radio)
        transport_layout.addWidget(self._usb_radio)

        self._udp_group = QGroupBox(i18n.tr("conn_udp_group"))
        udp_form = QFormLayout(self._udp_group)
        self._host_edit = QLineEdit(args.host)
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(args.port)
        self._udp_mode_combo = QComboBox()
        self._udp_mode_combo.addItems(["listen", "connect"])
        self._udp_mode_combo.setCurrentText(args.udp_mode)
        udp_form.addRow(i18n.tr("conn_host_label"), self._host_edit)
        udp_form.addRow(i18n.tr("conn_port_label"), self._port_spin)
        udp_form.addRow(i18n.tr("conn_mode_label"), self._udp_mode_combo)

        self._usb_group = QGroupBox(i18n.tr("conn_usb_group"))
        usb_form = QFormLayout(self._usb_group)
        port_row = QHBoxLayout()
        self._serial_combo = QComboBox()
        self._serial_combo.setEditable(True)
        refresh_btn = QPushButton(i18n.tr("conn_refresh_btn"))
        refresh_btn.clicked.connect(lambda: self._refresh_serial_ports())
        port_row.addWidget(self._serial_combo, 1)
        port_row.addWidget(refresh_btn)
        self._baud_spin = QSpinBox()
        self._baud_spin.setRange(1200, 2_000_000)
        self._baud_spin.setValue(args.baud)
        usb_form.addRow(i18n.tr("conn_port_label"), port_row)
        usb_form.addRow(i18n.tr("conn_baud_label"), self._baud_spin)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText(i18n.tr("conn_connect_btn"))
        if show_demo_button:
            demo_btn = button_box.addButton(i18n.tr("conn_demo_btn"), QDialogButtonBox.ButtonRole.ActionRole)
            demo_btn.clicked.connect(self._start_demo)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(protocol_box)
        layout.addWidget(transport_box)
        layout.addWidget(self._udp_group)
        layout.addWidget(self._usb_group)
        layout.addWidget(button_box)

        self._mavlink_radio.setChecked(args.protocol == "mavlink")
        self._crsf_radio.setChecked(args.protocol == "crsf")
        self._udp_radio.setChecked(args.connection == "udp")
        self._usb_radio.setChecked(args.connection == "usb")

        self._udp_radio.toggled.connect(self._update_transport_visibility)
        self._protocol_group.buttonToggled.connect(self._apply_protocol_defaults)
        self._usb_radio.toggled.connect(self._on_usb_selected)

        self._refresh_serial_ports(preselect=args.serial_port)
        self._update_transport_visibility()

    def _on_usb_selected(self, checked: bool) -> None:
        if checked:
            # Re-scan on switching to USB so devices plugged in after opening
            # the dialog show up without needing the manual search button.
            self._refresh_serial_ports(preselect=self._selected_serial_port())

    def _start_demo(self) -> None:
        self.demo_requested = True
        self.accept()

    def _update_transport_visibility(self) -> None:
        self._udp_group.setVisible(self._udp_radio.isChecked())
        self._usb_group.setVisible(self._usb_radio.isChecked())

    def _apply_protocol_defaults(self, button, checked) -> None:
        if not checked:
            return
        protocol = "mavlink" if button is self._mavlink_radio else "crsf"
        self._port_spin.setValue(DEFAULT_UDP_PORT[protocol])
        self._baud_spin.setValue(DEFAULT_BAUD[protocol])

    def _refresh_serial_ports(self, preselect: str = "") -> None:
        self._serial_combo.clear()
        for p in list_serial_ports():
            label = f"{p.device} - {p.description}" if p.description else p.device
            self._serial_combo.addItem(label, p.device)

        if preselect:
            idx = self._serial_combo.findData(preselect)
            if idx >= 0:
                self._serial_combo.setCurrentIndex(idx)
            else:
                self._serial_combo.setEditText(preselect)

    def _selected_serial_port(self) -> str:
        data = self._serial_combo.currentData()
        if data:
            return data
        return self._serial_combo.currentText().strip()

    def result_values(self) -> dict:
        return {
            "protocol": "mavlink" if self._mavlink_radio.isChecked() else "crsf",
            "connection": "udp" if self._udp_radio.isChecked() else "usb",
            "host": self._host_edit.text().strip() or "0.0.0.0",
            "port": self._port_spin.value(),
            "udp_mode": self._udp_mode_combo.currentText(),
            "serial_port": self._selected_serial_port(),
            "baud": self._baud_spin.value(),
        }
