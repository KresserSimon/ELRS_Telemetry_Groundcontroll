"""Simulation/demo telemetry source.

Flies a synthetic loiter circle around a configurable center point so the UI
(map, dashboard, GPX/KML export, low-battery TTS alert) can be exercised
without any ELRS hardware attached.
"""
from __future__ import annotations

import math
import random
import time

from core.telemetry_state import TelemetryState
from telemetry.base_worker import TelemetryWorker

TICK_S = 0.3
LOOP_PERIOD_S = 60.0        # time for one full circle
BATTERY_DRAIN_PERIOD_S = 150.0  # time to drain 100% -> 0%, then it "swaps" and resets
RADIUS_M = 250.0
FLIGHT_MODES = ["STABILIZE", "LOITER", "AUTO", "RTL"]
PACK_CAPACITY_MAH = 4000.0
CRUISE_SPEED_MPS = 2 * math.pi * RADIUS_M / LOOP_PERIOD_S


class DemoWorker(TelemetryWorker):
    def __init__(self, center_lat: float = 48.1372, center_lon: float = 11.5756, cells: int = 4) -> None:
        super().__init__()
        self._center_lat = center_lat
        self._center_lon = center_lon
        self._cells = cells
        self._state = TelemetryState(source="demo")

    def run(self) -> None:
        self.connection_changed.emit(True)
        t0 = time.monotonic()
        deg_per_m_lat = 1.0 / 111_320.0
        deg_per_m_lon = 1.0 / (111_320.0 * max(math.cos(math.radians(self._center_lat)), 0.01))

        max_voltage = self._cells * 4.2
        min_voltage = self._cells * 3.3

        while self._running:
            t = time.monotonic() - t0
            angle = (t / LOOP_PERIOD_S) * 2 * math.pi

            offset_lat_m = RADIUS_M * math.sin(angle)
            offset_lon_m = RADIUS_M * math.cos(angle)

            s = self._state
            s.lat = self._center_lat + offset_lat_m * deg_per_m_lat
            s.lon = self._center_lon + offset_lon_m * deg_per_m_lon
            s.alt = 80.0 + 20.0 * math.sin(angle * 2)
            s.satellites = 11 + random.randint(-1, 1)
            s.gps_fix = 3

            # heading = direction of travel (derivative of the circle position)
            heading_rad = math.atan2(math.cos(angle), -math.sin(angle))
            s.heading = (math.degrees(heading_rad) + 360) % 360

            # constant-radius turn -> constant bank angle, plus a little life via jitter/pitch bob
            s.roll = -18.0 + random.uniform(-1.5, 1.5)
            s.pitch = 4.0 * math.sin(angle * 2) + random.uniform(-0.5, 0.5)

            mode_idx = int(t // 15) % len(FLIGHT_MODES)
            s.flight_mode = FLIGHT_MODES[mode_idx]

            drain_progress = (t % BATTERY_DRAIN_PERIOD_S) / BATTERY_DRAIN_PERIOD_S
            s.battery_voltage = round(max_voltage - drain_progress * (max_voltage - min_voltage), 2)
            s.battery_remaining = round((1.0 - drain_progress) * 100)
            per_cell = s.battery_voltage / self._cells
            s.cell_voltages = [round(per_cell + random.uniform(-0.02, 0.02), 3) for _ in range(self._cells)]
            s.battery_current = round(15.0 + random.uniform(-2.0, 2.0), 1)
            s.battery_capacity_used = round(drain_progress * PACK_CAPACITY_MAH)

            s.link_quality = max(0, min(100, 95 - int(15 * abs(math.sin(angle))) + random.randint(-3, 3)))
            s.rssi = -40 - int(20 * abs(math.sin(angle))) + random.randint(-2, 2)
            s.snr = round(8 + random.uniform(-1, 1), 1)
            s.tx_power = 100

            s.vario = round(1.5 * math.cos(angle * 2) + random.uniform(-0.1, 0.1), 2)
            s.baro_altitude = round(s.alt + random.uniform(-1.0, 1.0), 1)
            s.rpm = 6500 + random.randint(-100, 100)
            s.temperature = round(35.0 + random.uniform(-1.0, 1.0), 1)
            s.groundspeed = round(CRUISE_SPEED_MPS + random.uniform(-0.5, 0.5), 1)

            s.connected = True
            s.source = "demo"
            self.telemetry_received.emit(s.copy())

            time.sleep(TICK_S)

        self.connection_changed.emit(False)
