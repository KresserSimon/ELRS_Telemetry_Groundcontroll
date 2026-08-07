"""QWebEngineView wrapper exposing a tiny Python API over the Leaflet page."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWebEngineWidgets import QWebEngineView

from ui.map_template import get_map_html


class MapWidget(QWebEngineView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._auto_center = True
        self.setHtml(get_map_html())

    def update_position(self, lat: float, lon: float, heading: Optional[float]) -> None:
        heading_js = "null" if heading is None else f"{heading}"
        self.page().runJavaScript(f"updateDrone({lat}, {lon}, {heading_js});")

    def set_auto_center(self, enabled: bool) -> None:
        self._auto_center = enabled
        self.page().runJavaScript(f"setAutoCenter({'true' if enabled else 'false'});")

    def clear_path(self) -> None:
        self.page().runJavaScript("clearPath();")
