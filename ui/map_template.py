"""Self-contained Leaflet/OSM HTML page loaded once into QWebEngineView.

All live updates afterwards go through small JS function calls
(updateDrone / setAutoCenter / setHeadingMode / setHeatmapEnabled /
clearPath / setVehicleType / jumpToDrone / centerOnPoint / setRoute /
setRouteMode / setCoordOverlayVisible) via runJavaScript(), so the map
never reloads and the marker moves smoothly.
Route-drawing clicks, the "set home"/view-options context menu entries, and
the coordinate readout travel the other way (JS -> Python) over a
QWebChannel bridge registered as `routeBridge`.

Leaflet itself is vendored inline (ui/leaflet_assets.py) rather than
fetched from a CDN, so the map UI, route planning, and drone tracking all
still work with no network connection - only the OSM/satellite tile
images require one; without them the map just shows a blank/gray
background behind everything else.
"""

from ui.leaflet_assets import LEAFLET_CSS, LEAFLET_JS

MAP_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<style>__LEAFLET_CSS__</style>
<script>__LEAFLET_JS__</script>
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
  .route-context-menu {
    position: absolute; display: none; z-index: 1000;
    background: #20242b; border: 1px solid #3a4048; border-radius: 6px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.5); overflow: visible; min-width: 170px;
    padding: 4px 0;
  }
  .route-context-menu button {
    display: block; width: 100%; padding: 7px 14px; border: none; background: none;
    color: #e8e8e8; text-align: left; font-size: 12px; cursor: pointer;
  }
  .route-context-menu button:hover { background: #2ecc71; color: #10151a; }
  .route-context-menu-sep { height: 1px; background: #3a4048; margin: 4px 0; }
  .route-context-submenu { position: relative; }
  .route-context-submenu-label {
    padding: 7px 14px; font-size: 12px; color: #e8e8e8; cursor: default;
  }
  .route-context-submenu:hover .route-context-submenu-label { background: #2ecc71; color: #10151a; }
  .route-context-submenu-flyout {
    display: none; position: absolute; left: 100%; top: -4px;
    background: #20242b; border: 1px solid #3a4048; border-radius: 6px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.5); min-width: 190px; overflow: hidden; padding: 4px 0;
  }
  .route-context-submenu:hover .route-context-submenu-flyout { display: block; }
  .route-context-submenu-flyout button {
    display: block; width: 100%; padding: 7px 14px; border: none; background: none;
    color: #e8e8e8; text-align: left; font-size: 12px; cursor: pointer;
  }
  .route-context-submenu-flyout button:hover { background: #2ecc71; color: #10151a; }
  .coord-overlay {
    position: absolute; display: none; z-index: 999; pointer-events: none;
    background: rgba(18,22,28,0.88); color: #e8e8e8; font-size: 11px; font-family: monospace;
    padding: 3px 7px; border-radius: 5px; border: 1px solid #0d1117; white-space: nowrap;
  }
</style>
</head>
<body>
<div id="map"></div>
<div id="coord-overlay" class="coord-overlay"></div>
<div id="route-context-menu" class="route-context-menu">
  <button onclick="contextMenuPick('waypoint')">__LABEL_WAYPOINT__</button>
  <button onclick="contextMenuPick('start')">__LABEL_START__</button>
  <button onclick="contextMenuPick('end')">__LABEL_END__</button>
  <div class="route-context-menu-sep"></div>
  <button onclick="contextMenuSetHome()">__LABEL_SET_HOME__</button>
  <div class="route-context-submenu">
    <div class="route-context-submenu-label">__LABEL_VIEW__ &#9656;</div>
    <div class="route-context-submenu-flyout">
      <button onclick="contextMenuViewAction('lock')">__LABEL_VIEW_LOCK__</button>
      <button onclick="contextMenuViewAction('heading')">__LABEL_VIEW_HEADING__</button>
      <button onclick="contextMenuViewAction('route_editor')">__LABEL_VIEW_ROUTE_EDITOR__</button>
      <button onclick="contextMenuViewAction('coords')">__LABEL_VIEW_COORDS__</button>
      <button onclick="contextMenuViewAction('heatmap')">__LABEL_VIEW_HEATMAP__</button>
    </div>
  </div>
</div>
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

  // ------------------------------------------------- RSSI/LQ heatmap track
  //
  // A parallel set of short 2-point colored segments, one per telemetry
  // tick, alongside the always-on plain-orange pathLine above - toggling
  // heatmap mode just swaps which layer is shown, so no track data is ever
  // lost switching back and forth, and nothing needs to be redrawn/recolored
  // retroactively.
  var heatmapEnabled = false;
  var heatSegments = [];
  var lastHeatPoint = null;

  function linkQualityColor(lq) {
    if (lq === null || lq === undefined) return '#888888';
    if (lq >= 80) return '#2ecc71';
    if (lq >= 50) return '#f1c40f';
    return '#e74c3c';
  }

  function setHeatmapEnabled(enabled) {
    heatmapEnabled = enabled;
    if (enabled) {
      map.removeLayer(pathLine);
      heatSegments.forEach(function (seg) { seg.addTo(map); });
      lastHeatPoint = pathLatLngs.length ? pathLatLngs[pathLatLngs.length - 1] : null;
    } else {
      heatSegments.forEach(function (seg) { map.removeLayer(seg); });
      pathLine.addTo(map);
    }
  }

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
      // In heading-up mode the whole map container is rotated by
      // -lastHeading (see setMapRotation), so the icon's own +lastHeading
      // rotation cancels that out and it ends up pointing straight up -
      // no heading-up-specific case needed here.
      if (svg) { svg.style.transform = 'rotate(' + lastHeading + 'deg)'; }
    }
  }

  // ------------------------------------------------------- map orientation
  //
  // North-up (default) leaves the map container untransformed and only
  // rotates the drone icon (above). Heading-up instead rotates the whole
  // map container so the drone's current heading always points to the
  // screen's top edge, like a car GPS's "track up" mode.

  var headingUp = false;
  var mapRotationDeg = 0;

  function setMapRotation(deg) {
    mapRotationDeg = deg || 0;
    var container = map.getContainer();
    container.style.transformOrigin = '50% 50%';
    container.style.transform = mapRotationDeg ? ('rotate(' + (-mapRotationDeg) + 'deg)') : '';
  }

  function setHeadingMode(enabled) {
    headingUp = enabled;
    setMapRotation(enabled ? (lastHeading || 0) : 0);
  }

  // Converts a raw browser mouse position back to the geographic point
  // visually under the cursor, undoing the container's CSS rotation - the
  // rotation is paint-only, so Leaflet's own (unrotated) hit-testing would
  // otherwise place waypoints/NFZ clicks at the wrong spot whenever the map
  // is visually rotated (see map.on('click'...) / ('contextmenu'...) below).
  function screenPointToLatLng(clientX, clientY) {
    var rect = map.getContainer().getBoundingClientRect();
    var cx = rect.left + rect.width / 2;
    var cy = rect.top + rect.height / 2;
    var dx = clientX - cx;
    var dy = clientY - cy;
    var theta = mapRotationDeg * Math.PI / 180;
    var rdx = dx * Math.cos(theta) - dy * Math.sin(theta);
    var rdy = dx * Math.sin(theta) + dy * Math.cos(theta);
    var size = map.getSize();
    var localPoint = L.point(size.x / 2 + rdx, size.y / 2 + rdy);
    return map.containerPointToLatLng(localPoint);
  }

  function updateDrone(lat, lon, heading, linkQuality) {
    var latlng = [lat, lon];
    pathLatLngs.push(latlng);
    pathLine.setLatLngs(pathLatLngs);

    if (heatmapEnabled) {
      if (lastHeatPoint !== null) {
        var seg = L.polyline([lastHeatPoint, latlng], {
          color: linkQualityColor(linkQuality === undefined ? null : linkQuality),
          weight: 4,
        }).addTo(map);
        heatSegments.push(seg);
      }
      lastHeatPoint = latlng;
    }

    if (droneMarker === null) {
      droneMarker = L.marker(latlng, { icon: buildIcon() }).addTo(map);
    } else {
      droneMarker.setLatLng(latlng);
    }

    if (heading !== null && heading !== undefined) {
      lastHeading = heading;
    }
    applyRotation();
    if (headingUp) {
      setMapRotation(lastHeading || 0);
    }

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

  function centerOnPoint(lat, lon) {
    map.setView([lat, lon], map.getZoom());
  }

  function clearPath() {
    pathLatLngs = [];
    pathLine.setLatLngs([]);
    heatSegments.forEach(function (seg) { map.removeLayer(seg); });
    heatSegments = [];
    lastHeatPoint = null;
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
      // e.latlng is only correct when the map isn't visually rotated - see
      // screenPointToLatLng() for why.
      var ll = mapRotationDeg ? screenPointToLatLng(e.originalEvent.clientX, e.originalEvent.clientY) : e.latlng;
      routeBridge.waypoint_clicked(ll.lat, ll.lng);
    }
  });

  // -------------------------------------------------- right-click point menu
  //
  // Independent of routeMode/Wegpunkt-Modus above (right-click never
  // conflicts with panning), so a waypoint/start/end point can always be
  // dropped without first switching modes. Feeds into the same RouteManager
  // list as every other waypoint source, via routeBridge.waypoint_clicked_typed.

  var contextMenuEl = document.getElementById('route-context-menu');
  var contextMenuLatLng = null;

  function hideContextMenu() {
    contextMenuEl.style.display = 'none';
    contextMenuLatLng = null;
  }

  map.on('contextmenu', function (e) {
    L.DomEvent.preventDefault(e);
    var oe = e.originalEvent;
    contextMenuLatLng = mapRotationDeg ? screenPointToLatLng(oe.clientX, oe.clientY) : e.latlng;
    // Placed from raw client coordinates rather than map.latLngToContainerPoint()
    // (which is unrotated map-space) - #map and this menu are body siblings
    // with no positioned ancestor between them, so client coordinates already
    // match the menu's own absolute-positioning frame, rotated or not.
    contextMenuEl.style.left = oe.clientX + 'px';
    contextMenuEl.style.top = oe.clientY + 'px';
    contextMenuEl.style.display = 'block';
  });

  map.on('click movestart zoomstart', hideContextMenu);

  function contextMenuPick(kind) {
    if (contextMenuLatLng && routeBridge) {
      routeBridge.waypoint_clicked_typed(contextMenuLatLng.lat, contextMenuLatLng.lng, kind);
    }
    hideContextMenu();
  }

  function contextMenuSetHome() {
    if (contextMenuLatLng && routeBridge) {
      routeBridge.pick_home_position(contextMenuLatLng.lat, contextMenuLatLng.lng);
    }
    hideContextMenu();
  }

  function contextMenuViewAction(action) {
    if (routeBridge) { routeBridge.view_action(action); }
    hideContextMenu();
  }

  // ---------------------------------------------------------- coordinate readout

  var coordOverlayEl = document.getElementById('coord-overlay');
  var coordOverlayEnabled = false;

  function setCoordOverlayVisible(enabled) {
    coordOverlayEnabled = enabled;
    if (!enabled) { coordOverlayEl.style.display = 'none'; }
  }

  map.on('mousemove', function (e) {
    if (!coordOverlayEnabled) return;
    var oe = e.originalEvent;
    var ll = mapRotationDeg ? screenPointToLatLng(oe.clientX, oe.clientY) : e.latlng;
    coordOverlayEl.textContent = ll.lat.toFixed(6) + ', ' + ll.lng.toFixed(6);
    coordOverlayEl.style.left = (oe.clientX + 14) + 'px';
    coordOverlayEl.style.top = (oe.clientY + 14) + 'px';
    coordOverlayEl.style.display = 'block';
  });

  map.on('mouseout', function () {
    if (coordOverlayEnabled) { coordOverlayEl.style.display = 'none'; }
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


def get_map_html(
    center_lat: float = 48.1372,
    center_lon: float = 11.5756,
    zoom: int = 16,
    label_waypoint: str = "Wegpunkt",
    label_start: str = "Startpunkt",
    label_end: str = "Endpunkt",
    label_set_home: str = "Als Home setzen",
    label_view: str = "Ansicht",
    label_view_lock: str = "Auto-Center",
    label_view_heading: str = "Drohnenrichtung/Norden oben",
    label_view_route_editor: str = "Wegpunkt-Editor anzeigen",
    label_view_coords: str = "Koordinaten anzeigen",
    label_view_heatmap: str = "RSSI/LQ Heatmap",
) -> str:
    return (
        MAP_HTML_TEMPLATE
        .replace("__CENTER_LAT__", str(center_lat))
        .replace("__CENTER_LON__", str(center_lon))
        .replace("__ZOOM__", str(zoom))
        .replace("__LABEL_WAYPOINT__", label_waypoint)
        .replace("__LABEL_START__", label_start)
        .replace("__LABEL_END__", label_end)
        .replace("__LABEL_SET_HOME__", label_set_home)
        .replace("__LABEL_VIEW__", label_view)
        .replace("__LABEL_VIEW_LOCK__", label_view_lock)
        .replace("__LABEL_VIEW_HEADING__", label_view_heading)
        .replace("__LABEL_VIEW_ROUTE_EDITOR__", label_view_route_editor)
        .replace("__LABEL_VIEW_COORDS__", label_view_coords)
        .replace("__LABEL_VIEW_HEATMAP__", label_view_heatmap)
        .replace("__LEAFLET_CSS__", LEAFLET_CSS)
        .replace("__LEAFLET_JS__", LEAFLET_JS)
    )
