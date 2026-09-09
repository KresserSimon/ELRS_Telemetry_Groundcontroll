"""Background poller for live air traffic (ADS-B) - the periodic counterpart
to the one-shot fetches elsewhere (core/openaip_import.py, core/terrain.py).
A plain QThread (not a TelemetryWorker - there is no telemetry protocol
here), timer-driven rather than event-driven, since the data source is a
polled HTTP API, not a stream. Runs independently of the telemetry
connection/demo mode - traffic is useful to see before a flight even starts.

Altitude filtering happens here, before emitting, so the map side never even
sees a contact above the configured ceiling - see core/traffic_config.py's
ALTITUDE_MODE_AGL default and docs/feature_plan.md's "Maximalhoehen-Filter"
design note for why AGL uses a single ground-reference elevation
(core/terrain.py, itself disk-cached) rather than a per-contact terrain
lookup: the reference point barely moves between polls, so
core/terrain.py's own 5-decimal-place cache key makes repeated lookups at
the same rounded point free after the first one - no extra caching needed
here.
"""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from PyQt6.QtCore import QThread, pyqtSignal

from core import i18n
from core.terrain import TerrainLookupError, fetch_elevations
from core.traffic_config import ALTITUDE_MODE_AGL, TrafficConfig
from core.traffic_import import AircraftState, TrafficFetchError, fetch_traffic

_STOP_POLL_CHUNK_S = 0.5
_MIN_POLL_INTERVAL_S = 5.0  # floor against a misconfigured/typo'd interval hammering the API


class TrafficWorker(QThread):
    traffic_updated = pyqtSignal(list)  # List[AircraftState], already altitude-filtered
    traffic_error = pyqtSignal(str)     # "" clears a previously shown error/notice

    def __init__(self, get_reference: Callable[[], Optional[Tuple[float, float]]]) -> None:
        super().__init__()
        self._running = True
        self._get_reference = get_reference
        self._config: Optional[TrafficConfig] = None

    def update_config(self, config: TrafficConfig) -> None:
        # Reassigning the whole dict is an atomic reference swap under the
        # GIL - the run loop always sees either the old or the new config
        # in full, never a half-updated mix, so no lock is needed (same
        # reasoning the rest of this codebase applies to simple
        # cross-thread attribute reads, e.g. TelemetryState.copy()).
        self._config = config

    def stop(self) -> None:
        self._running = False
        self.wait(3000)

    def run(self) -> None:
        while self._running:
            config = self._config
            if config is not None and config["enabled"]:
                self._poll_once(config)
            self._sleep_interruptible(config["poll_interval_s"] if config else _MIN_POLL_INTERVAL_S)

    def _sleep_interruptible(self, seconds: float) -> None:
        remaining = max(seconds, _MIN_POLL_INTERVAL_S)
        while self._running and remaining > 0:
            chunk = min(_STOP_POLL_CHUNK_S, remaining)
            self.msleep(int(chunk * 1000))
            remaining -= chunk

    def _poll_once(self, config: TrafficConfig) -> None:
        reference = self._get_reference()
        if reference is None:
            self.traffic_updated.emit([])
            self.traffic_error.emit("")
            return

        try:
            aircraft = fetch_traffic(
                config["provider"], config["base_url"], reference[0], reference[1], config["radius_km"]
            )
        except TrafficFetchError as exc:
            self.traffic_updated.emit([])
            self.traffic_error.emit(str(exc))
            return

        ground_ref_m = None
        agl_unavailable = False
        if config["altitude_mode"] == ALTITUDE_MODE_AGL:
            try:
                ground_ref_m = fetch_elevations([reference])[0]
            except TerrainLookupError:
                # Falls back to a raw-MSL comparison for this poll only (see
                # _passes_altitude_filter) - never fabricates a ground
                # elevation, and never hides a contact just because the
                # elevation lookup failed.
                agl_unavailable = True

        filtered = [
            ac for ac in aircraft
            if _passes_altitude_filter(ac, config["max_altitude_m"], config["altitude_mode"], ground_ref_m)
        ]
        self.traffic_updated.emit(filtered)
        self.traffic_error.emit(i18n.tr("status_traffic_agl_unavailable") if agl_unavailable else "")


def _passes_altitude_filter(
    ac: AircraftState, max_altitude_m: float, altitude_mode: str, ground_ref_m: Optional[float]
) -> bool:
    if ac.alt_m is None:
        return True  # unknown altitude is never silently hidden - core/openaip_import.py applies the same rule
    effective_alt = ac.alt_m
    if altitude_mode == ALTITUDE_MODE_AGL and ground_ref_m is not None:
        effective_alt = ac.alt_m - ground_ref_m
    return effective_alt <= max_altitude_m
