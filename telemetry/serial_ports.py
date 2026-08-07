"""Small helper to discover available USB/serial ports (used by --list-ports)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import serial.tools.list_ports


@dataclass
class SerialPortInfo:
    device: str
    description: str


def list_serial_ports() -> List[SerialPortInfo]:
    return [
        SerialPortInfo(device=p.device, description=p.description or "")
        for p in serial.tools.list_ports.comports()
    ]
