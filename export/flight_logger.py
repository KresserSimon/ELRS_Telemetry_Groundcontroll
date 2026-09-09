"""Continuous flight-data logger: writes a time-series CSV of telemetry
fields at a configurable interval, on a QTimer on the GUI thread (each
tick is a cheap CSV row write, so this doesn't need its own thread).

field_value()/ALL_FIELDS are also reused by export/track_export.py's own
CSV export ("Flugpfad als CSV exportieren") so both CSV formats stay
byte-for-byte identical wherever their field sets overlap - a file from
either one loads back through telemetry/replay_worker.py's Log-Replay the
same way. The two remain otherwise independent: this logger runs
continuously at a fixed interval regardless of GPS fix, while
track_export.py's recorder only keeps points that had one, and only
turns them into a file after the fact.
"""
from __future__ import annotations

import csv
import time
from typing import Callable, List, Optional

from PyQt6.QtCore import QObject, QTimer

from core.telemetry_state import TelemetryState

ALL_FIELDS = (
    "timestamp", "lat", "lon", "alt", "satellites", "gps_fix", "heading",
    "roll", "pitch", "flight_mode",
    "battery_voltage", "battery_remaining", "battery_current", "battery_capacity_used", "cell_voltages",
    "rssi", "link_quality", "snr", "tx_power",
    "vario", "baro_altitude", "rpm", "temperature", "groundspeed", "airspeed",
    "connected",
)
DEFAULT_FIELDS = ALL_FIELDS

MIN_INTERVAL_MS = 50


def field_value(state: TelemetryState, field: str):
    if field == "timestamp":
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(state.timestamp))
    if field == "cell_voltages":
        return "|".join(f"{v:.3f}" for v in state.cell_voltages) if state.cell_voltages else ""
    value = getattr(state, field, "")
    return "" if value is None else value


class FlightLogger(QObject):
    def __init__(self, state_provider: Callable[[], Optional[TelemetryState]]) -> None:
        super().__init__()
        self._state_provider = state_provider
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._file = None
        self._writer = None
        self._fields: List[str] = list(DEFAULT_FIELDS)

    def is_active(self) -> bool:
        return self._file is not None

    def start(self, path: str, fields: List[str], interval_s: float) -> None:
        self.stop()
        self._fields = list(fields) or list(DEFAULT_FIELDS)
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(self._fields)
        self._file.flush()
        self._timer.start(max(MIN_INTERVAL_MS, round(interval_s * 1000)))

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        if self._file is not None:
            self._file.close()
            self._file = None
            self._writer = None

    def _tick(self) -> None:
        state = self._state_provider()
        if state is None or self._writer is None:
            return
        self._writer.writerow([field_value(state, f) for f in self._fields])
        self._file.flush()
