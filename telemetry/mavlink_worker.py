"""MAVLink telemetry backend, over UDP or a direct USB/serial connection.

UDP is the recommended path for ArduPilot / Betaflight flight controllers
paired with an ELRS receiver: the FC (or an ESP32/ESP8266 WiFi bridge sitting
between the FC and the ELRS RX) streams MAVLink on the standard GCS UDP port
(14550) and this worker just listens for it, exactly like QGroundControl or
Mission Planner would. Serial mode is for a FC or ELRS TX module plugged
directly into the PC via USB, outputting MAVLink on its USB-serial port.
"""
from __future__ import annotations

import math
import queue
import time
from typing import Callable

from PyQt6.QtCore import pyqtSignal
from pymavlink import mavutil

from core.telemetry_state import TelemetryState
from telemetry.base_worker import TelemetryWorker

CONNECTION_TIMEOUT_S = 3.0
MAVLINK_SERIAL_DEFAULT_BAUD = 57600


class MAVLinkWorker(TelemetryWorker):
    status_text_received = pyqtSignal(int, str)  # severity (MAV_SEVERITY 0-7), text
    mission_message_received = pyqtSignal(object)  # raw pymavlink MISSION_* message
    command_ack_received = pyqtSignal(int, int)  # (command id, MAV_RESULT)

    def __init__(
        self,
        connection_type: str = "udp",
        host: str = "0.0.0.0",
        port: int = 14550,
        udp_mode: str = "listen",
        serial_port: str = "",
        baud: int = MAVLINK_SERIAL_DEFAULT_BAUD,
    ) -> None:
        super().__init__()
        self._connection_type = connection_type
        self._host = host
        self._port = port
        self._udp_mode = udp_mode
        self._serial_port = serial_port
        self._baud = baud
        self._state = TelemetryState(source="mavlink")

        # The mavutil connection is only ever touched from this worker's
        # own thread (set in run(), cleared when it exits) - never call
        # .mav.xxx_send(...) on `connection` directly from the GUI thread,
        # use enqueue_send() instead. Exposed (read-only) for future
        # callers - mission upload/download, RTH/mode-change commands (see
        # docs/feature_plan.md's "MAVLink-Rueckkanal") - that need to read
        # connection details (e.g. target_system) while building a message.
        self._conn = None
        self._send_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()

    @property
    def connection(self):
        return self._conn

    def enqueue_send(self, send_fn: Callable[[], None]) -> None:
        """Thread-safe from any thread: queue a zero-arg callable (typically
        `lambda: worker.connection.mav.xxx_send(...)`) to run on this
        worker's own thread during its next receive-loop iteration - the
        only thread allowed to touch the underlying mavutil connection.
        Silently queued even if not yet connected; run()'s loop only
        drains it once `connection` is set."""
        self._send_queue.put(send_fn)

    def _drain_send_queue(self) -> None:
        while True:
            try:
                send_fn = self._send_queue.get_nowait()
            except queue.Empty:
                return
            try:
                send_fn()
            except Exception as exc:
                self.error_occurred.emit(f"MAVLink-Senden fehlgeschlagen: {exc}")

    def _connection_string(self) -> str:
        if self._connection_type == "serial":
            return self._serial_port
        if self._udp_mode == "connect":
            return f"udpout:{self._host}:{self._port}"
        return f"udpin:{self._host}:{self._port}"

    def run(self) -> None:
        try:
            if self._connection_type == "serial":
                self._conn = mavutil.mavlink_connection(self._connection_string(), baud=self._baud)
            else:
                self._conn = mavutil.mavlink_connection(self._connection_string())
        except Exception as exc:
            self.error_occurred.emit(f"MAVLink-Verbindung fehlgeschlagen: {exc}")
            return

        last_msg_time = 0.0
        was_connected = False

        while self._running:
            self._drain_send_queue()
            try:
                msg = self._conn.recv_match(blocking=True, timeout=1.0)
            except Exception as exc:
                self.error_occurred.emit(f"MAVLink Empfangsfehler: {exc}")
                msg = None

            now = time.time()

            if msg is not None:
                try:
                    self._apply_message(msg)
                except Exception as exc:
                    self.error_occurred.emit(f"MAVLink Parse-Fehler: {exc}")
                    continue

                last_msg_time = now
                self._state.connected = True
                self._state.source = "mavlink"
                self.telemetry_received.emit(self._state.copy())

                if not was_connected:
                    was_connected = True
                    self.connection_changed.emit(True)

            if was_connected and (now - last_msg_time) > CONNECTION_TIMEOUT_S:
                was_connected = False
                self._state.connected = False
                self.connection_changed.emit(False)

        try:
            self._conn.close()
        except Exception:
            pass
        self._conn = None

    def _apply_message(self, msg) -> None:
        msg_type = msg.get_type()
        s = self._state

        if msg_type == "HEARTBEAT":
            try:
                s.flight_mode = mavutil.mode_string_v10(msg)
            except Exception:
                s.flight_mode = f"MODE({msg.custom_mode})"

        elif msg_type == "ATTITUDE":
            s.roll = math.degrees(msg.roll)
            s.pitch = math.degrees(msg.pitch)

        elif msg_type == "GLOBAL_POSITION_INT":
            s.lat = msg.lat / 1e7
            s.lon = msg.lon / 1e7
            s.alt = msg.relative_alt / 1000.0
            if msg.hdg != 65535:
                s.heading = msg.hdg / 100.0

        elif msg_type == "GPS_RAW_INT":
            if s.lat is None:
                s.lat = msg.lat / 1e7
                s.lon = msg.lon / 1e7
            s.satellites = msg.satellites_visible
            s.gps_fix = msg.fix_type
            if msg.alt not in (0, None) and s.alt is None:
                s.alt = msg.alt / 1000.0

        elif msg_type == "SYS_STATUS":
            if msg.voltage_battery not in (0, 65535, -1):
                s.battery_voltage = msg.voltage_battery / 1000.0
            if msg.battery_remaining >= 0:
                s.battery_remaining = msg.battery_remaining

        elif msg_type == "BATTERY_STATUS":
            voltages = [v for v in msg.voltages if v not in (0, 65535)]
            if voltages:
                s.battery_voltage = sum(voltages) / 1000.0
                s.cell_voltages = [v / 1000.0 for v in voltages]
            if msg.battery_remaining >= 0:
                s.battery_remaining = msg.battery_remaining
            if msg.current_battery != -1:
                s.battery_current = msg.current_battery / 100.0
            if msg.current_consumed != -1:
                s.battery_capacity_used = float(msg.current_consumed)

        elif msg_type in ("RADIO_STATUS", "RADIO"):
            if msg.rssi != 255:
                s.rssi = msg.rssi

        elif msg_type == "RC_CHANNELS":
            if getattr(msg, "rssi", 255) != 255:
                s.link_quality = round(msg.rssi / 255 * 100)

        elif msg_type == "VFR_HUD":
            s.vario = msg.climb
            s.groundspeed = msg.groundspeed
            # Only meaningful with a real airspeed sensor (fixed-wing).
            # Firmware without one (most multirotors) mirrors groundspeed
            # into this field, which core/wind_estimate.py's caller-side
            # "same value" check treats as "no real airspeed data".
            s.airspeed = msg.airspeed

        elif msg_type in ("NAMED_VALUE_FLOAT", "NAMED_VALUE_INT"):
            # Catch-all for telemetry outside the fixed fields above -
            # e.g. custom firmware/sensor values a flight controller
            # exposes under its own name, with no dedicated field here to
            # parse them into. See core/telemetry_catalog.py and
            # docs/feature_plan.md's "Telemetrie-Variablen-Editor".
            name = msg.name
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            name = name.rstrip("\x00")
            if name:
                s.extra[name] = float(msg.value)

        elif msg_type == "STATUSTEXT":
            # An event (prearm/EKF/mode-change messages, etc.), not a
            # persistent field - deliberately NOT written into `s`/
            # TelemetryState, which only holds current-value telemetry.
            # Emitted as its own signal for a future scrollable console
            # (see docs/feature_plan.md's "MAVLink-STATUSTEXT-Konsole");
            # no listener is wired up to it yet.
            text = msg.text
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="replace")
            self.status_text_received.emit(msg.severity, text.rstrip("\x00"))

        elif msg_type in (
            "MISSION_COUNT", "MISSION_ITEM_INT", "MISSION_ITEM",
            "MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK",
        ):
            # Mission upload/download protocol messages, not telemetry
            # fields - forwarded to whichever MissionUploadSession/
            # MissionDownloadSession is currently active, if any (see
            # telemetry/mavlink_mission.py).
            self.mission_message_received.emit(msg)

        elif msg_type == "COMMAND_ACK":
            # Acknowledges a COMMAND_LONG we sent (RTH/mode-change) - lets
            # the UI confirm the flight controller actually accepted it,
            # not just that we managed to send it.
            self.command_ack_received.emit(msg.command, msg.result)
