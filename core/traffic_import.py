"""Live air-traffic (ADS-B) lookup for the traffic overlay - the periodic,
provider-abstracted counterpart to core/openaip_import.py's one-shot
airspace fetch. See docs/feature_plan.md, "P3: Live-Flugverkehr (ADS-B)".

Two free, no-API-key providers are supported, selected by `provider`:
- "airplanes_live" (default): point+radius query, altitude in feet and
  speed in knots - both converted to metres/m-per-second here so the rest
  of the app never has to care which provider is configured.
- "opensky": bounding-box query, altitude/speed already metric.

Deliberately no cached-fallback-on-failure here (unlike openaip_import.py):
live traffic positions go stale within seconds, so a failed poll must show
"no data" rather than quietly replaying an old snapshot - see
core/traffic_worker.py.
"""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

PROVIDER_AIRPLANES_LIVE = "airplanes_live"
PROVIDER_OPENSKY = "opensky"

DEFAULT_BASE_URLS = {
    PROVIDER_AIRPLANES_LIVE: "https://api.airplanes.live/v2/point",
    PROVIDER_OPENSKY: "https://opensky-network.org/api/states/all",
}

_TIMEOUT_S = 10
_FEET_TO_M = 0.3048
_KT_TO_MS = 0.514444
_FPM_TO_MS = 0.00508


class TrafficFetchError(RuntimeError):
    """Traffic data could not be downloaded or parsed. Callers must treat a
    failed poll as "no data right now" and clear any previously shown
    contacts, never fall back to a stale snapshot - see the module
    docstring."""


@dataclass
class AircraftState:
    icao24: str
    callsign: str
    lat: float
    lon: float
    alt_m: Optional[float]  # MSL, metres
    heading_deg: Optional[float]
    groundspeed_ms: Optional[float]
    vertical_rate_ms: Optional[float]


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "elrs_ground_station"})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError) as exc:
        raise TrafficFetchError(f"Flugverkehrsdaten konnten nicht abgerufen werden: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise TrafficFetchError(f"Ungültige Antwort vom Flugverkehr-Dienst: {exc}") from exc


def _fetch_airplanes_live(base_url: str, lat: float, lon: float, radius_km: float) -> List[AircraftState]:
    # airplanes.live's point endpoint takes a radius in nautical miles,
    # capped at 250 nm by the service itself - clamped here too so an
    # oversized configured radius_km fails obviously (0 results) rather
    # than silently getting truncated server-side.
    radius_nm = max(1.0, min(radius_km / 1.852, 250.0))
    url = f"{base_url.rstrip('/')}/{lat}/{lon}/{radius_nm:.1f}"
    data = _get_json(url)
    aircraft = data.get("ac")
    if not isinstance(aircraft, list):
        raise TrafficFetchError("Unerwartetes Antwortformat vom Flugverkehr-Dienst (airplanes.live).")

    result: List[AircraftState] = []
    for ac in aircraft:
        if not isinstance(ac, dict):
            continue
        try:
            lat_i, lon_i = float(ac["lat"]), float(ac["lon"])
        except (KeyError, TypeError, ValueError):
            continue  # no current position report yet - skip, not fatal
        alt_baro = ac.get("alt_baro")
        if isinstance(alt_baro, (int, float)):
            alt_m = alt_baro * _FEET_TO_M
        elif alt_baro == "ground":
            alt_m = 0.0
        else:
            alt_m = None
        track = ac.get("track")
        gs = ac.get("gs")
        vrate = ac.get("baro_rate")
        result.append(AircraftState(
            icao24=str(ac.get("hex", "")),
            callsign=str(ac.get("flight") or "").strip(),
            lat=lat_i,
            lon=lon_i,
            alt_m=alt_m,
            heading_deg=float(track) if isinstance(track, (int, float)) else None,
            groundspeed_ms=gs * _KT_TO_MS if isinstance(gs, (int, float)) else None,
            vertical_rate_ms=vrate * _FPM_TO_MS if isinstance(vrate, (int, float)) else None,
        ))
    return result


def _fetch_opensky(base_url: str, lat: float, lon: float, radius_km: float) -> List[AircraftState]:
    deg_lat = radius_km / 111.32
    deg_lon = radius_km / (111.32 * max(math.cos(math.radians(lat)), 0.01))
    params = {
        "lamin": lat - deg_lat, "lamax": lat + deg_lat,
        "lomin": lon - deg_lon, "lomax": lon + deg_lon,
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    data = _get_json(url)
    states = data.get("states")
    if states is None:
        return []  # a quiet region legitimately has no traffic - not an error
    if not isinstance(states, list):
        raise TrafficFetchError("Unerwartetes Antwortformat vom Flugverkehr-Dienst (OpenSky).")

    result: List[AircraftState] = []
    for s in states:
        if not isinstance(s, list) or len(s) < 17:
            continue
        lon_i, lat_i = s[5], s[6]
        if not isinstance(lon_i, (int, float)) or not isinstance(lat_i, (int, float)):
            continue  # no current position report - skip, not fatal
        geo_alt, baro_alt = s[13], s[7]
        if isinstance(geo_alt, (int, float)):
            alt_m = float(geo_alt)
        elif isinstance(baro_alt, (int, float)):
            alt_m = float(baro_alt)
        else:
            alt_m = None
        velocity, track, vrate = s[9], s[10], s[11]
        result.append(AircraftState(
            icao24=str(s[0] or ""),
            callsign=str(s[1] or "").strip(),
            lat=float(lat_i),
            lon=float(lon_i),
            alt_m=alt_m,
            heading_deg=float(track) if isinstance(track, (int, float)) else None,
            groundspeed_ms=float(velocity) if isinstance(velocity, (int, float)) else None,
            vertical_rate_ms=float(vrate) if isinstance(vrate, (int, float)) else None,
        ))
    return result


def fetch_traffic(provider: str, base_url: str, lat: float, lon: float, radius_km: float) -> List[AircraftState]:
    if provider == PROVIDER_OPENSKY:
        return _fetch_opensky(base_url, lat, lon, radius_km)
    return _fetch_airplanes_live(base_url, lat, lon, radius_km)
