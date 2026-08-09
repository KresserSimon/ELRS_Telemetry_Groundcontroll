"""Generates a boustrophedon (zigzag/lawnmower) survey route covering either
a rectangle (two opposite corner lat/lon points) or a circle (center point +
radius), with parallel scan lines a configurable spacing apart running at a
configurable angle from north - the same shape of tool as Mission Planner's
"Survey (Grid)" feature.

Pure geometry, no PyQt/network dependency: works entirely offline, unlike
core/terrain.py's Open-Elevation lookups.

All work happens in a local metre-plane (equirectangular projection around
the area's own centre - accurate enough for the areas this is meant for,
at most a few km across) rather than directly in lat/lon degrees, since
"spacing in metres" and "rotate by an angle" are only well-defined in a
flat local frame.
"""
from __future__ import annotations

import math
from typing import Callable, List, Optional, Tuple

from core.geo import EARTH_RADIUS_M
from core.route import Waypoint

Segment = Tuple[float, float, float, float]
ClipFn = Callable[[float, float, float, float], Optional[Segment]]


def _meters_per_degree(lat0_deg: float) -> Tuple[float, float]:
    m_per_deg_lat = math.radians(1.0) * EARTH_RADIUS_M
    m_per_deg_lon = math.radians(1.0) * EARTH_RADIUS_M * math.cos(math.radians(lat0_deg))
    return m_per_deg_lat, m_per_deg_lon


def _to_local_xy(lat: float, lon: float, lat0: float, lon0: float, m_lat: float, m_lon: float) -> Tuple[float, float]:
    return (lon - lon0) * m_lon, (lat - lat0) * m_lat


def _to_latlon(x: float, y: float, lat0: float, lon0: float, m_lat: float, m_lon: float) -> Tuple[float, float]:
    return lat0 + y / m_lat, lon0 + x / m_lon


def _rotate(x: float, y: float, cos_a: float, sin_a: float) -> Tuple[float, float]:
    return x * cos_a - y * sin_a, x * sin_a + y * cos_a


def _clip_segment_to_box(
    x0: float, y0: float, x1: float, y1: float, x_min: float, x_max: float, y_min: float, y_max: float
) -> Optional[Segment]:
    """Liang-Barsky clip of a line segment against an axis-aligned box."""
    dx, dy = x1 - x0, y1 - y0
    p = (-dx, dx, -dy, dy)
    q = (x0 - x_min, x_max - x0, y0 - y_min, y_max - y0)
    t0, t1 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if pi == 0:
            if qi < 0:
                return None
            continue
        t = qi / pi
        if pi < 0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)
    if t0 > t1:
        return None
    return (x0 + t0 * dx, y0 + t0 * dy, x0 + t1 * dx, y0 + t1 * dy)


def _clip_segment_to_circle(x0: float, y0: float, x1: float, y1: float, radius_m: float) -> Optional[Segment]:
    """Line-circle intersection clip, circle centred on the local origin."""
    dx, dy = x1 - x0, y1 - y0
    a = dx * dx + dy * dy
    if a == 0:
        return (x0, y0, x1, y1) if x0 * x0 + y0 * y0 <= radius_m * radius_m else None
    b = 2 * (x0 * dx + y0 * dy)
    c = x0 * x0 + y0 * y0 - radius_m * radius_m
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    sqrt_disc = math.sqrt(disc)
    t0 = max(0.0, (-b - sqrt_disc) / (2 * a))
    t1 = min(1.0, (-b + sqrt_disc) / (2 * a))
    if t0 > t1:
        return None
    return (x0 + t0 * dx, y0 + t0 * dy, x0 + t1 * dx, y0 + t1 * dy)


def _candidate_lines(
    x_min: float, x_max: float, y_min: float, y_max: float, spacing_m: float, angle_deg: float
) -> List[Segment]:
    """Full-length candidate scan lines (original local-metre frame) spaced
    spacing_m apart at angle_deg from north, generous enough to fully cross
    the given bounds regardless of angle - callers clip each one to the
    actual area shape (box or circle)."""
    angle_rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)

    corners = [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max)]
    rotated = [_rotate(x, y, cos_a, -sin_a) for x, y in corners]
    rx_min = min(p[0] for p in rotated)
    rx_max = max(p[0] for p in rotated)
    ry_lo = min(p[1] for p in rotated)
    ry_hi = max(p[1] for p in rotated)
    ry_span = max(ry_hi - ry_lo, 1.0)
    ry_min, ry_max = ry_lo - ry_span, ry_hi + ry_span  # generous overshoot so every line fully crosses the bounds

    lines: List[Segment] = []
    x = rx_min
    while x <= rx_max + 1e-6:
        p0 = _rotate(x, ry_min, cos_a, sin_a)
        p1 = _rotate(x, ry_max, cos_a, sin_a)
        lines.append((p0[0], p0[1], p1[0], p1[1]))
        x += spacing_m
    return lines


def _zigzag_points(lines: List[Segment], clip_fn: ClipFn) -> List[Tuple[float, float]]:
    points: List[Tuple[float, float]] = []
    going_forward = True
    for x0, y0, x1, y1 in lines:
        if not going_forward:
            x0, y0, x1, y1 = x1, y1, x0, y0
        clipped = clip_fn(x0, y0, x1, y1)
        if clipped is None:
            continue
        points.append((clipped[0], clipped[1]))
        points.append((clipped[2], clipped[3]))
        going_forward = not going_forward
    return points


def generate_grid_route(
    corners: Optional[Tuple[Tuple[float, float], Tuple[float, float]]] = None,
    center: Optional[Tuple[float, float]] = None,
    radius_m: Optional[float] = None,
    spacing_m: float = 50.0,
    angle_deg: float = 0.0,
    altitude_m: float = 50.0,
) -> List[Waypoint]:
    """Generate a zigzag survey route. Pass either `corners` (two opposite
    lat/lon points defining a rectangle) or `center` + `radius_m` (a
    circle) - exactly one of the two modes. Every generated point becomes a
    plain WAYPOINT at `altitude_m` (height above home, matching
    Waypoint.alt's usual meaning elsewhere in the app).
    """
    if spacing_m <= 0:
        raise ValueError("Der Zeilenabstand muss größer als 0 sein.")

    if corners is not None:
        (lat1, lon1), (lat2, lon2) = corners
        lat0, lon0 = (lat1 + lat2) / 2, (lon1 + lon2) / 2
        m_lat, m_lon = _meters_per_degree(lat0)
        x1, y1 = _to_local_xy(lat1, lon1, lat0, lon0, m_lat, m_lon)
        x2, y2 = _to_local_xy(lat2, lon2, lat0, lon0, m_lat, m_lon)
        x_min, x_max = min(x1, x2), max(x1, x2)
        y_min, y_max = min(y1, y2), max(y1, y2)
        if x_max - x_min < 1 or y_max - y_min < 1:
            raise ValueError("Die beiden Eckpunkte müssen ein sichtbares Gebiet aufspannen.")

        lines = _candidate_lines(x_min, x_max, y_min, y_max, spacing_m, angle_deg)

        def clip_fn(x0: float, y0: float, x1_: float, y1_: float) -> Optional[Segment]:
            return _clip_segment_to_box(x0, y0, x1_, y1_, x_min, x_max, y_min, y_max)

    elif center is not None and radius_m is not None:
        if radius_m <= 0:
            raise ValueError("Der Radius muss größer als 0 sein.")
        lat0, lon0 = center
        m_lat, m_lon = _meters_per_degree(lat0)
        lines = _candidate_lines(-radius_m, radius_m, -radius_m, radius_m, spacing_m, angle_deg)

        def clip_fn(x0: float, y0: float, x1_: float, y1_: float) -> Optional[Segment]:
            return _clip_segment_to_circle(x0, y0, x1_, y1_, radius_m)

    else:
        raise ValueError("Entweder zwei Eckpunkte oder Mittelpunkt und Radius angeben.")

    local_points = _zigzag_points(lines, clip_fn)
    if not local_points:
        raise ValueError("Für diese Parameter wurde keine Route erzeugt - Zeilenabstand/Gebiet prüfen.")

    return [
        Waypoint(*_to_latlon(x, y, lat0, lon0, m_lat, m_lon), alt=altitude_m)
        for x, y in local_points
    ]
