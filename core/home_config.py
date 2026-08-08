"""Persists the user's preferred startup map center ("home position") across
runs, in a small JSON file under the user's home directory - independent of
the live telemetry-derived home marker (always the first GPS fix of the
current session) used for distance/bearing-to-home stats. This is only
about where the map first opens, before any fix has arrived.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

CONFIG_PATH = Path.home() / ".elrs_ground_station" / "home_position.json"


def load_home_position() -> Optional[Tuple[float, float]]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return float(data["lat"]), float(data["lon"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_home_position(lat: float, lon: float) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({"lat": lat, "lon": lon}), encoding="utf-8")
    except OSError:
        pass


def clear_home_position() -> None:
    try:
        CONFIG_PATH.unlink()
    except OSError:
        pass
