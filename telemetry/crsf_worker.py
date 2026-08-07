"""UDP receiver worker for raw CRSF telemetry streams."""
from __future__ import annotations

import socket
from typing import Optional

from telemetry.crsf_transport_worker import CRSFTransportWorker

SOCKET_TIMEOUT_S = 1.0


class CRSFWorker(CRSFTransportWorker):
    def __init__(self, host: str = "0.0.0.0", port: int = 14551) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._sock: Optional[socket.socket] = None

    def _open(self) -> bool:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.settimeout(SOCKET_TIMEOUT_S)
            self._sock.bind((self._host, self._port))
            return True
        except OSError as exc:
            self.error_occurred.emit(f"CRSF UDP-Bind fehlgeschlagen ({self._host}:{self._port}): {exc}")
            return False

    def _read_chunk(self) -> Optional[bytes]:
        try:
            data, _addr = self._sock.recvfrom(4096)
            return data
        except socket.timeout:
            return None

    def _close(self) -> None:
        if self._sock is not None:
            self._sock.close()
