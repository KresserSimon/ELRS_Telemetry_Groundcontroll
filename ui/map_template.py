"""Self-contained Leaflet/OSM HTML page loaded once into QWebEngineView.

All live updates afterwards go through small JS function calls
(updateDrone / setAutoCenter / clearPath) via runJavaScript(), so the map
never reloads and the marker moves smoothly.
"""

MAP_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body, #map { height: 100%; margin: 0; padding: 0; background: #1b1f24; }
  .drone-icon {
    width: 22px; height: 22px;
    display: flex; align-items: center; justify-content: center;
    transform-origin: 50% 50%;
  }
  .drone-icon svg { width: 22px; height: 22px; filter: drop-shadow(0 0 2px rgba(0,0,0,0.6)); }
</style>
</head>
<body>
<div id="map"></div>
<script>
  var map = L.map('map', { zoomControl: true }).setView([__CENTER_LAT__, __CENTER_LON__], __ZOOM__);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);

  var pathLatLngs = [];
  var pathLine = L.polyline([], { color: '#ff8000', weight: 3 }).addTo(map);

  var droneIcon = L.divIcon({
    className: 'drone-icon',
    html: '<svg viewBox="0 0 24 24"><polygon points="12,2 20,20 12,15 4,20" fill="#ff3b30" stroke="#ffffff" stroke-width="1"/></svg>',
    iconSize: [22, 22],
    iconAnchor: [11, 11]
  });
  var droneMarker = null;

  var autoCenter = true;
  var hasCentered = false;

  function updateDrone(lat, lon, heading) {
    var latlng = [lat, lon];
    pathLatLngs.push(latlng);
    pathLine.setLatLngs(pathLatLngs);

    if (droneMarker === null) {
      droneMarker = L.marker(latlng, { icon: droneIcon }).addTo(map);
    } else {
      droneMarker.setLatLng(latlng);
    }

    if (heading !== null && heading !== undefined) {
      var el = droneMarker.getElement();
      if (el) {
        var svg = el.querySelector('svg');
        if (svg) { svg.style.transform = 'rotate(' + heading + 'deg)'; }
      }
    }

    if (!hasCentered) {
      map.setView(latlng, __ZOOM__);
      hasCentered = true;
    } else if (autoCenter) {
      map.panTo(latlng, { animate: true, duration: 0.3 });
    }
  }

  function setAutoCenter(enabled) {
    autoCenter = enabled;
    if (enabled && droneMarker) {
      map.panTo(droneMarker.getLatLng(), { animate: true });
    }
  }

  function clearPath() {
    pathLatLngs = [];
    pathLine.setLatLngs([]);
    hasCentered = false;
  }
</script>
</body>
</html>
"""


def get_map_html(center_lat: float = 48.1372, center_lon: float = 11.5756, zoom: int = 16) -> str:
    return (
        MAP_HTML_TEMPLATE
        .replace("__CENTER_LAT__", str(center_lat))
        .replace("__CENTER_LON__", str(center_lon))
        .replace("__ZOOM__", str(zoom))
    )
