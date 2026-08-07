"""USB/serial receiver worker for raw CRSF telemetry (e.g. an ELRS TX module
or a receiver's UART wired straight into the PC via USB). ELRS/CRSF hardware
UARTs run at 420000 baud by default.
"""
from __future__ import annotations

from typing import Optional

import serial

from telemetry.crsf_transport_worker import CRSFTransportWorker

CRSF_DEFAULT_BAUD = 420000
SERIAL_TIMEOUT_S = 1.0


class CRSFSerialWorker(CRSFTransportWorker):
    def __init__(self, serial_port: str, baud: int = CRSF_DEFAULT_BAUD) -> None:
        super().__init__()
        self._port_name = serial_port
        self._baud = baud
        self._serial: Optional[serial.Serial] = None

    def _open(self) -> bool:
        try:
            self._serial = serial.Serial(self._port_name, baudrate=self._baud, timeout=SERIAL_TIMEOUT_S)
            return True
        except serial.SerialException as exc:
            self.error_occurred.emit(f"CRSF USB-Verbindung fehlgeschlagen ({self._port_name}): {exc}")
            return False

    def _read_chunk(self) -> Optional[bytes]:
        data = self._serial.read(self._serial.in_waiting or 1)
        return data or None

    def _close(self) -> None:
        if self._serial is not None:
            self._serial.close()
