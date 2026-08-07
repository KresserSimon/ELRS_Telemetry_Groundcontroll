"""Shared telemetry data model used by every receiver backend and the UI."""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Optional


@dataclass
class TelemetryState:
    lat: Optional[float] = None
    lon: Optional[float] = None
    alt: Optional[float] = None            # meters (GPS altitude)
    satellites: Optional[int] = None
    gps_fix: Optional[int] = None          # 0=no fix,1=no fix,2=2D,3=3D,4-6=RTK etc (MAVLink scale)
    heading: Optional[float] = None        # degrees, 0-360

    flight_mode: Optional[str] = None

    battery_voltage: Optional[float] = None    # volts
    battery_remaining: Optional[int] = None    # percent, 0-100

    rssi: Optional[int] = None             # dBm
    link_quality: Optional[int] = None     # LQ percent, 0-100
    snr: Optional[float] = None            # dB
    tx_power: Optional[int] = None         # mW

    connected: bool = False
    source: str = ""                       # 'mavlink' | 'crsf' | 'demo'
    timestamp: float = field(default_factory=time.time)

    def has_gps_fix(self) -> bool:
        return (
            self.lat is not None
            and self.lon is not None
            and not (self.lat == 0.0 and self.lon == 0.0)
        )

    def copy(self) -> "TelemetryState":
        return replace(self, timestamp=time.time())
