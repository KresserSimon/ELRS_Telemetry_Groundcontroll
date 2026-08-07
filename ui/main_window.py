"""Main application window: map + dashboard + menus, wired to a telemetry worker."""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QWidget,
    QVBoxLayout,
)

from alerts.tts_alert import BatteryAlertMonitor, TTSWorker
from core.telemetry_state import TelemetryState
from export.track_export import TrackRecorder
from telemetry.crsf_worker import CRSFWorker
from telemetry.demo_worker import DemoWorker
from telemetry.mavlink_worker import MAVLinkWorker
from ui.dashboard import Dashboard
from ui.map_widget import MapWidget

HEARTBEAT_TIMEOUT_S = 3.0


class MainWindow(QMainWindow):
    def __init__(self, args) -> None:
        super().__init__()
        self._args = args
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

        self._build_menu()

        self._last_telemetry_time = 0.0
        self._has_fix = False

        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(1000)
        self._heartbeat_timer.timeout.connect(self._check_heartbeat)
        self._heartbeat_timer.start()

        self._worker = None
        self._demo_mode = bool(args.demo)
        self._start_worker(demo=self._demo_mode)

    # ---------------------------------------------------------------- menu

    def _build_menu(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&Datei")
        export_gpx_action = file_menu.addAction("Flugpfad als GPX exportieren...")
        export_gpx_action.triggered.connect(lambda: self._export_track("gpx"))
        export_kml_action = file_menu.addAction("Flugpfad als KML exportieren...")
        export_kml_action.triggered.connect(lambda: self._export_track("kml"))
        file_menu.addSeparator()
        exit_action = file_menu.addAction("Beenden")
        exit_action.triggered.connect(self.close)

        view_menu = menu.addMenu("&Ansicht")
        self._auto_center_action = view_menu.addAction("Auto-Center")
        self._auto_center_action.setCheckable(True)
        self._auto_center_action.setChecked(True)
        self._auto_center_action.toggled.connect(self._map.set_auto_center)

        sim_menu = menu.addMenu("&Simulation")
        self._demo_action = sim_menu.addAction("Demo-Modus")
        self._demo_action.setCheckable(True)
        self._demo_action.setChecked(self._demo_mode)
        self._demo_action.toggled.connect(self._toggle_demo_mode)

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
        self.statusBar().showMessage(
            "Demo-Modus gestartet" if demo else f"Warte auf Telemetrie ({self._args.protocol}, Port {self._args.port})..."
        )

    def _toggle_demo_mode(self, enabled: bool) -> None:
        self._demo_mode = enabled
        self._start_worker(demo=enabled)

    # ------------------------------------------------------------ signals

    def _on_telemetry(self, state: TelemetryState) -> None:
        self._last_telemetry_time = time.time()
        self._dashboard.update_state(state)

        if state.has_gps_fix():
            self._map.update_position(state.lat, state.lon, state.heading)
            self._track_recorder.add_point(state)
            self._has_fix = True

        self._battery_monitor.check(state)

    def _on_connection_changed(self, connected: bool) -> None:
        self.statusBar().showMessage("Telemetrie verbunden" if connected else "Telemetrie getrennt")

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
            QMessageBox.warning(self, "Kein Flugpfad", "Es wurden noch keine GPS-Punkte aufgezeichnet.")
            return

        filter_str = "GPX-Datei (*.gpx)" if fmt == "gpx" else "KML-Datei (*.kml)"
        default_name = f"flight_{time.strftime('%Y%m%d_%H%M%S')}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, "Flugpfad exportieren", default_name, filter_str)
        if not path:
            return

        try:
            if fmt == "gpx":
                self._track_recorder.export_gpx(path)
            else:
                self._track_recorder.export_kml(path)
        except OSError as exc:
            QMessageBox.critical(self, "Export fehlgeschlagen", str(exc))
            return

        self.statusBar().showMessage(f"Flugpfad gespeichert: {path}", 5000)

    # -------------------------------------------------------------- close

    def closeEvent(self, event) -> None:
        if self._worker is not None:
            self._worker.stop()
        self._tts_worker.stop()
        super().closeEvent(event)
