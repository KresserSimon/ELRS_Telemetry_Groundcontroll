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
    # pyserial's Windows backend queries WMI per device and can raise
    # pywintypes.com_error for certain USB composite devices (e.g. a
    # RadioMaster transmitter exposing both a joystick/HID and a serial
    # interface) - letting that escape here used to crash the whole app at
    # startup (ConnectionSettingsDialog refreshes this list unconditionally
    # on open) whenever such a device happened to be plugged in.
    try:
        ports = list(serial.tools.list_ports.comports())
    except Exception:
        return []
    return [
        SerialPortInfo(device=p.device, description=p.description or "")
        for p in ports
    ]
