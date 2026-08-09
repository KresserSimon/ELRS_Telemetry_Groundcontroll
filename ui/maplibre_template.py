"""Experimental, parallel vector-tile map page (MapLibre GL JS + PMTiles),
loaded instead of ui/map_template.py's Leaflet/raster page when the
"MapLibre (Vektor, experimentell)" renderer is selected - see
ui/map_widget.py for how the choice is made. Drone tracking, native
map-bearing rotation, and route/waypoint editing (Stages 1-3 of the
migration plan) are implemented; NFZ zones and the RSSI/LQ heatmap track
(Stage 4) are still no-op stubs - see the bottom of the JS below.

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
  html, body, #map { height: 100%; margin: 0; padding: 0; background: #1b1f24; cursor: default; }
  #map.route-mode { cursor: crosshair; }
  .coord-overlay {
    position: absolute; display: none; z-index: 999; pointer-events: none;
    background: rgba(18,22,28,0.88); color: #e8e8e8; font-size: 11px; font-family: monospace;
    padding: 3px 7px; border-radius: 5px; border: 1px solid #0d1117; white-space: nowrap;
  }
  .drone-icon-el, .home-icon-el { pointer-events: none; }
  .route-wp-dot {
    width: 20px; height: 20px; border-radius: 50%;
    background: #2ecc71; color: #ffffff; font-size: 11px; font-weight: 600;
    display: flex; align-items: center; justify-content: center;
    border: 1.5px solid #ffffff; box-shadow: 0 0 2px rgba(0,0,0,0.6);
    cursor: pointer;
  }
  .route-wp-dot-selected {
    background: #3ba7ff !important; box-shadow: 0 0 0 3px rgba(59,167,255,0.45);
  }
  .route-seg-label {
    background: rgba(20,24,30,0.85); color: #ffffff; font-size: 10px; font-weight: 600;
    padding: 1px 5px; border-radius: 6px; white-space: nowrap; text-align: center;
    border: 1px solid #2ecc71; pointer-events: none;
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
</div>
<div id="waypoint-context-menu" class="route-context-menu">
  <button onclick="wpContextMenuEdit()">__LABEL_WP_EDIT__</button>
  <button onclick="wpContextMenuDelete()">__LABEL_WP_DELETE__</button>
</div>
<script>
  var map = null;
  var pmtilesBridge = null;
  var routeBridge = null;
  var mapReady = false;

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
    map.on('load', function () { setupDroneLayers(); });
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
    routeBridge = channel.objects.routeBridge;
    initMapWhenReady();
  });

  // --- Native map-bearing rotation, the whole reason this parallel
  // renderer is being explored - no CSS transforms, no oversized/
  // re-centered container, no counter-rotation registry (compare
  // ui/map_template.py's setMapRotation/fitMapContainer/
  // applyCounterRotation*, all made unnecessary here). Verified
  // empirically (not assumed from docs) that map.setBearing(deg) puts
  // compass direction `deg` at the top of the screen - e.g. bearing=90
  // puts due east at the top - so heading-up mode is simply
  // map.setBearing(heading), no sign flip needed (unlike the CSS
  // rotate() case in map_template.py, which needed rotate(-heading)). ---
  function setBearingDeg(deg) {
    if (map) { map.setBearing(deg); }
  }

  // ----------------------------------------------------- vehicle markers

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

  var homeIconSvg = '<svg viewBox="0 0 24 24" width="26" height="26" style="filter: drop-shadow(0 0 2px rgba(0,0,0,0.7));">'
    + '<path d="M12 2 L22 11 L19 11 L19 22 L14 22 L14 15 L10 15 L10 22 L5 22 L5 11 L2 11 Z" '
    + 'fill="#3ba7ff" stroke="#ffffff" stroke-width="1.2" stroke-linejoin="round"/>'
    + '</svg>';

  var droneEl = null;
  var droneMarker = null;
  var homeMarker = null;
  var lastHeading = null;
  var headingUp = false;

  function buildDroneEl() {
    var el = document.createElement('div');
    el.className = 'drone-icon-el';
    el.style.width = '22px';
    el.style.height = '22px';
    el.innerHTML = vehicleIcons[vehicleType] || vehicleIcons.quad;
    return el;
  }

  // Unlike Leaflet, MapLibre markers stay screen-upright by default
  // regardless of map bearing - there's no implicit container rotation to
  // "cancel out" like map_template.py's applyRotation() relies on, so the
  // icon's own rotation has to explicitly account for the map's current
  // bearing: (heading - bearing) shows the true heading on an unrotated
  // (north-up) map, and collapses to 0 (icon points straight up, its
  // design-default orientation) once the map's own bearing has already
  // been turned to match the heading, i.e. heading-up mode.
  function applyRotation() {
    if (!droneEl || lastHeading === null || !map) return;
    var svg = droneEl.querySelector('svg');
    if (svg) { svg.style.transform = 'rotate(' + (lastHeading - map.getBearing()) + 'deg)'; }
  }

  function setVehicleType(type) {
    if (!vehicleIcons.hasOwnProperty(type)) return;
    vehicleType = type;
    if (droneEl) {
      droneEl.innerHTML = vehicleIcons[vehicleType];
      applyRotation();
    }
  }

  function setHeadingMode(enabled) {
    headingUp = enabled;
    if (map) { map.setBearing(enabled ? (lastHeading || 0) : 0); }
    applyRotation();
  }

  // ------------------------------------------------------------ path trail

  var pathLatLngs = [];  // [[lon, lat], ...] - GeoJSON coordinate order
  var lastPathPoint = null;  // [lat, lon]
  var pathPointThresholdM = 1.5;
  var MAX_PATH_POINTS = 2000;
  var dronelayersReady = false;

  function haversineDistanceM(lat1, lon1, lat2, lon2) {
    var R = 6371000, toRad = Math.PI / 180;
    var dLat = (lat2 - lat1) * toRad, dLon = (lon2 - lon1) * toRad;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
      + Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function setPathPointThreshold(meters) {
    pathPointThresholdM = meters;
  }

  function updatePathSource() {
    var source = map.getSource('path');
    if (source) {
      source.setData({ type: 'Feature', geometry: { type: 'LineString', coordinates: pathLatLngs } });
    }
  }

  function setupDroneLayers() {
    mapReady = true;
    map.addSource('path', { type: 'geojson', data: { type: 'Feature', geometry: { type: 'LineString', coordinates: pathLatLngs } } });
    map.addLayer({ id: 'path-line', type: 'line', source: 'path', paint: { 'line-color': '#ff8000', 'line-width': 3 } });
    initCoordOverlayEvents();
    initRouteEvents();
    dronelayersReady = true;
  }

  function clearPath() {
    pathLatLngs = [];
    lastPathPoint = null;
    if (mapReady) { updatePathSource(); }
    if (homeMarker) { homeMarker.remove(); homeMarker = null; }
    hasCentered = false;
  }

  // --------------------------------------------------------- drone updates

  var autoCenter = true;
  var hasCentered = false;

  function updateDrone(lat, lon, heading, linkQuality) {
    if (!dronelayersReady) { return; }  // self-heals on the next throttled update from Python

    var latlng = [lat, lon];
    if (lastPathPoint === null || haversineDistanceM(lastPathPoint[0], lastPathPoint[1], lat, lon) >= pathPointThresholdM) {
      pathLatLngs.push([lon, lat]);
      if (pathLatLngs.length > MAX_PATH_POINTS) {
        pathLatLngs = pathLatLngs.filter(function (_, i) { return i % 2 === 0; });
      }
      updatePathSource();
      lastPathPoint = latlng;
    }

    if (droneMarker === null) {
      droneEl = buildDroneEl();
      droneMarker = new maplibregl.Marker({ element: droneEl, anchor: 'center' }).setLngLat([lon, lat]).addTo(map);
    } else {
      droneMarker.setLngLat([lon, lat]);
    }

    if (heading !== null && heading !== undefined) { lastHeading = heading; }
    if (headingUp) { map.setBearing(lastHeading || 0); }
    applyRotation();

    if (!hasCentered) {
      var homeEl = document.createElement('div');
      homeEl.className = 'home-icon-el';
      homeEl.style.width = '26px';
      homeEl.style.height = '26px';
      homeEl.innerHTML = homeIconSvg;
      homeMarker = new maplibregl.Marker({ element: homeEl, anchor: 'bottom' }).setLngLat([lon, lat]).addTo(map);
      map.jumpTo({ center: [lon, lat], zoom: __ZOOM__ });
      hasCentered = true;
    } else if (autoCenter) {
      map.easeTo({ center: [lon, lat], duration: 300 });
    }
  }

  function setAutoCenter(enabled) {
    autoCenter = enabled;
    if (enabled && droneMarker) {
      map.easeTo({ center: droneMarker.getLngLat() });
    }
  }

  function jumpToDrone() {
    if (droneMarker) { map.easeTo({ center: droneMarker.getLngLat() }); }
  }

  function centerOnPoint(lat, lon) {
    if (map) { map.jumpTo({ center: [lon, lat] }); }
  }

  // ---------------------------------------------------------- coordinate readout

  var coordOverlayEl = document.getElementById('coord-overlay');
  var coordOverlayEnabled = false;

  function setCoordOverlayVisible(enabled) {
    coordOverlayEnabled = enabled;
    if (!enabled) { coordOverlayEl.style.display = 'none'; }
  }

  function initCoordOverlayEvents() {
    // e.lngLat is already correctly projected for the map's current
    // bearing - no manual unrotation math needed (unlike
    // map_template.py's screenPointToLatLng(), required there because
    // Leaflet's own hit-testing doesn't know about the CSS rotation hack).
    map.on('mousemove', function (e) {
      if (!coordOverlayEnabled) return;
      var oe = e.originalEvent;
      coordOverlayEl.textContent = e.lngLat.lat.toFixed(6) + ', ' + e.lngLat.lng.toFixed(6);
      coordOverlayEl.style.left = (oe.clientX + 14) + 'px';
      coordOverlayEl.style.top = (oe.clientY + 14) + 'px';
      coordOverlayEl.style.display = 'block';
    });
    map.on('mouseout', function () {
      if (coordOverlayEnabled) { coordOverlayEl.style.display = 'none'; }
    });
  }

  // ---------------------------------------------------------- planned route

  var routeMarkers = [];
  var routeSegLabels = [];
  var routeMode = false;
  var selectedWaypointIndex = -1;

  function formatDistance(m) {
    return m >= 1000 ? (m / 1000).toFixed(2) + ' km' : Math.round(m) + ' m';
  }

  function updateRouteLineSource(latlngs) {
    if (!mapReady) return;
    var source = map.getSource('route');
    if (source) {
      source.setData({ type: 'Feature', geometry: { type: 'LineString', coordinates: latlngs } });
    }
  }

  function selectWaypoint(idx) {
    selectedWaypointIndex = idx;
    // The marker's element *is* the .route-wp-dot div (no extra wrapper
    // like Leaflet's L.divIcon creates around its `html` content), so the
    // class toggles directly on it rather than on a queried-for descendant.
    routeMarkers.forEach(function (m, i) {
      var dot = m.getElement();
      if (dot) { dot.classList.toggle('route-wp-dot-selected', i === idx); }
    });
  }

  function setRoute(wps) {
    routeMarkers.forEach(function (m) { m.remove(); });
    routeMarkers = [];
    routeSegLabels.forEach(function (m) { m.remove(); });
    routeSegLabels = [];

    var latlngs = [];
    wps.forEach(function (wp, idx) {
      latlngs.push([wp.lon, wp.lat]);

      var dotWrap = document.createElement('div');
      dotWrap.innerHTML = '<div class="route-wp-dot' + (idx === selectedWaypointIndex ? ' route-wp-dot-selected' : '') + '">' + (idx + 1) + '</div>';
      var dotEl = dotWrap.firstElementChild;
      var marker = new maplibregl.Marker({ element: dotEl, anchor: 'center', draggable: true }).setLngLat([wp.lon, wp.lat]).addTo(map);

      dotEl.addEventListener('click', function (e) {
        e.stopPropagation();
        selectWaypoint(idx);
        if (routeBridge) { routeBridge.waypoint_marker_clicked(idx); }
      });
      dotEl.addEventListener('contextmenu', function (e) {
        e.preventDefault();
        e.stopPropagation();
        wpContextIndex = idx;
        wpContextMenuEl.style.left = e.clientX + 'px';
        wpContextMenuEl.style.top = e.clientY + 'px';
        wpContextMenuEl.style.display = 'block';
      });
      marker.on('dragend', function () {
        var ll = marker.getLngLat();
        if (routeBridge) { routeBridge.waypoint_marker_moved(idx, ll.lat, ll.lng); }
      });
      routeMarkers.push(marker);

      if (idx > 0 && wp.seg !== null && wp.seg !== undefined) {
        var prev = wps[idx - 1];
        var midLat = (prev.lat + wp.lat) / 2;
        var midLon = (prev.lon + wp.lon) / 2;
        var segWrap = document.createElement('div');
        segWrap.innerHTML = '<div class="route-seg-label">' + formatDistance(wp.seg) + '</div>';
        var segLabel = new maplibregl.Marker({ element: segWrap.firstElementChild, anchor: 'center' }).setLngLat([midLon, midLat]).addTo(map);
        routeSegLabels.push(segLabel);
      }
    });
    updateRouteLineSource(latlngs);
  }

  function setRouteMode(enabled) {
    routeMode = enabled;
    var el = document.getElementById('map');
    if (enabled) { el.classList.add('route-mode'); } else { el.classList.remove('route-mode'); }
  }

  // -------------------------------------------------- right-click point menu
  //
  // Independent of routeMode (right-click never conflicts with panning), so
  // a waypoint/start/end point can always be dropped without first
  // switching modes - matches map_template.py's behavior.

  var contextMenuEl = document.getElementById('route-context-menu');
  var contextMenuLatLng = null;
  var wpContextMenuEl = document.getElementById('waypoint-context-menu');
  var wpContextIndex = -1;

  function hideContextMenu() {
    contextMenuEl.style.display = 'none';
    contextMenuLatLng = null;
  }

  function hideWpContextMenu() {
    wpContextMenuEl.style.display = 'none';
    wpContextIndex = -1;
  }

  function wpContextMenuEdit() {
    if (wpContextIndex >= 0 && routeBridge) { routeBridge.waypoint_marker_edit(wpContextIndex); }
    hideWpContextMenu();
  }

  function wpContextMenuDelete() {
    if (wpContextIndex >= 0 && routeBridge) { routeBridge.waypoint_marker_delete(wpContextIndex); }
    hideWpContextMenu();
  }

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

  function initRouteEvents() {
    map.addSource('route', { type: 'geojson', data: { type: 'Feature', geometry: { type: 'LineString', coordinates: [] } } });
    map.addLayer({
      id: 'route-line', type: 'line', source: 'route',
      paint: { 'line-color': '#2ecc71', 'line-width': 3, 'line-dasharray': [2, 2] }
    });

    map.on('click', function (e) {
      if (routeMode && routeBridge) {
        routeBridge.waypoint_clicked(e.lngLat.lat, e.lngLat.lng);
      }
    });

    map.on('contextmenu', function (e) {
      e.preventDefault();
      var oe = e.originalEvent;
      contextMenuLatLng = e.lngLat;
      contextMenuEl.style.left = oe.clientX + 'px';
      contextMenuEl.style.top = oe.clientY + 'px';
      contextMenuEl.style.display = 'block';
    });

    ['click', 'movestart', 'zoomstart'].forEach(function (evt) {
      map.on(evt, hideContextMenu);
      map.on(evt, hideWpContextMenu);
    });
  }

  // --------------------- not yet ported (Stage 4 of the migration plan) -
  // NFZ zones and the RSSI/LQ heatmap track are not built yet, but both are
  // already called unconditionally from ui/map_widget.py/main_window.py
  // regardless of active renderer, so they need to exist as harmless
  // no-ops for now rather than throwing ReferenceError.
  function setBaseLayer(id) {}
  function setHeatmapEnabled(enabled) {}
  function setNoFlyZones(zones) {}
  function setNoFlyZonesVisible(enabled) {}
</script>
</body>
</html>
"""


def get_maplibre_html(
    center_lat: float = 48.1372,
    center_lon: float = 11.5756,
    zoom: int = 12,
    label_waypoint: str = "Wegpunkt",
    label_start: str = "Start",
    label_end: str = "Ende",
    label_set_home: str = "Als Home setzen",
    label_wp_edit: str = "Bearbeiten",
    label_wp_delete: str = "Löschen",
) -> str:
    return (
        MAPLIBRE_HTML_TEMPLATE
        .replace("__MAPLIBRE_CSS__", MAPLIBRE_CSS)
        .replace("__PMTILES_JS__", PMTILES_JS)
        .replace("__MAPLIBRE_JS__", MAPLIBRE_JS)
        .replace("__BASEMAPS_JS__", BASEMAPS_JS)
        .replace("__CENTER_LAT__", str(center_lat))
        .replace("__CENTER_LON__", str(center_lon))
        .replace("__ZOOM__", str(zoom))
        .replace("__LABEL_WAYPOINT__", label_waypoint)
        .replace("__LABEL_START__", label_start)
        .replace("__LABEL_END__", label_end)
        .replace("__LABEL_SET_HOME__", label_set_home)
        .replace("__LABEL_WP_EDIT__", label_wp_edit)
        .replace("__LABEL_WP_DELETE__", label_wp_delete)
    )
