"""MAVLink single-shot commands (RTH, flight-mode change) sent via
COMMAND_LONG - see docs/feature_plan.md's "MAVLink-Rueckkanal". Same
timeout/retry-then-fail-visibly shape as telemetry/mavlink_mission.py's
upload/download sessions, but simpler: one COMMAND_LONG out, one matching
COMMAND_ACK in (MAVLinkWorker.command_ack_received), no multi-message
handshake.

Pure protocol logic - no UI, no confirmation dialog (that is
ui/mavlink_command_dialog.py's job, shown before ever calling start()).
"""
from __future__ import annotations

from typing import Tuple

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

REQUEST_TIMEOUT_MS = 3000
MAX_RETRIES = 3

MAV_RESULT_ACCEPTED = 0

MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
MAV_CMD_DO_SET_MODE = 176
_MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 1

# Curated, deliberately non-exhaustive ArduPilot custom_mode numbers - just
# enough safe/common modes to be useful, not a full reproduction of every
# firmware's mode table. Copter modes apply to vehicle_type "quad"; the same
# ArduPlane mode table is used for both "wing" and "plane" (both fixed-wing
# from a flight-mode point of view - see core/model_profiles.py's
# vehicle_type values and ui/main_window.py's VEHICLE_TYPES).
COPTER_MODES: Tuple[Tuple[str, int], ...] = (
    ("mode_stabilize", 0),
    ("mode_alt_hold", 2),
    ("mode_loiter", 5),
    ("mode_auto", 3),
    ("mode_guided", 4),
    ("mode_rtl", 6),
    ("mode_land", 9),
)
PLANE_MODES: Tuple[Tuple[str, int], ...] = (
    ("mode_manual", 0),
    ("mode_fbwa", 5),
    ("mode_cruise", 7),
    ("mode_auto", 10),
    ("mode_loiter", 12),
    ("mode_rtl", 11),
)


def modes_for_vehicle_type(vehicle_type: str) -> Tuple[Tuple[str, int], ...]:
    if vehicle_type == "quad":
        return COPTER_MODES
    return PLANE_MODES


class CommandSession(QObject):
    """One COMMAND_LONG, one matching COMMAND_ACK, timeout+retry in between.
    `description` is only used in the timeout/failure message text."""

    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        worker,
        command_id: int,
        params: Tuple[float, float, float, float, float, float, float] = (0, 0, 0, 0, 0, 0, 0),
        description: str = "",
        target_system: int = 1,
        target_component: int = 1,
    ) -> None:
        super().__init__()
        self._worker = worker
        self._command_id = command_id
        self._params = params
        self._description = description
        self._target_system = target_system
        self._target_component = target_component
        self._retries = 0
        self._done = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def start(self) -> None:
        self._send()

    def _send(self) -> None:
        conn = self._worker.connection
        p = self._params
        self._worker.enqueue_send(
            lambda: conn.mav.command_long_send(
                self._target_system, self._target_component, self._command_id, 0,
                p[0], p[1], p[2], p[3], p[4], p[5], p[6],
            )
        )
        self._timer.start(REQUEST_TIMEOUT_MS)

    def _on_timeout(self) -> None:
        if self._done:
            return
        self._retries += 1
        if self._retries > MAX_RETRIES:
            self._finish(False, f"Zeitüberschreitung - keine Antwort vom Fluggerät ({self._description}).")
            return
        self._send()

    def handle_ack(self, command: int, result: int) -> None:
        if self._done or command != self._command_id:
            return
        self._timer.stop()
        if result == MAV_RESULT_ACCEPTED:
            self._finish(True, f"{self._description}: vom Fluggerät bestätigt.")
        else:
            self._finish(False, f"{self._description}: vom Fluggerät abgelehnt (Code {result}).")

    def _finish(self, success: bool, message: str) -> None:
        self._done = True
        self._timer.stop()
        self.finished.emit(success, message)


def rth_command_session(worker, target_system: int = 1, target_component: int = 1) -> CommandSession:
    return CommandSession(
        worker, MAV_CMD_NAV_RETURN_TO_LAUNCH,
        description="Return to Launch",
        target_system=target_system, target_component=target_component,
    )


def set_mode_command_session(worker, custom_mode: int, target_system: int = 1, target_component: int = 1) -> CommandSession:
    return CommandSession(
        worker, MAV_CMD_DO_SET_MODE,
        params=(_MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, custom_mode, 0, 0, 0, 0, 0),
        description="Moduswechsel",
        target_system=target_system, target_component=target_component,
    )
