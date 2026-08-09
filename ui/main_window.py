"""Main application window: map + dashboard + menus, wired to a telemetry worker."""
from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QActionGroup, QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QWidget,
    QVBoxLayout,
)

from alerts.tts_alert import BatteryAlertMonitor, TTSWorker
from core import i18n
from core.dashboard_config import (
    load_dashboard_position,
    save_dashboard_layout,
    save_dashboard_position,
    save_visible_fields,
)
from core.geo import haversine_distance_m
from core.home_config import load_home_position, save_home_position
from core.nfz import NoFlyZoneManager
from core.nfz_proximity import DEFAULT_THRESHOLD_M, NfzProximityMonitor
from core.openaip_config import load_openaip_config, save_openaip_config
from core.openaip_import import OpenAipError, fetch_airspaces_geojson, geojson_to_zones
from core.model_profiles import ModelProfile, load_profiles
from core.resources import resource_path
from core.route import RouteManager
from core.telemetry_state import TelemetryState
from core.tracker_output import TrackerOutputSender
from core.ui_state_config import load_ui_state, save_ui_state
from export.flight_logger import ALL_FIELDS, FlightLogger
from export.nfz_import import import_nfz_file
from export.route_export import export_route_csv, export_route_gpx
from export.route_import import import_route_file
from export.track_export import TrackRecorder
from telemetry.crsf_serial_worker import CRSFSerialWorker
from telemetry.crsf_worker import CRSFWorker
from telemetry.demo_worker import DemoWorker
from telemetry.mavlink_worker import MAVLinkWorker
from ui.altitude_track_overlay import AltitudeTrackOverlay
from ui.battery_settings_dialog import BatterySettingsDialog
from ui.connection_dialog import ConnectionSettingsDialog
from ui.dashboard import Dashboard
from ui.dashboard_settings_dialog import DashboardSettingsDialog
from ui.elevation_profile_dialog import ElevationProfileDialog
from ui.flight_log_dialog import FlightLogSettingsDialog
from ui.grid_pattern_dialog import GridPatternDialog
from ui.home_position_dialog import DEFAULT_LAT, DEFAULT_LON, HomePositionDialog
from ui.horizon_widget import HorizonWidget
from ui.map_buttons import HeadingModeButton, LockButton
from ui.map_widget import MapWidget
from ui.model_profile_dialog import ModelProfileDialog
from ui.openaip_settings_dialog import OpenAipSettingsDialog
from ui.route_editor_overlay import RouteEditorOverlay
from ui.track_overlay import TrackOverlay
from ui.tracker_output_dialog import TrackerOutputDialog

HEARTBEAT_TIMEOUT_S = 3.0
# How far the model must move from where it last stood still before
# "Auto" track recording kicks in - high enough to ignore ordinary GPS
# jitter while parked, low enough to catch the start of a real flight
# promptly.
AUTO_TRACK_THRESHOLD_M = 3.0
# Minimum drone movement (in meters) before a new track/flight-path point is
# recorded on the map - user-configurable via "Anzeige & Karte" ->
# "Karten-Performance...".
DEFAULT_PATH_POINT_THRESHOLD_M = 1.5

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
ALTITUDE_TRACK_TIME_UNITS = (
    ("menu_altitude_track_unit_s", "s"),
    ("menu_altitude_track_unit_min", "min"),
    ("menu_altitude_track_unit_h", "h"),
)
DEFAULT_ALTITUDE_TRACK_TIME_UNIT = "s"


def _resize_from_saved(widget, size) -> None:
    """Apply a [width, height] pair loaded from ui_state.json, if present
    and well-formed - leaves the widget at its own constructor default
    otherwise."""
    if isinstance(size, list) and len(size) == 2 and all(isinstance(v, (int, float)) for v in size):
        widget.resize(int(size[0]), int(size[1]))


class MainWindow(QMainWindow):
    def __init__(self, args) -> None:
        super().__init__()
        self._args = args
        self._ui_state = load_ui_state()
        lang = getattr(args, "lang", None) or self._ui_state.get("language") or "de"
        i18n.set_language(lang)
        self._path_point_threshold_m = self._ui_state.get(
            "path_point_threshold_m", DEFAULT_PATH_POINT_THRESHOLD_M
        )

        self.setWindowTitle("ELRS Ground Station")
        self.resize(1200, 800)
        icon_path = resource_path("assets", "app_icon.ico")
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._track_recorder = TrackRecorder()
        self._tts_worker = TTSWorker()
        self._tts_worker.start()
        self._battery_monitor = BatteryAlertMonitor(
            self._tts_worker,
            cells=args.cells,
            low_cell_voltage=args.low_cell_voltage,
            critical_cell_voltage=args.critical_cell_voltage,
        )
        self._nfz_proximity_monitor = NfzProximityMonitor(self._tts_worker)
        self._tracker_output_sender = TrackerOutputSender()
        self._tracker_output_sender.error_occurred.connect(self._on_tracker_output_error)
        self._battery_chemistry = "lipo"
        self._battery_cells = args.cells
        self._battery_low_v = args.low_cell_voltage
        self._battery_critical_v = args.critical_cell_voltage
        self._battery_capacity_mah = 1300

        home_position = load_home_position()
        home_lat, home_lon = home_position if home_position is not None else (None, None)
        self._map = MapWidget(home_lat=home_lat, home_lon=home_lon)
        self._dashboard = Dashboard()
        self._dashboard.set_model_profile_names(list(load_profiles().keys()))
        self._horizon = HorizonWidget()
        self._horizon.set_scale(self._ui_state.get("horizon_scale", DEFAULT_HORIZON_SCALE))
        self._map.add_overlay(self._horizon, self._ui_state.get("horizon_corner", DEFAULT_HORIZON_CORNER))
        # A scale actually restored from a previous session is a deliberate
        # value - never auto-fit-override it. A brand new install with no
        # saved scale yet has nothing to respect, so it's free to auto-fit
        # once docked (see the startup sync block below and
        # _on_horizon_dock_toggled for the interactive-toggle case).
        self._horizon_scale_manual = "horizon_scale" in self._ui_state

        self._route_manager = RouteManager()
        self._route_manager.changed.connect(self._on_route_changed)
        self._map.route_bridge.waypoint_added.connect(self._route_manager.add)
        self._map.route_bridge.waypoint_added_typed.connect(self._route_manager.add_typed)
        self._map.route_bridge.home_position_picked.connect(self._on_home_position_picked)
        self._map.route_bridge.view_action_triggered.connect(self._on_view_action)
        self._map.route_bridge.waypoint_selected.connect(self._on_waypoint_marker_selected)
        self._map.route_bridge.waypoint_delete_requested.connect(self._on_waypoint_marker_delete)
        self._map.route_bridge.waypoint_edit_requested.connect(self._on_waypoint_marker_edit)
        self._map.route_bridge.waypoint_moved.connect(self._route_manager.update_position)

        self._route_overlay = RouteEditorOverlay()
        self._route_overlay.waypoints_edited.connect(self._route_manager.set_all)
        self._route_overlay.row_selected.connect(self._map.select_waypoint)
        self._route_overlay.delete_requested.connect(self._route_manager.remove_many)
        self._route_overlay.insert_after_requested.connect(self._route_manager.insert_between)
        self._route_overlay.reverse_requested.connect(self._route_manager.reverse)
        self._route_overlay.reorder_requested.connect(self._route_manager.reorder)
        self._route_overlay.bulk_altitude_requested.connect(self._route_manager.set_altitude_many)
        self._route_overlay.bulk_speed_requested.connect(self._route_manager.set_speed_many)
        _resize_from_saved(self._route_overlay, self._ui_state.get("route_editor_size"))
        self._map.add_overlay(self._route_overlay, "bottom-left")

        self._track_recording = False
        self._track_auto_reference_position = None
        self._track_overlay = TrackOverlay()
        self._track_overlay.start_pause_clicked.connect(self._toggle_track_recording)
        self._track_overlay.export_clicked.connect(self._export_track_prompt)
        # Auto-start track recording once the model moves defaults to ON,
        # unlike every other toggle here which defaults to its previous
        # off/on state - matches the explicit "Tracking soll standardmaessig
        # aktiv sein" requirement.
        self._track_overlay.set_auto_enabled(self._ui_state.get("track_auto", True))
        _resize_from_saved(self._track_overlay, self._ui_state.get("track_overlay_size"))
        self._map.add_overlay(self._track_overlay, "top-left")

        self._altitude_track_start = None
        self._altitude_track_overlay = AltitudeTrackOverlay()
        _resize_from_saved(self._altitude_track_overlay, self._ui_state.get("altitude_track_size"))
        self._map.add_overlay(self._altitude_track_overlay, "top-left")

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

        self._splitter = QSplitter()
        self._splitter.addWidget(self._map)
        self._splitter.addWidget(self._dashboard)
        layout.addWidget(self._splitter)
        self.setCentralWidget(central)

        self._dashboard_position = load_dashboard_position()
        self._apply_dashboard_position(self._dashboard_position)

        self.setStatusBar(QStatusBar())

        self._worker = None
        self._demo_mode = bool(args.demo)
        self._plan_mode = False

        self._i18n_menus: list[tuple] = []
        self._i18n_actions: list[tuple] = []
        self._build_menu()
        i18n.on_language_changed(self._retranslate_menu)

        # Every menu action's toggled signal is connected *after* its own
        # initial setChecked() call above (so constructing the menu never
        # fires side effects on a not-yet-fully-built window) - which means
        # a loaded-from-disk checked state never actually reached the real
        # behavior it controls. Apply all of it explicitly now that
        # everything exists and every signal is wired.
        self._lock_button.set_locked(self._auto_center_action.isChecked())
        self._heading_button.set_heading_up(self._heading_mode_action.isChecked())
        self._dashboard.resized.connect(self._fit_docked_horizon)

        # These all end up calling page().runJavaScript() on the map, which
        # is a silent no-op if the page hasn't finished loading yet - true
        # at this exact point in startup. Unlike updateDrone()/clearPath()
        # (called repeatedly on every telemetry tick, so an early miss
        # self-heals moments later), these are one-shot: a dropped call
        # here would leave the JS side permanently out of sync with the
        # restored Python-side state. Defer them to loadFinished instead.
        def _apply_initial_map_js_state(ok: bool) -> None:
            self._map.set_auto_center(self._auto_center_action.isChecked())
            self._apply_heading_mode(self._heading_mode_action.isChecked())
            self._map.set_coord_overlay_visible(self._coord_overlay_action.isChecked())
            self._map.set_heatmap_enabled(self._heatmap_action.isChecked())
            self._map.set_nfz_visible(self._nfz_visible_action.isChecked())
            self._map.set_base_layer(self._ui_state.get("base_layer", "osm"))
            self._map.set_vehicle_type(self._ui_state.get("vehicle_type", "quad"))
            self._map.set_path_point_threshold(self._path_point_threshold_m)

        self._map.page().loadFinished.connect(_apply_initial_map_js_state)
        self._horizon.setVisible(self._horizon_toggle_action.isChecked())
        self._route_overlay.setVisible(self._route_editor_action.isChecked())
        self._track_overlay.setVisible(self._track_overlay_action.isChecked())
        self._altitude_track_overlay.setVisible(self._altitude_track_action.isChecked())
        if self._horizon_dock_action.isChecked():
            self._set_horizon_docked(True)
            if not self._horizon_scale_manual:
                # No scale was ever saved (fresh install) - give it a
                # sensible initial fit instead of sitting at its bare
                # 130px base size until the next window resize.
                self._fit_docked_horizon()
        if self._altitude_track_dock_action.isChecked():
            self._set_altitude_track_docked(True)
        if self._route_editor_dock_action.isChecked():
            self._set_route_editor_docked(True)

        saved_model_name = self._ui_state.get("model_profile", "")
        saved_profiles = load_profiles()
        if saved_model_name and saved_model_name in saved_profiles:
            self._apply_model_profile(saved_profiles[saved_model_name])

        self._altitude_track_overlay.set_time_unit(
            self._ui_state.get("altitude_track_time_unit", DEFAULT_ALTITUDE_TRACK_TIME_UNIT)
        )

        # Persist every menu/view toggle immediately on change (matching
        # every other config file in this app); overlay sizes only change
        # via continuous mouse-drag ticks, so those are captured once in
        # closeEvent() instead of on every pixel of movement.
        for action in (
            self._auto_center_action, self._heading_mode_action, self._coord_overlay_action,
            self._heatmap_action, self._nfz_visible_action, self._nfz_proximity_action,
            self._horizon_toggle_action, self._horizon_dock_action, self._route_editor_action,
            self._route_editor_dock_action, self._track_overlay_action,
            self._altitude_track_action, self._altitude_track_dock_action,
        ):
            action.toggled.connect(self._persist_ui_state)
        self._layer_group.triggered.connect(self._persist_ui_state)
        self._vehicle_group.triggered.connect(self._persist_ui_state)
        self._horizon_pos_group.triggered.connect(self._persist_ui_state)
        self._horizon_scale_group.triggered.connect(self._persist_ui_state)
        self._altitude_track_unit_group.triggered.connect(self._persist_ui_state)
        self._lang_group.triggered.connect(self._persist_ui_state)
        self._track_overlay.auto_toggled.connect(self._persist_ui_state)
        self._dashboard.model_profile_selected.connect(self._on_dashboard_model_selected)

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
        # 7 top-level menus grouped by purpose (Datei | Route & Planung |
        # Anzeige & Karte | Telemetrie & Hardware | Tools & Simulation |
        # Einstellungen | Hilfe). Sperrzonen lives as a submenu inside
        # "Anzeige & Karte" rather than its own top-level menu, since it's
        # fundamentally a map-display concern. A few QActions are
        # intentionally constructed in one menu's section and then also
        # added to another menu later in this method via menu.addAction() -
        # that's the *same* QAction object appearing in two places, not a
        # copy, so toggling it from either menu (or from the map's
        # right-click view-options submenu, see _on_view_action) keeps every
        # appearance in sync for free without any extra state-sync code.
        menu = self.menuBar()

        # --------------------------------------------------------- Datei
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

        # ----------------------------------------------- Route & Planung
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
        self._route_editor_action.setChecked(self._ui_state.get("route_editor_visible", True))
        self._route_editor_action.toggled.connect(self._route_overlay.setVisible)
        self._route_overlay.closed.connect(lambda: self._route_editor_action.setChecked(False))

        self._route_editor_dock_action = route_menu.addAction("")
        self._i18n_actions.append((self._route_editor_dock_action, "menu_route_edit_dock"))
        self._route_editor_dock_action.setCheckable(True)
        self._route_editor_dock_action.setChecked(self._ui_state.get("route_editor_docked", False))
        self._route_editor_dock_action.toggled.connect(self._set_route_editor_docked)

        route_menu.addSeparator()
        import_route_action = route_menu.addAction("")
        self._i18n_actions.append((import_route_action, "menu_route_import"))
        import_route_action.triggered.connect(self._import_route)

        export_route_action = route_menu.addAction("")
        self._i18n_actions.append((export_route_action, "menu_route_export"))
        export_route_action.triggered.connect(self._export_route)

        route_menu.addSeparator()
        grid_pattern_action = route_menu.addAction("")
        self._i18n_actions.append((grid_pattern_action, "menu_grid_pattern"))
        grid_pattern_action.triggered.connect(self._open_grid_pattern)

        # ----------------------------------------------- Anzeige & Karte
        view_map_menu = menu.addMenu("")
        self._i18n_menus.append((view_map_menu, "menu_map"))

        # Sperrzonen lives as a submenu here (not its own top-level menu)
        # since it's fundamentally a map-display concern.
        nfz_menu = view_map_menu.addMenu("")
        self._i18n_menus.append((nfz_menu, "menu_nfz"))

        import_nfz_action = nfz_menu.addAction("")
        self._i18n_actions.append((import_nfz_action, "menu_map_nfz_import"))
        import_nfz_action.triggered.connect(self._import_nfz)

        self._nfz_visible_action = nfz_menu.addAction("")
        self._i18n_actions.append((self._nfz_visible_action, "menu_map_nfz_visible"))
        self._nfz_visible_action.setCheckable(True)
        self._nfz_visible_action.setChecked(self._ui_state.get("nfz_visible", True))
        self._nfz_visible_action.toggled.connect(self._map.set_nfz_visible)

        self._nfz_proximity_action = nfz_menu.addAction("")
        self._i18n_actions.append((self._nfz_proximity_action, "menu_nfz_proximity"))
        self._nfz_proximity_action.setCheckable(True)
        self._nfz_proximity_action.setChecked(self._ui_state.get("nfz_proximity", False))

        nfz_menu.addSeparator()
        openaip_settings_action = nfz_menu.addAction("")
        self._i18n_actions.append((openaip_settings_action, "menu_nfz_openaip_settings"))
        openaip_settings_action.triggered.connect(self._open_openaip_settings)

        openaip_load_action = nfz_menu.addAction("")
        self._i18n_actions.append((openaip_load_action, "menu_nfz_openaip_load"))
        openaip_load_action.triggered.connect(self._load_openaip_zones)

        view_map_menu.addSeparator()

        layer_menu = view_map_menu.addMenu("")
        self._i18n_menus.append((layer_menu, "menu_map_layer"))
        self._layer_group = QActionGroup(self)
        self._layer_group.setExclusive(True)
        for key, layer_id in BASE_LAYERS:
            action = layer_menu.addAction("")
            self._i18n_actions.append((action, key))
            action.setCheckable(True)
            action.setData(layer_id)
            action.setChecked(layer_id == self._ui_state.get("base_layer", "osm"))
            self._layer_group.addAction(action)
        self._layer_group.triggered.connect(lambda action: self._map.set_base_layer(action.data()))

        view_map_menu.addSeparator()

        self._auto_center_action = view_map_menu.addAction("")
        self._i18n_actions.append((self._auto_center_action, "menu_view_auto_center"))
        self._auto_center_action.setCheckable(True)
        self._auto_center_action.setChecked(self._ui_state.get("auto_center", True))
        self._auto_center_action.toggled.connect(self._map.set_auto_center)
        self._auto_center_action.toggled.connect(self._lock_button.set_locked)

        self._heading_mode_action = view_map_menu.addAction("")
        self._i18n_actions.append((self._heading_mode_action, "menu_view_heading_mode"))
        self._heading_mode_action.setCheckable(True)
        self._heading_mode_action.setChecked(self._ui_state.get("heading_mode", False))
        self._heading_mode_action.toggled.connect(self._apply_heading_mode)

        jump_action = view_map_menu.addAction("")
        self._i18n_actions.append((jump_action, "menu_view_jump"))
        jump_action.setShortcut("Ctrl+Home")
        jump_action.triggered.connect(self._map.center_on_current)

        # Same QAction instance as in the Route menu.
        view_map_menu.addAction(self._route_editor_action)

        self._coord_overlay_action = view_map_menu.addAction("")
        self._i18n_actions.append((self._coord_overlay_action, "menu_view_coords"))
        self._coord_overlay_action.setCheckable(True)
        self._coord_overlay_action.setChecked(self._ui_state.get("coord_overlay", False))
        self._coord_overlay_action.toggled.connect(self._map.set_coord_overlay_visible)

        self._heatmap_action = view_map_menu.addAction("")
        self._i18n_actions.append((self._heatmap_action, "menu_heatmap"))
        self._heatmap_action.setCheckable(True)
        self._heatmap_action.setChecked(self._ui_state.get("heatmap", False))
        self._heatmap_action.toggled.connect(self._map.set_heatmap_enabled)

        map_performance_action = view_map_menu.addAction("")
        self._i18n_actions.append((map_performance_action, "menu_map_performance"))
        map_performance_action.triggered.connect(self._open_map_performance_settings)

        self._altitude_track_action = view_map_menu.addAction("")
        self._i18n_actions.append((self._altitude_track_action, "menu_altitude_track"))
        self._altitude_track_action.setCheckable(True)
        self._altitude_track_action.setChecked(self._ui_state.get("altitude_track_visible", True))
        self._altitude_track_action.toggled.connect(self._altitude_track_overlay.setVisible)
        self._altitude_track_overlay.closed.connect(lambda: self._altitude_track_action.setChecked(False))

        self._altitude_track_dock_action = view_map_menu.addAction("")
        self._i18n_actions.append((self._altitude_track_dock_action, "menu_altitude_track_dock"))
        self._altitude_track_dock_action.setCheckable(True)
        self._altitude_track_dock_action.setChecked(self._ui_state.get("altitude_track_docked", True))
        self._altitude_track_dock_action.toggled.connect(self._set_altitude_track_docked)

        altitude_track_unit_menu = view_map_menu.addMenu("")
        self._i18n_menus.append((altitude_track_unit_menu, "menu_altitude_track_unit"))
        self._altitude_track_unit_group = QActionGroup(self)
        self._altitude_track_unit_group.setExclusive(True)
        for key, unit in ALTITUDE_TRACK_TIME_UNITS:
            action = altitude_track_unit_menu.addAction("")
            self._i18n_actions.append((action, key))
            action.setCheckable(True)
            action.setData(unit)
            action.setChecked(unit == self._ui_state.get("altitude_track_time_unit", DEFAULT_ALTITUDE_TRACK_TIME_UNIT))
            self._altitude_track_unit_group.addAction(action)
        self._altitude_track_unit_group.triggered.connect(
            lambda action: self._altitude_track_overlay.set_time_unit(action.data())
        )

        self._track_overlay_action = view_map_menu.addAction("")
        self._i18n_actions.append((self._track_overlay_action, "menu_track_overlay"))
        self._track_overlay_action.setCheckable(True)
        self._track_overlay_action.setChecked(self._ui_state.get("track_overlay_visible", True))
        self._track_overlay_action.toggled.connect(self._track_overlay.setVisible)
        self._track_overlay.closed.connect(lambda: self._track_overlay_action.setChecked(False))

        vehicle_menu = view_map_menu.addMenu("")
        self._i18n_menus.append((vehicle_menu, "menu_view_vehicle"))
        self._vehicle_group = QActionGroup(self)
        self._vehicle_group.setExclusive(True)
        for key, vehicle_id in VEHICLE_TYPES:
            action = vehicle_menu.addAction("")
            self._i18n_actions.append((action, key))
            action.setCheckable(True)
            action.setData(vehicle_id)
            action.setChecked(vehicle_id == self._ui_state.get("vehicle_type", "quad"))
            self._vehicle_group.addAction(action)
        self._vehicle_group.triggered.connect(lambda action: self._map.set_vehicle_type(action.data()))

        self._horizon_toggle_action = view_map_menu.addAction("")
        self._i18n_actions.append((self._horizon_toggle_action, "menu_view_horizon_toggle"))
        self._horizon_toggle_action.setCheckable(True)
        self._horizon_toggle_action.setChecked(self._ui_state.get("horizon_visible", True))
        self._horizon_toggle_action.toggled.connect(self._horizon.setVisible)
        self._horizon.closed.connect(lambda: self._horizon_toggle_action.setChecked(False))

        self._horizon_dock_action = view_map_menu.addAction("")
        self._i18n_actions.append((self._horizon_dock_action, "menu_horizon_dock"))
        self._horizon_dock_action.setCheckable(True)
        self._horizon_dock_action.setChecked(self._ui_state.get("horizon_docked", True))
        self._horizon_dock_action.toggled.connect(self._on_horizon_dock_toggled)

        horizon_pos_menu = view_map_menu.addMenu("")
        self._i18n_menus.append((horizon_pos_menu, "menu_view_horizon_position"))
        self._horizon_pos_group = QActionGroup(self)
        self._horizon_pos_group.setExclusive(True)
        for key, corner in HORIZON_CORNERS:
            action = horizon_pos_menu.addAction("")
            self._i18n_actions.append((action, key))
            action.setCheckable(True)
            action.setData(corner)
            action.setChecked(corner == self._ui_state.get("horizon_corner", DEFAULT_HORIZON_CORNER))
            self._horizon_pos_group.addAction(action)
        self._horizon_pos_group.triggered.connect(
            lambda action: self._map.set_overlay_corner(self._horizon, action.data())
        )

        horizon_scale_menu = view_map_menu.addMenu("")
        self._i18n_menus.append((horizon_scale_menu, "menu_view_horizon_scale"))
        self._horizon_scale_group = QActionGroup(self)
        self._horizon_scale_group.setExclusive(True)
        for key, scale in HORIZON_SCALES:
            action = horizon_scale_menu.addAction("")
            self._i18n_actions.append((action, key))
            action.setCheckable(True)
            action.setData(scale)
            action.setChecked(scale == self._ui_state.get("horizon_scale", DEFAULT_HORIZON_SCALE))
            self._horizon_scale_group.addAction(action)
        self._horizon_scale_group.triggered.connect(self._set_horizon_scale)

        # ----------------------------------------- Telemetrie & Hardware
        telemetry_menu = menu.addMenu("")
        self._i18n_menus.append((telemetry_menu, "menu_telemetry_hardware"))

        conn_settings_action = telemetry_menu.addAction("")
        self._i18n_actions.append((conn_settings_action, "menu_connection_settings"))
        conn_settings_action.triggered.connect(self._open_connection_dialog)

        telemetry_menu.addSeparator()
        flightlog_settings_action = telemetry_menu.addAction("")
        self._i18n_actions.append((flightlog_settings_action, "menu_flightlog_settings"))
        flightlog_settings_action.triggered.connect(self._open_flight_log_settings)

        self._flightlog_active_action = telemetry_menu.addAction("")
        self._i18n_actions.append((self._flightlog_active_action, "menu_flightlog_active"))
        self._flightlog_active_action.setCheckable(True)
        self._flightlog_active_action.toggled.connect(self._toggle_flight_logging)

        telemetry_menu.addSeparator()
        battery_settings_action = telemetry_menu.addAction("")
        self._i18n_actions.append((battery_settings_action, "menu_battery_settings"))
        battery_settings_action.triggered.connect(self._open_battery_settings)

        telemetry_menu.addSeparator()
        tracker_output_action = telemetry_menu.addAction("")
        self._i18n_actions.append((tracker_output_action, "menu_tracker_output"))
        tracker_output_action.triggered.connect(self._open_tracker_output)

        model_profiles_action = telemetry_menu.addAction("")
        self._i18n_actions.append((model_profiles_action, "menu_model_profiles"))
        model_profiles_action.triggered.connect(self._open_model_profiles)

        # -------------------------------------------- Tools & Simulation
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

        sim_menu.addSeparator()
        elevation_profile_action = sim_menu.addAction("")
        self._i18n_actions.append((elevation_profile_action, "menu_elevation_profile"))
        elevation_profile_action.triggered.connect(self._open_elevation_profile)

        # ------------------------------------------------- Einstellungen
        settings_menu = menu.addMenu("")
        self._i18n_menus.append((settings_menu, "menu_settings"))

        home_settings_action = settings_menu.addAction("")
        self._i18n_actions.append((home_settings_action, "menu_home_settings"))
        home_settings_action.triggered.connect(self._open_home_settings)

        self._dashboard_settings_action = settings_menu.addAction("")
        self._i18n_actions.append((self._dashboard_settings_action, "menu_dashboard_settings"))
        self._dashboard_settings_action.triggered.connect(self._open_dashboard_settings)
        # Same QAction instance, mirrored into Anzeige & Karte too.
        view_map_menu.addAction(self._dashboard_settings_action)

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

        # --------------------------------------------------------- Hilfe
        help_menu = menu.addMenu("")
        self._i18n_menus.append((help_menu, "menu_help"))
        manual_action = help_menu.addAction("")
        self._i18n_actions.append((manual_action, "menu_help_manual"))
        manual_action.triggered.connect(self._open_manual)

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
        self._track_auto_reference_position = None
        self._track_overlay.set_state(False, 0)
        self._dashboard.reset_session()
        self._altitude_track_start = None
        self._altitude_track_overlay.reset()

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
            self._track_auto_reference_position = None
            self._track_overlay.set_state(False, 0)
            self._altitude_track_start = None
            self._altitude_track_overlay.reset()
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
        self._heading_mode_action.setChecked(not self._heading_mode_action.isChecked())

    def _apply_heading_mode(self, enabled: bool) -> None:
        self._map.set_heading_mode(enabled)
        self._heading_button.set_heading_up(enabled)

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
            self._battery_chemistry, self._battery_cells, self._battery_low_v, self._battery_critical_v,
            capacity_mah=self._battery_capacity_mah, parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._battery_chemistry = dialog.chemistry()
        self._battery_cells = dialog.cells()
        self._battery_low_v = dialog.low_cell_voltage()
        self._battery_critical_v = dialog.critical_cell_voltage()
        self._battery_capacity_mah = dialog.capacity_mah()
        self._battery_monitor.configure(self._battery_cells, self._battery_low_v, self._battery_critical_v)

    def _open_map_performance_settings(self) -> None:
        value, ok = QInputDialog.getDouble(
            self,
            i18n.tr("map_performance_dialog_title"),
            i18n.tr("map_performance_threshold_label"),
            self._path_point_threshold_m,
            0.1,
            100.0,
            1,
        )
        if not ok:
            return
        self._path_point_threshold_m = value
        self._map.set_path_point_threshold(value)
        self._persist_ui_state()

    def _open_tracker_output(self) -> None:
        dialog = TrackerOutputDialog(self._tracker_output_sender, self)
        dialog.exec()

    def _on_tracker_output_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 8000)

    def _build_current_model_profile(self, name: str) -> ModelProfile:
        return ModelProfile(
            name=name,
            battery_chemistry=self._battery_chemistry,
            battery_cells=self._battery_cells,
            battery_low_v=self._battery_low_v,
            battery_critical_v=self._battery_critical_v,
            battery_capacity_mah=self._battery_capacity_mah,
            dashboard_visible_fields=sorted(self._dashboard.visible_fields()),
            dashboard_group_order=self._dashboard.group_order(),
            dashboard_rows=self._dashboard.rows(),
        )

    def _open_model_profiles(self) -> None:
        dialog = ModelProfileDialog(self._build_current_model_profile, self)
        dialog.profile_loaded.connect(self._apply_model_profile)
        dialog.exec()
        # The dialog may have added/deleted profiles - refresh the
        # telemetry-bar dropdown's contents to match either way.
        self._dashboard.set_model_profile_names(list(load_profiles().keys()))

    def _on_dashboard_model_selected(self, name: str) -> None:
        profiles = load_profiles()
        if name in profiles:
            self._apply_model_profile(profiles[name])
            self._persist_ui_state()

    def _apply_model_profile(self, profile: ModelProfile) -> None:
        self._battery_chemistry = profile.battery_chemistry
        self._battery_cells = profile.battery_cells
        self._battery_low_v = profile.battery_low_v
        self._battery_critical_v = profile.battery_critical_v
        self._battery_capacity_mah = profile.battery_capacity_mah
        self._battery_monitor.configure(self._battery_cells, self._battery_low_v, self._battery_critical_v)

        visible_fields = set(profile.dashboard_visible_fields)
        self._dashboard.apply_field_visibility(visible_fields)
        save_visible_fields(visible_fields)

        self._dashboard.apply_layout(profile.dashboard_group_order, profile.dashboard_rows)
        save_dashboard_layout(profile.dashboard_group_order, profile.dashboard_rows)

        self._dashboard.set_current_model_profile_name(profile.name)

        self.statusBar().showMessage(i18n.tr("status_model_profile_loaded", name=profile.name), 5000)

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

    def _open_grid_pattern(self) -> None:
        live_position = None
        if self._last_telemetry_state is not None and self._last_telemetry_state.has_gps_fix():
            live_position = (self._last_telemetry_state.lat, self._last_telemetry_state.lon)

        center_default = live_position or load_home_position() or (DEFAULT_LAT, DEFAULT_LON)

        dialog = GridPatternDialog(center_default, live_position, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        waypoints = dialog.waypoints()
        self._route_manager.set_all(waypoints)
        self.statusBar().showMessage(i18n.tr("status_grid_pattern_generated", count=len(waypoints)), 5000)

    def _open_elevation_profile(self) -> None:
        if not self._route_manager.waypoints():
            QMessageBox.warning(self, i18n.tr("msgbox_no_route_title"), i18n.tr("msgbox_no_route_body"))
            return

        home = None
        if self._last_telemetry_state is not None and self._last_telemetry_state.has_gps_fix():
            home = (self._last_telemetry_state.lat, self._last_telemetry_state.lon)

        dialog = ElevationProfileDialog(self._route_manager, home, self)
        dialog.exec()

    def _open_manual(self) -> None:
        path = self._manual_pdf_path()
        if not path.is_file():
            QMessageBox.warning(self, i18n.tr("msgbox_manual_missing_title"), i18n.tr("msgbox_manual_missing_body"))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @staticmethod
    def _manual_pdf_path() -> Path:
        return resource_path("docs", "ELRS_Ground_Station_Benutzerhandbuch.pdf")

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
        elif action == "heatmap":
            self._heatmap_action.setChecked(not self._heatmap_action.isChecked())

    def _set_horizon_scale(self, action) -> None:
        self._horizon.set_scale(action.data())
        self._map.reposition_overlays()
        # A size the user picked explicitly (menu preset, or in the future
        # a slider) is a deliberate choice - stop auto-fitting on window
        # resize from now on so it isn't immediately overridden again.
        self._horizon_scale_manual = True

    def _open_dashboard_settings(self) -> None:
        dialog = DashboardSettingsDialog(
            self._dashboard.field_catalog(),
            self._dashboard.visible_fields(),
            self._dashboard.group_order(),
            self._dashboard.rows(),
            self._dashboard_position,
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

        position = dialog.position()
        self._apply_dashboard_position(position)
        save_dashboard_position(position)

    def _apply_dashboard_position(self, position: str) -> None:
        self._dashboard_position = position
        side_docked = position in ("left", "right")
        # A side-docked (left/right) splitter is horizontal, and the
        # dashboard's own fields switch to a vertical stack to fit the
        # resulting narrow column instead of overflowing wide rows.
        self._dashboard.set_vertical(side_docked)
        self._splitter.setOrientation(Qt.Orientation.Horizontal if side_docked else Qt.Orientation.Vertical)
        if position in ("top", "left"):
            self._splitter.insertWidget(0, self._dashboard)
            self._splitter.insertWidget(1, self._map)
        else:
            self._splitter.insertWidget(0, self._map)
            self._splitter.insertWidget(1, self._dashboard)
        self._splitter.setStretchFactor(self._splitter.indexOf(self._map), 1)
        self._splitter.setStretchFactor(self._splitter.indexOf(self._dashboard), 0)

    def _set_horizon_docked(self, docked: bool) -> None:
        if docked:
            self._map.remove_overlay(self._horizon)
            self._horizon.set_docked(True)
            self._dashboard.set_top_docked(self._horizon, True)
        else:
            self._dashboard.set_top_docked(self._horizon, False)
            self._horizon.set_docked(False)
            self._map.add_overlay(self._horizon, DEFAULT_HORIZON_CORNER)

    def _on_horizon_dock_toggled(self, docked: bool) -> None:
        """Menu-triggered (interactive) docking - unlike applying a
        *restored* dock state at startup (which must respect whatever
        scale was already restored from disk), a fresh interactive dock
        always starts from a good auto-fit."""
        if docked:
            self._horizon_scale_manual = False
        self._set_horizon_docked(docked)
        if docked:
            self._fit_docked_horizon()

    def _fit_docked_horizon(self) -> None:
        """Scale the artificial horizon to the dashboard's current width
        while it's docked there, instead of it staying at whatever small
        fixed size it happened to have when docked - called on every
        dashboard resize (see Dashboard.resized) as well as right after
        docking. Skipped once the user has explicitly picked a size via
        the Groesse menu (see _set_horizon_scale), so that choice isn't
        immediately fought and overridden on the next window resize."""
        if not self._horizon.is_docked() or self._horizon_scale_manual:
            return
        available = self._dashboard.width()
        if self._altitude_track_dock_action.isChecked():
            available //= 2
        target = max(90, min(int(available * 0.3), 260))
        self._horizon.request_resize(target, target)

    def _set_altitude_track_docked(self, docked: bool) -> None:
        if docked:
            self._map.remove_overlay(self._altitude_track_overlay)
            self._altitude_track_overlay.set_docked(True)
            self._dashboard.set_top_docked(self._altitude_track_overlay, True)
        else:
            self._dashboard.set_top_docked(self._altitude_track_overlay, False)
            self._altitude_track_overlay.set_docked(False)
            self._map.add_overlay(self._altitude_track_overlay, "top-left")

    def _set_route_editor_docked(self, docked: bool) -> None:
        if docked:
            self._map.remove_overlay(self._route_overlay)
            self._route_overlay.set_docked(True)
            self._dashboard.set_bottom_docked(self._route_overlay, True)
        else:
            self._dashboard.set_bottom_docked(self._route_overlay, False)
            self._route_overlay.set_docked(False)
            self._map.add_overlay(self._route_overlay, "bottom-left")

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
            self._map.update_position(state.lat, state.lon, state.heading, state.link_quality)
            if self._track_recording:
                self._track_recorder.add_point(state)
                self._track_overlay.update_count(len(self._track_recorder))
            else:
                self._check_auto_track_start(state)
            self._has_fix = True
            if state.alt is not None:
                if self._altitude_track_start is None:
                    self._altitude_track_start = time.monotonic()
                self._altitude_track_overlay.add_sample(time.monotonic() - self._altitude_track_start, state.alt)

        self._battery_monitor.check(state)
        self._check_nfz_proximity(state)
        if self._tracker_output_sender.is_active():
            self._tracker_output_sender.send(state)

    def _check_nfz_proximity(self, state: TelemetryState) -> None:
        if not self._nfz_proximity_action.isChecked():
            return
        self._nfz_proximity_monitor.check(state, self._nfz_manager.zones())
        result = self._nfz_proximity_monitor.last_result()
        if result is not None and result[1] <= DEFAULT_THRESHOLD_M:
            zone, distance = result
            self.statusBar().showMessage(
                i18n.tr("status_nfz_proximity_warning", name=zone.name, distance=f"{distance:.0f}")
            )

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

    def _on_waypoint_marker_selected(self, index: int) -> None:
        self._route_overlay.select_row(index)

    def _on_waypoint_marker_delete(self, index: int) -> None:
        self._route_manager.remove_at(index)

    def _on_waypoint_marker_edit(self, index: int) -> None:
        self._route_editor_action.setChecked(True)
        self._route_overlay.select_row(index)
        self._route_overlay.raise_()

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

    def _open_openaip_settings(self) -> None:
        config = load_openaip_config()
        dialog = OpenAipSettingsDialog(config["api_key"], config["base_url"], config["preferred_types"], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        save_openaip_config(dialog.api_key(), dialog.base_url(), dialog.preferred_types())

    def _load_openaip_zones(self) -> None:
        config = load_openaip_config()
        if not config["api_key"]:
            QMessageBox.warning(self, i18n.tr("msgbox_openaip_no_key_title"), i18n.tr("msgbox_openaip_no_key_body"))
            return

        position = None
        if self._last_telemetry_state is not None and self._last_telemetry_state.has_gps_fix():
            position = (self._last_telemetry_state.lat, self._last_telemetry_state.lon)
        elif load_home_position() is not None:
            position = load_home_position()
        if position is None:
            QMessageBox.warning(
                self, i18n.tr("msgbox_openaip_no_position_title"), i18n.tr("msgbox_openaip_no_position_body")
            )
            return

        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            geojson = fetch_airspaces_geojson(config["base_url"], config["api_key"], position[0], position[1])
        except OpenAipError as exc:
            QMessageBox.critical(self, i18n.tr("msgbox_openaip_failed_title"), str(exc))
            return
        finally:
            self.unsetCursor()

        zones = geojson_to_zones(geojson, config["preferred_types"])
        self._nfz_manager.set_all(zones)
        self.statusBar().showMessage(i18n.tr("status_openaip_loaded", count=len(zones)), 5000)

    # --------------------------------------------------------------- track

    def _toggle_track_recording(self) -> None:
        self._track_recording = not self._track_recording
        # Re-anchor "still standing here" at wherever recording just paused
        # (or clear it while starting, since it's unused while recording),
        # so Auto mode measures movement from the right reference point.
        self._track_auto_reference_position = None
        self._track_overlay.set_state(self._track_recording, len(self._track_recorder))
        key = "status_track_recording_started" if self._track_recording else "status_track_recording_paused"
        self.statusBar().showMessage(i18n.tr(key), 3000)

    def _check_auto_track_start(self, state: TelemetryState) -> None:
        if not self._track_overlay.is_auto_enabled():
            self._track_auto_reference_position = None
            return
        if self._track_auto_reference_position is None:
            self._track_auto_reference_position = (state.lat, state.lon)
            return
        distance = haversine_distance_m(state.lat, state.lon, *self._track_auto_reference_position)
        if distance >= AUTO_TRACK_THRESHOLD_M:
            self._toggle_track_recording()

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

    def _gather_ui_state(self) -> dict:
        layer_action = self._layer_group.checkedAction()
        vehicle_action = self._vehicle_group.checkedAction()
        horizon_pos_action = self._horizon_pos_group.checkedAction()
        return {
            "auto_center": self._auto_center_action.isChecked(),
            "heading_mode": self._heading_mode_action.isChecked(),
            "coord_overlay": self._coord_overlay_action.isChecked(),
            "heatmap": self._heatmap_action.isChecked(),
            "nfz_visible": self._nfz_visible_action.isChecked(),
            "nfz_proximity": self._nfz_proximity_action.isChecked(),
            "base_layer": layer_action.data() if layer_action is not None else "osm",
            "vehicle_type": vehicle_action.data() if vehicle_action is not None else "quad",
            "horizon_visible": self._horizon_toggle_action.isChecked(),
            "horizon_docked": self._horizon_dock_action.isChecked(),
            "horizon_corner": horizon_pos_action.data() if horizon_pos_action is not None else DEFAULT_HORIZON_CORNER,
            "horizon_scale": self._horizon.scale(),
            "route_editor_visible": self._route_editor_action.isChecked(),
            "route_editor_docked": self._route_editor_dock_action.isChecked(),
            "route_editor_size": [self._route_overlay.width(), self._route_overlay.height()],
            "track_overlay_visible": self._track_overlay_action.isChecked(),
            "track_overlay_size": [self._track_overlay.width(), self._track_overlay.height()],
            "track_auto": self._track_overlay.is_auto_enabled(),
            "altitude_track_visible": self._altitude_track_action.isChecked(),
            "altitude_track_docked": self._altitude_track_dock_action.isChecked(),
            "altitude_track_size": [self._altitude_track_overlay.width(), self._altitude_track_overlay.height()],
            "language": i18n.get_language(),
            "path_point_threshold_m": self._path_point_threshold_m,
            "model_profile": self._dashboard.current_model_profile_name(),
            "altitude_track_time_unit": self._altitude_track_overlay.time_unit(),
        }

    def _persist_ui_state(self, *_args) -> None:
        save_ui_state(self._gather_ui_state())

    def closeEvent(self, event) -> None:
        if self._worker is not None:
            self._worker.stop()
        self._flight_logger.stop()
        self._tts_worker.stop()
        self._tracker_output_sender.stop()
        # Overlay sizes only change via continuous mouse-drag ticks, so
        # rather than persisting on every pixel of movement, capture their
        # final size here alongside everything else.
        self._persist_ui_state()
        super().closeEvent(event)
