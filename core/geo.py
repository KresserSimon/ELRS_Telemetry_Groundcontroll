"""Great-circle distance/bearing, and a local flat-earth metre projection
for the handful of callers (core/grid_pattern.py, core/nfz_proximity.py)
that need to do planar geometry - spacing, angles, point-to-segment
distance - which isn't well-defined directly in lat/lon degrees.
"""
from __future__ import annotations

import math
from typing import Tuple

EARTH_RADIUS_M = 6371000.0


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing (degrees, 0-360) for the great-circle path from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def meters_per_degree(lat0_deg: float) -> Tuple[float, float]:
    """(metres per degree latitude, metres per degree longitude) at lat0 -
    the latter shrinks toward the poles since meridians converge."""
    m_per_deg_lat = math.radians(1.0) * EARTH_RADIUS_M
    m_per_deg_lon = math.radians(1.0) * EARTH_RADIUS_M * math.cos(math.radians(lat0_deg))
    return m_per_deg_lat, m_per_deg_lon


def to_local_xy(lat: float, lon: float, lat0: float, lon0: float, m_lat: float, m_lon: float) -> Tuple[float, float]:
    """Project (lat, lon) to metres on a flat plane centred at (lat0, lon0),
    using the m_per_deg_lat/lon from meters_per_degree(lat0)."""
    return (lon - lon0) * m_lon, (lat - lat0) * m_lat


def to_local_latlon(x: float, y: float, lat0: float, lon0: float, m_lat: float, m_lon: float) -> Tuple[float, float]:
    """Inverse of to_local_xy()."""
    return lat0 + y / m_lat, lon0 + x / m_lon
