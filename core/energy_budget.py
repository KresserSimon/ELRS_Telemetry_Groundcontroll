"""Estimates whether there's enough battery left to get home, from distance
to home, groundspeed, and a consumption-rate estimate - a heuristic aid for
planning a timely return, not a guaranteed prediction (see
docs/feature_plan.md's explicit warning-text requirement). Mirrors
alerts/tts_alert.py's BatteryAlertMonitor structure (hysteresis + a
re-announce cooldown) for the reserve-ampel TTS warning.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from core import i18n
from core.geo import haversine_distance_m
from core.telemetry_state import TelemetryState

LEVEL_GREEN = "green"
LEVEL_YELLOW = "yellow"
LEVEL_RED = "red"
_LEVEL_ORDER = {LEVEL_RED: 0, LEVEL_YELLOW: 1, LEVEL_GREEN: 2}

DEFAULT_YELLOW_THRESHOLD_PCT = 15.0
DEFAULT_GREEN_THRESHOLD_PCT = 30.0
DEFAULT_MIN_SPEED_ASSUMPTION_MS = 5.0
RATE_WINDOW_S = 10.0
REANNOUNCE_INTERVAL_S = 30.0


@dataclass
class EnergyBudget:
    rate_mah_per_s: Optional[float] = None
    mah_for_home: Optional[float] = None
    remaining_mah: Optional[float] = None
    reserve_mah: Optional[float] = None
    reserve_pct: Optional[float] = None
    level: Optional[str] = None  # None = not computable ("n/v")


def consumption_rate_from_current(battery_current_a: Optional[float]) -> Optional[float]:
    """mAh/s from an instantaneous current reading, if the FC provides one -
    the accurate path, preferred over the capacity_used derivative below."""
    if battery_current_a is None:
        return None
    return battery_current_a * 1000.0 / 3600.0


class ConsumptionRateEstimator:
    """Fallback rate estimate (mAh/s) for FCs with no current sensor: the
    slope of battery_capacity_used over a trailing time window, not a
    single two-point difference, which would be too noisy at typical
    telemetry rates."""

    def __init__(self, window_s: float = RATE_WINDOW_S) -> None:
        self._window_s = window_s
        self._samples: List[Tuple[float, float]] = []

    def reset(self) -> None:
        self._samples = []

    def add_sample(self, timestamp: float, capacity_used_mah: Optional[float]) -> Optional[float]:
        if capacity_used_mah is None:
            return None
        self._samples.append((timestamp, capacity_used_mah))
        cutoff = timestamp - self._window_s
        self._samples = [s for s in self._samples if s[0] >= cutoff]
        if len(self._samples) < 2:
            return None
        t0, c0 = self._samples[0]
        t1, c1 = self._samples[-1]
        dt = t1 - t0
        if dt <= 0:
            return None
        return (c1 - c0) / dt


def estimate(
    distance_home_m: Optional[float],
    groundspeed_ms: Optional[float],
    rate_mah_per_s: Optional[float],
    capacity_mah: float,
    battery_remaining_pct: Optional[int],
    battery_capacity_used_mah: Optional[float],
    min_speed_assumption_ms: float = DEFAULT_MIN_SPEED_ASSUMPTION_MS,
    yellow_threshold_pct: float = DEFAULT_YELLOW_THRESHOLD_PCT,
    green_threshold_pct: float = DEFAULT_GREEN_THRESHOLD_PCT,
) -> EnergyBudget:
    """Pure calculation - see docs/feature_plan.md's "Heimkehr-Energiebudget"
    section for the formula and the explicit reasoning behind each
    fallback. Returns level=None ("n/v") whenever a required input is
    missing - never fabricates a number/warning from incomplete data."""
    if distance_home_m is None or rate_mah_per_s is None or capacity_mah <= 0:
        return EnergyBudget(rate_mah_per_s=rate_mah_per_s)

    speed = max(groundspeed_ms or 0.0, min_speed_assumption_ms)
    home_time_s = distance_home_m / speed
    mah_for_home = home_time_s * rate_mah_per_s

    if battery_remaining_pct is not None:
        remaining_mah = capacity_mah * (battery_remaining_pct / 100.0)
    elif battery_capacity_used_mah is not None:
        remaining_mah = capacity_mah - battery_capacity_used_mah
    else:
        return EnergyBudget(rate_mah_per_s=rate_mah_per_s, mah_for_home=mah_for_home)

    reserve_mah = remaining_mah - mah_for_home
    reserve_pct = reserve_mah / capacity_mah * 100.0

    if reserve_pct >= green_threshold_pct:
        level = LEVEL_GREEN
    elif reserve_pct >= yellow_threshold_pct:
        level = LEVEL_YELLOW
    else:
        level = LEVEL_RED

    return EnergyBudget(rate_mah_per_s, mah_for_home, remaining_mah, reserve_mah, reserve_pct, level)


class EnergyBudgetMonitor:
    def __init__(self, tts_worker) -> None:
        self._tts = tts_worker
        self._rate_estimator = ConsumptionRateEstimator()
        self._level: Optional[str] = None
        self._last_announce = 0.0
        self._last_result = EnergyBudget()

    def reset(self) -> None:
        self._rate_estimator.reset()
        self._level = None
        self._last_result = EnergyBudget()

    def last_result(self) -> EnergyBudget:
        return self._last_result

    def check(
        self,
        state: TelemetryState,
        home: Optional[Tuple[float, float]],
        capacity_mah: float,
        min_speed_assumption_ms: float,
        yellow_threshold_pct: float,
        green_threshold_pct: float,
    ) -> None:
        rate = consumption_rate_from_current(state.battery_current)
        derived_rate = self._rate_estimator.add_sample(state.timestamp, state.battery_capacity_used)
        if rate is None:
            rate = derived_rate

        distance_home_m = None
        if home is not None and state.has_gps_fix():
            distance_home_m = haversine_distance_m(state.lat, state.lon, *home)

        result = estimate(
            distance_home_m, state.groundspeed, rate, capacity_mah,
            state.battery_remaining, state.battery_capacity_used,
            min_speed_assumption_ms, yellow_threshold_pct, green_threshold_pct,
        )
        self._last_result = result

        if result.level is None:
            return

        now = state.timestamp
        # Only speak on a transition into a *worse* level (the recommended
        # turn-back point) or while staying in a non-green level past the
        # re-announce cooldown - recovering to green never speaks, matching
        # BatteryAlertMonitor's "no chatter" approach for an ok state.
        if result.level != self._level:
            worsened = self._level is None or _LEVEL_ORDER[result.level] < _LEVEL_ORDER[self._level]
            self._level = result.level
            if worsened and result.level != LEVEL_GREEN:
                self._last_announce = now
                self._speak(result.level)
        elif result.level != LEVEL_GREEN and (now - self._last_announce) >= REANNOUNCE_INTERVAL_S:
            self._last_announce = now
            self._speak(result.level)

    def _speak(self, level: str) -> None:
        key = "tts_energy_budget_critical" if level == LEVEL_RED else "tts_energy_budget_low"
        self._tts.say(i18n.tr(key))
