"""QWebEngineView wrapper exposing a tiny Python API over the map page -
either the default Leaflet/raster-tile page (ui/map_template.py) or the
experimental, parallel MapLibre/vector-tile page (ui/maplibre_template.py),
picked at construction time via the `renderer` parameter. See
ui/maplibre_template.py's module docstring and the migration plan for why
these coexist rather than one replacing the other.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable, List, Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView

from core import i18n
from core.nfz import NoFlyZone
from core.pmtiles_extract import FALLBACK_REGION_FILE, KNOWN_REGIONS
from core.resources import resource_path
from core.route import Waypoint
from ui.map_template import get_map_html
from ui.maplibre_template import get_maplibre_html
from ui.pmtiles_bridge import PMTilesBridge
from ui.route_bridge import RouteBridge
from ui.tile_cache_handler import SCHEME as TILE_CACHE_SCHEME
from ui.tile_cache_handler import TileCacheSchemeHandler

OVERLAY_MARGIN = 10

# Real region extracts are multi-GB (see the migration plan) and are never
# bundled into the .exe by the build itself - either downloaded in-app
# (ui/pmtiles_download_dialog.py, via core/pmtiles_extract.py) or placed
# manually. _select_pmtiles_region() picks automatically based on the
# drone's home position, using each file's real bounding box (read
# directly from its own header via the `pmtiles show` CLI, not guessed).
def pmtiles_dir() -> Path:
    if getattr(sys, "frozen", False):
        # A packaged .exe ships no region files at all (see the migration
        # plan's size analysis) - point at a user-managed folder instead,
        # same ~/.elrs_ground_station/ convention as tile_cache/ and
        # gs_position.json. Users who want the MapLibre renderer in the
        # packaged app copy their own *.pmtiles region extracts here.
        # Deliberately NOT core/resources.py's resource_path() (which
        # resolves into the frozen bundle itself, i.e. read-only/temporary
        # territory) - this is real, permanent user data, not a bundled
        # asset.
        return Path.home() / ".elrs_ground_station" / "pmtiles"
    # Running from source: the real region extracts already checked out
    # under dev_data/ (gitignored, dev-only - see the migration plan).
    return Path(__file__).resolve().parent.parent / "dev_data" / "pmtiles"


def _pmtiles_search_dirs() -> List[Path]:
    """Every directory checked, in order, for a *.pmtiles region file.
    pmtiles_dir() (the user-writable folder) is both where the in-app
    download dialog writes new regions to AND where anyone can manually
    drop their own *.pmtiles files - but some people instead follow this
    app's existing assets/ bundling convention (icons/logo) and place
    files under assets/pmtiles next to the exe, which resource_path()
    resolves correctly whether frozen or run from source - so that's
    checked too, as a fallback location, not the primary one (new
    downloads still always go to pmtiles_dir())."""
    primary = pmtiles_dir()
    bundled = resource_path("assets", "pmtiles")
    return [primary] if bundled == primary else [primary, bundled]


def _select_pmtiles_region(lat: Optional[float], lon: Optional[float]) -> Path:
    filename = FALLBACK_REGION_FILE
    if lat is not None and lon is not None:
        for region in KNOWN_REGIONS:
            if region.min_lon <= lon <= region.max_lon and region.min_lat <= lat <= region.max_lat:
                filename = region.filename
                break
    for directory in _pmtiles_search_dirs():
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return pmtiles_dir() / filename  # missing - points at the primary (writable/download) location


CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")

DISK_CACHE_MAX_BYTES = 500 * 1024 * 1024  # 500 MB, per the offline-tile-cache sizing goal
POSITION_UPDATE_INTERVAL_MS = 200  # throttle JS map updates to max 5 Hz
DEFAULT_PATH_POINT_THRESHOLD_M = 1.5
_PROFILE_STORAGE_NAME = "elrs_ground_station_map"

_shared_profile: Optional[QWebEngineProfile] = None


def _get_shared_profile() -> QWebEngineProfile:
    # A plain self.page().profile() is an anonymous, off-the-record profile
    # whose HTTP cache always stays in-memory regardless of
    # setHttpCacheType() - only an explicitly named (persistent) profile
    # actually keeps a disk-backed cache across launches. That name must
    # stay a single shared instance rather than one-per-MapWidget: two
    # QWebEngineProfile objects pointed at the same persistent storage name
    # at once (e.g. transiently, while an old window is being torn down)
    # contend over the same on-disk cache and can stall page loads.
    global _shared_profile
    if _shared_profile is None:
        _shared_profile = QWebEngineProfile(_PROFILE_STORAGE_NAME)
        _shared_profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        _shared_profile.setHttpCacheMaximumSize(DISK_CACHE_MAX_BYTES)
    return _shared_profile


class MapWidget(QWebEngineView):
    def __init__(
        self,
        parent=None,
        home_lat: Optional[float] = None,
        home_lon: Optional[float] = None,
        renderer: str = "leaflet",
    ) -> None:
        super().__init__(parent)
        self._auto_center = True
        self._overlays: list = []  # [[widget, corner], ...]
        self._pending_position: Optional[tuple] = None
        self._renderer = renderer if renderer == "maplibre" else "leaflet"
        self._pmtiles_region_missing = False

        self._profile = _get_shared_profile()
        self.setPage(QWebEnginePage(self._profile, self))

        self.route_bridge = RouteBridge()
        self.pmtiles_bridge = PMTilesBridge()
        self._channel = QWebChannel(self.page())
        self._channel.registerObject("routeBridge", self.route_bridge)
        self._channel.registerObject("pmtilesBridge", self.pmtiles_bridge)
        self.page().setWebChannel(self._channel)

        self._tile_cache_handler = TileCacheSchemeHandler(self)
        self._profile.installUrlSchemeHandler(TILE_CACHE_SCHEME, self._tile_cache_handler)

        # Telemetry can arrive far faster than the map needs to visually
        # update - coalesce to the latest position and flush it to the JS
        # side at a fixed, gentle rate instead of one runJavaScript() call
        # per telemetry tick.
        self._position_timer = QTimer(self)
        self._position_timer.setInterval(POSITION_UPDATE_INTERVAL_MS)
        self._position_timer.timeout.connect(self._flush_position)
        self._position_timer.start()

        if self._renderer == "maplibre":
            self._load_maplibre_page(home_lat, home_lon)
        else:
            self._load_leaflet_page(home_lat, home_lon)

    def _load_leaflet_page(self, home_lat: Optional[float], home_lon: Optional[float]) -> None:
        html_kwargs = {
            "label_waypoint": i18n.tr("mapctx_waypoint"),
            "label_start": i18n.tr("mapctx_start"),
            "label_end": i18n.tr("mapctx_end"),
            "label_set_home": i18n.tr("mapctx_set_home"),
            "label_view": i18n.tr("mapctx_view"),
            "label_view_lock": i18n.tr("mapctx_view_lock"),
            "label_view_heading": i18n.tr("mapctx_view_heading"),
            "label_view_route_editor": i18n.tr("mapctx_view_route_editor"),
            "label_view_coords": i18n.tr("mapctx_view_coords"),
            "label_view_heatmap": i18n.tr("mapctx_view_heatmap"),
            "label_wp_edit": i18n.tr("mapctx_wp_edit"),
            "label_wp_delete": i18n.tr("mapctx_wp_delete"),
        }
        if home_lat is not None and home_lon is not None:
            html_kwargs["center_lat"] = home_lat
            html_kwargs["center_lon"] = home_lon
        self.setHtml(get_map_html(**html_kwargs))

    def _load_maplibre_page(self, home_lat: Optional[float], home_lon: Optional[float]) -> None:
        # No user-facing region picker yet (see the migration plan) - the
        # region whose bbox contains the home position is opened
        # automatically. A missing file degrades to a blank map (no crash)
        # rather than falling back to the Leaflet path, since silently
        # substituting a different renderer than the one explicitly
        # selected would be more confusing than an empty map.
        region_path = _select_pmtiles_region(home_lat, home_lon)
        if region_path.is_file():
            self.pmtiles_bridge.open(region_path)
        else:
            self._pmtiles_region_missing = True
        html_kwargs = {
            "label_waypoint": i18n.tr("mapctx_waypoint"),
            "label_start": i18n.tr("mapctx_start"),
            "label_end": i18n.tr("mapctx_end"),
            "label_set_home": i18n.tr("mapctx_set_home"),
            "label_wp_edit": i18n.tr("mapctx_wp_edit"),
            "label_wp_delete": i18n.tr("mapctx_wp_delete"),
        }
        if home_lat is not None and home_lon is not None:
            html_kwargs["center_lat"] = home_lat
            html_kwargs["center_lon"] = home_lon
        self.setHtml(get_maplibre_html(**html_kwargs))

    def pmtiles_region_missing(self) -> bool:
        """True only when the MapLibre renderer is active and no matching
        *.pmtiles region file was found at startup (see pmtiles_dir()) -
        the map is showing a blank/black base layer, not a crash."""
        return self._pmtiles_region_missing

    def add_overlay(self, widget, corner: str = "top-right") -> None:
        widget.setParent(self)
        self._overlays.append([widget, corner])
        self._reposition_overlays()
        widget.raise_()

    def remove_overlay(self, widget) -> None:
        """Detach a widget previously added via add_overlay() - used when
        docking it elsewhere (e.g. into the telemetry dashboard) instead of
        floating on the map. Leaves the widget's parent untouched; the
        caller is expected to reparent it immediately afterwards."""
        self._overlays = [entry for entry in self._overlays if entry[0] is not widget]
        self._reposition_overlays()

    def set_overlay_corner(self, widget, corner: str) -> None:
        for entry in self._overlays:
            if entry[0] is widget:
                entry[1] = corner
        self._reposition_overlays()

    def set_overlay_free(self, widget) -> None:
        """Mark an overlay as manually (drag-)positioned: keep it where it is
        on resize instead of snapping back to its last preset corner."""
        for entry in self._overlays:
            if entry[0] is widget:
                entry[1] = None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposition_overlays()

    def reposition_overlays(self) -> None:
        """Re-clamp all overlays into the current bounds - call after resizing
        an overlay widget itself (e.g. a scale change), since that doesn't
        raise a MapWidget resize event on its own."""
        self._reposition_overlays()

    def _reposition_overlays(self) -> None:
        # Overlays sharing a fixed corner (e.g. the lock + heading-mode
        # buttons both in bottom-right) stack outward from that corner in
        # the order they were added, instead of all landing on top of
        # each other - single-occupant corners keep their exact old offset.
        stack_offset: dict = {}
        for widget, corner in self._overlays:
            w, h = widget.width(), widget.height()
            if corner is None:
                # Freely (drag-)positioned: just keep it inside the current bounds.
                max_x = max(OVERLAY_MARGIN, self.width() - w - OVERLAY_MARGIN)
                max_y = max(OVERLAY_MARGIN, self.height() - h - OVERLAY_MARGIN)
                x = min(max(widget.x(), OVERLAY_MARGIN), max_x)
                y = min(max(widget.y(), OVERLAY_MARGIN), max_y)
                widget.move(x, y)
                widget.raise_()
                continue

            if corner == "center":
                # Not a stacking corner - always dead-center regardless of
                # other overlays, for anything meant to actively grab
                # attention (e.g. the warning banner) rather than sit
                # unobtrusively out of the way.
                x = max(OVERLAY_MARGIN, (self.width() - w) // 2)
                y = max(OVERLAY_MARGIN, (self.height() - h) // 2)
                widget.move(x, y)
                widget.raise_()
                continue

            offset = stack_offset.get(corner, 0)
            if corner == "top-left":
                x, y = OVERLAY_MARGIN, OVERLAY_MARGIN + offset
            elif corner == "bottom-left":
                x, y = OVERLAY_MARGIN, self.height() - h - OVERLAY_MARGIN - offset
            elif corner == "bottom-right":
                x, y = self.width() - w - OVERLAY_MARGIN, self.height() - h - OVERLAY_MARGIN - offset
            else:  # top-right
                x, y = self.width() - w - OVERLAY_MARGIN, OVERLAY_MARGIN + offset
            stack_offset[corner] = offset + h + OVERLAY_MARGIN
            widget.move(x, y)
            widget.raise_()

    def update_position(
        self, lat: float, lon: float, heading: Optional[float], link_quality: Optional[int] = None
    ) -> None:
        self._pending_position = (lat, lon, heading, link_quality)

    def _flush_position(self) -> None:
        if self._pending_position is None:
            return
        lat, lon, heading, link_quality = self._pending_position
        self._pending_position = None
        heading_js = "null" if heading is None else f"{heading}"
        lq_js = "null" if link_quality is None else f"{link_quality}"
        self.page().runJavaScript(f"updateDrone({lat}, {lon}, {heading_js}, {lq_js});")

    def set_path_point_threshold(self, meters: float) -> None:
        self.page().runJavaScript(f"setPathPointThreshold({meters});")

    def set_auto_center(self, enabled: bool) -> None:
        self._auto_center = enabled
        self.page().runJavaScript(f"setAutoCenter({'true' if enabled else 'false'});")

    def set_heatmap_enabled(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setHeatmapEnabled({'true' if enabled else 'false'});")

    def set_heading_mode(self, heading_up: bool) -> None:
        self.page().runJavaScript(f"setHeadingMode({'true' if heading_up else 'false'});")

    def set_coord_overlay_visible(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setCoordOverlayVisible({'true' if enabled else 'false'});")

    def clear_path(self) -> None:
        self.page().runJavaScript("clearPath();")

    def set_vehicle_type(self, vehicle_type: str) -> None:
        self.page().runJavaScript(f"setVehicleType('{vehicle_type}');")

    def set_base_layer(self, layer_id: str) -> None:
        self.page().runJavaScript(f"setBaseLayer('{layer_id}');")

    def center_on_current(self) -> None:
        self.page().runJavaScript("jumpToDrone();")

    def center_on_point(self, lat: float, lon: float) -> None:
        self.page().runJavaScript(f"centerOnPoint({lat}, {lon});")

    def render_route(self, waypoints: Iterable[Waypoint], segment_distances: Optional[List[float]] = None) -> None:
        waypoints = list(waypoints)
        segment_distances = segment_distances or []
        payload = [
            {"lat": wp.lat, "lon": wp.lon, "seg": segment_distances[i - 1] if i > 0 and i - 1 < len(segment_distances) else None}
            for i, wp in enumerate(waypoints)
        ]
        self.page().runJavaScript(f"setRoute({json.dumps(payload)});")

    def select_waypoint(self, index: int) -> None:
        self.page().runJavaScript(f"selectWaypoint({index});")

    def set_route_mode(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setRouteMode({'true' if enabled else 'false'});")

    def render_nfz(self, zones: Iterable[NoFlyZone]) -> None:
        payload = []
        for z in zones:
            if z.kind == "circle":
                payload.append({"kind": "circle", "name": z.name, "center": list(z.center), "radius_m": z.radius_m})
            else:
                payload.append({"kind": "polygon", "name": z.name, "points": [list(p) for p in z.points]})
        self.page().runJavaScript(f"setNoFlyZones({json.dumps(payload)});")

    def set_nfz_visible(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setNoFlyZonesVisible({'true' if enabled else 'false'});")

    def set_geofence(self, lat: float, lon: float, radius_m: float) -> None:
        self.page().runJavaScript(f"setGeofence({lat}, {lon}, {radius_m});")

    def clear_geofence(self) -> None:
        self.page().runJavaScript("clearGeofence();")

    def set_geofence_visible(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setGeofenceVisible({'true' if enabled else 'false'});")
