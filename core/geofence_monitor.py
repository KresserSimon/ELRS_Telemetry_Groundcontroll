"""Live geofence-breach alerting - mirrors core/nfz_proximity.py's
NfzProximityMonitor almost exactly (hysteresis + a re-announce cooldown so
the alert doesn't flap or spam every telemetry packet), just keyed off
"outside my own configured boundary" instead of "inside an imported
restricted zone".
"""
from __future__ import annotations

from typing import Optional, Tuple

from core import i18n
from core.geofence import GeofenceBreach, check_geofence
from core.telemetry_state import TelemetryState

REANNOUNCE_INTERVAL_S = 30.0


class GeofenceMonitor:
    def __init__(self, tts_worker) -> None:
        self._tts = tts_worker
        self._warning_active = False
        self._last_announce = 0.0
        self._last_result: Optional[GeofenceBreach] = None

    def last_result(self) -> Optional[GeofenceBreach]:
        return self._last_result

    def reset(self) -> None:
        self._warning_active = False
        self._last_result = None

    def check(
        self,
        state: TelemetryState,
        center: Optional[Tuple[float, float]],
        radius_m: float,
        max_alt_m: Optional[float],
        enabled: bool,
    ) -> None:
        if not enabled or center is None or not state.has_gps_fix():
            self._last_result = None
            return

        result = check_geofence(state.lat, state.lon, state.alt, center, radius_m, max_alt_m)
        self._last_result = result

        now = state.timestamp
        if not result.breached():
            self._warning_active = False
            return

        if not self._warning_active:
            self._warning_active = True
            self._last_announce = now
            self._tts.say(i18n.tr("tts_geofence_breach"), key="tts_geofence_breach")
        elif (now - self._last_announce) >= REANNOUNCE_INTERVAL_S:
            self._last_announce = now
            self._tts.say(i18n.tr("tts_geofence_breach"), key="tts_geofence_breach")
