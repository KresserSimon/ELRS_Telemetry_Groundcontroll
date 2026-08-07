"""Terrain elevation lookups and terrain-collision checking for planned
routes - uses the free Open-Elevation public API (no API key needed), the
same "assume internet is reachable for map data" assumption the app already
makes for its OSM/Esri tile layers.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import List, Optional, Tuple

from core.route import Waypoint

_API_URL = "https://api.open-elevation.com/api/v1/lookup"
_BATCH_SIZE = 100
_TIMEOUT_S = 10


class TerrainLookupError(RuntimeError):
    """Elevation data could not be retrieved (no network, API down, bad
    response, ...). Callers must treat a failed lookup as "unknown", never
    silently as "safe"."""


def fetch_elevations(points: List[Tuple[float, float]]) -> List[float]:
    """Return MSL elevation in metres for each (lat, lon) point, in order."""
    if not points:
        return []

    elevations: List[float] = []
    for start in range(0, len(points), _BATCH_SIZE):
        chunk = points[start:start + _BATCH_SIZE]
        payload = json.dumps({
            "locations": [{"latitude": lat, "longitude": lon} for lat, lon in chunk]
        }).encode("utf-8")
        request = urllib.request.Request(
            _API_URL, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError) as exc:
            raise TerrainLookupError(f"Geländedaten konnten nicht abgerufen werden: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise TerrainLookupError(f"Ungültige Antwort vom Höhendaten-Dienst: {exc}") from exc

        results = body.get("results")
        if not isinstance(results, list) or len(results) != len(chunk):
            raise TerrainLookupError("Unerwartete Antwort vom Höhendaten-Dienst.")
        try:
            elevations.extend(float(r["elevation"]) for r in results)
        except (KeyError, TypeError, ValueError) as exc:
            raise TerrainLookupError(f"Unerwartete Antwort vom Höhendaten-Dienst: {exc}") from exc

    return elevations


def check_terrain_clearance(
    waypoints: List[Waypoint],
    home_lat: Optional[float] = None,
    home_lon: Optional[float] = None,
) -> List[float]:
    """Return, per waypoint, the clearance in metres between its predicted
    absolute altitude and the terrain directly beneath it. Negative means
    the waypoint's altitude is below ground level there - it would fly into
    the terrain (a hill/mountain slope, typically, since that's the case
    where a constant-looking "height above home" profile intersects rising
    ground).

    Waypoint.alt is height above home (see ui/route_editor_dialog.py), so
    this first resolves a home elevation - either at the given home_lat/lon
    (pass the live telemetry home fix when one exists) or, failing that, at
    the route's own first waypoint, since a planned route commonly starts at
    the launch point. Home elevation plus each waypoint's alt gives its
    predicted absolute (MSL) altitude, compared against the terrain
    elevation sampled directly under that waypoint.
    """
    if not waypoints:
        return []

    if home_lat is None or home_lon is None:
        home_lat, home_lon = waypoints[0].lat, waypoints[0].lon

    points = [(home_lat, home_lon)] + [(wp.lat, wp.lon) for wp in waypoints]
    elevations = fetch_elevations(points)
    home_elevation, terrain = elevations[0], elevations[1:]

    clearances = []
    for wp, ground in zip(waypoints, terrain):
        predicted_alt = home_elevation + (wp.alt if wp.alt is not None else 0.0)
        clearances.append(predicted_alt - ground)
    return clearances
