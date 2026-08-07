"""UDP receiver worker for raw CRSF telemetry streams."""
from __future__ import annotations

import socket
import time

from core.telemetry_state import TelemetryState
from telemetry.base_worker import TelemetryWorker
from telemetry.crsf_parser import CRSFParser

CONNECTION_TIMEOUT_S = 3.0
SOCKET_TIMEOUT_S = 1.0


class CRSFWorker(TelemetryWorker):
    def __init__(self, host: str = "0.0.0.0", port: int = 14551) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._state = TelemetryState(source="crsf")

    def run(self) -> None:
        parser = CRSFParser()

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(SOCKET_TIMEOUT_S)
            sock.bind((self._host, self._port))
        except OSError as exc:
            self.error_occurred.emit(f"CRSF UDP-Bind fehlgeschlagen ({self._host}:{self._port}): {exc}")
            return

        last_msg_time = 0.0
        was_connected = False

        while self._running:
            try:
                data, _addr = sock.recvfrom(4096)
            except socket.timeout:
                data = None
            except OSError as exc:
                self.error_occurred.emit(f"CRSF Empfangsfehler: {exc}")
                data = None

            now = time.time()

            if data:
                try:
                    updates = parser.feed(data)
                except Exception as exc:
                    self.error_occurred.emit(f"CRSF Parse-Fehler: {exc}")
                    updates = []

                if updates:
                    for fields in updates:
                        for key, value in fields.items():
                            setattr(self._state, key, value)

                    last_msg_time = now
                    self._state.connected = True
                    self._state.source = "crsf"
                    self.telemetry_received.emit(self._state.copy())

                    if not was_connected:
                        was_connected = True
                        self.connection_changed.emit(True)

            if was_connected and (now - last_msg_time) > CONNECTION_TIMEOUT_S:
                was_connected = False
                self._state.connected = False
                self.connection_changed.emit(False)

        sock.close()
