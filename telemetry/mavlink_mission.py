"""MAVLink mission upload/download protocol (MISSION_COUNT/MISSION_ITEM_INT/
MISSION_REQUEST_INT/MISSION_ACK) - see docs/feature_plan.md's
"MAVLink-Rueckkanal". Runs as a small state machine driven by the app's own
Qt event loop: outgoing messages go through MAVLinkWorker.enqueue_send()
(telemetry/mavlink_worker.py's Refactoring #2 - the only thread allowed to
touch the actual connection is the worker's own), incoming MISSION_*
messages are forwarded in via handle_message(), and a QTimer-based timeout
with a small number of retries keeps a dropped/ignored request from
hanging forever - it fails visibly instead.

Pure protocol logic - no UI, no confirmation dialogs (that's
ui/mavlink_command_dialog.py's job, shown before ever starting a session).
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.route import Waypoint

REQUEST_TIMEOUT_MS = 3000
MAX_RETRIES = 3

# MAV_MISSION_RESULT (subset worth distinguishing to the user).
MAV_MISSION_ACCEPTED = 0

# MAV_CMD values used for the action <-> MAVLink command mapping below -
# see export/inav_mission.py's MissionAction for the same action strings
# used by the existing INAV import/export path, reused here rather than
# inventing a second vocabulary.
_MAV_CMD_NAV_WAYPOINT = 16
_MAV_CMD_NAV_LAND = 21
_MAV_CMD_NAV_LOITER_TIME = 19
_MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
_MAV_CMD_DO_JUMP = 177

_ACTION_TO_MAV_CMD = {
    "WAYPOINT": _MAV_CMD_NAV_WAYPOINT,
    "HOLD": _MAV_CMD_NAV_LOITER_TIME,
    "RTH": _MAV_CMD_NAV_RETURN_TO_LAUNCH,
    "JUMP": _MAV_CMD_DO_JUMP,
    "LAND": _MAV_CMD_NAV_LAND,
}
_MAV_CMD_TO_ACTION = {v: k for k, v in _ACTION_TO_MAV_CMD.items()}

# MAV_FRAME_GLOBAL_RELATIVE_ALT - altitude relative to home, matching how
# Waypoint.alt is already interpreted everywhere else in this app (see
# routeeditor_alt's i18n label).
_MAV_FRAME_GLOBAL_RELATIVE_ALT = 3


def waypoint_to_mission_item_params(wp: Waypoint) -> dict:
    """Pure mapping, no Qt/mavutil dependency - easy to unit test."""
    command = _ACTION_TO_MAV_CMD.get(wp.action, _MAV_CMD_NAV_WAYPOINT)
    if command == _MAV_CMD_NAV_WAYPOINT:
        param1 = float(wp.p1)  # hold time (s)
    elif command == _MAV_CMD_NAV_LOITER_TIME:
        param1 = float(wp.p1)  # duration (s)
    elif command == _MAV_CMD_DO_JUMP:
        param1 = float(wp.p1)  # target seq (1-based)
    else:
        param1 = 0.0
    param2 = float(wp.p2) if command == _MAV_CMD_DO_JUMP else 0.0
    return {
        "command": command,
        "param1": param1,
        "param2": param2,
        "param3": 0.0,
        "param4": 0.0,
        "x": int(round(wp.lat * 1e7)),
        "y": int(round(wp.lon * 1e7)),
        "z": float(wp.alt or 0.0),
    }


def mission_item_params_to_waypoint(command: int, param1: float, param2: float, x: int, y: int, z: float) -> Waypoint:
    """Inverse of waypoint_to_mission_item_params() - for download."""
    action = _MAV_CMD_TO_ACTION.get(command, "WAYPOINT")
    p1 = int(round(param1)) if action in ("WAYPOINT", "HOLD", "JUMP") else 0
    p2 = int(round(param2)) if action == "JUMP" else 0
    return Waypoint(lat=x / 1e7, lon=y / 1e7, alt=z, action=action, p1=p1, p2=p2)


class MissionUploadSession(QObject):
    progress = pyqtSignal(int, int)  # (uploaded count, total)
    finished = pyqtSignal(bool, str)  # (success, human-readable message)

    def __init__(self, worker, waypoints: List[Waypoint], target_system: int = 1, target_component: int = 1) -> None:
        super().__init__()
        self._worker = worker
        self._waypoints = waypoints
        self._target_system = target_system
        self._target_component = target_component
        self._retries = 0
        self._done = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def start(self) -> None:
        if not self._waypoints:
            self._finish(False, "Keine Wegpunkte zum Hochladen.")
            return
        self._send_count()

    def _send_count(self) -> None:
        count = len(self._waypoints)
        conn = self._worker.connection
        self._worker.enqueue_send(
            lambda: conn.mav.mission_count_send(self._target_system, self._target_component, count)
        )
        self._timer.start(REQUEST_TIMEOUT_MS)

    def _on_timeout(self) -> None:
        if self._done:
            return
        self._retries += 1
        if self._retries > MAX_RETRIES:
            self._finish(False, "Zeitüberschreitung - keine Antwort vom Fluggerät.")
            return
        self._send_count()

    def handle_message(self, msg) -> None:
        if self._done:
            return
        msg_type = msg.get_type()
        if msg_type in ("MISSION_REQUEST_INT", "MISSION_REQUEST"):
            self._timer.stop()
            self._retries = 0
            seq = msg.seq
            if seq >= len(self._waypoints):
                return
            self._send_item(seq, self._waypoints[seq])
            self.progress.emit(seq, len(self._waypoints))
            self._timer.start(REQUEST_TIMEOUT_MS)
        elif msg_type == "MISSION_ACK":
            self._timer.stop()
            if msg.type == MAV_MISSION_ACCEPTED:
                self._finish(True, "Mission erfolgreich hochgeladen.")
            else:
                self._finish(False, f"Fluggerät hat die Mission abgelehnt (Code {msg.type}).")

    def _send_item(self, seq: int, wp: Waypoint) -> None:
        params = waypoint_to_mission_item_params(wp)
        conn = self._worker.connection
        self._worker.enqueue_send(
            lambda: conn.mav.mission_item_int_send(
                self._target_system, self._target_component, seq,
                _MAV_FRAME_GLOBAL_RELATIVE_ALT, params["command"], 0, 1,
                params["param1"], params["param2"], params["param3"], params["param4"],
                params["x"], params["y"], params["z"],
            )
        )

    def _finish(self, success: bool, message: str) -> None:
        self._done = True
        self._timer.stop()
        self.finished.emit(success, message)


class MissionDownloadSession(QObject):
    progress = pyqtSignal(int, int)  # (received count, total)
    finished = pyqtSignal(bool, str, list)  # (success, message, waypoints)

    def __init__(self, worker, target_system: int = 1, target_component: int = 1) -> None:
        super().__init__()
        self._worker = worker
        self._target_system = target_system
        self._target_component = target_component
        self._retries = 0
        self._done = False
        self._total = 0
        self._items: dict = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def start(self) -> None:
        conn = self._worker.connection
        self._worker.enqueue_send(
            lambda: conn.mav.mission_request_list_send(self._target_system, self._target_component)
        )
        self._timer.start(REQUEST_TIMEOUT_MS)

    def _on_timeout(self) -> None:
        if self._done:
            return
        self._retries += 1
        if self._retries > MAX_RETRIES:
            self._finish(False, "Zeitüberschreitung - keine Antwort vom Fluggerät.", [])
            return
        if self._total == 0:
            self.start()
        else:
            self._request_next()

    def handle_message(self, msg) -> None:
        if self._done:
            return
        msg_type = msg.get_type()
        if msg_type == "MISSION_COUNT":
            self._timer.stop()
            self._retries = 0
            self._total = msg.count
            if self._total == 0:
                self._finish(True, "Fluggerät hat keine Mission gespeichert.", [])
                return
            self._request_next()
        elif msg_type in ("MISSION_ITEM_INT", "MISSION_ITEM"):
            self._timer.stop()
            self._retries = 0
            self._items[msg.seq] = mission_item_params_to_waypoint(
                msg.command, msg.param1, msg.param2, msg.x, msg.y, msg.z
            )
            self.progress.emit(len(self._items), self._total)
            if len(self._items) >= self._total:
                self._send_ack_and_finish()
            else:
                self._request_next()

    def _request_next(self) -> None:
        seq = len(self._items)
        conn = self._worker.connection
        self._worker.enqueue_send(
            lambda: conn.mav.mission_request_int_send(self._target_system, self._target_component, seq)
        )
        self._timer.start(REQUEST_TIMEOUT_MS)

    def _send_ack_and_finish(self) -> None:
        conn = self._worker.connection
        self._worker.enqueue_send(
            lambda: conn.mav.mission_ack_send(self._target_system, self._target_component, MAV_MISSION_ACCEPTED)
        )
        waypoints = [self._items[i] for i in range(self._total)]
        self._finish(True, f"{self._total} Wegpunkte heruntergeladen.", waypoints)

    def _finish(self, success: bool, message: str, waypoints: list) -> None:
        self._done = True
        self._timer.stop()
        self.finished.emit(success, message, waypoints)
