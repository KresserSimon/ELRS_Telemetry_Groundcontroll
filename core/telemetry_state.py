"""Shared telemetry data model used by every receiver backend and the UI."""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import List, Optional


@dataclass
class TelemetryState:
    lat: Optional[float] = None
    lon: Optional[float] = None
    alt: Optional[float] = None            # meters (GPS altitude)
    satellites: Optional[int] = None
    gps_fix: Optional[int] = None          # 0=no fix,1=no fix,2=2D,3=3D,4-6=RTK etc (MAVLink scale)
    heading: Optional[float] = None        # degrees, 0-360
    roll: Optional[float] = None           # degrees, positive = right bank
    pitch: Optional[float] = None          # degrees, positive = nose up

    flight_mode: Optional[str] = None

    battery_voltage: Optional[float] = None    # volts
    battery_remaining: Optional[int] = None    # percent, 0-100
    battery_current: Optional[float] = None    # amps
    battery_capacity_used: Optional[float] = None  # mAh

    groundspeed: Optional[float] = None    # m/s
    airspeed: Optional[float] = None       # m/s (MAVLink VFR_HUD.airspeed only - CRSF has no equivalent)

    rssi: Optional[int] = None             # dBm
    link_quality: Optional[int] = None     # LQ percent, 0-100
    snr: Optional[float] = None            # dB
    tx_power: Optional[int] = None         # mW

    vario: Optional[float] = None          # m/s, positive = climbing
    baro_altitude: Optional[float] = None  # meters, barometric (vs. GPS alt)
    rpm: Optional[int] = None              # first reported motor/rotor RPM
    temperature: Optional[float] = None    # degC, first reported sensor
    cell_voltages: Optional[List[float]] = None  # volts, one per cell

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
