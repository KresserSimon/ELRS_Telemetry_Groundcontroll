"""Self-contained Leaflet/OSM HTML page loaded once into QWebEngineView.

All live updates afterwards go through small JS function calls
(updateDrone / setAutoCenter / clearPath / setVehicleType / jumpToDrone) via
runJavaScript(), so the map never reloads and the marker moves smoothly.
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

  var vehicleIcons = {
    quad: '<svg viewBox="0 0 24 24">'
      + '<line x1="6" y1="6" x2="18" y2="18" stroke="#ffffff" stroke-width="2"/>'
      + '<line x1="18" y1="6" x2="6" y2="18" stroke="#ffffff" stroke-width="2"/>'
      + '<circle cx="6" cy="6" r="2.6" fill="#ff3b30" stroke="#ffffff" stroke-width="0.8"/>'
      + '<circle cx="18" cy="6" r="2.6" fill="#ff3b30" stroke="#ffffff" stroke-width="0.8"/>'
      + '<circle cx="6" cy="18" r="2.6" fill="#ff3b30" stroke="#ffffff" stroke-width="0.8"/>'
      + '<circle cx="18" cy="18" r="2.6" fill="#ff3b30" stroke="#ffffff" stroke-width="0.8"/>'
      + '<polygon points="12,3 15,10 9,10" fill="#ffffff"/>'
      + '</svg>',
    wing: '<svg viewBox="0 0 24 24">'
      + '<polygon points="12,2 22,20 12,16 2,20" fill="#ff3b30" stroke="#ffffff" stroke-width="1"/>'
      + '</svg>',
    plane: '<svg viewBox="0 0 24 24">'
      + '<path d="M12 1 L13.4 8.5 L22 13 L22 15 L13.2 13 L13.8 19.5 L17.5 22 L17.5 23 L12 21.7 L6.5 23 L6.5 22 L10.2 19.5 L10.8 13 L2 15 L2 13 L10.6 8.5 Z" '
      + 'fill="#ff3b30" stroke="#ffffff" stroke-width="0.6"/>'
      + '</svg>'
  };
  var vehicleType = 'quad';

  function buildIcon() {
    return L.divIcon({
      className: 'drone-icon',
      html: vehicleIcons[vehicleType] || vehicleIcons.quad,
      iconSize: [22, 22],
      iconAnchor: [11, 11]
    });
  }

  var droneMarker = null;
  var lastHeading = null;

  var autoCenter = true;
  var hasCentered = false;

  function applyRotation() {
    if (!droneMarker || lastHeading === null) return;
    var el = droneMarker.getElement();
    if (el) {
      var svg = el.querySelector('svg');
      if (svg) { svg.style.transform = 'rotate(' + lastHeading + 'deg)'; }
    }
  }

  function updateDrone(lat, lon, heading) {
    var latlng = [lat, lon];
    pathLatLngs.push(latlng);
    pathLine.setLatLngs(pathLatLngs);

    if (droneMarker === null) {
      droneMarker = L.marker(latlng, { icon: buildIcon() }).addTo(map);
    } else {
      droneMarker.setLatLng(latlng);
    }

    if (heading !== null && heading !== undefined) {
      lastHeading = heading;
    }
    applyRotation();

    if (!hasCentered) {
      map.setView(latlng, __ZOOM__);
      hasCentered = true;
    } else if (autoCenter) {
      map.panTo(latlng, { animate: true, duration: 0.3 });
    }
  }

  function setVehicleType(type) {
    if (!vehicleIcons.hasOwnProperty(type)) return;
    vehicleType = type;
    if (droneMarker) {
      droneMarker.setIcon(buildIcon());
      applyRotation();
    }
  }

  function setAutoCenter(enabled) {
    autoCenter = enabled;
    if (enabled && droneMarker) {
      map.panTo(droneMarker.getLatLng(), { animate: true });
    }
  }

  function jumpToDrone() {
    if (droneMarker) {
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
