"""QWebChannel bridge exposing byte-range reads of local .pmtiles files to
the MapLibre GL JS side (ui/maplibre_template.py's vendored pmtiles.js).

This exists instead of a custom Qt URL scheme handler (the approach used
for raster tiles in tile_cache_handler.py) because the pmtiles JS library
accepts a custom "Source" object - {getBytes(offset, length), getKey()} -
in place of a URL, so a PMTiles instance can be backed directly by a plain
byte-range read with no HTTP semantics, no Range-header parsing, and no new
QWebEngineUrlSchemeHandler needed at all. See PMTILES_JS in
ui/maplibre_assets.py for the vendored library and ui/maplibre_template.py
for the JS-side Source implementation that calls read_range() below.

Every QWebChannel method call is inherently asynchronous from JS's side
(the call crosses the WebChannel transport and back) - a method with a
`result=` type becomes callback-based on the JS side:
`bridge.read_range(key, offset, length, function(base64) { ... })`,
matching the pattern already established for every other bridge object in
this app (route_bridge.py), just with a return value instead of "fire and
forget".

All *currently downloaded* regions are opened simultaneously (not just the
one covering the drone's home position) so their vector tiles can be
layered on top of each other in the MapLibre style - see
ui/map_widget.py:_list_downloaded_pmtiles() and buildMap() in
maplibre_template.py. Each open archive gets its own key (the filename
stem, e.g. "austria") so the pmtiles.js library's Protocol can address them
independently via pmtiles://<key>/{z}/{x}/{y} source URLs.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSlot


class PMTilesBridge(QObject):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._files: Dict[str, BinaryIO] = {}
        self._keys: List[str] = []

    def open_all(self, paths: List[Path]) -> None:
        """Point this bridge at a set of local .pmtiles files, keyed by
        filename stem. Safe to call again later to switch the set - the
        previous handles are closed first. `paths` order is preserved and
        exposed via get_keys_json() - see _list_downloaded_pmtiles() for
        what that order means (priority region first)."""
        self.close()
        for path in paths:
            key = path.stem
            self._files[key] = path.open("rb")
            self._keys.append(key)

    def close(self) -> None:
        for f in self._files.values():
            f.close()
        self._files = {}
        self._keys = []

    @pyqtSlot(str, int, int, result=str)
    def read_range(self, key: str, offset: int, length: int) -> str:
        """Base64-encoded bytes at [offset, offset+length) of the archive
        registered under `key` - base64 because QWebChannel marshals
        JS-visible return values as JSON, which has no native binary type."""
        f = self._files.get(key)
        if f is None:
            return ""
        f.seek(offset)
        return base64.b64encode(f.read(length)).decode("ascii")

    @pyqtSlot(result=str)
    def get_keys_json(self) -> str:
        """JSON array of every currently open archive's key, in priority
        order (index 0 = drawn on top - see _list_downloaded_pmtiles()).
        A plain JSON string, not a QWebChannel list return, to match the
        str-result convention already used everywhere else in this bridge
        and in route_bridge.py."""
        return json.dumps(self._keys)
