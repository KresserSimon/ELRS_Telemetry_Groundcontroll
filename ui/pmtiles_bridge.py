"""QWebChannel bridge exposing byte-range reads of a local .pmtiles file to
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
`bridge.read_range(offset, length, function(base64) { ... })`, matching
the pattern already established for every other bridge object in this app
(route_bridge.py), just with a return value instead of "fire and forget".
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSlot


class PMTilesBridge(QObject):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._file = None
        self._key = ""

    def open(self, path: Path) -> None:
        """Point this bridge at a local .pmtiles file. Safe to call again
        later to switch files - the previous handle is closed first."""
        self.close()
        self._file = path.open("rb")
        self._key = str(path)

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        self._key = ""

    @pyqtSlot(int, int, result=str)
    def read_range(self, offset: int, length: int) -> str:
        """Base64-encoded bytes at [offset, offset+length) of the currently
        open file - base64 because QWebChannel marshals JS-visible return
        values as JSON, which has no native binary type."""
        if self._file is None:
            return ""
        self._file.seek(offset)
        return base64.b64encode(self._file.read(length)).decode("ascii")

    @pyqtSlot(result=str)
    def get_key(self) -> str:
        """A stable identifier for the currently open archive - the pmtiles
        JS library's Protocol registry keys PMTiles instances by this, and
        MapLibre style source URLs (pmtiles://<key>/{z}/{x}/{y}) resolve
        against it."""
        return self._key
