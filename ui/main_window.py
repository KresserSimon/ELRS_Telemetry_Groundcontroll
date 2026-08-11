"""Main application window: map + dashboard + menus, wired to a telemetry worker."""
from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QActionGroup, QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QWidget,
    QVBoxLayout,
)

from alerts.tts_alert import LEVEL_CRITICAL as BATTERY_LEVEL_CRITICAL
from alerts.tts_alert import LEVEL_LOW as BATTERY_LEVEL_LOW
from alerts.tts_alert import BatteryAlertMonitor, TTSWorker
from core import i18n
from core.dashboard_config import (
    load_dashboard_position,
    save_dashboard_layout,
    save_dashboard_position,
    save_visible_fields,
)
from core.display_info import (
    DASHBOARD_SCALE_LARGE,
    DASHBOARD_SCALE_MEDIUM,
    DASHBOARD_SCALE_SMALL,
    auto_dashboard_scale,
    detect_available_width,
)
from core.geo import haversine_distance_m
from core.energy_budget import (
    DEFAULT_GREEN_THRESHOLD_PCT,
    DEFAULT_MIN_SPEED_ASSUMPTION_MS,
    DEFAULT_YELLOW_THRESHOLD_PCT,
    LEVEL_RED as ENERGY_LEVEL_RED,
    LEVEL_YELLOW as ENERGY_LEVEL_YELLOW,
    EnergyBudgetMonitor,
)
from core.geofence import DEFAULT_MAX_ALT_M, DEFAULT_RADIUS_M, find_out_of_bounds
from core.geofence_monitor import GeofenceMonitor
from core.flight_summary import summarize
from core.gs_position import GsPosition, compute_azimuth_elevation, load_gs_position, save_gs_position
from core.home_config import load_home_position, save_home_position
from core.lost_model_monitor import DEFAULT_TIMEOUT_S as LOST_MODEL_DEFAULT_TIMEOUT_S, LostModelMonitor
from core.nfz import NoFlyZoneManager
from core.nfz_proximity import DEFAULT_THRESHOLD_M, NfzProximityMonitor, nearest_zone
from core.openaip_config import load_openaip_config, save_openaip_config
from core.openaip_import import OpenAipError, fetch_airspaces_geojson, geojson_to_zones
from core.model_profiles import ModelProfile, load_profiles, save_profiles
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
from telemetry.mavlink_command import rth_command_session, set_mode_command_session
from telemetry.mavlink_mission import MissionDownloadSession, MissionUploadSession
from telemetry.mavlink_worker import MAVLinkWorker
from telemetry.replay_worker import ReplayWorker, parse_flight_log_csv
from ui.altitude_track_overlay import AltitudeTrackOverlay
from ui.battery_settings_dialog import BatterySettingsDialog
from ui.connection_dialog import ConnectionSettingsDialog
from ui.dashboard import Dashboard
from ui.dashboard_settings_dialog import DashboardSettingsDialog
from ui.elevation_profile_dialog import ElevationProfileDialog
from ui.energy_budget_settings_dialog import EnergyBudgetSettingsDialog
from ui.flight_log_dialog import FlightLogSettingsDialog
from ui.geofence_settings_dialog import GeofenceSettingsDialog
from ui.grid_pattern_dialog import GridPatternDialog
from ui.gs_position_dialog import GsPositionDialog
from ui.home_position_dialog import DEFAULT_LAT, DEFAULT_LON, HomePositionDialog
from ui.horizon_widget import HorizonWidget
from ui.lost_model_overlay import LostModelOverlay
from ui.map_buttons import HeadingModeButton, LockButton
from ui.map_widget import MapWidget, pmtiles_dir
from ui.mode_change_dialog import ModeChangeDialog
from ui.model_editor_dialog import ModelEditorDialog
from ui.model_profile_dialog import ModelProfileDialog
from ui.openaip_settings_dialog import OpenAipSettingsDialog
from ui.flight_summary_dialog import FlightSummaryDialog
from ui.pmtiles_download_dialog import PMTilesDownloadDialog
from ui.replay_transport_overlay import ReplayTransportOverlay
from ui.route_editor_overlay import RouteEditorOverlay
from ui.statustext_console import StatusTextConsole
from ui.warning_banner import WarningBanner
from ui.track_overlay import TrackOverlay
from ui.tracker_output_dialog import TrackerOutputDialog

HEARTBEAT_TIMEOUT_S = 3.0
DEFAULT_REPLAY_SPEED = 1.0
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
# The MapLibre/vector option lives in the same exclusive group as the two
# raster base layers above (all under the "Kartentyp" menu, since from the
# user's point of view they're all just "which kind of map") even though
# it behaves differently under the hood: picking it (or picking a raster
# layer while MapLibre is currently active) switches the whole map engine,
# not just a live layer, and needs a restart - see _on_layer_selected().
MAPLIBRE_LAYER_KEY = "maplayer_maplibre"
MAPLIBRE_LAYER_ID = "maplibre"
# Vector map is the default renderer (see docs/feature_plan.md's "PMTiles-
# Region herunterladen" - the region-download dialog is what makes this a
# reasonable out-of-the-box default rather than a permanently-blank map);
# the raster tile layers (OSM/Satellit) remain fully available as the
# alternative, just no longer pre-selected on a fresh install.
DEFAULT_MAP_RENDERER = "maplibre"
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
DASHBOARD_SCALES = (
    ("dashboard_scale_small", DASHBOARD_SCALE_SMALL),
    ("dashboard_scale_medium", DASHBOARD_SCALE_MEDIUM),
    ("dashboard_scale_large", DASHBOARD_SCALE_LARGE),
)
ALTITUDE_TRACK_TIME_UNITS = (
    ("menu_altitude_track_unit_s", "s"),
    ("menu_altitude_track_unit_min", "min"),
    ("menu_altitude_track_unit_h", "h"),
)
DEFAULT_ALTITUDE_TRACK_TIME_UNIT = "s"
# Initial telemetry-panel share of the window's width (side-docked) or
# height (top/bottom-docked) - just the starting point, the splitter stays
# freely draggable afterwards like any other pane.
DEFAULT_DASHBOARD_SPLIT_FRACTION = 0.20


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
        self._geofence_monitor = GeofenceMonitor(self._tts_worker)
        self._energy_budget_monitor = EnergyBudgetMonitor(self._tts_worker)
        self._tracker_output_sender = TrackerOutputSender()
        self._tracker_output_sender.error_occurred.connect(self._on_tracker_output_error)
        self._battery_chemistry = "lipo"
        self._battery_cells = args.cells
        self._battery_low_v = args.low_cell_voltage
        self._battery_critical_v = args.critical_cell_voltage
        self._battery_capacity_mah = 1300
        self._geofence_enabled = self._ui_state.get("geofence_enabled", False)
        self._geofence_radius_m = DEFAULT_RADIUS_M
        self._geofence_max_alt_m = DEFAULT_MAX_ALT_M
        self._geofence_drawn = False
        self._energy_speed_assumption_ms = DEFAULT_MIN_SPEED_ASSUMPTION_MS
        self._energy_yellow_pct = self._ui_state.get("energy_reserve_yellow_pct", DEFAULT_YELLOW_THRESHOLD_PCT)
        self._energy_green_pct = self._ui_state.get("energy_reserve_green_pct", DEFAULT_GREEN_THRESHOLD_PCT)

        home_position = load_home_position()
        home_lat, home_lon = home_position if home_position is not None else (None, None)
        self._map = MapWidget(
            home_lat=home_lat, home_lon=home_lon,
            renderer=self._ui_state.get("map_renderer", DEFAULT_MAP_RENDERER),
        )
        self._dashboard = Dashboard()
        self._dashboard.set_model_profile_names(list(load_profiles().keys()))
        # No saved preference yet -> auto-pick from the actual screen size
        # (see core/display_info.py), not just DASHBOARD_SCALE_MEDIUM -
        # built after a real report that the dashboard, tuned on a
        # 4K/200%-scaled dev display, looked cramped on a 1920x1080/100%
        # laptop with the same fixed size. An explicit user choice (menu)
        # always wins after that, exactly like horizon_scale above.
        auto_scale = auto_dashboard_scale(detect_available_width(QApplication.primaryScreen()))
        self._dashboard.set_scale(self._ui_state.get("dashboard_scale", auto_scale))
        # The dashboard's natural (unscrolled) minimum height - many field
        # groups plus a docked horizon/altitude chart - can exceed a real
        # screen's usable height (confirmed by a real report: content ran
        # off the bottom, behind the taskbar, with the map's own corner
        # buttons unreachable along with it). A plain QWidget's minimum
        # size propagates straight up to the splitter and then the whole
        # window, which "maximized" can't shrink below - wrapping it in a
        # scroll area caps what the window is forced to grow to; anything
        # that doesn't fit scrolls instead of pushing the window (and
        # everything below it) off-screen.
        self._dashboard_scroll = QScrollArea()
        self._dashboard_scroll.setWidget(self._dashboard)
        self._dashboard_scroll.setWidgetResizable(True)
        self._dashboard_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
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

        self._lost_model_monitor = LostModelMonitor(self._tts_worker)
        self._lost_model_timeout_s = self._ui_state.get("lost_model_timeout_s", LOST_MODEL_DEFAULT_TIMEOUT_S)
        self._lost_model_overlay = LostModelOverlay()
        self._lost_model_overlay.export_gpx_clicked.connect(self._export_lost_model_gpx)
        self._lost_model_overlay.copy_coords_clicked.connect(self._copy_lost_model_coords)
        _resize_from_saved(self._lost_model_overlay, self._ui_state.get("lost_model_overlay_size"))
        self._map.add_overlay(self._lost_model_overlay, "bottom-left")

        self._statustext_console = StatusTextConsole()
        _resize_from_saved(self._statustext_console, self._ui_state.get("statustext_console_size"))
        self._map.add_overlay(self._statustext_console, "top-right")

        self._warning_banner = WarningBanner()
        self._map.add_overlay(self._warning_banner, "center")

        self._replay_states: list = []
        self._replay_transport_overlay = ReplayTransportOverlay()
        self._replay_transport_overlay.play_pause_clicked.connect(self._toggle_replay_play_pause)
        self._replay_transport_overlay.speed_changed.connect(self._on_replay_speed_changed)
        self._replay_transport_overlay.seek_requested.connect(self._on_replay_seek)
        self._replay_transport_overlay.summary_requested.connect(self._open_flight_summary_for_replay)
        self._replay_transport_overlay.closed.connect(self._stop_worker)
        self._replay_transport_overlay.setVisible(False)
        self._map.add_overlay(self._replay_transport_overlay, "top-left")

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
        self._splitter.addWidget(self._dashboard_scroll)
        layout.addWidget(self._splitter)
        self.setCentralWidget(central)

        self._dashboard_position = load_dashboard_position()
        self._apply_dashboard_position(self._dashboard_position)

        self.setStatusBar(QStatusBar())

        if self._map.pmtiles_region_missing():
            # A silently blank/black MapLibre base layer used to be a real,
            # user-reported bug (wrong path resolution under PyInstaller) -
            # now that the path itself is correct, a genuinely-missing file
            # still degrades to a blank map, but the user gets told why and
            # where to put one instead of just seeing black.
            QMessageBox.warning(
                self, i18n.tr("menu_map_layer"), i18n.tr("msgbox_pmtiles_missing_body", path=str(pmtiles_dir()))
            )

        self._worker = None
        self._demo_mode = bool(args.demo)
        self._plan_mode = False
        self._initial_show_handled = False
        self._gs_position = load_gs_position()  # GsPosition | None
        self._mission_session = None  # Optional[MissionUploadSession | MissionDownloadSession]
        self._command_session = None  # Optional[CommandSession] (RTH/mode-change)
        self._mission_progress_dialog = None  # Optional[QProgressDialog]

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
        # Deliberately NOT tied to the menu checkbox's checked state like
        # the other overlays above - this panel should only actually
        # appear once a loss is real (see _check_heartbeat()), not sit on
        # the map permanently showing "not lost". The checkbox instead
        # just gates whether it's *allowed* to pop up at all.
        self._lost_model_overlay.setVisible(False)
        # Same "only pop up for a real event" behavior as the lost-model
        # overlay just above.
        self._warning_banner.setVisible(False)
        self._statustext_console.setVisible(self._statustext_console_action.isChecked())
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
            self._geofence_visible_action, self._geofence_enabled_action,
            self._horizon_toggle_action, self._horizon_dock_action, self._route_editor_action,
            self._route_editor_dock_action, self._track_overlay_action, self._lost_model_overlay_action,
            self._statustext_console_action, self._warning_banner_action,
            self._altitude_track_action, self._altitude_track_dock_action,
        ):
            action.toggled.connect(self._persist_ui_state)
        # _layer_group is deliberately NOT wired here - _on_layer_selected()
        # already persists explicitly, since a raster-layer pick and a
        # renderer-engine switch need different handling first (see there).
        self._vehicle_group.triggered.connect(self._persist_ui_state)
        self._horizon_pos_group.triggered.connect(self._persist_ui_state)
        self._horizon_scale_group.triggered.connect(self._persist_ui_state)
        self._altitude_track_unit_group.triggered.connect(self._persist_ui_state)
        self._lang_group.triggered.connect(self._persist_ui_state)
        self._track_overlay.auto_toggled.connect(self._persist_ui_state)
        self._dashboard.model_profile_selected.connect(self._on_dashboard_model_selected)
        self._dashboard.new_model_profile_requested.connect(self._open_new_model_editor)
        self._dashboard.edit_model_profile_requested.connect(self._open_model_editor_for_active)

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
        self._route_mode_action.toggled.connect(self._on_route_mode_toggled)

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

        # MAVLink mission upload/download - only meaningful with a real
        # MAVLink connection, disabled (not hidden) otherwise; see
        # _update_mavlink_command_availability().
        route_menu.addSeparator()
        self._mission_upload_action = route_menu.addAction("")
        self._i18n_actions.append((self._mission_upload_action, "menu_mission_upload"))
        self._mission_upload_action.triggered.connect(self._start_mission_upload)

        self._mission_download_action = route_menu.addAction("")
        self._i18n_actions.append((self._mission_download_action, "menu_mission_download"))
        self._mission_download_action.triggered.connect(self._start_mission_download)

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

        # Own configured boundary - deliberately its own toggles, independent
        # of the imported-NFZ-zones toggles above (see docs/feature_plan.md:
        # "Eigener Geofence"). Two separate checkboxes, mirroring how NFZ
        # itself splits "sichtbar" from "Distanz-Warnung aktivieren": one
        # for the map ring's visibility, one for whether the feature (live
        # warning + route pre-check) runs at all - a direct one-click menu
        # toggle rather than only a checkbox buried in the settings dialog,
        # so completely disabling it never requires opening a dialog.
        self._geofence_visible_action = view_map_menu.addAction("")
        self._i18n_actions.append((self._geofence_visible_action, "menu_geofence_visible"))
        self._geofence_visible_action.setCheckable(True)
        self._geofence_visible_action.setChecked(self._ui_state.get("geofence_visible", True))
        self._geofence_visible_action.toggled.connect(self._map.set_geofence_visible)

        self._geofence_enabled_action = view_map_menu.addAction("")
        self._i18n_actions.append((self._geofence_enabled_action, "menu_geofence_enabled"))
        self._geofence_enabled_action.setCheckable(True)
        self._geofence_enabled_action.setChecked(self._ui_state.get("geofence_enabled", False))
        self._geofence_enabled_action.toggled.connect(self._on_geofence_enabled_toggled)

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
        # Vector map first - it's the default renderer (see
        # DEFAULT_MAP_RENDERER), the raster tile layers below are the
        # alternative, not the other way around.
        self._maplibre_layer_action = layer_menu.addAction("")
        self._i18n_actions.append((self._maplibre_layer_action, MAPLIBRE_LAYER_KEY))
        self._maplibre_layer_action.setCheckable(True)
        self._maplibre_layer_action.setData(MAPLIBRE_LAYER_ID)
        self._maplibre_layer_action.setChecked(self._ui_state.get("map_renderer", DEFAULT_MAP_RENDERER) == "maplibre")
        self._layer_group.addAction(self._maplibre_layer_action)

        layer_menu.addSeparator()

        # Remembers the last-picked *raster* layer separately from
        # whichever entry is currently checked in the 3-way group below -
        # needed because while "Vektorkarte" is checked, neither "osm" nor
        # "satellite" is, but switching back to Leaflet should still land
        # on whichever raster layer was last actually used, not a hardcoded
        # default.
        self._selected_base_layer = self._ui_state.get("base_layer", "osm")
        for key, layer_id in BASE_LAYERS:
            action = layer_menu.addAction("")
            self._i18n_actions.append((action, key))
            action.setCheckable(True)
            action.setData(layer_id)
            action.setChecked(
                self._ui_state.get("map_renderer", DEFAULT_MAP_RENDERER) == "leaflet"
                and layer_id == self._selected_base_layer
            )
            self._layer_group.addAction(action)
        self._layer_group.triggered.connect(self._on_layer_selected)

        pmtiles_download_action = layer_menu.addAction("")
        self._i18n_actions.append((pmtiles_download_action, "menu_pmtiles_download"))
        pmtiles_download_action.triggered.connect(self._open_pmtiles_download_dialog)

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

        self._track_overlay_action = view_map_menu.addAction("")
        self._i18n_actions.append((self._track_overlay_action, "menu_track_overlay"))
        self._track_overlay_action.setCheckable(True)
        self._track_overlay_action.setChecked(self._ui_state.get("track_overlay_visible", True))
        self._track_overlay_action.toggled.connect(self._track_overlay.setVisible)
        self._track_overlay.closed.connect(lambda: self._track_overlay_action.setChecked(False))

        self._lost_model_overlay_action = view_map_menu.addAction("")
        self._i18n_actions.append((self._lost_model_overlay_action, "menu_lost_model_overlay"))
        self._lost_model_overlay_action.setCheckable(True)
        self._lost_model_overlay_action.setChecked(self._ui_state.get("lost_model_overlay_visible", True))
        self._lost_model_overlay_action.toggled.connect(self._on_lost_model_overlay_enabled_toggled)
        self._lost_model_overlay.closed.connect(lambda: self._lost_model_overlay_action.setChecked(False))

        self._warning_banner_action = view_map_menu.addAction("")
        self._i18n_actions.append((self._warning_banner_action, "menu_warning_banner"))
        self._warning_banner_action.setCheckable(True)
        self._warning_banner_action.setChecked(self._ui_state.get("warning_banner_visible", True))
        self._warning_banner_action.toggled.connect(self._on_warning_banner_enabled_toggled)
        self._warning_banner.closed.connect(lambda: self._warning_banner_action.setChecked(False))

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

        geofence_settings_action = telemetry_menu.addAction("")
        self._i18n_actions.append((geofence_settings_action, "menu_geofence_settings"))
        geofence_settings_action.triggered.connect(self._open_geofence_settings)

        energy_budget_settings_action = telemetry_menu.addAction("")
        self._i18n_actions.append((energy_budget_settings_action, "menu_energy_budget_settings"))
        energy_budget_settings_action.triggered.connect(self._open_energy_budget_settings)

        lost_model_settings_action = telemetry_menu.addAction("")
        self._i18n_actions.append((lost_model_settings_action, "menu_lost_model_settings"))
        lost_model_settings_action.triggered.connect(self._open_lost_model_settings)

        telemetry_menu.addSeparator()
        tracker_output_action = telemetry_menu.addAction("")
        self._i18n_actions.append((tracker_output_action, "menu_tracker_output"))
        tracker_output_action.triggered.connect(self._open_tracker_output)

        model_profiles_action = telemetry_menu.addAction("")
        self._i18n_actions.append((model_profiles_action, "menu_model_profiles"))
        model_profiles_action.triggered.connect(self._open_model_profiles)

        telemetry_menu.addSeparator()
        altitude_track_unit_menu = telemetry_menu.addMenu("")
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

        dashboard_scale_menu = telemetry_menu.addMenu("")
        self._i18n_menus.append((dashboard_scale_menu, "menu_dashboard_scale"))
        self._dashboard_scale_group = QActionGroup(self)
        self._dashboard_scale_group.setExclusive(True)
        for key, scale in DASHBOARD_SCALES:
            action = dashboard_scale_menu.addAction("")
            self._i18n_actions.append((action, key))
            action.setCheckable(True)
            action.setData(scale)
            action.setChecked(scale == self._dashboard.scale())
            self._dashboard_scale_group.addAction(action)
        self._dashboard_scale_group.triggered.connect(self._set_dashboard_scale)

        self._statustext_console_action = telemetry_menu.addAction("")
        self._i18n_actions.append((self._statustext_console_action, "menu_statustext_console"))
        self._statustext_console_action.setCheckable(True)
        self._statustext_console_action.setChecked(self._ui_state.get("statustext_console_visible", True))
        self._statustext_console_action.toggled.connect(self._statustext_console.setVisible)
        self._statustext_console.closed.connect(lambda: self._statustext_console_action.setChecked(False))

        # MAVLink RTH/mode-change - only meaningful with a real MAVLink
        # connection, disabled (not hidden) otherwise; see
        # _update_mavlink_command_availability().
        telemetry_menu.addSeparator()
        self._rth_action = telemetry_menu.addAction("")
        self._i18n_actions.append((self._rth_action, "menu_rth"))
        self._rth_action.triggered.connect(self._trigger_rth)

        self._mode_change_action = telemetry_menu.addAction("")
        self._i18n_actions.append((self._mode_change_action, "menu_mode_change"))
        self._mode_change_action.triggered.connect(self._open_mode_change_dialog)

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

        replay_action = sim_menu.addAction("")
        self._i18n_actions.append((replay_action, "menu_replay_load"))
        replay_action.triggered.connect(self._open_replay_file)

        flight_summary_action = sim_menu.addAction("")
        self._i18n_actions.append((flight_summary_action, "menu_flight_summary"))
        flight_summary_action.triggered.connect(self._open_flight_summary_from_file)

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

        gs_position_action = settings_menu.addAction("")
        self._i18n_actions.append((gs_position_action, "menu_gs_position"))
        gs_position_action.triggered.connect(self._open_gs_position_settings)

        self._dashboard_settings_action = settings_menu.addAction("")
        self._i18n_actions.append((self._dashboard_settings_action, "menu_dashboard_settings"))
        self._dashboard_settings_action.triggered.connect(self._open_dashboard_settings)
        # Same QAction instance, mirrored into Anzeige & Karte and
        # Telemetrie & Hardware too - one settings dialog reachable from
        # wherever it's contextually relevant.
        view_map_menu.addAction(self._dashboard_settings_action)
        telemetry_menu.addAction(self._dashboard_settings_action)

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
        self._update_mavlink_command_availability()
        # Region files are never bundled (multi-GB, see the migration plan)
        # - the tooltip is the one place this folder path is discoverable
        # without opening the manual.
        self._maplibre_layer_action.setToolTip(i18n.tr("maplayer_maplibre_tooltip", path=str(pmtiles_dir())))

    def _update_mavlink_command_availability(self) -> None:
        """Explicitly disable (never just hide) mission upload/download,
        RTH and mode-change whenever MAVLink isn't the configured protocol -
        explicit requirement in docs/feature_plan.md's "MAVLink-Rueckkanal",
        since CRSF/demo have no equivalent commands to send at all."""
        enabled = self._args.protocol == "mavlink"
        tooltip = "" if enabled else i18n.tr("mavlink_command_requires_mavlink")
        for action in (
            self._mission_upload_action, self._mission_download_action,
            self._rth_action, self._mode_change_action,
        ):
            action.setEnabled(enabled)
            action.setToolTip(tooltip)

    # ------------------------------------------------------------- worker

    def _stop_worker(self) -> None:
        if self._worker is not None:
            self._worker.telemetry_received.disconnect(self._on_telemetry)
            self._worker.connection_changed.disconnect(self._on_connection_changed)
            self._worker.error_occurred.disconnect(self._on_error)
            if isinstance(self._worker, MAVLinkWorker):
                self._worker.status_text_received.disconnect(self._statustext_console.add_message)
                self._worker.mission_message_received.disconnect(self._on_mission_message)
                self._worker.command_ack_received.disconnect(self._on_command_ack)
            if isinstance(self._worker, ReplayWorker):
                self._worker.progress.disconnect(self._replay_transport_overlay.set_progress)
                self._worker.finished_replay.disconnect(self._on_replay_finished)
                self._replay_transport_overlay.setVisible(False)
            self._worker.stop()
            self._worker = None
        # Any in-flight mission/command session is now talking to a
        # connection that no longer exists - drop it (this also stops its
        # QTimer, since the timer is a Qt-child of the session) rather than
        # leaving it to time out silently against a dead worker.
        self._mission_session = None
        self._command_session = None
        if self._mission_progress_dialog is not None:
            self._mission_progress_dialog.close()
            self._mission_progress_dialog = None

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
        if isinstance(self._worker, MAVLinkWorker):
            # CRSF/Demo have no MAVLink STATUSTEXT equivalent - the console
            # just stays empty for those, no need to disable/grey it out.
            self._worker.status_text_received.connect(self._statustext_console.add_message)
            self._worker.mission_message_received.connect(self._on_mission_message)
            self._worker.command_ack_received.connect(self._on_command_ack)
        self._worker.start()

        self._reset_session_state()

        if demo:
            status = i18n.tr("status_demo_started")
        elif self._args.connection == "usb":
            status = i18n.tr("status_waiting_usb", protocol=self._args.protocol, port=self._args.serial_port)
        else:
            status = i18n.tr("status_waiting_udp", protocol=self._args.protocol, port=self._args.port)
        self.statusBar().showMessage(status)

    def _reset_session_state(self) -> None:
        """Shared by every worker-start path (live/demo/replay) - clears
        everything that's scoped to "this session's flight" rather than
        to the app as a whole."""
        self._has_fix = False
        self._map.clear_path()
        self._track_recorder.clear()
        self._track_recording = False
        self._track_auto_reference_position = None
        self._track_overlay.set_state(False, 0)
        self._dashboard.reset_session()
        self._altitude_track_start = None
        self._altitude_track_overlay.reset()
        self._map.clear_geofence()
        self._geofence_drawn = False
        self._geofence_monitor.reset()
        self._energy_budget_monitor.reset()
        self._dashboard.update_energy_budget(self._energy_budget_monitor.last_result())
        self._lost_model_monitor.reset()
        self._lost_model_overlay.set_inactive()
        self._warning_banner.setVisible(False)

    def _start_replay(self, states: list) -> None:
        self._stop_worker()
        self._set_plan_mode_checked_silently(False)
        self._set_demo_checked_silently(False)

        self._replay_states = states
        self._worker = ReplayWorker(states, speed=DEFAULT_REPLAY_SPEED)
        self._worker.telemetry_received.connect(self._on_telemetry)
        self._worker.connection_changed.connect(self._on_connection_changed)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.progress.connect(self._replay_transport_overlay.set_progress)
        self._worker.finished_replay.connect(self._on_replay_finished)
        self._worker.start()

        self._reset_session_state()

        self._replay_transport_overlay.set_playing(True)
        self._replay_transport_overlay.setVisible(True)
        self.statusBar().showMessage(i18n.tr("status_replay_started"))

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

    # ------------------------------------------------------------- replay

    def _open_replay_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.tr("menu_replay_load"), "", i18n.tr("route_csv_filter")
        )
        if not path:
            return
        try:
            states = parse_flight_log_csv(path)
        except OSError as exc:
            QMessageBox.critical(self, i18n.tr("msgbox_replay_load_failed_title"), str(exc))
            return
        if not states:
            QMessageBox.warning(
                self, i18n.tr("msgbox_replay_load_failed_title"), i18n.tr("msgbox_replay_empty_body")
            )
            return
        self._start_replay(states)

    def _toggle_replay_play_pause(self) -> None:
        if not isinstance(self._worker, ReplayWorker):
            return
        playing = not self._replay_transport_overlay.is_playing()
        self._worker.set_paused(not playing)
        self._replay_transport_overlay.set_playing(playing)

    def _on_replay_speed_changed(self, speed: float) -> None:
        if isinstance(self._worker, ReplayWorker):
            self._worker.set_speed(speed)

    def _on_replay_seek(self, index: int) -> None:
        if isinstance(self._worker, ReplayWorker):
            self._worker.seek(index)

    def _on_replay_finished(self) -> None:
        self._replay_transport_overlay.set_playing(False)
        self.statusBar().showMessage(i18n.tr("status_replay_finished"), 5000)

    def _open_flight_summary_for_replay(self) -> None:
        summary = summarize(self._replay_states)
        if summary is None:
            QMessageBox.warning(self, i18n.tr("flightsummary_dialog_title"), i18n.tr("msgbox_replay_empty_body"))
            return
        FlightSummaryDialog(summary, self).exec()

    def _open_flight_summary_from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.tr("menu_flight_summary"), "", i18n.tr("route_csv_filter")
        )
        if not path:
            return
        try:
            states = parse_flight_log_csv(path)
        except OSError as exc:
            QMessageBox.critical(self, i18n.tr("msgbox_replay_load_failed_title"), str(exc))
            return
        summary = summarize(states)
        if summary is None:
            QMessageBox.warning(self, i18n.tr("flightsummary_dialog_title"), i18n.tr("msgbox_replay_empty_body"))
            return
        FlightSummaryDialog(summary, self).exec()

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
        self._update_mavlink_command_availability()

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

    def _open_geofence_settings(self) -> None:
        dialog = GeofenceSettingsDialog(self._geofence_radius_m, self._geofence_max_alt_m, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._geofence_radius_m = dialog.radius_m()
        self._geofence_max_alt_m = dialog.max_alt_m()
        self._geofence_monitor.reset()
        self._apply_geofence_to_map()

    def _on_geofence_enabled_toggled(self, enabled: bool) -> None:
        self._geofence_enabled = enabled
        self._geofence_monitor.reset()
        self._apply_geofence_to_map()

    def _open_energy_budget_settings(self) -> None:
        dialog = EnergyBudgetSettingsDialog(
            self._energy_speed_assumption_ms, self._energy_yellow_pct, self._energy_green_pct, parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._energy_speed_assumption_ms = dialog.speed_assumption_ms()
        self._energy_yellow_pct = dialog.yellow_threshold_pct()
        self._energy_green_pct = dialog.green_threshold_pct()
        self._energy_budget_monitor.reset()
        self._persist_ui_state()

    def _open_lost_model_settings(self) -> None:
        value, ok = QInputDialog.getDouble(
            self,
            i18n.tr("menu_lost_model_settings"),
            i18n.tr("lostmodel_timeout_label"),
            self._lost_model_timeout_s,
            1.0,
            600.0,
            0,
        )
        if not ok:
            return
        self._lost_model_timeout_s = value
        self._lost_model_monitor.reset()
        self._lost_model_overlay.set_inactive()
        self._persist_ui_state()

    def _export_lost_model_gpx(self) -> None:
        position = self._lost_model_overlay.frozen_position()
        if position is None:
            return
        default_name = f"lost_model_{time.strftime('%Y%m%d_%H%M%S')}.gpx"
        path, _ = QFileDialog.getSaveFileName(self, i18n.tr("lostmodel_export_gpx_btn"), default_name, i18n.tr("export_gpx_filter"))
        if not path:
            return
        recorder = TrackRecorder()
        recorder.add_point(TelemetryState(lat=position[0], lon=position[1], connected=False))
        try:
            recorder.export_gpx(path)
        except OSError as exc:
            QMessageBox.critical(self, i18n.tr("msgbox_export_failed_title"), str(exc))
            return
        self.statusBar().showMessage(i18n.tr("status_track_saved", path=path), 5000)

    def _copy_lost_model_coords(self) -> None:
        position = self._lost_model_overlay.frozen_position()
        if position is None:
            return
        QApplication.clipboard().setText(f"{position[0]:.6f}, {position[1]:.6f}")
        self.statusBar().showMessage(i18n.tr("status_lost_model_coords_copied"), 5000)

    def _apply_geofence_to_map(self) -> None:
        home = self._dashboard.home_position()
        if self._geofence_enabled and home is not None:
            self._map.set_geofence(home[0], home[1], self._geofence_radius_m)
            self._geofence_drawn = True
        else:
            self._map.clear_geofence()
            self._geofence_drawn = False

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

    def _on_layer_selected(self, action) -> None:
        layer_id = action.data()
        # self._map._renderer is what this session actually launched with -
        # more reliable than re-deriving it from self._ui_state, which is
        # just the on-disk snapshot from startup and never mutated after.
        live_renderer = self._map._renderer
        target_renderer = "maplibre" if layer_id == MAPLIBRE_LAYER_ID else "leaflet"

        if layer_id != MAPLIBRE_LAYER_ID:
            self._selected_base_layer = layer_id

        if target_renderer == live_renderer:
            # No engine change needed - a raster layer switch while already
            # running Leaflet applies live exactly like before; picking
            # "Vektorkarte" again while it's already active is a no-op.
            if layer_id != MAPLIBRE_LAYER_ID:
                self._map.set_base_layer(layer_id)
            self._persist_ui_state()
            return

        # Switching the map engine itself can't be done live - see the
        # migration plan.
        self._persist_ui_state()
        QMessageBox.information(
            self, i18n.tr("menu_map_layer"), i18n.tr("map_renderer_restart_required")
        )

    def _open_pmtiles_download_dialog(self) -> None:
        PMTilesDownloadDialog(self).exec()

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
            geofence_enabled=self._geofence_enabled,
            geofence_radius_m=self._geofence_radius_m,
            geofence_max_alt_m=self._geofence_max_alt_m,
            energy_rth_speed_assumption_ms=self._energy_speed_assumption_ms,
            vehicle_type=self._current_vehicle_type(),
        )

    def _current_vehicle_type(self) -> str:
        action = self._vehicle_group.checkedAction()
        return action.data() if action is not None else "quad"

    def _apply_vehicle_type(self, vehicle_type: str) -> None:
        # setChecked() alone drives the group's exclusivity + menu
        # checkmark (QActionGroup's exclusivity is enforced off each
        # action's toggled signal, not just triggered) but does NOT emit
        # triggered() the way an actual click does - the map update that
        # normally rides on _vehicle_group.triggered has to be done here
        # explicitly, same reasoning as the geofence-enabled sync.
        for action in self._vehicle_group.actions():
            if action.data() == vehicle_type:
                action.setChecked(True)
                break
        self._map.set_vehicle_type(vehicle_type)

    def _open_model_profiles(self) -> None:
        dialog = ModelProfileDialog(self._build_current_model_profile, self)
        dialog.profile_loaded.connect(self._apply_model_profile)
        dialog.profile_edited.connect(self._on_model_profile_edited)
        dialog.exec()
        # The dialog may have added/deleted/renamed profiles - refresh the
        # telemetry-bar dropdown's contents to match either way.
        self._dashboard.set_model_profile_names(list(load_profiles().keys()))

    def _on_model_profile_edited(self, profile: ModelProfile) -> None:
        # Editing a profile that isn't currently active only touches the
        # saved file (ModelProfileDialog._on_edit already did that) - only
        # apply it live here if it's the one actually loaded right now.
        if profile.name == self._dashboard.current_model_profile_name():
            self._apply_model_profile(profile)

    def _open_new_model_editor(self) -> None:
        # Defining a brand-new model directly, instead of the old flow of
        # "save whatever the live app state currently happens to be" -
        # see docs/feature_plan.md's "Erweiterter Modell-Editor".
        dialog = ModelEditorDialog(ModelProfile(name=""), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        profile = dialog.result_profile()
        if not profile.name:
            QMessageBox.warning(self, i18n.tr("modeleditor_dialog_title"), i18n.tr("msgbox_model_name_required"))
            return
        profile.dashboard_visible_fields = sorted(self._dashboard.visible_fields())
        profile.dashboard_group_order = self._dashboard.group_order()
        profile.dashboard_rows = self._dashboard.rows()

        profiles = load_profiles()
        profiles[profile.name] = profile
        save_profiles(profiles)
        self._dashboard.set_model_profile_names(list(profiles.keys()))
        self._dashboard.set_current_model_profile_name(profile.name)
        self._apply_model_profile(profile)
        self._persist_ui_state()

    def _open_model_editor_for_active(self, name: str) -> None:
        # The dropdown's own edit button always targets the currently
        # selected (= active) profile, unlike the Model Manager's Edit
        # button which can target any saved profile - so this always
        # applies live, no "is it still active?" check needed.
        if not name:
            return
        profiles = load_profiles()
        if name not in profiles:
            return
        original = profiles[name]
        dialog = ModelEditorDialog(original, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        edited = dialog.result_profile()
        if not edited.name:
            QMessageBox.warning(self, i18n.tr("modeleditor_dialog_title"), i18n.tr("msgbox_model_name_required"))
            return
        edited.dashboard_visible_fields = original.dashboard_visible_fields
        edited.dashboard_group_order = original.dashboard_group_order
        edited.dashboard_rows = original.dashboard_rows

        if edited.name != name:
            del profiles[name]
        profiles[edited.name] = edited
        save_profiles(profiles)
        self._dashboard.set_model_profile_names(list(profiles.keys()))
        self._dashboard.set_current_model_profile_name(edited.name)
        self._apply_model_profile(edited)
        self._persist_ui_state()

    def _on_route_mode_toggled(self, enabled: bool) -> None:
        self._map.set_route_mode(enabled)
        if enabled and not self._route_editor_action.isChecked():
            # Placing waypoints with the editor panel hidden gives no
            # feedback about what you just added - showing it automatically
            # (never hiding it automatically on the way out, that's still
            # the user's own call) matches what starting waypoint mode is
            # actually for.
            self._route_editor_action.setChecked(True)

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

        self._geofence_radius_m = profile.geofence_radius_m
        self._geofence_max_alt_m = profile.geofence_max_alt_m
        # setChecked() alone (not the enabled=... assignment done directly
        # elsewhere) so its toggled signal fires _on_geofence_enabled_toggled
        # and keeps the menu checkbox as the single source of truth - see
        # ui/geofence_settings_dialog.py's module docstring.
        self._geofence_enabled_action.setChecked(profile.geofence_enabled)
        self._geofence_monitor.reset()
        self._apply_geofence_to_map()

        self._energy_speed_assumption_ms = profile.energy_rth_speed_assumption_ms
        self._energy_budget_monitor.reset()

        self._apply_vehicle_type(profile.vehicle_type)

        visible_fields = set(profile.dashboard_visible_fields)
        self._dashboard.apply_field_visibility(visible_fields)
        save_visible_fields(visible_fields)

        self._dashboard.apply_layout(profile.dashboard_group_order, profile.dashboard_rows)
        save_dashboard_layout(profile.dashboard_group_order, profile.dashboard_rows)
        # Re-fits the splitter's dashboard-pane width to whatever column
        # count the loaded profile actually needs (see
        # _apply_dashboard_position()) - a profile with more columns than
        # currently fit would otherwise stay clipped until something else
        # happens to trigger a re-fit.
        self._apply_dashboard_position(self._dashboard_position)

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

    def _open_gs_position_settings(self) -> None:
        dialog = GsPositionDialog(self._gs_position, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._gs_position = dialog.gs_position()
        save_gs_position(self._gs_position)
        self.statusBar().showMessage(i18n.tr("status_gs_position_saved"), 5000)

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

    def _set_dashboard_scale(self, action) -> None:
        self._dashboard.set_scale(action.data())
        self._persist_ui_state()

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
            self._splitter.insertWidget(0, self._dashboard_scroll)
            self._splitter.insertWidget(1, self._map)
        else:
            self._splitter.insertWidget(0, self._map)
            self._splitter.insertWidget(1, self._dashboard_scroll)
        map_index = self._splitter.indexOf(self._map)
        dashboard_index = self._splitter.indexOf(self._dashboard_scroll)
        self._splitter.setStretchFactor(map_index, 1)
        self._splitter.setStretchFactor(dashboard_index, 0)

        # Give the telemetry panel a sensible default of ~20% of the
        # window's extent (width when side-docked, height when docked to
        # top/bottom) instead of Qt's plain even split - the map is the
        # primary content and the dashboard's stretch factor of 0 above
        # keeps it from growing further on its own as the window resizes.
        # Purely a starting point: the splitter handle stays freely
        # draggable afterwards, same as any other QSplitter pane.
        # Applied twice, deliberately. Right now, synchronously: a fresh
        # QSplitter defaults new panes to a plain even (or even fully
        # lopsided, e.g. 0/100) split until something overrides it, and
        # that raw default is what a slow startup (heavy WebEngine/JS
        # asset load blocking the GUI thread before anything else runs)
        # can end up actually painting to the screen - the "telemetry
        # fills the whole window" flash. Calling it now, using the size
        # from the resize() already applied above, prevents that flash
        # even though the window hasn't been shown yet.
        # And once more, deferred via singleShot(0): calling setSizes()
        # before the window has ever been shown (no real geometry/size-hints
        # resolved yet) doesn't reliably stick on its own - Qt's first-show
        # layout pass can override it, collapsing one pane to 0. Running it
        # again right after the current event-loop pass finishes (geometry
        # settled) is what actually holds long-term.
        def _apply_split_ratio() -> None:
            total = self.width() if side_docked else self.height()
            if total <= 0:
                return
            dashboard_extent = round(total * DEFAULT_DASHBOARD_SPLIT_FRACTION)
            if side_docked:
                # The flat 20% default can be narrower than what the
                # dashboard's own chosen column count actually needs (its
                # width is no longer free to silently borrow space from
                # the map now that it's wrapped in a scroll area - see
                # self._dashboard_scroll - so an under-sized allocation
                # used to just widen the pane automatically, and now
                # instead clips/squeezes the extra columns). Confirmed via
                # a real report: a 2-column layout at 20% width showed
                # only slivers of the second column. Never shrink below
                # what's actually needed to show every column at its
                # natural width.
                dashboard_extent = max(dashboard_extent, self._dashboard.minimumSizeHint().width())
            sizes = [0, 0]
            sizes[dashboard_index] = dashboard_extent
            sizes[map_index] = total - dashboard_extent
            self._splitter.setSizes(sizes)

        _apply_split_ratio()
        QTimer.singleShot(0, _apply_split_ratio)

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
        # state.source == "replay" (reserved for the planned Log-Replay
        # feature - see docs/feature_plan.md's Refactoring #1) marks a
        # packet as historical, not live. Everything below that only
        # *displays* the packet stays unconditional; anything that reaches
        # outside this method - TTS warnings, the external tracker-output
        # connection, live track recording - must not fire for replayed
        # packets, or replaying an old log would speak stale warnings,
        # send fabricated positions to a real antenna tracker, and corrupt
        # the current session's live track.
        is_live = state.source != "replay"

        self._last_telemetry_time = time.time()
        self._last_telemetry_state = state
        self._lost_model_monitor.note_telemetry(state)
        self._dashboard.update_state(state, cells=self._battery_cells)
        self._horizon.update_attitude(state.roll, state.pitch)

        if state.has_gps_fix():
            self._map.update_position(state.lat, state.lon, state.heading, state.link_quality)
            if is_live:
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

            if self._geofence_enabled and not self._geofence_drawn:
                self._apply_geofence_to_map()

            if self._gs_position is not None:
                result = compute_azimuth_elevation(
                    self._gs_position.lat, self._gs_position.lon, self._gs_position.alt,
                    state.lat, state.lon, state.alt,
                )
                self._dashboard.update_gs_azimuth_elevation(result.azimuth_deg, result.elevation_deg)
            else:
                self._dashboard.update_gs_azimuth_elevation(None, None)

        if is_live:
            self._battery_monitor.check(state)
            self._check_nfz_proximity(state)
            self._check_geofence(state)
            self._energy_budget_monitor.check(
                state, self._dashboard.home_position(), self._battery_capacity_mah,
                self._energy_speed_assumption_ms, self._energy_yellow_pct, self._energy_green_pct,
            )
            self._dashboard.update_energy_budget(self._energy_budget_monitor.last_result())
            self._update_warning_banner()
            if self._tracker_output_sender.is_active():
                self._tracker_output_sender.send(state)

    def _check_geofence(self, state: TelemetryState) -> None:
        self._geofence_monitor.check(
            state, self._dashboard.home_position(), self._geofence_radius_m,
            self._geofence_max_alt_m, self._geofence_enabled,
        )
        result = self._geofence_monitor.last_result()
        if result is not None and result.breached():
            self.statusBar().showMessage(i18n.tr("status_geofence_breach", distance=f"{result.distance_m:.0f}"))

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
        now = time.time()
        if self._last_telemetry_time == 0:
            return
        if (now - self._last_telemetry_time) > HEARTBEAT_TIMEOUT_S:
            self._dashboard.set_connection_status(False)

        self._lost_model_monitor.check(now, self._last_telemetry_time, self._lost_model_timeout_s)
        # Finding a downed aircraft needs bearing/distance from where the
        # *pilot* actually is, not the flight-start point - prefer the
        # ground-station position when it's been set, matching
        # docs/feature_plan.md's fallback design (no hard P2 dependency).
        if self._gs_position is not None:
            reference = (self._gs_position.lat, self._gs_position.lon)
        else:
            reference = self._dashboard.home_position()
        info = self._lost_model_monitor.info(reference)
        if info is not None:
            self._lost_model_overlay.update_info(
                info.frozen_state.lat, info.frozen_state.lon, info.distance_m, info.bearing_deg,
                now - info.lost_since,
            )
            # Pop up only for a real loss, not as a permanently-shown
            # "not lost" placeholder - and only if the user hasn't
            # disabled it via the menu checkbox.
            if self._lost_model_overlay_action.isChecked():
                self._lost_model_overlay.setVisible(True)
        else:
            self._lost_model_overlay.set_inactive()
            self._lost_model_overlay.setVisible(False)

    def _on_lost_model_overlay_enabled_toggled(self, enabled: bool) -> None:
        if not enabled:
            self._lost_model_overlay.setVisible(False)
        elif self._lost_model_monitor.is_lost():
            # Re-enabling the checkbox while a loss is still ongoing should
            # bring the popup right back, not wait for the next loss.
            self._lost_model_overlay.setVisible(True)

    def _on_warning_banner_enabled_toggled(self, enabled: bool) -> None:
        if enabled:
            self._update_warning_banner()
        else:
            self._warning_banner.setVisible(False)

    def _update_warning_banner(self) -> None:
        """Surfaces every currently-active safety warning (battery,
        geofence, NFZ proximity, energy budget) visually, on top of the
        spoken TTS warning each of these already triggers - reuses each
        monitor's own state (last_result()/level()) rather than
        duplicating the warning-detection logic here."""
        messages = []

        battery_level = self._battery_monitor.level()
        if battery_level == BATTERY_LEVEL_CRITICAL:
            messages.append(i18n.tr("tts_critical"))
        elif battery_level == BATTERY_LEVEL_LOW:
            messages.append(i18n.tr("tts_low"))

        nfz_result = self._nfz_proximity_monitor.last_result()
        if nfz_result is not None and nfz_result[1] <= DEFAULT_THRESHOLD_M:
            zone, distance = nfz_result
            messages.append(i18n.tr("status_nfz_proximity_warning", name=zone.name, distance=f"{distance:.0f}"))

        geofence_result = self._geofence_monitor.last_result()
        if geofence_result is not None and geofence_result.breached():
            messages.append(i18n.tr("status_geofence_breach", distance=f"{geofence_result.distance_m:.0f}"))

        energy_result = self._energy_budget_monitor.last_result()
        if energy_result.level == ENERGY_LEVEL_RED:
            messages.append(i18n.tr("tts_energy_budget_critical"))
        elif energy_result.level == ENERGY_LEVEL_YELLOW:
            messages.append(i18n.tr("tts_energy_budget_low"))

        if messages and self._warning_banner_action.isChecked():
            self._warning_banner.set_messages(messages)
            self._warning_banner.setVisible(True)
            # set_messages() just changed the banner's own size
            # (adjustSize()), which - unlike the map widget's own resize -
            # doesn't trigger re-centering on its own.
            self._map.reposition_overlays()
        else:
            self._warning_banner.setVisible(False)

    # --------------------------------------------------------------- route

    def _on_route_changed(self) -> None:
        waypoints = self._route_manager.waypoints()
        segments = self._route_manager.segment_distances()
        self._map.render_route(waypoints, segments)
        self._route_overlay.set_waypoints(waypoints, segments)
        self._check_route_bounds(waypoints)

    def _check_route_bounds(self, waypoints) -> None:
        # Pre-flight check against the same geofence.check_geofence() the
        # live in-flight monitor uses (see docs/feature_plan.md), plus any
        # loaded NFZ zones - a lightweight status-bar warning rather than a
        # full per-row UI, since this is advisory, not a hard block.
        home = self._dashboard.home_position()
        out_of_bounds = set()
        if self._geofence_enabled and home is not None:
            out_of_bounds.update(find_out_of_bounds(waypoints, home, self._geofence_radius_m, self._geofence_max_alt_m))

        zones = self._nfz_manager.zones()
        if zones:
            for i, wp in enumerate(waypoints):
                result = nearest_zone(wp.lat, wp.lon, zones)
                if result is not None and result[1] <= 0.0:
                    out_of_bounds.add(i)

        if out_of_bounds:
            self.statusBar().showMessage(
                i18n.tr("status_route_out_of_bounds", count=len(out_of_bounds)), 8000
            )

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

    # ------------------------------------------------- MAVLink-Rueckkanal

    def _require_mavlink_connection(self) -> bool:
        if not isinstance(self._worker, MAVLinkWorker) or self._worker.connection is None:
            QMessageBox.warning(
                self, i18n.tr("msgbox_mavlink_not_connected_title"), i18n.tr("msgbox_mavlink_not_connected_body")
            )
            return False
        return True

    def _on_mission_message(self, msg) -> None:
        if self._mission_session is not None:
            self._mission_session.handle_message(msg)

    def _on_command_ack(self, command: int, result: int) -> None:
        if self._command_session is not None:
            self._command_session.handle_ack(command, result)

    def _begin_mission_progress_dialog(self, title: str):
        dialog = QProgressDialog(title, i18n.tr("mission_progress_cancel"), 0, 1, self)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setValue(0)
        dialog.canceled.connect(self._cancel_mission_session)
        self._mission_progress_dialog = dialog
        return dialog

    def _cancel_mission_session(self) -> None:
        # Only stops our own local state machine (drops the session, which
        # also stops its QTimer) - there is no safe/simple "abort" message
        # to send the flight controller mid-handshake, so a request the FC
        # already received may still be acted on.
        self._mission_session = None
        self._finish_mission_progress_dialog()
        self.statusBar().showMessage(i18n.tr("mission_progress_cancel"), 5000)

    def _finish_mission_progress_dialog(self) -> None:
        if self._mission_progress_dialog is not None:
            self._mission_progress_dialog.close()
            self._mission_progress_dialog = None

    def _start_mission_upload(self) -> None:
        if not self._require_mavlink_connection():
            return
        waypoints = self._route_manager.waypoints()
        if not waypoints:
            QMessageBox.warning(self, i18n.tr("msgbox_no_route_title"), i18n.tr("msgbox_no_route_body"))
            return
        confirm = QMessageBox.question(
            self, i18n.tr("menu_mission_upload"),
            i18n.tr("mavlink_confirm_mission_upload_body", count=len(waypoints)),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        session = MissionUploadSession(self._worker, waypoints)
        self._mission_session = session
        dialog = self._begin_mission_progress_dialog(i18n.tr("mission_upload_progress_title"))
        session.progress.connect(lambda i, total: (dialog.setMaximum(total), dialog.setValue(i)))
        session.finished.connect(self._on_mission_upload_finished)
        session.start()

    def _on_mission_upload_finished(self, success: bool, message: str) -> None:
        self._mission_session = None
        self._finish_mission_progress_dialog()
        if success:
            self.statusBar().showMessage(message, 8000)
        else:
            # MISSION_ACK error codes (and timeouts) must be visible, not
            # just logged - explicit requirement in docs/feature_plan.md.
            QMessageBox.critical(self, i18n.tr("menu_mission_upload"), message)

    def _start_mission_download(self) -> None:
        if not self._require_mavlink_connection():
            return
        confirm = QMessageBox.question(
            self, i18n.tr("menu_mission_download"), i18n.tr("mavlink_confirm_mission_download_body"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        session = MissionDownloadSession(self._worker)
        self._mission_session = session
        dialog = self._begin_mission_progress_dialog(i18n.tr("mission_download_progress_title"))
        session.progress.connect(lambda i, total: (dialog.setMaximum(max(total, 1)), dialog.setValue(i)))
        session.finished.connect(self._on_mission_download_finished)
        session.start()

    def _on_mission_download_finished(self, success: bool, message: str, waypoints: list) -> None:
        self._mission_session = None
        self._finish_mission_progress_dialog()
        if not success:
            QMessageBox.critical(self, i18n.tr("menu_mission_download"), message)
            return
        if waypoints:
            self._route_manager.set_all(waypoints)
        self.statusBar().showMessage(message, 8000)

    def _begin_command_session(self, session) -> None:
        self._command_session = session
        session.finished.connect(self._on_command_session_finished)
        session.start()
        self.statusBar().showMessage(i18n.tr("status_mavlink_command_sent"))

    def _on_command_session_finished(self, success: bool, message: str) -> None:
        self._command_session = None
        if success:
            self.statusBar().showMessage(message, 8000)
        else:
            QMessageBox.critical(self, i18n.tr("msgbox_mavlink_command_failed_title"), message)

    def _trigger_rth(self) -> None:
        if not self._require_mavlink_connection():
            return
        confirm = QMessageBox.question(self, i18n.tr("menu_rth"), i18n.tr("mavlink_confirm_rth_body"))
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._begin_command_session(rth_command_session(self._worker))

    def _open_mode_change_dialog(self) -> None:
        if not self._require_mavlink_connection():
            return
        dialog = ModeChangeDialog(self._current_vehicle_type(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        custom_mode = dialog.selected_mode()
        if custom_mode is None:
            return
        self._begin_command_session(set_mode_command_session(self._worker, custom_mode))

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
            "geofence_visible": self._geofence_visible_action.isChecked(),
            "geofence_enabled": self._geofence_enabled_action.isChecked(),
            "energy_reserve_yellow_pct": self._energy_yellow_pct,
            "energy_reserve_green_pct": self._energy_green_pct,
            "base_layer": self._selected_base_layer,
            "vehicle_type": vehicle_action.data() if vehicle_action is not None else "quad",
            "horizon_visible": self._horizon_toggle_action.isChecked(),
            "horizon_docked": self._horizon_dock_action.isChecked(),
            "horizon_corner": horizon_pos_action.data() if horizon_pos_action is not None else DEFAULT_HORIZON_CORNER,
            "horizon_scale": self._horizon.scale(),
            "dashboard_scale": self._dashboard.scale(),
            "route_editor_visible": self._route_editor_action.isChecked(),
            "route_editor_docked": self._route_editor_dock_action.isChecked(),
            "route_editor_size": [self._route_overlay.width(), self._route_overlay.height()],
            "track_overlay_visible": self._track_overlay_action.isChecked(),
            "track_overlay_size": [self._track_overlay.width(), self._track_overlay.height()],
            "track_auto": self._track_overlay.is_auto_enabled(),
            "lost_model_overlay_visible": self._lost_model_overlay_action.isChecked(),
            "lost_model_overlay_size": [self._lost_model_overlay.width(), self._lost_model_overlay.height()],
            "lost_model_timeout_s": self._lost_model_timeout_s,
            "statustext_console_visible": self._statustext_console_action.isChecked(),
            "statustext_console_size": [self._statustext_console.width(), self._statustext_console.height()],
            "warning_banner_visible": self._warning_banner_action.isChecked(),
            "altitude_track_visible": self._altitude_track_action.isChecked(),
            "altitude_track_docked": self._altitude_track_dock_action.isChecked(),
            "altitude_track_size": [self._altitude_track_overlay.width(), self._altitude_track_overlay.height()],
            "language": i18n.get_language(),
            "path_point_threshold_m": self._path_point_threshold_m,
            "model_profile": self._dashboard.current_model_profile_name(),
            "altitude_track_time_unit": self._altitude_track_overlay.time_unit(),
            "map_renderer": "maplibre" if layer_action is not None and layer_action.data() == MAPLIBRE_LAYER_ID else "leaflet",
        }

    def _persist_ui_state(self, *_args) -> None:
        save_ui_state(self._gather_ui_state())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._initial_show_handled:
            self._initial_show_handled = True
            # _apply_dashboard_position()'s deferred QTimer.singleShot(0, ...)
            # (meant to re-apply the split ratio once geometry has settled -
            # see its own comment) can still fire too early: when startup
            # goes through the real ConnectionSettingsDialog (any plain
            # launch without --demo), that dialog's exec() call is a nested
            # Qt event loop running *inside* MainWindow.__init__(), before
            # this window has ever actually been shown - the singleShot(0)
            # fires during that nested loop, against the splitter's
            # placeholder pre-layout size (Qt's 640x480 default), not the
            # real window size. The splitter then collapses one pane to 0
            # once real geometry finally arrives. Re-running it here, on
            # the window's own first real showEvent, is the one point
            # guaranteed to have final geometry and to never race a nested
            # dialog - this fixes it regardless of which startup path (demo/
            # plan/manual-connect) the user took.
            self._apply_dashboard_position(self._dashboard_position)

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
