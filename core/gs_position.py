"""Persists the pilot's own ground-station position and computes azimuth/
elevation from it to the model - primarily for manual antenna aiming (a
directional Yagi etc.), not for the existing tracker-output formats
(core/tracker_output.py), which already only need the model's absolute
position (see docs/feature_plan.md's "Position der Bodenstation" for that
scope note).

Deliberately a third, separate concept from:
- ui/dashboard.py's Dashboard._home (the flight-start reference behind
  "Entfernung/Peilung Heim" - resets every session, never persisted), and
- core/home_config.py's saved map-startup-center (only affects where the
  map first opens, unrelated to any distance/bearing calculation).

Only manual entry is implemented for now - `source` already distinguishes
"manual" from a future "gps" (a serial NMEA GPS-mouse reader), which is
real, hardware-dependent follow-up work, not yet built.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.geo import bearing_deg, haversine_distance_m

CONFIG_PATH = Path.home() / ".elrs_ground_station" / "gs_position.json"


@dataclass
class GsPosition:
    lat: float
    lon: float
    alt: Optional[float] = None  # meters, same reference as GPS altitude
    source: str = "manual"  # "manual" | "gps" (gps reader not yet implemented)


def load_gs_position() -> Optional[GsPosition]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return GsPosition(
            lat=float(data["lat"]),
            lon=float(data["lon"]),
            alt=float(data["alt"]) if data.get("alt") is not None else None,
            source=data.get("source", "manual"),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_gs_position(position: GsPosition) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {"lat": position.lat, "lon": position.lon, "alt": position.alt, "source": position.source}
        CONFIG_PATH.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def clear_gs_position() -> None:
    try:
        CONFIG_PATH.unlink()
    except OSError:
        pass


@dataclass
class AzimuthElevation:
    azimuth_deg: float
    elevation_deg: Optional[float]  # None if either altitude is unknown


def compute_azimuth_elevation(
    gs_lat: float,
    gs_lon: float,
    gs_alt: Optional[float],
    model_lat: float,
    model_lon: float,
    model_alt: Optional[float],
) -> AzimuthElevation:
    azimuth = bearing_deg(gs_lat, gs_lon, model_lat, model_lon)
    elevation = None
    if gs_alt is not None and model_alt is not None:
        horizontal_m = haversine_distance_m(gs_lat, gs_lon, model_lat, model_lon)
        # max(..., epsilon) avoids atan2's (0, 0) degeneracy directly
        # overhead, where "no horizontal distance" would otherwise make
        # the elevation angle numerically unstable rather than ~90 deg.
        elevation = math.degrees(math.atan2(model_alt - gs_alt, max(horizontal_m, 1e-6)))
    return AzimuthElevation(azimuth, elevation)
