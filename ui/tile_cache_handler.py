"""Local disk cache for OSM/Esri map tiles, served to the embedded Leaflet
map through a custom "elrstile://" URL scheme instead of Leaflet fetching
tile URLs directly - so a tile already downloaded once keeps rendering
with no internet connection, and any successful fetch refreshes/adds to
the cache for next time (the map's counterpart to core/elevation_cache.py
and core/openaip_cache.py).

Registering a custom QWebEngineUrlScheme must happen before QApplication
is constructed (a hard Qt requirement, like QtWebEngineWidgets itself
needing to be imported before QApplication - see ui/map_widget.py). This
module does that registration at import time; main.py already imports
ui.main_window (which imports ui.map_widget, which imports this module)
before creating QApplication, so the ordering holds automatically.

requestStarted() runs on the profile's IO thread, not the GUI thread, so
the plain blocking urllib fetch used here (matching the rest of the app's
network code - core/terrain.py, core/openaip_import.py) does not freeze
the UI; it only serializes further tile requests behind each other, which
is an acceptable trade-off for the simplicity and safety of not having to
manage cross-thread QNetworkReply/job-lifecycle bookkeeping.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

from PyQt6.QtCore import QBuffer, QIODevice, QUrl
from PyQt6.QtWebEngineCore import (
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)

SCHEME = b"elrstile"
CACHE_DIR = Path.home() / ".elrs_ground_station" / "tile_cache"
_TIMEOUT_S = 8
_USER_AGENT = "ELRS-Ground-Station/1.0 (+https://github.com/KresserSimon/ELRS_Telemetry_Groundcontroll)"

# {z}/{x}/{y} in the upstream URL template - satellite's own tile server
# happens to want {z}/{y}/{x}, but the custom-scheme URL Leaflet requests
# always uses the same {z}/{x}/{y} order, reordered here per layer.
_UPSTREAM_URLS = {
    "osm": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "satellite": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
}
_MIME_TYPES = {
    "osm": b"image/png",
    "satellite": b"image/jpeg",
}


def _register_scheme() -> None:
    if bytes(QWebEngineUrlScheme.schemeByName(SCHEME).name()) == SCHEME:
        return  # already registered - re-import, or a second MapWidget instance
    scheme = QWebEngineUrlScheme(SCHEME)
    # Host, not HostAndPort: elrstile:// URLs (elrstile://osm/{z}/{x}/{y}.png)
    # never carry a port - HostAndPort requires a default port to be set via
    # setDefaultPort(), which registerScheme() otherwise rejects at runtime.
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.CorsEnabled
    )
    QWebEngineUrlScheme.registerScheme(scheme)


_register_scheme()


def _cache_path(layer: str, z: str, x: str, y: str) -> Path:
    return CACHE_DIR / layer / z / x / f"{y}.tile"


def parse_tile_url(url: QUrl) -> Optional[Tuple[str, str, str, str]]:
    """(layer, z, x, y) parsed from an elrstile://layer/z/x/y.png URL, or
    None if it doesn't look like a well-formed tile request - pulled out
    of requestStarted() so this parsing can be unit-tested without a real
    QWebEngineUrlRequestJob (which Chromium creates internally and can't
    be constructed standalone in a test)."""
    layer = url.host()
    parts = [p for p in url.path().split("/") if p]
    if layer not in _UPSTREAM_URLS or len(parts) != 3 or not parts[2].endswith(".png"):
        return None
    z, x = parts[0], parts[1]
    y = parts[2][: -len(".png")]
    if not (z.isdigit() and x.isdigit() and y.isdigit()):
        return None
    return layer, z, x, y


def upstream_url(layer: str, z: str, x: str, y: str) -> str:
    return _UPSTREAM_URLS[layer].format(z=z, x=x, y=y)


class TileCacheSchemeHandler(QWebEngineUrlSchemeHandler):
    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:
        parsed = parse_tile_url(job.requestUrl())
        if parsed is None:
            job.fail(QWebEngineUrlRequestJob.Error.UrlInvalid)
            return
        layer, z, x, y = parsed

        cache_file = _cache_path(layer, z, x, y)
        if cache_file.is_file():
            try:
                data = cache_file.read_bytes()
            except OSError:
                data = None
            if data is not None:
                self._reply(job, layer, data)
                return

        try:
            request = urllib.request.Request(upstream_url(layer, z, x, y), headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
                data = response.read()
        except (urllib.error.URLError, OSError, ValueError):
            self._fail(job)
            return

        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(data)
        except OSError:
            pass  # cache write failure must not block showing the tile
        self._reply(job, layer, data)

    @staticmethod
    def _reply(job: QWebEngineUrlRequestJob, layer: str, data: bytes) -> None:
        buffer = QBuffer(job)
        buffer.setData(data)
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        try:
            job.reply(_MIME_TYPES.get(layer, b"image/png"), buffer)
        except RuntimeError:
            pass  # job's C++ object was already destroyed (page navigated away)

    @staticmethod
    def _fail(job: QWebEngineUrlRequestJob) -> None:
        try:
            job.fail(QWebEngineUrlRequestJob.Error.RequestFailed)
        except RuntimeError:
            pass
