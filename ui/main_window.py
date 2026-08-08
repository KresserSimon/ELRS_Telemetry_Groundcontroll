"""Main application window: map + dashboard + menus, wired to a telemetry worker."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QActionGroup, QDesktopServices
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
from core.dashboard_config import save_dashboard_layout, save_visible_fields
from core.home_config import load_home_position, save_home_position
from core.nfz import NoFlyZoneManager
from core.route import RouteManager
from core.telemetry_state import TelemetryState
from export.flight_logger import ALL_FIELDS, FlightLogger
from export.nfz_import import import_nfz_file
from export.route_export import export_route_csv, export_route_gpx
from export.route_import import import_route_file
from export.track_export import TrackRecorder
from telemetry.crsf_serial_worker import CRSFSerialWorker
from telemetry.crsf_worker import CRSFWorker
from telemetry.demo_worker import DemoWorker
from telemetry.mavlink_worker import MAVLinkWorker
from ui.battery_settings_dialog import BatterySettingsDialog
from ui.connection_dialog import ConnectionSettingsDialog
from ui.dashboard import Dashboard
from ui.dashboard_settings_dialog import DashboardSettingsDialog
from ui.flight_log_dialog import FlightLogSettingsDialog
from ui.home_position_dialog import HomePositionDialog
from ui.horizon_widget import HorizonWidget
from ui.map_buttons import HeadingModeButton, LockButton
from ui.map_widget import MapWidget
from ui.route_editor_overlay import RouteEditorOverlay
from ui.track_overlay import TrackOverlay

HEARTBEAT_TIMEOUT_S = 3.0

VEHICLE_TYPES = (("vehicle_quad", "quad"), ("vehicle_wing", "wing"), ("vehicle_plane", "plane"))
LANGUAGES = (("language_de", "de"), ("language_en", "en"))
BASE_LAYERS = (("maplayer_osm", "osm"), ("maplayer_satellite", "satellite"))
HORIZON_CORNERS = (
    ("horizon_top_left", "top-left"),
    ("horizon_top_right", "top-right"),
    ("horizon_bottom_left", "bottom-left"),
    ("horizon_bottom_right", "bottom-right"),
)
DEFAULT_HORIZON_CORNER = "top-right"
HORIZON_SCALES = (
    ("horizon_scale_small", 0.75),
    ("horizon_scale_normal", 1.0),
    ("horizon_scale_large", 1.5),
    ("horizon_scale_xlarge", 2.0),
)
DEFAULT_HORIZON_SCALE = 1.0


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
        self._battery_chemistry = "lipo"
        self._battery_cells = args.cells
        self._battery_low_v = args.low_cell_voltage
        self._battery_critical_v = args.critical_cell_voltage

        home_position = load_home_position()
        home_lat, home_lon = home_position if home_position is not None else (None, None)
        self._map = MapWidget(home_lat=home_lat, home_lon=home_lon)
        self._dashboard = Dashboard()
        self._horizon = HorizonWidget()
        self._map.add_overlay(self._horizon, DEFAULT_HORIZON_CORNER)

        self._route_manager = RouteManager()
        self._route_manager.changed.connect(self._on_route_changed)
        self._map.route_bridge.waypoint_added.connect(self._route_manager.add)
        self._map.route_bridge.waypoint_removed.connect(self._route_manager.remove_at)
        self._map.route_bridge.waypoint_added_typed.connect(self._route_manager.add_typed)
        self._map.route_bridge.home_position_picked.connect(self._on_home_position_picked)
        self._map.route_bridge.view_action_triggered.connect(self._on_view_action)

        self._route_overlay = RouteEditorOverlay()
        self._route_overlay.waypoints_edited.connect(self._route_manager.set_all)
        self._map.add_overlay(self._route_overlay, "bottom-left")

        self._track_recording = False
        self._track_overlay = TrackOverlay()
        self._track_overlay.start_pause_clicked.connect(self._toggle_track_recording)
        self._track_overlay.export_clicked.connect(self._export_track_prompt)
        self._map.add_overlay(self._track_overlay, "top-left")

        self._heading_up = False
        self._lock_button = LockButton()
        self._lock_button.clicked.connect(self._toggle_map_lock)
        self._map.add_overlay(self._lock_button, "bottom-right")
        self._heading_button = HeadingModeButton()
        self._heading_button.clicked.connect(self._toggle_heading_mode)
        self._map.add_overlay(self._heading_button, "bottom-right")

        self._nfz_manager = NoFlyZoneManager()
        self._nfz_manager.changed.connect(self._on_nfz_changed)

        self._last_telemetry_state = None
        self._flight_logger = FlightLogger(lambda: self._last_telemetry_state)
        self._log_fields = list(ALL_FIELDS)
        self._log_interval = 1.0

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
        self._plan_mode = False

        self._i18n_menus: list[tuple] = []
        self._i18n_actions: list[tuple] = []
        self._build_menu()
        i18n.on_language_changed(self._retranslate_menu)

        # The menu action's toggled signal is connected above, but that
        # connection postdates its own initial setChecked(True) - sync the
        # button's display explicitly so it doesn't start out looking
        # unlocked while auto-center is actually on.
        self._lock_button.set_locked(self._auto_center_action.isChecked())
        self._heading_button.set_heading_up(self._heading_up)

        self._last_telemetry_time = 0.0
        self._has_fix = False

        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(1000)
        self._heartbeat_timer.timeout.connect(self._check_heartbeat)
        self._heartbeat_timer.start()

        if not self._demo_mode:
            self._show_startup_connection_dialog()

        if not self._plan_mode:
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

        route_menu = menu.addMenu("")
        self._i18n_menus.append((route_menu, "menu_route"))

        self._route_mode_action = route_menu.addAction("")
        self._i18n_actions.append((self._route_mode_action, "menu_route_waypoint_mode"))
        self._route_mode_action.setCheckable(True)
        self._route_mode_action.toggled.connect(self._map.set_route_mode)

        remove_last_wp_action = route_menu.addAction("")
        self._i18n_actions.append((remove_last_wp_action, "menu_route_remove_last"))
        remove_last_wp_action.triggered.connect(self._route_manager.remove_last)

        clear_route_action = route_menu.addAction("")
        self._i18n_actions.append((clear_route_action, "menu_route_clear"))
        clear_route_action.triggered.connect(self._route_manager.clear)

        self._route_editor_action = route_menu.addAction("")
        self._i18n_actions.append((self._route_editor_action, "menu_route_edit"))
        self._route_editor_action.setCheckable(True)
        self._route_editor_action.setChecked(True)
        self._route_editor_action.toggled.connect(self._route_overlay.setVisible)

        route_menu.addSeparator()
        import_route_action = route_menu.addAction("")
        self._i18n_actions.append((import_route_action, "menu_route_import"))
        import_route_action.triggered.connect(self._import_route)

        export_route_action = route_menu.addAction("")
        self._i18n_actions.append((export_route_action, "menu_route_export"))
        export_route_action.triggered.connect(self._export_route)

        map_menu = menu.addMenu("")
        self._i18n_menus.append((map_menu, "menu_map"))

        layer_menu = map_menu.addMenu("")
        self._i18n_menus.append((layer_menu, "menu_map_layer"))
        self._layer_group = QActionGroup(self)
        self._layer_group.setExclusive(True)
        for key, layer_id in BASE_LAYERS:
            action = layer_menu.addAction("")
            self._i18n_actions.append((action, key))
            action.setCheckable(True)
            action.setData(layer_id)
            action.setChecked(layer_id == "osm")
            self._layer_group.addAction(action)
        self._layer_group.triggered.connect(lambda action: self._map.set_base_layer(action.data()))

        map_menu.addSeparator()
        import_nfz_action = map_menu.addAction("")
        self._i18n_actions.append((import_nfz_action, "menu_map_nfz_import"))
        import_nfz_action.triggered.connect(self._import_nfz)

        self._nfz_visible_action = map_menu.addAction("")
        self._i18n_actions.append((self._nfz_visible_action, "menu_map_nfz_visible"))
        self._nfz_visible_action.setCheckable(True)
        self._nfz_visible_action.setChecked(True)
        self._nfz_visible_action.toggled.connect(self._map.set_nfz_visible)

        flightlog_menu = menu.addMenu("")
        self._i18n_menus.append((flightlog_menu, "menu_flightlog"))

        flightlog_settings_action = flightlog_menu.addAction("")
        self._i18n_actions.append((flightlog_settings_action, "menu_flightlog_settings"))
        flightlog_settings_action.triggered.connect(self._open_flight_log_settings)

        self._flightlog_active_action = flightlog_menu.addAction("")
        self._i18n_actions.append((self._flightlog_active_action, "menu_flightlog_active"))
        self._flightlog_active_action.setCheckable(True)
        self._flightlog_active_action.toggled.connect(self._toggle_flight_logging)

        settings_menu = menu.addMenu("")
        self._i18n_menus.append((settings_menu, "menu_settings"))

        conn_settings_action = settings_menu.addAction("")
        self._i18n_actions.append((conn_settings_action, "menu_connection_settings"))
        conn_settings_action.triggered.connect(self._open_connection_dialog)

        battery_settings_action = settings_menu.addAction("")
        self._i18n_actions.append((battery_settings_action, "menu_battery_settings"))
        battery_settings_action.triggered.connect(self._open_battery_settings)

        home_settings_action = settings_menu.addAction("")
        self._i18n_actions.append((home_settings_action, "menu_home_settings"))
        home_settings_action.triggered.connect(self._open_home_settings)

        self._dashboard_settings_action = settings_menu.addAction("")
        self._i18n_actions.append((self._dashboard_settings_action, "menu_dashboard_settings"))
        self._dashboard_settings_action.triggered.connect(self._open_dashboard_settings)
        settings_menu.addSeparator()

        view_menu = settings_menu.addMenu("")
        self._i18n_menus.append((view_menu, "menu_view"))
        self._auto_center_action = view_menu.addAction("")
        self._i18n_actions.append((self._auto_center_action, "menu_view_auto_center"))
        self._auto_center_action.setCheckable(True)
        self._auto_center_action.setChecked(True)
        self._auto_center_action.toggled.connect(self._map.set_auto_center)
        self._auto_center_action.toggled.connect(self._lock_button.set_locked)

        jump_action = view_menu.addAction("")
        self._i18n_actions.append((jump_action, "menu_view_jump"))
        jump_action.setShortcut("Ctrl+Home")
        jump_action.triggered.connect(self._map.center_on_current)

        # Same QAction instance as under Einstellungen - one place to open
        # the dialog, reachable from both menus.
        view_menu.addAction(self._dashboard_settings_action)

        # Same QAction instance as in the Route menu - toggling it from
        # either place (or from the map's right-click view-options submenu)
        # keeps both checkmarks and the overlay's visibility in sync for free.
        view_menu.addAction(self._route_editor_action)

        self._coord_overlay_action = view_menu.addAction("")
        self._i18n_actions.append((self._coord_overlay_action, "menu_view_coords"))
        self._coord_overlay_action.setCheckable(True)
        self._coord_overlay_action.setChecked(False)
        self._coord_overlay_action.toggled.connect(self._map.set_coord_overlay_visible)

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

        horizon_scale_menu = view_menu.addMenu("")
        self._i18n_menus.append((horizon_scale_menu, "menu_view_horizon_scale"))
        self._horizon_scale_group = QActionGroup(self)
        self._horizon_scale_group.setExclusive(True)
        for key, scale in HORIZON_SCALES:
            action = horizon_scale_menu.addAction("")
            self._i18n_actions.append((action, key))
            action.setCheckable(True)
            action.setData(scale)
            action.setChecked(scale == DEFAULT_HORIZON_SCALE)
            self._horizon_scale_group.addAction(action)
        self._horizon_scale_group.triggered.connect(self._set_horizon_scale)

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

        help_menu = menu.addMenu("")
        self._i18n_menus.append((help_menu, "menu_help"))
        manual_action = help_menu.addAction("")
        self._i18n_actions.append((manual_action, "menu_help_manual"))
        manual_action.triggered.connect(self._open_manual)

        sim_menu = menu.addMenu("")
        self._i18n_menus.append((sim_menu, "menu_simulation"))
        self._demo_action = sim_menu.addAction("")
        self._i18n_actions.append((self._demo_action, "menu_simulation_demo"))
        self._demo_action.setCheckable(True)
        self._demo_action.setChecked(self._demo_mode)
        self._demo_action.toggled.connect(self._toggle_demo_mode)

        self._plan_action = sim_menu.addAction("")
        self._i18n_actions.append((self._plan_action, "menu_simulation_plan"))
        self._plan_action.setCheckable(True)
        self._plan_action.setChecked(self._plan_mode)
        self._plan_action.toggled.connect(self._toggle_plan_mode)

        self._retranslate_menu()

    def _retranslate_menu(self) -> None:
        for menu_widget, key in self._i18n_menus:
            menu_widget.setTitle(i18n.tr(key))
        for action, key in self._i18n_actions:
            action.setText(i18n.tr(key))

    # ------------------------------------------------------------- worker

    def _stop_worker(self) -> None:
        if self._worker is not None:
            self._worker.telemetry_received.disconnect(self._on_telemetry)
            self._worker.connection_changed.disconnect(self._on_connection_changed)
            self._worker.error_occurred.disconnect(self._on_error)
            self._worker.stop()
            self._worker = None

    def _start_worker(self, demo: bool) -> None:
        self._stop_worker()
        self._set_plan_mode_checked_silently(False)

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
        self._track_recording = False
        self._track_overlay.set_state(False, 0)
        self._dashboard.reset_session()

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

    def _set_plan_mode_checked_silently(self, checked: bool) -> None:
        self._plan_mode = checked
        self._plan_action.blockSignals(True)
        self._plan_action.setChecked(checked)
        self._plan_action.blockSignals(False)

    def _toggle_plan_mode(self, enabled: bool) -> None:
        self._plan_mode = enabled
        if enabled:
            self._set_demo_checked_silently(False)
            self._stop_worker()
            self._dashboard.reset_session()
            self._map.clear_path()
            self._track_recorder.clear()
            self._track_recording = False
            self._track_overlay.set_state(False, 0)
            # Nothing is flying, and the whole point of Plan Mode is to pan
            # freely while placing waypoints - so release the follow-the-drone
            # lock rather than leaving it fighting the user's own panning.
            self._set_auto_center_checked_silently(False)
            self.statusBar().showMessage(i18n.tr("status_plan_mode_active"))
        else:
            self._start_worker(demo=self._demo_mode)

    def _set_auto_center_checked_silently(self, checked: bool) -> None:
        self._map.set_auto_center(checked)
        self._auto_center_action.blockSignals(True)
        self._auto_center_action.setChecked(checked)
        self._auto_center_action.blockSignals(False)
        # blockSignals() above means the lock button's toggled-signal sync
        # doesn't fire either - update it explicitly so it doesn't show
        # "locked" while auto-center was just silently switched off.
        self._lock_button.set_locked(checked)

    def _toggle_map_lock(self) -> None:
        self._auto_center_action.setChecked(not self._auto_center_action.isChecked())

    def _toggle_heading_mode(self) -> None:
        self._heading_up = not self._heading_up
        self._map.set_heading_mode(self._heading_up)
        self._heading_button.set_heading_up(self._heading_up)

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
        dialog = ConnectionSettingsDialog(self._args, self, show_demo_button=True, show_plan_button=True)
        dialog.setWindowTitle(i18n.tr("conn_startup_title"))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return  # keep whatever was configured via CLI defaults

        if dialog.demo_requested:
            self._set_demo_checked_silently(True)
            return

        if dialog.plan_requested:
            self._plan_action.setChecked(True)
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

    def _open_battery_settings(self) -> None:
        dialog = BatterySettingsDialog(
            self._battery_chemistry, self._battery_cells, self._battery_low_v, self._battery_critical_v, self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._battery_chemistry = dialog.chemistry()
        self._battery_cells = dialog.cells()
        self._battery_low_v = dialog.low_cell_voltage()
        self._battery_critical_v = dialog.critical_cell_voltage()
        self._battery_monitor.configure(self._battery_cells, self._battery_low_v, self._battery_critical_v)

    def _open_home_settings(self) -> None:
        current = load_home_position()
        live_position = None
        if self._last_telemetry_state is not None and self._last_telemetry_state.has_gps_fix():
            live_position = (self._last_telemetry_state.lat, self._last_telemetry_state.lon)

        dialog = HomePositionDialog(current, live_position, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        lat, lon = dialog.home_position()
        save_home_position(lat, lon)
        self._map.center_on_point(lat, lon)
        self.statusBar().showMessage(i18n.tr("status_home_position_saved"), 5000)

    def _open_manual(self) -> None:
        path = self._manual_pdf_path()
        if not path.is_file():
            QMessageBox.warning(self, i18n.tr("msgbox_manual_missing_title"), i18n.tr("msgbox_manual_missing_body"))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @staticmethod
    def _manual_pdf_path() -> Path:
        # PyInstaller sets sys._MEIPASS to the bundled-data directory in
        # both --onefile and --onedir builds; running from source, docs/
        # sits next to this file's grandparent (ui/ -> elrs_ground_station/).
        if getattr(sys, "frozen", False):
            base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        else:
            base = Path(__file__).resolve().parent.parent
        return base / "docs" / "ELRS_Ground_Station_Benutzerhandbuch.pdf"

    def _on_home_position_picked(self, lat: float, lon: float) -> None:
        # Picked via the map's right-click "Als Home setzen" - the user is
        # already looking at exactly that spot, so unlike _open_home_settings()
        # there's no need to also re-center the view on save.
        save_home_position(lat, lon)
        self.statusBar().showMessage(i18n.tr("status_home_position_saved"), 5000)

    def _on_view_action(self, action: str) -> None:
        # Dispatch for the map's right-click "Ansicht" submenu - reuses the
        # exact same toggle methods/actions as the menu bar's View menu so
        # both stay in sync no matter which one the user last touched.
        if action == "lock":
            self._toggle_map_lock()
        elif action == "heading":
            self._toggle_heading_mode()
        elif action == "route_editor":
            self._route_editor_action.setChecked(not self._route_editor_action.isChecked())
        elif action == "coords":
            self._coord_overlay_action.setChecked(not self._coord_overlay_action.isChecked())

    def _set_horizon_scale(self, action) -> None:
        self._horizon.set_scale(action.data())
        self._map.reposition_overlays()

    def _open_dashboard_settings(self) -> None:
        dialog = DashboardSettingsDialog(
            self._dashboard.field_catalog(),
            self._dashboard.visible_fields(),
            self._dashboard.group_order(),
            self._dashboard.rows(),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        keys = dialog.visible_fields()
        self._dashboard.apply_field_visibility(keys)
        save_visible_fields(keys)

        group_order = dialog.group_order()
        rows = dialog.rows()
        self._dashboard.apply_layout(group_order, rows)
        save_dashboard_layout(group_order, rows)

    def _open_flight_log_settings(self) -> None:
        dialog = FlightLogSettingsDialog(self._log_fields, self._log_interval, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        # Only applies to the next time logging is (re)started - changing the
        # column set of an already-open CSV mid-file would corrupt it.
        self._log_fields = dialog.selected_fields()
        self._log_interval = dialog.interval_s()

    def _toggle_flight_logging(self, enabled: bool) -> None:
        if enabled:
            default_name = f"flightlog_{time.strftime('%Y%m%d_%H%M%S')}.csv"
            path, _ = QFileDialog.getSaveFileName(
                self, i18n.tr("flightlog_save_dialog_title"), default_name, i18n.tr("route_csv_filter")
            )
            if not path:
                self._flightlog_active_action.blockSignals(True)
                self._flightlog_active_action.setChecked(False)
                self._flightlog_active_action.blockSignals(False)
                return
            self._flight_logger.start(path, self._log_fields, self._log_interval)
            self.statusBar().showMessage(i18n.tr("status_flightlog_started", path=path), 5000)
        else:
            self._flight_logger.stop()
            self.statusBar().showMessage(i18n.tr("status_flightlog_stopped"), 5000)

    # ------------------------------------------------------------ signals

    def _on_telemetry(self, state: TelemetryState) -> None:
        self._last_telemetry_time = time.time()
        self._last_telemetry_state = state
        self._dashboard.update_state(state)
        self._horizon.update_attitude(state.roll, state.pitch)

        if state.has_gps_fix():
            self._map.update_position(state.lat, state.lon, state.heading)
            if self._track_recording:
                self._track_recorder.add_point(state)
                self._track_overlay.update_count(len(self._track_recorder))
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

    # --------------------------------------------------------------- route

    def _on_route_changed(self) -> None:
        waypoints = self._route_manager.waypoints()
        segments = self._route_manager.segment_distances()
        self._map.render_route(waypoints, segments)
        self._route_overlay.set_waypoints(waypoints, segments)

    def _import_route(self) -> None:
        filter_str = (
            f"{i18n.tr('route_all_supported_filter')};;"
            f"{i18n.tr('export_gpx_filter')};;"
            f"{i18n.tr('route_mission_filter')};;"
            f"{i18n.tr('route_xml_filter')};;"
            f"{i18n.tr('route_csv_filter')}"
        )
        path, _ = QFileDialog.getOpenFileName(self, i18n.tr("menu_route_import"), "", filter_str)
        if not path:
            return

        try:
            waypoints = import_route_file(path)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, i18n.tr("msgbox_route_import_failed_title"), str(exc))
            return

        self._route_manager.set_all(waypoints)
        self.statusBar().showMessage(i18n.tr("status_route_imported", count=len(waypoints)), 5000)

    def _export_route(self) -> None:
        waypoints = self._route_manager.waypoints()
        if not waypoints:
            QMessageBox.warning(self, i18n.tr("msgbox_no_route_title"), i18n.tr("msgbox_no_route_body"))
            return

        filter_str = f"{i18n.tr('export_gpx_filter')};;{i18n.tr('route_csv_filter')}"
        default_name = f"route_{time.strftime('%Y%m%d_%H%M%S')}.gpx"
        path, selected_filter = QFileDialog.getSaveFileName(
            self, i18n.tr("menu_route_export"), default_name, filter_str
        )
        if not path:
            return

        try:
            if path.lower().endswith(".csv") or selected_filter == i18n.tr("route_csv_filter"):
                export_route_csv(waypoints, path)
            else:
                export_route_gpx(waypoints, path)
        except OSError as exc:
            QMessageBox.critical(self, i18n.tr("msgbox_export_failed_title"), str(exc))
            return

        self.statusBar().showMessage(i18n.tr("status_route_exported", path=path), 5000)

    # ----------------------------------------------------------------- map

    def _on_nfz_changed(self) -> None:
        self._map.render_nfz(self._nfz_manager.zones())

    def _import_nfz(self) -> None:
        filter_str = f"{i18n.tr('nfz_geojson_filter')};;{i18n.tr('route_csv_filter')}"
        path, _ = QFileDialog.getOpenFileName(self, i18n.tr("menu_map_nfz_import"), "", filter_str)
        if not path:
            return

        try:
            zones = import_nfz_file(path)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, i18n.tr("msgbox_nfz_import_failed_title"), str(exc))
            return

        self._nfz_manager.set_all(zones)
        self.statusBar().showMessage(i18n.tr("status_nfz_imported", count=len(zones)), 5000)

    # --------------------------------------------------------------- track

    def _toggle_track_recording(self) -> None:
        self._track_recording = not self._track_recording
        self._track_overlay.set_state(self._track_recording, len(self._track_recorder))
        key = "status_track_recording_started" if self._track_recording else "status_track_recording_paused"
        self.statusBar().showMessage(i18n.tr(key), 3000)

    def _export_track_prompt(self) -> None:
        if len(self._track_recorder) == 0:
            QMessageBox.warning(self, i18n.tr("msgbox_no_track_title"), i18n.tr("msgbox_no_track_body"))
            return

        box = QMessageBox(self)
        box.setWindowTitle(i18n.tr("track_export_format_title"))
        box.setText(i18n.tr("track_export_format_question"))
        gpx_btn = box.addButton(i18n.tr("track_export_format_gpx"), QMessageBox.ButtonRole.ActionRole)
        kml_btn = box.addButton(i18n.tr("track_export_format_kml"), QMessageBox.ButtonRole.ActionRole)
        csv_btn = box.addButton(i18n.tr("track_export_format_csv"), QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()

        clicked = box.clickedButton()
        if clicked is gpx_btn:
            self._export_track("gpx")
        elif clicked is kml_btn:
            self._export_track("kml")
        elif clicked is csv_btn:
            self._export_track("csv")

    # ------------------------------------------------------------- export

    def _export_track(self, fmt: str) -> None:
        if len(self._track_recorder) == 0:
            QMessageBox.warning(self, i18n.tr("msgbox_no_track_title"), i18n.tr("msgbox_no_track_body"))
            return

        filter_keys = {"gpx": "export_gpx_filter", "kml": "export_kml_filter", "csv": "route_csv_filter"}
        filter_str = i18n.tr(filter_keys[fmt])
        default_name = f"flight_{time.strftime('%Y%m%d_%H%M%S')}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, i18n.tr("export_dialog_title"), default_name, filter_str)
        if not path:
            return

        try:
            if fmt == "gpx":
                self._track_recorder.export_gpx(path)
            elif fmt == "kml":
                self._track_recorder.export_kml(path)
            else:
                self._track_recorder.export_csv(path)
        except OSError as exc:
            QMessageBox.critical(self, i18n.tr("msgbox_export_failed_title"), str(exc))
            return

        self.statusBar().showMessage(i18n.tr("status_track_saved", path=path), 5000)

    # -------------------------------------------------------------- close

    def closeEvent(self, event) -> None:
        if self._worker is not None:
            self._worker.stop()
        self._flight_logger.stop()
        self._tts_worker.stop()
        super().closeEvent(event)
