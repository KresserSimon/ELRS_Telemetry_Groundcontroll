"""Own configurable safety boundary (radius + max altitude around the flight
start point) - conceptually distinct from imported no-fly zones (core/nfz.py):
this is the pilot's own limit, not a restricted area loaded from a file, so
it is checked and rendered separately (see ui/map_template.py's setGeofence)
and stays independently toggleable from imported NFZ zones.

Altitude here is "relative to home" the same way core/route.py's
Waypoint.alt already is (see routeeditor_alt's i18n label) - no unit
conversion needed when checking planned waypoints below.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from core.geo import haversine_distance_m

DEFAULT_RADIUS_M = 120.0
DEFAULT_MAX_ALT_M = 120.0


@dataclass
class GeofenceBreach:
    outside_radius: bool
    distance_m: float
    over_altitude: bool
    altitude_m: Optional[float]

    def breached(self) -> bool:
        return self.outside_radius or self.over_altitude


def check_geofence(
    lat: float,
    lon: float,
    alt: Optional[float],
    center: Tuple[float, float],
    radius_m: float,
    max_alt_m: Optional[float],
) -> GeofenceBreach:
    distance_m = haversine_distance_m(lat, lon, *center)
    outside_radius = distance_m > radius_m
    over_altitude = max_alt_m is not None and alt is not None and alt > max_alt_m
    return GeofenceBreach(outside_radius, distance_m, over_altitude, alt)


def find_out_of_bounds(
    waypoints: List, center: Tuple[float, float], radius_m: float, max_alt_m: Optional[float]
) -> List[int]:
    """Indices of `waypoints` (core/route.py Waypoint objects) that fall
    outside the geofence - for a pre-flight route-planning check, using the
    exact same check_geofence() the live in-flight monitor uses, so both
    can never drift apart on what "out of bounds" means."""
    out_of_bounds = []
    for i, wp in enumerate(waypoints):
        breach = check_geofence(wp.lat, wp.lon, wp.alt, center, radius_m, max_alt_m)
        if breach.breached():
            out_of_bounds.append(i)
    return out_of_bounds
