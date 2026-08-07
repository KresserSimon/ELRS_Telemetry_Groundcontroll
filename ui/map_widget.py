"""QWebEngineView wrapper exposing a tiny Python API over the Leaflet page."""
from __future__ import annotations

import json
from typing import Iterable, Optional

from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView

from core.route import Waypoint
from ui.map_template import get_map_html
from ui.route_bridge import RouteBridge

OVERLAY_MARGIN = 10
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")


class MapWidget(QWebEngineView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._auto_center = True
        self._overlays: list = []  # [[widget, corner], ...]

        self.route_bridge = RouteBridge()
        self._channel = QWebChannel(self.page())
        self._channel.registerObject("routeBridge", self.route_bridge)
        self.page().setWebChannel(self._channel)

        self.setHtml(get_map_html())

    def add_overlay(self, widget, corner: str = "top-right") -> None:
        widget.setParent(self)
        self._overlays.append([widget, corner])
        self._reposition_overlays()
        widget.raise_()

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

    def _reposition_overlays(self) -> None:
        for widget, corner in self._overlays:
            w, h = widget.width(), widget.height()
            if corner is None:
                # Freely (drag-)positioned: just keep it inside the current bounds.
                max_x = max(OVERLAY_MARGIN, self.width() - w - OVERLAY_MARGIN)
                max_y = max(OVERLAY_MARGIN, self.height() - h - OVERLAY_MARGIN)
                x = min(max(widget.x(), OVERLAY_MARGIN), max_x)
                y = min(max(widget.y(), OVERLAY_MARGIN), max_y)
            elif corner == "top-left":
                x, y = OVERLAY_MARGIN, OVERLAY_MARGIN
            elif corner == "bottom-left":
                x, y = OVERLAY_MARGIN, self.height() - h - OVERLAY_MARGIN
            elif corner == "bottom-right":
                x, y = self.width() - w - OVERLAY_MARGIN, self.height() - h - OVERLAY_MARGIN
            else:  # top-right
                x, y = self.width() - w - OVERLAY_MARGIN, OVERLAY_MARGIN
            widget.move(x, y)
            widget.raise_()

    def update_position(self, lat: float, lon: float, heading: Optional[float]) -> None:
        heading_js = "null" if heading is None else f"{heading}"
        self.page().runJavaScript(f"updateDrone({lat}, {lon}, {heading_js});")

    def set_auto_center(self, enabled: bool) -> None:
        self._auto_center = enabled
        self.page().runJavaScript(f"setAutoCenter({'true' if enabled else 'false'});")

    def clear_path(self) -> None:
        self.page().runJavaScript("clearPath();")

    def set_vehicle_type(self, vehicle_type: str) -> None:
        self.page().runJavaScript(f"setVehicleType('{vehicle_type}');")

    def center_on_current(self) -> None:
        self.page().runJavaScript("jumpToDrone();")

    def render_route(self, waypoints: Iterable[Waypoint]) -> None:
        payload = [{"lat": wp.lat, "lon": wp.lon} for wp in waypoints]
        self.page().runJavaScript(f"setRoute({json.dumps(payload)});")

    def set_route_mode(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setRouteMode({'true' if enabled else 'false'});")
