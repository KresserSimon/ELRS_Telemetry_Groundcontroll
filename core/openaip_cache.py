"""Disk cache for OpenAIP airspace responses (core/openaip_import.py), so
zones already downloaded once for a region keep showing up offline, and a
successful download always refreshes the cached copy for next time.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

CACHE_PATH = Path.home() / ".elrs_ground_station" / "openaip_cache.json"

# The request bbox is already ~100km wide (core.openaip_import._BBOX_MARGIN_DEG),
# so 1 decimal place (~11km) of key precision is coarse on purpose - the
# goal is "same general area", not an exact-position cache.
_PRECISION = 1


def cache_key(base_url: str, lat: float, lon: float) -> str:
    return f"{base_url}|{round(lat, _PRECISION)},{round(lon, _PRECISION)}"


def load_openaip_cache() -> Dict[str, dict]:
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_openaip_cache(cache: Dict[str, dict]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass


def get_cached_geojson(base_url: str, lat: float, lon: float) -> Optional[dict]:
    return load_openaip_cache().get(cache_key(base_url, lat, lon))


def store_geojson(base_url: str, lat: float, lon: float, geojson: dict) -> None:
    cache = load_openaip_cache()
    cache[cache_key(base_url, lat, lon)] = geojson
    save_openaip_cache(cache)
