"""Experimental, parallel vector-tile map page (MapLibre GL JS + PMTiles),
loaded instead of ui/map_template.py's Leaflet/raster page when the
"MapLibre (Vektor, experimentell)" renderer is selected - see
ui/map_widget.py for how the choice is made. This is Stage 1 of the
migration plan: enough to prove vector rendering and native map-bearing
rotation actually work inside this app's QtWebEngine, not yet full feature
parity with the Leaflet path (waypoint editing, NFZ zones, heatmap, etc.
follow in later stages once this is validated).

Tile data comes from a local .pmtiles file via ui/pmtiles_bridge.py's
QWebChannel bridge (byte-range reads), not a URL scheme handler - the
pmtiles JS library accepts a custom Source object in place of a URL, so no
HTTP Range-header semantics are needed at all for local files.
"""

from ui.maplibre_assets import BASEMAPS_JS, MAPLIBRE_CSS, MAPLIBRE_JS, PMTILES_JS

MAPLIBRE_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<style>__MAPLIBRE_CSS__</style>
<script>__PMTILES_JS__</script>
<script>__MAPLIBRE_JS__</script>
<script>__BASEMAPS_JS__</script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<style>
  html, body, #map { height: 100%; margin: 0; padding: 0; background: #1b1f24; }
</style>
</head>
<body>
<div id="map"></div>
<script>
  var map = null;
  var pmtilesBridge = null;

  // Implements the pmtiles JS library's Source interface
  // (getBytes(offset, length) -> Promise<{data: ArrayBuffer}>, getKey())
  // by delegating byte reads to the Python-side PMTilesBridge QObject over
  // QWebChannel instead of an HTTP(S) URL - see ui/pmtiles_bridge.py.
  class QtSource {
    constructor(bridge, key) {
      this.bridge = bridge;
      this.key = key;
    }

    getKey() {
      return this.key;
    }

    getBytes(offset, length) {
      return new Promise((resolve) => {
        this.bridge.read_range(offset, length, function (base64data) {
          const binary = atob(base64data);
          const len = binary.length;
          const bytes = new Uint8Array(len);
          for (let i = 0; i < len; i++) { bytes[i] = binary.charCodeAt(i); }
          resolve({ data: bytes.buffer });
        });
      });
    }
  }

  function buildMap(key) {
    const protocol = new pmtiles.Protocol();
    maplibregl.addProtocol("pmtiles", protocol.tile);

    const source = new pmtiles.PMTiles(new QtSource(pmtilesBridge, key));
    protocol.add(source);

    map = new maplibregl.Map({
      container: "map",
      zoom: __ZOOM__,
      center: [__CENTER_LON__, __CENTER_LAT__],
      style: {
        version: 8,
        glyphs: "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf",
        sprite: "https://protomaps.github.io/basemaps-assets/sprites/v4/light",
        sources: {
          protomaps: {
            type: "vector",
            url: "pmtiles://" + key,
            attribution: "&copy; OpenStreetMap contributors"
          }
        },
        layers: basemaps.layers("protomaps", basemaps.namedFlavor("light"), { lang: "en" })
      }
    });
  }

  function initMapWhenReady() {
    if (!pmtilesBridge || map) { return; }
    pmtilesBridge.get_key(function (key) {
      if (!key) {
        console.error("PMTilesBridge has no .pmtiles file open - nothing to render.");
        return;
      }
      buildMap(key);
    });
  }

  new QWebChannel(qt.webChannelTransport, function (channel) {
    pmtilesBridge = channel.objects.pmtilesBridge;
    initMapWhenReady();
  });

  // --- Stage 1 feasibility surface: native map-bearing rotation, the
  // whole reason this parallel renderer is being explored - no CSS
  // transforms, no oversized/re-centered container, no counter-rotation
  // registry (compare ui/map_template.py's setMapRotation/fitMapContainer/
  // applyCounterRotation*, all made unnecessary here). ---
  function setBearingDeg(deg) {
    if (map) { map.setBearing(deg); }
  }
</script>
</body>
</html>
"""


def get_maplibre_html(center_lat: float = 48.1372, center_lon: float = 11.5756, zoom: int = 12) -> str:
    return (
        MAPLIBRE_HTML_TEMPLATE
        .replace("__MAPLIBRE_CSS__", MAPLIBRE_CSS)
        .replace("__PMTILES_JS__", PMTILES_JS)
        .replace("__MAPLIBRE_JS__", MAPLIBRE_JS)
        .replace("__BASEMAPS_JS__", BASEMAPS_JS)
        .replace("__CENTER_LAT__", str(center_lat))
        .replace("__CENTER_LON__", str(center_lon))
        .replace("__ZOOM__", str(zoom))
    )
