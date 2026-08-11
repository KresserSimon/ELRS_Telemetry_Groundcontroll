"""Detects a telemetry cutoff and freezes the last known good position -
"Modell-verloren-Modus" in docs/feature_plan.md. Hooked into
MainWindow._check_heartbeat(), which already runs on a 1s QTimer and
already computes "time since last telemetry packet" for the existing
connection-status indicator; this reuses that exact signal instead of
adding a second timeout mechanism, with its own separately configurable
timeout (deliberately not reusing HEARTBEAT_TIMEOUT_S - see the plan for
why the two must stay independent).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from core import i18n
from core.geo import bearing_deg, haversine_distance_m
from core.telemetry_state import TelemetryState

DEFAULT_TIMEOUT_S = 10.0
REANNOUNCE_INTERVAL_S = 30.0


@dataclass
class LostModelInfo:
    frozen_state: TelemetryState
    lost_since: float
    distance_m: Optional[float]
    bearing_deg: Optional[float]  # from the reference point toward the model


class LostModelMonitor:
    def __init__(self, tts_worker) -> None:
        self._tts = tts_worker
        self._frozen_state: Optional[TelemetryState] = None
        self._lost_since: Optional[float] = None
        self._last_announce = 0.0

    def reset(self) -> None:
        self._frozen_state = None
        self._lost_since = None

    def note_telemetry(self, state: TelemetryState) -> None:
        """Call on every received packet - keeps the "last known good"
        position current, and a fresh packet always means the model isn't
        lost right now (even if it later cuts out again)."""
        if state.has_gps_fix():
            self._frozen_state = state
        self._lost_since = None

    def check(self, now: float, last_telemetry_time: float, timeout_s: float) -> None:
        """Call from the same periodic tick that already detects a
        connection drop (MainWindow._check_heartbeat()) - `now` and
        `last_telemetry_time` are both time.time() values, matching that
        method's own clock."""
        if self._frozen_state is None or last_telemetry_time == 0:
            return

        if (now - last_telemetry_time) <= timeout_s:
            self._lost_since = None
            return

        if self._lost_since is None:
            self._lost_since = last_telemetry_time
            self._last_announce = now
            self._tts.say(i18n.tr("tts_model_lost"), key="tts_model_lost")
        elif (now - self._last_announce) >= REANNOUNCE_INTERVAL_S:
            self._last_announce = now
            self._tts.say(i18n.tr("tts_model_lost"), key="tts_model_lost")

    def is_lost(self) -> bool:
        return self._lost_since is not None

    def info(self, reference: Optional[Tuple[float, float]]) -> Optional[LostModelInfo]:
        if not self.is_lost() or self._frozen_state is None:
            return None
        state = self._frozen_state
        distance_m = None
        bearing = None
        if reference is not None and state.has_gps_fix():
            distance_m = haversine_distance_m(reference[0], reference[1], state.lat, state.lon)
            bearing = bearing_deg(reference[0], reference[1], state.lat, state.lon)
        return LostModelInfo(state, self._lost_since, distance_m, bearing)
