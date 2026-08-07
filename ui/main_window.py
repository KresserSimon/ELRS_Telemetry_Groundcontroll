"""Main application window: map + dashboard + menus, wired to a telemetry worker."""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QActionGroup
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QWidget,
    QVBoxLayout,
)

from alerts.tts_alert import BatteryAlertMonitor, TTSWorker
from core import i18n
from core.telemetry_state import TelemetryState
from export.track_export import TrackRecorder
from telemetry.crsf_serial_worker import CRSFSerialWorker
from telemetry.crsf_worker import CRSFWorker
from telemetry.demo_worker import DemoWorker
from telemetry.mavlink_worker import MAVLinkWorker
from ui.connection_dialog import ConnectionSettingsDialog
from ui.dashboard import Dashboard
from ui.horizon_widget import HorizonWidget
from ui.map_widget import MapWidget

HEARTBEAT_TIMEOUT_S = 3.0

VEHICLE_TYPES = (("vehicle_quad", "quad"), ("vehicle_wing", "wing"), ("vehicle_plane", "plane"))
LANGUAGES = (("language_de", "de"), ("language_en", "en"))
HORIZON_CORNERS = (
    ("horizon_top_left", "top-left"),
    ("horizon_top_right", "top-right"),
    ("horizon_bottom_left", "bottom-left"),
    ("horizon_bottom_right", "bottom-right"),
)
DEFAULT_HORIZON_CORNER = "top-right"


class MainWindow(QMainWindow):
    def __init__(self, args) -> None:
        super().__init__()
        self._args = args
        i18n.set_language(getattr(args, "lang", "de"))

        self.setWindowTitle("ELRS Ground Station")
        self.resize(1200, 800)

        self._track_recorder = TrackRecorder()
        self._tts_worker = TTSWorker()
        self._tts_worker.start()
        self._battery_monitor = BatteryAlertMonitor(
            self._tts_worker,
            cells=args.cells,
            low_cell_voltage=args.low_cell_voltage,
            critical_cell_voltage=args.critical_cell_voltage,
        )

        self._map = MapWidget()
        self._dashboard = Dashboard()
        self._horizon = HorizonWidget()
        self._map.add_overlay(self._horizon, DEFAULT_HORIZON_CORNER)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._map)
        splitter.addWidget(self._dashboard)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        layout.addWidget(splitter)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())

        self._worker = None
        self._demo_mode = bool(args.demo)

        self._i18n_menus: list[tuple] = []
        self._i18n_actions: list[tuple] = []
        self._build_menu()
        i18n.on_language_changed(self._retranslate_menu)

        self._last_telemetry_time = 0.0
        self._has_fix = False

        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(1000)
        self._heartbeat_timer.timeout.connect(self._check_heartbeat)
        self._heartbeat_timer.start()

        if not self._demo_mode:
            self._show_startup_connection_dialog()

        self._start_worker(demo=self._demo_mode)

    # ---------------------------------------------------------------- menu

    def _build_menu(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("")
        self._i18n_menus.append((file_menu, "menu_file"))
        export_gpx_action = file_menu.addAction("")
        self._i18n_actions.append((export_gpx_action, "menu_file_export_gpx"))
        export_gpx_action.triggered.connect(lambda: self._export_track("gpx"))
        export_kml_action = file_menu.addAction("")
        self._i18n_actions.append((export_kml_action, "menu_file_export_kml"))
        export_kml_action.triggered.connect(lambda: self._export_track("kml"))
        file_menu.addSeparator()
        exit_action = file_menu.addAction("")
        self._i18n_actions.append((exit_action, "menu_file_exit"))
        exit_action.triggered.connect(self.close)

        settings_menu = menu.addMenu("")
        self._i18n_menus.append((settings_menu, "menu_settings"))

        conn_settings_action = settings_menu.addAction("")
        self._i18n_actions.append((conn_settings_action, "menu_connection_settings"))
        conn_settings_action.triggered.connect(self._open_connection_dialog)
        settings_menu.addSeparator()

        view_menu = settings_menu.addMenu("")
        self._i18n_menus.append((view_menu, "menu_view"))
        self._auto_center_action = view_menu.addAction("")
        self._i18n_actions.append((self._auto_center_action, "menu_view_auto_center"))
        self._auto_center_action.setCheckable(True)
        self._auto_center_action.setChecked(True)
        self._auto_center_action.toggled.connect(self._map.set_auto_center)

        jump_action = view_menu.addAction("")
        self._i18n_actions.append((jump_action, "menu_view_jump"))
        jump_action.setShortcut("Ctrl+Home")
        jump_action.triggered.connect(self._map.center_on_current)

        vehicle_menu = view_menu.addMenu("")
        self._i18n_menus.append((vehicle_menu, "menu_view_vehicle"))
        self._vehicle_group = QActionGroup(self)
        self._vehicle_group.setExclusive(True)
        for key, vehicle_id in VEHICLE_TYPES:
            action = vehicle_menu.addAction("")
            self._i18n_actions.append((action, key))
            action.setCheckable(True)
            action.setData(vehicle_id)
            action.setChecked(vehicle_id == "quad")
            self._vehicle_group.addAction(action)
        self._vehicle_group.triggered.connect(lambda action: self._map.set_vehicle_type(action.data()))

        horizon_toggle_action = view_menu.addAction("")
        self._i18n_actions.append((horizon_toggle_action, "menu_view_horizon_toggle"))
        horizon_toggle_action.setCheckable(True)
        horizon_toggle_action.setChecked(True)
        horizon_toggle_action.toggled.connect(self._horizon.setVisible)

        horizon_pos_menu = view_menu.addMenu("")
        self._i18n_menus.append((horizon_pos_menu, "menu_view_horizon_position"))
        self._horizon_pos_group = QActionGroup(self)
        self._horizon_pos_group.setExclusive(True)
        for key, corner in HORIZON_CORNERS:
            action = horizon_pos_menu.addAction("")
            self._i18n_actions.append((action, key))
            action.setCheckable(True)
            action.setData(corner)
            action.setChecked(corner == DEFAULT_HORIZON_CORNER)
            self._horizon_pos_group.addAction(action)
        self._horizon_pos_group.triggered.connect(
            lambda action: self._map.set_overlay_corner(self._horizon, action.data())
        )

        settings_menu.addSeparator()
        lang_menu = settings_menu.addMenu("")
        self._i18n_menus.append((lang_menu, "menu_language"))
        self._lang_group = QActionGroup(self)
        self._lang_group.setExclusive(True)
        for key, lang_code in LANGUAGES:
            action = lang_menu.addAction("")
            self._i18n_actions.append((action, key))
            action.setCheckable(True)
            action.setData(lang_code)
            action.setChecked(lang_code == i18n.get_language())
            self._lang_group.addAction(action)
        self._lang_group.triggered.connect(lambda action: i18n.set_language(action.data()))

        sim_menu = menu.addMenu("")
        self._i18n_menus.append((sim_menu, "menu_simulation"))
        self._demo_action = sim_menu.addAction("")
        self._i18n_actions.append((self._demo_action, "menu_simulation_demo"))
        self._demo_action.setCheckable(True)
        self._demo_action.setChecked(self._demo_mode)
        self._demo_action.toggled.connect(self._toggle_demo_mode)

        self._retranslate_menu()

    def _retranslate_menu(self) -> None:
        for menu_widget, key in self._i18n_menus:
            menu_widget.setTitle(i18n.tr(key))
        for action, key in self._i18n_actions:
            action.setText(i18n.tr(key))

    # ------------------------------------------------------------- worker

    def _start_worker(self, demo: bool) -> None:
        if self._worker is not None:
            self._worker.telemetry_received.disconnect(self._on_telemetry)
            self._worker.connection_changed.disconnect(self._on_connection_changed)
            self._worker.error_occurred.disconnect(self._on_error)
            self._worker.stop()
            self._worker = None

        if demo:
            lat, lon = self._args.demo_center
            self._worker = DemoWorker(center_lat=lat, center_lon=lon, cells=self._args.cells)
        elif self._args.connection == "usb":
            if self._args.protocol == "mavlink":
                self._worker = MAVLinkWorker(
                    connection_type="serial", serial_port=self._args.serial_port, baud=self._args.baud
                )
            else:
                self._worker = CRSFSerialWorker(serial_port=self._args.serial_port, baud=self._args.baud)
        elif self._args.protocol == "mavlink":
            self._worker = MAVLinkWorker(host=self._args.host, port=self._args.port, udp_mode=self._args.udp_mode)
        else:
            self._worker = CRSFWorker(host=self._args.host, port=self._args.port)

        self._worker.telemetry_received.connect(self._on_telemetry)
        self._worker.connection_changed.connect(self._on_connection_changed)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()

        self._has_fix = False
        self._map.clear_path()
        self._track_recorder.clear()

        if demo:
            status = i18n.tr("status_demo_started")
        elif self._args.connection == "usb":
            status = i18n.tr("status_waiting_usb", protocol=self._args.protocol, port=self._args.serial_port)
        else:
            status = i18n.tr("status_waiting_udp", protocol=self._args.protocol, port=self._args.port)
        self.statusBar().showMessage(status)

    def _toggle_demo_mode(self, enabled: bool) -> None:
        self._demo_mode = enabled
        self._start_worker(demo=enabled)

    def _apply_connection_values(self, values: dict) -> None:
        self._args.protocol = values["protocol"]
        self._args.connection = values["connection"]
        self._args.host = values["host"]
        self._args.port = values["port"]
        self._args.udp_mode = values["udp_mode"]
        self._args.serial_port = values["serial_port"]
        self._args.baud = values["baud"]

    def _set_demo_checked_silently(self, checked: bool) -> None:
        self._demo_mode = checked
        self._demo_action.blockSignals(True)
        self._demo_action.setChecked(checked)
        self._demo_action.blockSignals(False)

    def _show_startup_connection_dialog(self) -> None:
        dialog = ConnectionSettingsDialog(self._args, self, show_demo_button=True)
        dialog.setWindowTitle(i18n.tr("conn_startup_title"))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return  # keep whatever was configured via CLI defaults

        if dialog.demo_requested:
            self._set_demo_checked_silently(True)
            return

        values = dialog.result_values()
        if values["connection"] == "usb" and not values["serial_port"]:
            QMessageBox.warning(self, i18n.tr("msgbox_no_usb_title"), i18n.tr("msgbox_no_usb_body"))
            return

        self._apply_connection_values(values)

    def _open_connection_dialog(self) -> None:
        dialog = ConnectionSettingsDialog(self._args, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        values = dialog.result_values()
        if values["connection"] == "usb" and not values["serial_port"]:
            QMessageBox.warning(self, i18n.tr("msgbox_no_usb_title"), i18n.tr("msgbox_no_usb_body"))
            return

        self._apply_connection_values(values)
        self._set_demo_checked_silently(False)
        self._start_worker(demo=False)

    # ------------------------------------------------------------ signals

    def _on_telemetry(self, state: TelemetryState) -> None:
        self._last_telemetry_time = time.time()
        self._dashboard.update_state(state)
        self._horizon.update_attitude(state.roll, state.pitch)

        if state.has_gps_fix():
            self._map.update_position(state.lat, state.lon, state.heading)
            self._track_recorder.add_point(state)
            self._has_fix = True

        self._battery_monitor.check(state)

    def _on_connection_changed(self, connected: bool) -> None:
        self.statusBar().showMessage(i18n.tr("status_connected" if connected else "status_disconnected"))

    def _on_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 5000)

    def _check_heartbeat(self) -> None:
        if self._last_telemetry_time == 0:
            return
        if (time.time() - self._last_telemetry_time) > HEARTBEAT_TIMEOUT_S:
            self._dashboard.set_connection_status(False)

    # ------------------------------------------------------------- export

    def _export_track(self, fmt: str) -> None:
        if len(self._track_recorder) == 0:
            QMessageBox.warning(self, i18n.tr("msgbox_no_track_title"), i18n.tr("msgbox_no_track_body"))
            return

        filter_str = i18n.tr("export_gpx_filter" if fmt == "gpx" else "export_kml_filter")
        default_name = f"flight_{time.strftime('%Y%m%d_%H%M%S')}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, i18n.tr("export_dialog_title"), default_name, filter_str)
        if not path:
            return

        try:
            if fmt == "gpx":
                self._track_recorder.export_gpx(path)
            else:
                self._track_recorder.export_kml(path)
        except OSError as exc:
            QMessageBox.critical(self, i18n.tr("msgbox_export_failed_title"), str(exc))
            return

        self.statusBar().showMessage(i18n.tr("status_track_saved", path=path), 5000)

    # -------------------------------------------------------------- close

    def closeEvent(self, event) -> None:
        if self._worker is not None:
            self._worker.stop()
        self._tts_worker.stop()
        super().closeEvent(event)
