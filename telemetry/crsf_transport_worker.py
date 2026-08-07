"""Shared receive loop for raw-CRSF workers (UDP and USB/serial).

CRSFParser.feed() only cares about bytes, not where they came from, so both
transports reuse the exact same connection-tracking/parsing loop here and
only implement how to open/read/close their underlying channel.
"""
from __future__ import annotations

import time
from typing import Optional

from core.telemetry_state import TelemetryState
from telemetry.base_worker import TelemetryWorker
from telemetry.crsf_parser import CRSFParser

CONNECTION_TIMEOUT_S = 3.0


class CRSFTransportWorker(TelemetryWorker):
    def __init__(self) -> None:
        super().__init__()
        self._state = TelemetryState(source="crsf")

    def _open(self) -> bool:
        """Open the transport. Emit error_occurred and return False on failure."""
        raise NotImplementedError

    def _read_chunk(self) -> Optional[bytes]:
        """Block up to ~1s for data; return bytes or None on timeout."""
        raise NotImplementedError

    def _close(self) -> None:
        raise NotImplementedError

    def run(self) -> None:
        if not self._open():
            return

        parser = CRSFParser()
        last_msg_time = 0.0
        was_connected = False

        while self._running:
            try:
                data = self._read_chunk()
            except Exception as exc:
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

        self._close()
