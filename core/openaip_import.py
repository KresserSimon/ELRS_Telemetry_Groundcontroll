"""Downloads airspace data from OpenAIP (or any compatible GeoJSON airspace
API/URL) for the region around a given center point and converts it into
NoFlyZone objects - the network counterpart to export/nfz_import.py's
file-based GeoJSON import, reusing its Polygon/MultiPolygon geometry
parsing (core.polygon_rings_from_geometry).

OpenAIP's exact REST response shape (property names, whether `type` is a
numeric code or a string) isn't pinned down with full certainty here -
different API versions/plans have used different shapes, and baking in a
wrong guess would be worse than being explicit about the uncertainty for
data with real airspace-safety relevance. So:
  - the base URL is user-configurable (core/openaip_config.py), not a
    single hardcoded endpoint, in case OpenAIP's real schema or a mirror
    needs a different one;
  - the type filter is built from the *actual* type-like values seen in a
    response rather than a hardcoded enum - see available_type_codes();
  - an unrecognized type code is always included rather than silently
    dropped, so an unfamiliar airspace category never just disappears.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional, Set

from core.nfz import NoFlyZone
from core.openaip_cache import get_cached_geojson, store_geojson
from export.nfz_import import polygon_rings_from_geometry

DEFAULT_BASE_URL = "https://api.core.openaip.net/api/airspaces"
_TIMEOUT_S = 15
_BBOX_MARGIN_DEG = 0.5  # roughly a 100km-wide box at mid-latitudes

# Best-known label for the handful of airspace type codes most likely to
# actually be filtered on - anything else observed in a response still
# gets included (see geojson_to_zones), just labelled with its raw code
# instead of a friendly name.
KNOWN_TYPE_LABELS = {
    "CTR": "CTR (Kontrollzone)",
    "R": "Restricted",
    "RESTRICTED": "Restricted",
    "P": "Prohibited",
    "PROHIBITED": "Prohibited",
    "Q": "Danger",
    "DANGER": "Danger",
    "TMA": "TMA",
    "TMZ": "TMZ (Transponderpflicht)",
    "RMZ": "RMZ (Funkpflicht)",
    "ATZ": "ATZ",
}


class OpenAipError(RuntimeError):
    """Airspace data could not be downloaded or parsed. Callers must treat a
    failed lookup as "unknown", never silently as "no airspaces here"."""


def _build_url(base_url: str, api_key: str, lat: float, lon: float) -> str:
    bbox = (
        f"{lon - _BBOX_MARGIN_DEG},{lat - _BBOX_MARGIN_DEG},"
        f"{lon + _BBOX_MARGIN_DEG},{lat + _BBOX_MARGIN_DEG}"
    )
    params = {"bbox": bbox}
    if api_key:
        params["apiKey"] = api_key
    return f"{base_url}?{urllib.parse.urlencode(params)}"


def fetch_airspaces_geojson(base_url: str, api_key: str, lat: float, lon: float) -> dict:
    """Fetch the raw response and normalize it to a GeoJSON FeatureCollection
    - OpenAIP's plain REST list endpoint returns {"items": [...]} with each
    item already carrying a GeoJSON `geometry`, so that shape is wrapped
    into a FeatureCollection too rather than requiring two code paths
    downstream.

    A successful fetch is cached to disk (core/openaip_cache.py) for this
    region; if the request fails (typically: no network), a previously
    cached response for the same region is returned instead of raising, so
    zones already downloaded once keep showing up offline. Only raises
    when there is no cached fallback either."""
    url = _build_url(base_url, api_key, lat, lon)
    headers = {"x-openaip-api-key": api_key} if api_key else {}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError) as exc:
        cached = get_cached_geojson(base_url, lat, lon)
        if cached is not None:
            return cached
        raise OpenAipError(f"Luftraumdaten konnten nicht abgerufen werden: {exc}") from exc
    except json.JSONDecodeError as exc:
        cached = get_cached_geojson(base_url, lat, lon)
        if cached is not None:
            return cached
        raise OpenAipError(f"Ungültige Antwort vom Luftraum-Dienst: {exc}") from exc

    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        geojson = data
    elif isinstance(data, dict) and isinstance(data.get("items"), list):
        features = [
            {"type": "Feature", "geometry": item.get("geometry"), "properties": item}
            for item in data["items"]
            if item.get("geometry")
        ]
        geojson = {"type": "FeatureCollection", "features": features}
    else:
        raise OpenAipError("Unerwartetes Antwortformat vom Luftraum-Dienst.")

    store_geojson(base_url, lat, lon, geojson)
    return geojson


def _feature_type_code(properties: dict) -> str:
    for key in ("type", "airspaceType", "class", "icaoClass", "category"):
        value = properties.get(key)
        if value is not None and value != "":
            return str(value)
    return "?"


def available_type_codes(geojson: dict) -> List[str]:
    """Every distinct type-like code actually present in a response."""
    codes: Set[str] = set()
    for feature in geojson.get("features", []):
        codes.add(_feature_type_code(feature.get("properties") or {}))
    return sorted(codes)


def type_label(code: str) -> str:
    return KNOWN_TYPE_LABELS.get(code.upper(), f"Typ {code}")


def _should_include(code: str, preferred_type_codes: Optional[List[str]]) -> bool:
    if not preferred_type_codes:
        return True
    if code.upper() in {t.upper() for t in preferred_type_codes}:
        return True
    # A recognized type the user didn't select -> excluded. An unrecognized
    # one always passes through so an unfamiliar category is never silently
    # hidden just because it wasn't in the (necessarily incomplete) filter list.
    return code.upper() not in KNOWN_TYPE_LABELS


def geojson_to_zones(geojson: dict, preferred_type_codes: Optional[List[str]] = None) -> List[NoFlyZone]:
    zones: List[NoFlyZone] = []
    for feature in geojson.get("features", []):
        properties = feature.get("properties") or {}
        code = _feature_type_code(properties)
        if not _should_include(code, preferred_type_codes):
            continue
        geometry = feature.get("geometry") or {}
        name = str(properties.get("name") or properties.get("Name") or "Luftraum")
        label = f"{type_label(code)}: {name}" if code != "?" else name
        for points in polygon_rings_from_geometry(geometry):
            zones.append(NoFlyZone(name=label, kind="polygon", points=points))
    return zones
