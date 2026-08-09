"""Disk cache for terrain elevation lookups (core/terrain.py), so a route
already looked up once keeps working offline, and only points not seen
before need a live Open-Elevation request when a connection is available.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

CACHE_PATH = Path.home() / ".elrs_ground_station" / "elevation_cache.json"

# 5 decimal places is roughly 1.1 m of latitude resolution - fine enough
# that a route re-flown/re-planned over the same ground reuses the cache,
# without the cache file growing unboundedly from float-noise "new" points.
_PRECISION = 5


def cache_key(lat: float, lon: float) -> str:
    return f"{round(lat, _PRECISION)},{round(lon, _PRECISION)}"


def load_elevation_cache() -> Dict[str, float]:
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    result = {}
    for key, value in data.items():
        try:
            result[key] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def save_elevation_cache(cache: Dict[str, float]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass
