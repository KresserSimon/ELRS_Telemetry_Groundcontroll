"""Sends the current drone position out to an external antenna-tracker
device, in either MAVLink (GLOBAL_POSITION_INT) or NMEA ($GPGGA) format,
over a serial port or UDP - the mirror image of telemetry/mavlink_worker.py
(which reads MAVLink in), just for output instead of input.

A plain QObject (only for the error_occurred signal), not a QThread: a
send happens once per telemetry tick (a few times a second at most), which
is fast and non-blocking enough not to need a background thread, and
avoids the extra concurrency complexity of coordinating one.
"""
from __future__ import annotations

import socket
import time
from datetime import datetime, timezone
from typing import Optional

import serial
from PyQt6.QtCore import QObject, pyqtSignal
from pymavlink import mavutil

from core.telemetry_state import TelemetryState

MODE_SERIAL = "serial"
MODE_UDP = "udp"
FORMAT_MAVLINK = "mavlink"
FORMAT_NMEA = "nmea"

# The system ID GLOBAL_POSITION_INT is sent under - 1 is the conventional
# default "vehicle" system ID, which is what most antenna trackers expect
# to see position updates from out of the box (not 255/GCS, which is what
# a ground-control station would normally claim for itself).
MAVLINK_SOURCE_SYSTEM = 1


def _nmea_lat(lat: float) -> str:
    hemisphere = "N" if lat >= 0 else "S"
    lat = abs(lat)
    degrees = int(lat)
    minutes = (lat - degrees) * 60
    return f"{degrees:02d}{minutes:07.4f},{hemisphere}"


def _nmea_lon(lon: float) -> str:
    hemisphere = "E" if lon >= 0 else "W"
    lon = abs(lon)
    degrees = int(lon)
    minutes = (lon - degrees) * 60
    return f"{degrees:03d}{minutes:07.4f},{hemisphere}"


def _nmea_checksum(sentence: str) -> str:
    checksum = 0
    for ch in sentence:
        checksum ^= ord(ch)
    return f"{checksum:02X}"


def build_gpgga(state: TelemetryState) -> str:
    """A $GPGGA NMEA sentence (with trailing CRLF) for the given state's
    position. Caller must already have checked state.has_gps_fix()."""
    time_str = datetime.now(timezone.utc).strftime("%H%M%S.00")
    fix_quality = 1 if state.has_gps_fix() else 0
    num_sats = state.satellites if state.satellites is not None else 0
    alt = state.alt if state.alt is not None else 0.0
    body = (
        f"GPGGA,{time_str},{_nmea_lat(state.lat)},{_nmea_lon(state.lon)},"
        f"{fix_quality},{num_sats:02d},1.0,{alt:.1f},M,0.0,M,,"
    )
    return f"${body}*{_nmea_checksum(body)}\r\n"


class TrackerOutputSender(QObject):
    error_occurred = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._mavlink_conn = None
        self._udp_socket: Optional[socket.socket] = None
        self._serial_conn: Optional[serial.Serial] = None
        self._output_format = FORMAT_MAVLINK
        self._udp_target = None

    def is_active(self) -> bool:
        return self._mavlink_conn is not None or self._udp_socket is not None or self._serial_conn is not None

    def start(
        self,
        mode: str,
        output_format: str,
        serial_port: str = "",
        baud: int = 57600,
        host: str = "",
        port: int = 0,
    ) -> None:
        self.stop()
        self._output_format = output_format
        try:
            if output_format == FORMAT_MAVLINK:
                target = serial_port if mode == MODE_SERIAL else f"udpout:{host}:{port}"
                if mode == MODE_SERIAL:
                    self._mavlink_conn = mavutil.mavlink_connection(
                        target, baud=baud, source_system=MAVLINK_SOURCE_SYSTEM
                    )
                else:
                    self._mavlink_conn = mavutil.mavlink_connection(target, source_system=MAVLINK_SOURCE_SYSTEM)
            elif mode == MODE_SERIAL:
                self._serial_conn = serial.Serial(serial_port, baudrate=baud, timeout=0)
            else:
                self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._udp_target = (host, port)
        except Exception as exc:
            self.stop()
            self.error_occurred.emit(f"Telemetrie-Ausgabe konnte nicht gestartet werden: {exc}")

    def stop(self) -> None:
        if self._mavlink_conn is not None:
            try:
                self._mavlink_conn.close()
            except Exception:
                pass
            self._mavlink_conn = None
        if self._serial_conn is not None:
            try:
                self._serial_conn.close()
            except Exception:
                pass
            self._serial_conn = None
        if self._udp_socket is not None:
            try:
                self._udp_socket.close()
            except Exception:
                pass
            self._udp_socket = None
            self._udp_target = None

    def send(self, state: TelemetryState) -> None:
        if not self.is_active() or not state.has_gps_fix():
            return
        try:
            if self._mavlink_conn is not None:
                self._send_mavlink(state)
            else:
                self._send_nmea(state)
        except Exception as exc:
            self.error_occurred.emit(f"Telemetrie-Ausgabe fehlgeschlagen: {exc}")
            self.stop()

    def _send_mavlink(self, state: TelemetryState) -> None:
        alt_mm = int((state.alt or 0.0) * 1000)
        hdg_cdeg = int(state.heading * 100) if state.heading is not None else 65535
        self._mavlink_conn.mav.global_position_int_send(
            int(time.time() * 1000) & 0xFFFFFFFF,
            int(state.lat * 1e7),
            int(state.lon * 1e7),
            alt_mm,
            alt_mm,
            0, 0, 0,
            hdg_cdeg,
        )

    def _send_nmea(self, state: TelemetryState) -> None:
        sentence = build_gpgga(state).encode("ascii")
        if self._serial_conn is not None:
            self._serial_conn.write(sentence)
        elif self._udp_socket is not None:
            self._udp_socket.sendto(sentence, self._udp_target)
