"""Persists the user's live-traffic (ADS-B) overlay settings - provider,
base URL, poll radius/interval, and the altitude filter (mode + threshold)
that keeps airliner cruise traffic out of view. Same load_*/save_* pattern
as core/openaip_config.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from core.traffic_import import DEFAULT_BASE_URLS, PROVIDER_AIRPLANES_LIVE, PROVIDER_OPENSKY

CONFIG_PATH = Path.home() / ".elrs_ground_station" / "traffic_config.json"

# Default: height above ground, not sea level - see docs/feature_plan.md's
# "Maximalhoehen-Filter" note on why AGL uses a single ground-reference
# elevation (core/terrain.py) rather than a per-contact lookup. MSL remains
# selectable for anyone who prefers to reason in raw reported altitude.
ALTITUDE_MODE_AGL = "agl"
ALTITUDE_MODE_MSL = "msl"

DEFAULT_RADIUS_KM = 30.0
DEFAULT_POLL_INTERVAL_S = 15.0
DEFAULT_MAX_ALTITUDE_M = 1500.0


class TrafficConfig(TypedDict):
    enabled: bool
    provider: str
    base_url: str
    radius_km: float
    poll_interval_s: float
    altitude_mode: str
    max_altitude_m: float


def load_traffic_config() -> TrafficConfig:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    provider = data.get("provider")
    if provider not in (PROVIDER_AIRPLANES_LIVE, PROVIDER_OPENSKY):
        provider = PROVIDER_AIRPLANES_LIVE
    altitude_mode = data.get("altitude_mode")
    if altitude_mode not in (ALTITUDE_MODE_AGL, ALTITUDE_MODE_MSL):
        altitude_mode = ALTITUDE_MODE_AGL
    return {
        "enabled": bool(data.get("enabled", False)),
        "provider": provider,
        "base_url": str(data.get("base_url") or DEFAULT_BASE_URLS[provider]),
        "radius_km": float(data.get("radius_km", DEFAULT_RADIUS_KM)),
        "poll_interval_s": float(data.get("poll_interval_s", DEFAULT_POLL_INTERVAL_S)),
        "altitude_mode": altitude_mode,
        "max_altitude_m": float(data.get("max_altitude_m", DEFAULT_MAX_ALTITUDE_M)),
    }


def save_traffic_config(config: TrafficConfig) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(dict(config), indent=2), encoding="utf-8")
    except OSError:
        pass
