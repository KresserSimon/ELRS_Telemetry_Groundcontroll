"""Distance-to-nearest-no-fly-zone check and the alert state machine that
turns it into a spoken warning - mirrors alerts/tts_alert.py's
BatteryAlertMonitor almost exactly (hysteresis + a re-announce cooldown so
the alert doesn't flap or spam every single telemetry packet), just keyed
off proximity to a zone instead of battery level.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from core import i18n
from core.geo import haversine_distance_m, meters_per_degree, to_local_xy
from core.nfz import NoFlyZone
from core.telemetry_state import TelemetryState

DEFAULT_THRESHOLD_M = 50.0
REANNOUNCE_INTERVAL_S = 30.0


def _point_to_segment_distance_m(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _point_in_polygon(x: float, y: float, poly: List[Tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_at_y = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_at_y:
                inside = not inside
    return inside


def distance_to_zone_m(lat: float, lon: float, zone: NoFlyZone) -> float:
    """Distance in metres from (lat, lon) to the nearest edge of `zone` - 0
    if the point is inside it. inf if the zone has no usable geometry."""
    if zone.kind == "circle" and zone.center is not None and zone.radius_m is not None:
        return max(0.0, haversine_distance_m(lat, lon, *zone.center) - zone.radius_m)

    if zone.kind == "polygon" and zone.points:
        # Project to a local metre-plane centred on the query point itself,
        # so the query point sits at the origin - cheap and accurate enough
        # for the "how close am I" distances this is used for (typically
        # well under the couple-km range where the flat-earth approximation
        # starts to matter).
        m_lat, m_lon = meters_per_degree(lat)
        poly_xy = [to_local_xy(plat, plon, lat, lon, m_lat, m_lon) for plat, plon in zone.points]
        if _point_in_polygon(0.0, 0.0, poly_xy):
            return 0.0
        n = len(poly_xy)
        return min(
            _point_to_segment_distance_m(0.0, 0.0, *poly_xy[i], *poly_xy[(i + 1) % n])
            for i in range(n)
        )

    return math.inf


def nearest_zone(lat: float, lon: float, zones: List[NoFlyZone]) -> Optional[Tuple[NoFlyZone, float]]:
    """The (zone, distance_m) with the smallest distance, or None if `zones`
    is empty or none of them have usable geometry."""
    best: Optional[Tuple[NoFlyZone, float]] = None
    for zone in zones:
        distance = distance_to_zone_m(lat, lon, zone)
        if distance == math.inf:
            continue
        if best is None or distance < best[1]:
            best = (zone, distance)
    return best


class NfzProximityMonitor:
    """Speaks a warning (via the given TTSWorker-like object's say(text))
    the first time the aircraft comes within `threshold_m` of any loaded
    no-fly zone, and again every REANNOUNCE_INTERVAL_S while still inside
    that range - not on every single telemetry tick.
    """

    def __init__(self, tts_worker, threshold_m: float = DEFAULT_THRESHOLD_M) -> None:
        self._tts = tts_worker
        self._threshold_m = threshold_m
        self._warning_active = False
        self._last_announce = 0.0
        self._last_result: Optional[Tuple[NoFlyZone, float]] = None

    def configure(self, threshold_m: float) -> None:
        self._threshold_m = threshold_m
        self._warning_active = False  # re-evaluate cleanly against the new threshold

    def last_result(self) -> Optional[Tuple[NoFlyZone, float]]:
        """The most recent (zone, distance_m) checked, regardless of whether
        it was within the warning threshold - for a status-bar/UI display."""
        return self._last_result

    def check(self, state: TelemetryState, zones: List[NoFlyZone]) -> None:
        if not zones or not state.has_gps_fix():
            self._last_result = None
            return

        result = nearest_zone(state.lat, state.lon, zones)
        self._last_result = result
        if result is None:
            return
        _, distance = result

        now = state.timestamp
        if distance > self._threshold_m:
            self._warning_active = False
            return

        if not self._warning_active:
            self._warning_active = True
            self._last_announce = now
            self._tts.say(i18n.tr("tts_nfz_proximity"))
        elif (now - self._last_announce) >= REANNOUNCE_INTERVAL_S:
            self._last_announce = now
            self._tts.say(i18n.tr("tts_nfz_proximity"))
