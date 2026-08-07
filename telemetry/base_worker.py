"""Common QThread interface every telemetry backend (MAVLink, CRSF, demo) implements.

Keeping one signal contract lets the UI stay completely agnostic of where the
data actually comes from.
"""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from core.telemetry_state import TelemetryState


class TelemetryWorker(QThread):
    telemetry_received = pyqtSignal(object)     # TelemetryState
    connection_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._running = True

    def stop(self) -> None:
        self._running = False
        self.wait(3000)
