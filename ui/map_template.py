"""Self-contained Leaflet/OSM HTML page loaded once into QWebEngineView.

All live updates afterwards go through small JS function calls
(updateDrone / setAutoCenter / clearPath / setVehicleType / jumpToDrone /
setRoute / setRouteMode) via runJavaScript(), so the map never reloads and
the marker moves smoothly. Route-drawing clicks travel the other way (JS ->
Python) over a QWebChannel bridge registered as `routeBridge`.
"""

MAP_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<style>
  html, body, #map { height: 100%; margin: 0; padding: 0; background: #1b1f24; cursor: default; }
  #map.route-mode { cursor: crosshair; }
  .drone-icon {
    width: 22px; height: 22px;
    display: flex; align-items: center; justify-content: center;
    transform-origin: 50% 50%;
  }
  .drone-icon svg { width: 22px; height: 22px; filter: drop-shadow(0 0 2px rgba(0,0,0,0.6)); }
  .route-wp-dot {
    width: 20px; height: 20px; border-radius: 50%;
    background: #2ecc71; color: #ffffff; font-size: 11px; font-weight: 600;
    display: flex; align-items: center; justify-content: center;
    border: 1.5px solid #ffffff; box-shadow: 0 0 2px rgba(0,0,0,0.6);
    cursor: pointer;
  }
  .route-seg-label {
    background: rgba(20,24,30,0.85); color: #ffffff; font-size: 10px; font-weight: 600;
    padding: 1px 5px; border-radius: 6px; white-space: nowrap; text-align: center;
    border: 1px solid #2ecc71;
  }
</style>
</head>
<body>
<div id="map"></div>
<script>
  var map = L.map('map', { zoomControl: true }).setView([__CENTER_LAT__, __CENTER_LON__], __ZOOM__);

  var baseLayers = {
    osm: L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }),
    satellite: L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { maxZoom: 19, attribution: 'Tiles &copy; Esri' }
    )
  };
  var currentBaseLayer = 'osm';
  baseLayers[currentBaseLayer].addTo(map);

  function setBaseLayer(id) {
    if (!baseLayers.hasOwnProperty(id) || id === currentBaseLayer) return;
    map.removeLayer(baseLayers[currentBaseLayer]);
    currentBaseLayer = id;
    baseLayers[currentBaseLayer].addTo(map);
  }

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

  var homeMarker = null;
  var homeIcon = L.divIcon({
    className: '',
    html: '<svg viewBox="0 0 24 24" width="26" height="26" style="filter: drop-shadow(0 0 2px rgba(0,0,0,0.7));">'
      + '<path d="M12 2 L22 11 L19 11 L19 22 L14 22 L14 15 L10 15 L10 22 L5 22 L5 11 L2 11 Z" '
      + 'fill="#3ba7ff" stroke="#ffffff" stroke-width="1.2" stroke-linejoin="round"/>'
      + '</svg>',
    iconSize: [26, 26],
    iconAnchor: [13, 24]
  });

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
      homeMarker = L.marker(latlng, { icon: homeIcon, zIndexOffset: -100 }).addTo(map);
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

  // Keep the drone glued to the viewport centre even right after a manual
  // zoom (zooming otherwise re-centres on the zoom focus point, not the
  // drone, until the next telemetry tick nudges it back).
  map.on('zoomend', function () {
    if (autoCenter && droneMarker) {
      map.panTo(droneMarker.getLatLng(), { animate: false });
    }
  });

  function jumpToDrone() {
    if (droneMarker) {
      map.panTo(droneMarker.getLatLng(), { animate: true });
    }
  }

  function clearPath() {
    pathLatLngs = [];
    pathLine.setLatLngs([]);
    hasCentered = false;
    if (homeMarker) {
      map.removeLayer(homeMarker);
      homeMarker = null;
    }
  }

  // ---------------------------------------------------------- planned route

  var routeMarkers = [];
  var routeSegLabels = [];
  var routeLine = L.polyline([], { color: '#2ecc71', weight: 3, dashArray: '6,6' }).addTo(map);
  var routeMode = false;
  var routeBridge = null;

  function formatDistance(m) {
    return m >= 1000 ? (m / 1000).toFixed(2) + ' km' : Math.round(m) + ' m';
  }

  function setRoute(wps) {
    routeMarkers.forEach(function (m) { map.removeLayer(m); });
    routeMarkers = [];
    routeSegLabels.forEach(function (m) { map.removeLayer(m); });
    routeSegLabels = [];

    var latlngs = [];
    wps.forEach(function (wp, idx) {
      var latlng = [wp.lat, wp.lon];
      latlngs.push(latlng);
      var icon = L.divIcon({
        className: '',
        html: '<div class="route-wp-dot">' + (idx + 1) + '</div>',
        iconSize: [20, 20],
        iconAnchor: [10, 10]
      });
      var marker = L.marker(latlng, { icon: icon, zIndexOffset: 500 }).addTo(map);
      marker.on('click', function (e) {
        L.DomEvent.stopPropagation(e);
        if (routeBridge) { routeBridge.waypoint_marker_clicked(idx); }
      });
      routeMarkers.push(marker);

      if (idx > 0 && wp.seg !== null && wp.seg !== undefined) {
        var prev = wps[idx - 1];
        var midLat = (prev.lat + wp.lat) / 2;
        var midLon = (prev.lon + wp.lon) / 2;
        var segIcon = L.divIcon({
          className: '',
          html: '<div class="route-seg-label">' + formatDistance(wp.seg) + '</div>',
          iconSize: [70, 16],
          iconAnchor: [35, 8]
        });
        var segLabel = L.marker([midLat, midLon], { icon: segIcon, interactive: false, zIndexOffset: 400 }).addTo(map);
        routeSegLabels.push(segLabel);
      }
    });
    routeLine.setLatLngs(latlngs);
  }

  function setRouteMode(enabled) {
    routeMode = enabled;
    var el = document.getElementById('map');
    if (enabled) { el.classList.add('route-mode'); } else { el.classList.remove('route-mode'); }
  }

  map.on('click', function (e) {
    if (routeMode && routeBridge) {
      routeBridge.waypoint_clicked(e.latlng.lat, e.latlng.lng);
    }
  });

  // -------------------------------------------------------------- no-fly zones

  var nfzLayers = [];
  var nfzVisible = true;

  function setNoFlyZones(zones) {
    nfzLayers.forEach(function (l) { map.removeLayer(l); });
    nfzLayers = [];

    zones.forEach(function (zone) {
      var layer;
      if (zone.kind === 'circle') {
        layer = L.circle([zone.center[0], zone.center[1]], {
          radius: zone.radius_m, color: '#e74c3c', weight: 2, fillColor: '#e74c3c', fillOpacity: 0.2
        });
      } else {
        var latlngs = zone.points.map(function (p) { return [p[0], p[1]]; });
        layer = L.polygon(latlngs, { color: '#e74c3c', weight: 2, fillColor: '#e74c3c', fillOpacity: 0.2 });
      }
      layer.bindTooltip(zone.name, { sticky: true });
      if (nfzVisible) { layer.addTo(map); }
      nfzLayers.push(layer);
    });
  }

  function setNoFlyZonesVisible(enabled) {
    nfzVisible = enabled;
    nfzLayers.forEach(function (l) {
      var onMap = map.hasLayer(l);
      if (enabled && !onMap) { l.addTo(map); }
      else if (!enabled && onMap) { map.removeLayer(l); }
    });
  }

  if (typeof qt !== 'undefined' && qt.webChannelTransport) {
    new QWebChannel(qt.webChannelTransport, function (channel) {
      routeBridge = channel.objects.routeBridge;
    });
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
