"""MAVLink telemetry backend, over UDP or a direct USB/serial connection.

UDP is the recommended path for ArduPilot / Betaflight flight controllers
paired with an ELRS receiver: the FC (or an ESP32/ESP8266 WiFi bridge sitting
between the FC and the ELRS RX) streams MAVLink on the standard GCS UDP port
(14550) and this worker just listens for it, exactly like QGroundControl or
Mission Planner would. Serial mode is for a FC or ELRS TX module plugged
directly into the PC via USB, outputting MAVLink on its USB-serial port.
"""
from __future__ import annotations

import time

from pymavlink import mavutil

from core.telemetry_state import TelemetryState
from telemetry.base_worker import TelemetryWorker

CONNECTION_TIMEOUT_S = 3.0
MAVLINK_SERIAL_DEFAULT_BAUD = 57600


class MAVLinkWorker(TelemetryWorker):
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

    def _connection_string(self) -> str:
        if self._connection_type == "serial":
            return self._serial_port
        if self._udp_mode == "connect":
            return f"udpout:{self._host}:{self._port}"
        return f"udpin:{self._host}:{self._port}"

    def run(self) -> None:
        try:
            if self._connection_type == "serial":
                conn = mavutil.mavlink_connection(self._connection_string(), baud=self._baud)
            else:
                conn = mavutil.mavlink_connection(self._connection_string())
        except Exception as exc:
            self.error_occurred.emit(f"MAVLink-Verbindung fehlgeschlagen: {exc}")
            return

        last_msg_time = 0.0
        was_connected = False

        while self._running:
            try:
                msg = conn.recv_match(blocking=True, timeout=1.0)
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
            conn.close()
        except Exception:
            pass

    def _apply_message(self, msg) -> None:
        msg_type = msg.get_type()
        s = self._state

        if msg_type == "HEARTBEAT":
            try:
                s.flight_mode = mavutil.mode_string_v10(msg)
            except Exception:
                s.flight_mode = f"MODE({msg.custom_mode})"

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
            if msg.battery_remaining >= 0:
                s.battery_remaining = msg.battery_remaining

        elif msg_type in ("RADIO_STATUS", "RADIO"):
            if msg.rssi != 255:
                s.rssi = msg.rssi

        elif msg_type == "RC_CHANNELS":
            if getattr(msg, "rssi", 255) != 255:
                s.link_quality = round(msg.rssi / 255 * 100)
