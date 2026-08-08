# ELRS Ground Station

Ein schlanker Ground-Control-Bildschirm für Modelle mit ExpressLRS (ELRS):
zeigt live, wo das Modell gerade fliegt und wie es ihm geht, ohne die
Komplexität von Mission Planner oder QGroundControl. Gedacht für alle, die
im Feld nur "wo ist mein Flieger und wie steht's um Akku/Funkverbindung"
auf einen Blick sehen wollen.

Ausführliches Benutzerhandbuch (PDF, Deutsch):
[docs/ELRS_Ground_Station_Benutzerhandbuch.pdf](docs/ELRS_Ground_Station_Benutzerhandbuch.pdf)

## Was die App kann

- **Live-Position auf einer OpenStreetMap- oder Esri-Satellitenkarte**
  (umschaltbar), mit nachgezogenem Flugpfad, einem Häuschen-Symbol am
  Startpunkt (Home-Position) und wählbarem Fahrzeugsymbol (Quadrocopter,
  Wing, Flugzeug).
- **Google-Maps-artige Kartensteuerung**: ein fixer Button sperrt/löst die
  automatische Kameraverfolgung der Drohne, ein zweiter schaltet zwischen
  Norden-oben und Drohnenrichtung-oben um (die ganze Karte dreht sich dabei
  mit dem aktuellen Kurs).
- **Frei konfigurierbares Dashboard**: GPS, Funkverbindung, Akku (inkl.
  Strom/mAh und Min-Zellspannung), zusätzliche Sensoren (Vario, Baro-Höhe,
  RPM, Temperatur) und Long-Range-Werte (Geschwindigkeit, Entfernung/Peilung
  zur Home-Position, Flugzeit) – jedes einzelne Feld lässt sich ein-/aus-
  blenden und wird als eigener Standard-Layout gespeichert.
- **Frei verschieb- und größenveränderbare Karten-Overlays** (künstlicher
  Horizont, Wegpunkt-Editor, Tracking-Aufzeichnung) – wie kleine Fenster
  direkt mit der Maus ziehen und über eine Ecken-Anfassmarke skalieren.
- **Wegpunkt-Editor als Live-Overlay** auf der Karte: Liste aller
  Wegpunkte mit Höhe, Name und INAV-Missionsparametern (Aktion,
  Geschwindigkeit, P1–P3), Änderungen wirken sofort. Export/Import als
  INAV-`.mission`-JSON sowie eine Geländeprüfung (färbt Wegpunkte rot/gelb/
  grün je nach Bodenfreiheit) sind direkt im Overlay verfügbar.
- **Rechtsklick auf die Karte** öffnet ein Menü zum Setzen von Wegpunkt/
  Startpunkt/Endpunkt, zum direkten Teachen der Home-Position an der
  angeklickten Stelle sowie ein "Ansicht"-Untermenü mit den wichtigsten
  Kartenoptionen (Auto-Center, Kartenausrichtung, Wegpunkt-Editor,
  Koordinatenanzeige).
- **No-Fly-Zones**: Sperrzonen aus GeoJSON oder CSV laden und als rote
  Kreise/Polygone auf der Karte anzeigen (ein-/ausblendbar).
- **Konfigurierbare Home-Position**: legt fest, wo die Karte beim Start
  zentriert ist, unabhängig von der live über den ersten GPS-Fix ermittelten
  Home-Position für die Entfernungs-/Peilungsanzeige – wahlweise über einen
  Dialog mit Lat/Lon-Eingabe (inkl. "aktuelle Position übernehmen") oder per
  Rechtsklick direkt auf der Karte gesetzt.
- **Optionale Koordinatenanzeige**: zeigt Lat/Lon unter dem Mauszeiger beim
  Bewegen über die Karte, ein-/ausblendbar.
- **Plan-Modus**: Routen planen und Wegpunkte setzen, ohne dass eine echte
  oder simulierte Telemetrieverbindung läuft – auch direkt beim Start über
  das Verbindungs-Popup wählbar. Löst dabei automatisch die
  Auto-Center-Sperre, damit man frei über die Karte navigieren kann.
- **Künstlicher Horizont** als frei verschiebbares und skalierbares Overlay
  auf der Karte (Roll/Pitch aus MAVLink- oder CRSF-Attitude-Daten).
- **Akkuwarnung per Sprachansage**, sobald der Akku niedrig oder kritisch
  wird – mit separat einstellbaren Schwellwerten für LiPo und Li-Ion, da
  sich deren sichere Entladeschlussspannung deutlich unterscheidet.
- **Route/Wegpunkte auf der Karte planen**: per Klick oder Rechtsklick
  zeichnen, oder aus GPX, iNav `.mission` (klassisches MW-XML- wie auch das
  moderne JSON-Format), generischem XML oder CSV importieren – als eigene,
  von der geflogenen Spur unabhängige Referenzlinie; Export als GPX, CSV
  oder INAV-`.mission`-JSON.
- **Getrennt steuerbare Flugpfad-Aufzeichnung** (Start/Pause/Export-Overlay
  auf der Karte, mit Formatabfrage GPX/KML/CSV) und **Fluglog** (kontinuier-
  liche CSV-Aufzeichnung aller Telemetriedaten mit frei wählbaren Spalten
  und Intervall) – zwei unabhängige Aufzeichnungen für unterschiedliche
  Zwecke.
- **WiFi (UDP) oder direktes USB-Kabel** als Verbindungsweg zur Telemetrie,
  zur Laufzeit umschaltbar – ebenso wie das Protokoll (MAVLink oder CRSF/
  TBS Crossfire) und die Sprache der Oberfläche (Deutsch/Englisch).
- **Demo-Modus** mit einer simulierten Flugbahn, um die App komplett ohne
  Modell oder ELRS-Hardware auszuprobieren.

Funktioniert mit Flugsteuerungen (ArduPilot/Betaflight/iNav), die ihre
Telemetrie per MAVLink ausgeben, ebenso wie mit dem rohen CRSF/TBS-Crossfire-
Telemetriestrom direkt vom ELRS-Empfänger (ExpressLRS nutzt bewusst dasselbe
CRSF-Frameformat wie TBS Crossfire).

## Installation

```bash
cd elrs_ground_station
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

`pyttsx3` nutzt unter Windows die eingebaute SAPI5-Sprachausgabe, es sind
also keine zusätzlichen Systempakete nötig.

## Ausführung

Demo-Modus (keine Hardware nötig, simuliert einen Loiter-Kreisflug inkl.
Akku-Entladung, um alle Funktionen inkl. TTS-Warnung zu testen):

```bash
python main.py --demo
```

Mit echter Telemetrie über MAVLink (Standardfall, siehe unten):

```bash
python main.py --protocol mavlink --host 0.0.0.0 --port 14550
```

Mit rohem CRSF-Telemetriestrom über UDP:

```bash
python main.py --protocol crsf --host 0.0.0.0 --port 14551
```

Mit direkter USB/seriell-Verbindung (FC oder ELRS TX-Modul per USB-Kabel
angeschlossen) statt WiFi/UDP – verfügbare Ports zuerst auflisten:

```bash
python main.py --list-ports
python main.py --connection usb --protocol mavlink --serial-port COM5
python main.py --connection usb --protocol crsf --serial-port COM5 --baud 420000
```

Weitere Optionen: `python main.py --help` (u. a. `--cells`,
`--low-cell-voltage`, `--critical-cell-voltage` für die Akkuwarnung,
`--demo-center lat,lon` für den Startpunkt der Simulation und
`--lang de|en` für die Startsprache der Oberfläche).

Beim Start (außer mit `--demo`) öffnet sich zunächst ein Popup zur Auswahl
von Verbindung (WiFi/UDP oder USB) und Protokoll (MAVLink oder CRSF) —
Abbrechen übernimmt einfach die per Kommandozeile übergebenen/Standard-
Einstellungen, ein zusätzlicher Button startet direkt den Demo-Modus.

Im laufenden Programm:
- **Datei → Flugpfad als GPX/KML exportieren** speichert alle bisher
  aufgezeichneten GPS-Punkte des aktuellen Fluges (alternativ das
  Tracking-Overlay auf der Karte, siehe unten, mit zusätzlicher
  CSV-Option).
- **Route → Wegpunkt-Modus** schaltet den Klick-zum-Hinzufügen-Modus auf
  der Karte ein; ein Klick auf einen bestehenden Wegpunkt entfernt ihn
  wieder. **Route → Letzten Wegpunkt entfernen / Route löschen** für die
  restliche Bearbeitung. Ein **Rechtsklick** auf die Karte öffnet jederzeit
  (unabhängig vom Wegpunkt-Modus) ein Menü mit Wegpunkt/Startpunkt/
  Endpunkt, "Als Home setzen" sowie einem "Ansicht"-Untermenü.
- **Route → Wegpunkt-Editor anzeigen** blendet das Editor-Overlay auf der
  Karte ein/aus (auch unter Einstellungen → Ansicht verfügbar) – zeigt
  Wegpunktanzahl/Gesamtdistanz über einer bearbeitbaren Tabelle mit Höhe,
  Name, INAV-Aktion, Geschwindigkeit und P1–P3; Änderungen wirken sofort,
  kein Bestätigen nötig. Buttons darin exportieren/importieren die Route
  als INAV-`.mission`-JSON und prüfen die Route gegen Geländehöhen (rot =
  Kollision, gelb = knapp, grün = frei).
- **Route → Route importieren/exportieren...** lädt bzw. speichert eine
  Wegpunktliste als GPX, CSV, iNav `.mission` (klassisches MW-XML- oder
  modernes JSON-Format, wird beim Import automatisch erkannt) oder
  generisches XML.
- **Karte → Kartentyp** wechselt zwischen OpenStreetMap und Esri-
  Satellitenbild. **Karte → Sperrzonen laden...** importiert No-Fly-Zones
  aus GeoJSON/CSV, **Sperrzonen anzeigen** blendet sie ein/aus.
- **Tracking-Overlay** (auf der Karte) startet/pausiert die
  Flugpfad-Aufzeichnung eigenständig von der Live-Anzeige – die Karte
  zeichnet den Pfad immer nach, aber nur bei laufender Aufzeichnung landen
  Punkte im Export. **Exportieren...** fragt das gewünschte Format
  (GPX/KML/CSV) ab.
- **Fluglog → Log-Einstellungen...** wählt, welche Telemetriefelder
  aufgezeichnet werden und in welchem Intervall (0,1–60 s). **Fluglog →
  Logging aktiv** fragt einen Zielpfad ab und schreibt ab dann laufend
  eine CSV-Zeile pro Intervall, bis der Haken wieder entfernt wird.
- **Einstellungen → Verbindung...** wechselt zur Laufzeit zwischen
  WiFi/UDP und USB/Seriell sowie zwischen MAVLink und CRSF, inkl.
  Host/Port bzw. seriellem Port + Baudrate — ohne die App neu zu starten.
  Beendet dabei automatisch einen laufenden Demo-Modus.
- **Einstellungen → Akkuwarnung...** wählt LiPo oder Li-Ion (füllt dabei
  passende Standard-Schwellwerte vor) sowie Zellenzahl und die genauen
  Warn-/Kritisch-Spannungen pro Zelle.
- **Einstellungen → Home-Position...** legt fest, wo die Karte beim
  nächsten Start zentriert ist (Lat/Lon-Eingabe oder "aktuelle Position
  übernehmen"); alternativ per Rechtsklick auf der Karte → "Als Home
  setzen" direkt an der gewünschten Stelle teachen.
- **Einstellungen → Dashboard anpassen...** blendet einzelne Dashboard-
  Felder ein/aus (nicht nur ganze Gruppen) – die Auswahl wird als
  persönlicher Standard unter `~/.elrs_ground_station/dashboard_fields.json`
  gespeichert und beim nächsten Start automatisch wieder geladen.
- **Einstellungen → Ansicht → Auto-Center** schaltet das automatische
  Nachführen der Karte auf die aktuelle Position ein/aus (auch über den
  Lock-Button direkt auf der Karte erreichbar, Google-Maps-artig).
- **Einstellungen → Ansicht → Aktuelle Position anspringen** (`Strg+Pos1`)
  zentriert die Karte sofort auf die letzte bekannte Position, unabhängig
  von Auto-Center.
- **Einstellungen → Ansicht → Fahrzeugtyp** wählt das Kartensymbol:
  Quadrocopter, Wing (Nurflügler) oder Flugzeug.
- **Einstellungen → Ansicht → Künstlicher Horizont anzeigen** blendet das
  Horizont-Overlay ein/aus; es lässt sich außerdem direkt mit der Maus auf
  der Karte verschieben (Ziehen) und über eine Anfassmarke in der Ecke
  größer/kleiner ziehen, und **Position**/**Größe** bieten zusätzlich feste
  Ecken- bzw. Zoomstufen-Presets.
- **Einstellungen → Ansicht → Wegpunkt-Editor anzeigen** und
  **Koordinaten unter Mauszeiger anzeigen** blenden die jeweiligen
  Karten-Overlays ein/aus (siehe oben).
- Ein zweiter fixer Button auf der Karte schaltet zwischen Norden-oben und
  Drohnenrichtung-oben um; im letzteren Modus dreht sich die gesamte Karte
  mit dem aktuellen Kurs.
- **Einstellungen → Sprache → Deutsch/English** wechselt die komplette
  Oberfläche (Menüs, Dashboard, Dialoge, Sprachwarnungen) sofort ohne
  Neustart.
- **Simulation → Demo-Modus / Plan-Modus** schaltet zur Laufzeit zwischen
  echter Telemetrie, simulierten Daten und dem telemetriefreien Plan-Modus
  um; beide sind auch direkt im Verbindungs-Popup beim Start wählbar.

## Einrichtung von ELRS-Sender/-Empfänger für WiFi-Telemetrie

ELRS-Hardware selbst spricht kein natives "Telemetrie-über-WiFi" – das
eingebaute WiFi eines ELRS-Moduls (TX-Modul oder RX) dient primär dem
Flashen/Konfigurieren (Access Point `ExpressLRS TX`/`ExpressLRS RX`,
Standardpasswort `expresslrs`, erreichbar unter `http://10.0.0.1` bzw.
per mDNS). Um Telemetrie tatsächlich per UDP an diese App zu bekommen,
braucht es eine Bridge – zwei gängige Wege:

### Weg 1: MAVLink über WiFi (empfohlen, `--protocol mavlink`)

Voraussetzung ist eine Flugsteuerung (ArduPilot/iNav/Betaflight mit MAVLink),
die per CRSF-Telemetrie mit dem ELRS-Empfänger verbunden ist. Die
Flugsteuerung selbst gibt MAVLink über ihren Telemetrie-UART aus; dieser
serielle Strom muss per WiFi-Bridge (z. B. ein ESP32/ESP8266 mit
`MAVESP8266`-Firmware oder ein Telemetrieradio mit WiFi-Modul) auf UDP-Port
`14550` gebracht werden. Sobald PC und Bridge im selben WLAN sind, hört die
App per `udpin` (Standard) auf eingehende Pakete – kein manuelles Verbinden
nötig. Falls die Bridge stattdessen aktiv eine Verbindung zum PC aufbauen
muss, `--udp-mode connect --host <IP-der-Bridge>` verwenden.

### Weg 2: Rohes CRSF/TBS-Crossfire über WiFi (`--protocol crsf`)

Manche ELRS-"Backpack"-Bridges (ESP32-basiert) leiten den rohen CRSF-
Bytestrom der Empfänger-Telemetrie direkt per UDP weiter, ohne Umweg über
MAVLink. CRSF ist ursprünglich TBS' (Team BlackSheep) Crossfire-Protokoll;
ExpressLRS verwendet bewusst dasselbe Frameformat, dieser Modus funktioniert
also gleichermaßen mit echter TBS-Crossfire-Hardware. Den in der
Backpack-Konfiguration eingestellten Ziel-Port mit `--port` angeben
(Beispiel-Default hier: `14551` – je nach Bridge-Firmware anpassen). Dieser
Modus deckt GPS (inkl. Geschwindigkeit), Akku (Spannung/Strom/Restkapazität/
verbrauchte mAh), Link-Statistiken (RSSI/LQ/SNR/TX-Power), Attitude
(Roll/Pitch) sowie – falls vom Sender/FC gesendet – Vario, Baro-Höhe, RPM,
Temperatur und Zellspannungen ab. Flight-Mode wird nur übertragen, wenn die
Bridge CRSF-Flight-Mode-Frames weiterleitet.

In beiden Fällen müssen PC (auf dem diese App läuft) und die Bridge/das
ELRS-Modul im selben Netzwerk sein – entweder beide im selben Heim-WLAN,
oder der PC verbindet sich direkt mit dem Access Point des Moduls.

### Weg 3: USB/seriell (`--connection usb`)

Alternative ohne WLAN: Flugsteuerung oder ELRS TX-Modul per USB-Kabel direkt
an den PC anschließen. Windows legt dafür einen COM-Port an (z. B. `COM5`);
mit `python main.py --list-ports` lassen sich alle erkannten Ports samt
Beschreibung auflisten. Danach:

- `--connection usb --protocol mavlink --serial-port COM5` – Standard-Baudrate
  57600 (per `--baud` überschreibbar), passend zum MAVLink-Telemetrieausgang
  der Flugsteuerung.
- `--connection usb --protocol crsf --serial-port COM5` – Standard-Baudrate
  420000 (Standard-Baudrate von CRSF-UARTs), für ein direkt angeschlossenes
  ELRS-Modul oder eine Empfänger-UART, die per USB-Seriell-Adapter am PC
  hängt.

Diese Verbindungsart ist ein Ersatz für Weg 1/2, kein Zusatz – `--connection`
wählt UDP (Standard) oder USB, unabhängig vom gewählten `--protocol`.

## Als .exe kompilieren (Windows)

```bash
cd elrs_ground_station
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt pyinstaller
pyinstaller --name ELRS_GroundStation --onedir main.py
```

Ergebnis liegt unter `dist\ELRS_GroundStation\ELRS_GroundStation.exe` – der
gesamte `dist\ELRS_GroundStation`-Ordner (Exe + `_internal`-Verzeichnis mit
Qt/WebEngine-Ressourcen, ca. 500 MB) muss zusammen weitergegeben werden,
nicht nur die .exe allein. `--onedir` (statt `--onefile`) wird empfohlen, da
QtWebEngine einen eigenen Hilfsprozess samt Ressourcendateien braucht, die in
einer Single-File-Exe beim Start erst in ein Temp-Verzeichnis entpackt werden
müssten – das funktioniert, ist aber langsamer beim Start und fehleranfälliger.

Die Exe behält die Konsole (kein `--windowed`), damit `--list-ports`,
`--demo` usw. weiterhin normal über die Kommandozeile nutzbar sind; beim
Doppelklick öffnet sich zusätzlich ein Konsolenfenster im Hintergrund.

## Architektur

```
elrs_ground_station/
  main.py                  CLI-Einstieg
  core/
    telemetry_state.py     gemeinsames Datenmodell
    route.py                Wegpunkt/Routen-Datenmodell (RouteManager), inkl. INAV-
                             Missionsfeldern (Aktion/Speed/P1-P3) und typisierten
                             Wegpunkten (Wegpunkt/Startpunkt/Endpunkt) aus dem
                             Rechtsklick-Menü
    geo.py                   Haversine-Distanz + Peilung (Long-Range-Anzeige)
    nfz.py                    No-Fly-Zone-Datenmodell (NoFlyZoneManager)
    terrain.py                 Geländehöhen-Abfrage (Open-Elevation API) + Kollisionscheck
    dashboard_config.py      Persistiert die gewählten Dashboard-Felder
    home_config.py            Persistiert die konfigurierte Home-/Startposition
    i18n.py                 DE/EN-Strings + Laufzeit-Sprachumschaltung
  telemetry/
    base_worker.py             gemeinsames QThread-Interface
    mavlink_worker.py          MAVLink-Empfänger (pymavlink), UDP oder USB/seriell
    crsf_parser.py             CRSF-Frame-Parser (GPS/Battery/LinkStats/Attitude/
                                Vario/Baro/RPM/Temp/Cells/FlightMode)
    crsf_transport_worker.py   gemeinsame Empfangsschleife fuer CRSF (UDP + USB)
    crsf_worker.py             CRSF-UDP-Empfänger
    crsf_serial_worker.py      CRSF-USB/seriell-Empfänger (pyserial)
    serial_ports.py            Hilfsfunktion fuer --list-ports
    demo_worker.py              Simulierte Telemetrie
  ui/
    main_window.py           Hauptfenster, verbindet Worker <-> UI, Menüs, Startpopup,
                              Plan-Modus, Rechtsklick-/Ansicht-Dispatch
    connection_dialog.py     Dialog zum Wechsel WiFi/USB + Protokoll (auch als
                              Startpopup, inkl. Demo-/Plan-Modus-Buttons)
    battery_settings_dialog.py  LiPo/Li-Ion-Chemie + Zellenzahl + Schwellwerte
    dashboard_settings_dialog.py  Dashboard-Felder ein-/ausblenden
    home_position_dialog.py   Home-/Startposition setzen (Lat/Lon oder aktuelle Position)
    flight_log_dialog.py     Fluglog-Feldauswahl + Intervall
    map_widget.py            QWebEngineView-Wrapper um die Leaflet-Karte + QWebChannel,
                              Overlay-Stacking/Positionierung
    map_template.py          Self-contained Leaflet/OSM+Satellit HTML+JS (Fahrzeugsymbole,
                              Home-Marker, Routen-/NFZ-Layer, Rechtsklick-Menü,
                              Kartenrotation für Drohnenrichtung-oben, Koordinatenanzeige)
    map_buttons.py            Fixe Google-Maps-artige Kartenbuttons (Auto-Center-Sperre,
                              Kartenausrichtung)
    route_bridge.py          QWebChannel-Bruecke fuer Wegpunkt-/Kontextmenü-/
                              Koordinaten-Events (JS -> Python)
    draggable_overlay.py      Basisklasse fuer verschieb-/groessenveraenderbare
                              Karten-Overlays (Ecken-Anfassmarke)
    horizon_widget.py        Kuenstlicher Horizont (QPainter, verschieb-/skalierbares Overlay)
    route_editor_overlay.py   Wegpunkt-Editor als Live-Overlay (Tabelle, INAV-Mission-
                              Export/Import, Geländeprüfung)
    track_overlay.py          Start/Pause/Export-Overlay fuer die Flugpfad-Aufzeichnung
    dashboard.py             Frei konfigurierbare Telemetrie-Leiste mit Status-Icons
    icons.py                  QPainter-gezeichnete Dashboard-Icons (keine Bilddateien)
  export/
    track_export.py         GPX/KML/CSV-Export des geflogenen Pfads
    route_export.py          GPX/CSV-Export der geplanten Route
    route_import.py          Routen-Import: GPX, iNav .mission (MW-XML + JSON,
                              automatisch erkannt), generisches XML, CSV
    inav_mission.py           INAV-.mission-JSON Export/Import/Validierung
    nfz_import.py             No-Fly-Zone-Import: GeoJSON, CSV
    flight_logger.py          Kontinuierliches CSV-Fluglog (QTimer-basiert)
  alerts/tts_alert.py        Akku-Sprachwarnung (pyttsx3, eigener Thread, i18n-Texte,
                              LiPo/Li-Ion-Schwellwerte)
```

Die komplette Netzwerk-/Parsing-Arbeit läuft in eigenen `QThread`s
(`MAVLinkWorker`, `CRSFWorker`, `CRSFSerialWorker`, `DemoWorker`), die alle dasselbe
Signal-Interface (`telemetry_received`, `connection_changed`,
`error_occurred`) implementieren – die GUI blockiert dadurch nie und weiß
nicht, woher die Daten kommen. Fehlerhafte/unvollständige Pakete werden pro
Nachricht abgefangen und übersprungen, ohne den Worker zu beenden.

---

# ELRS Ground Station (English)

A lightweight ground-control screen for ExpressLRS (ELRS) models: shows
live where the model is flying and how it's doing, without the complexity
of Mission Planner or QGroundControl. Built for anyone who just wants
"where's my aircraft and how's the battery/link" at a glance in the field.

## What the app does

- **Live position on an OpenStreetMap or Esri satellite map** (switchable),
  with a trailing flight path, a house icon marking the launch point (home
  position), and a selectable vehicle marker (quadcopter, wing, airplane).
- **Google-Maps-style map controls**: a fixed button locks/releases the
  camera following the drone, a second one switches between north-up and
  heading-up (the whole map rotates to match the current course).
- **A fully configurable dashboard**: GPS, radio link, battery (incl.
  current/mAh and minimum cell voltage), extra sensors (vario, baro
  altitude, RPM, temperature), and long-range readouts (speed,
  distance/bearing to home, flight timer) - every individual field can be
  shown or hidden and is saved as your personal default layout.
- **Freely draggable and resizable map overlays** (artificial horizon,
  waypoint editor, track recorder) - drag them around like little windows
  and resize from a corner grip, just like a window.
- **Waypoint editor as a live map overlay**: a table of every waypoint with
  altitude, name, and INAV mission parameters (action, speed, P1-P3) -
  edits apply immediately. Export/import as INAV `.mission` JSON and a
  terrain check (colors waypoints red/yellow/green by ground clearance) are
  built right into the overlay.
- **Right-click the map** to open a menu for dropping a waypoint/start
  point/end point, teaching the home position directly at the clicked
  spot, and a "View" submenu with the most-used map toggles (auto-center,
  map orientation, waypoint editor, coordinate readout).
- **No-fly zones**: load restricted areas from GeoJSON or CSV and show them
  as red circles/polygons on the map (toggleable).
- **Configurable home position**: sets where the map centers on startup,
  independent of the live home position derived from the first GPS fix
  (used for the distance/bearing-to-home readout) - set it via a dialog
  with lat/lon entry (including "use current position"), or right-click
  directly on the map.
- **Optional coordinate readout**: shows lat/lon under the mouse cursor
  while hovering the map, toggleable.
- **Plan mode**: plan routes and drop waypoints without any real or
  simulated telemetry connection running - also selectable straight from
  the startup connection popup. Automatically releases the auto-center
  lock so you can pan freely.
- **Artificial horizon** as a freely draggable and resizable overlay on the
  map (roll/pitch from MAVLink or CRSF attitude data).
- **Spoken battery warnings** once the battery gets low or critical - with
  separately configurable thresholds for LiPo and Li-Ion, since their safe
  discharge cutoff voltages differ significantly.
- **Plan a route/waypoints on the map**: draw by clicking or right-
  clicking, or import from GPX, iNav `.mission` (both the classic MW-XML
  and the modern JSON format), generic XML, or CSV - as its own reference
  line, independent of the actually-flown track; export as GPX, CSV, or
  INAV `.mission` JSON.
- **Independently controllable track recording** (start/pause/export
  overlay on the map, with a GPX/KML/CSV format prompt) and **flight log**
  (continuous CSV recording of all telemetry data with freely selectable
  columns and interval) - two separate recordings for different purposes.
- **WiFi (UDP) or a direct USB cable** as the telemetry connection, switchable
  at runtime - as is the protocol (MAVLink or CRSF/TBS Crossfire) and the
  UI language (German/English).
- **Demo mode** with a simulated flight path, to try the whole app out
  without a model or ELRS hardware.

Works with flight controllers (ArduPilot/Betaflight/iNav) that output
their telemetry via MAVLink, as well as with the raw CRSF/TBS Crossfire
telemetry stream straight from the ELRS receiver (ExpressLRS deliberately
reuses the same CRSF frame format as TBS Crossfire).

## Installation

```bash
cd elrs_ground_station
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

`pyttsx3` uses Windows' built-in SAPI5 text-to-speech, so no extra system
packages are needed.

## Running it

Demo mode (no hardware needed, simulates a loiter circle incl. battery
drain, to test every feature including the TTS warning):

```bash
python main.py --demo
```

With real telemetry over MAVLink (the default case, see below):

```bash
python main.py --protocol mavlink --host 0.0.0.0 --port 14550
```

With a raw CRSF telemetry stream over UDP:

```bash
python main.py --protocol crsf --host 0.0.0.0 --port 14551
```

With a direct USB/serial connection (FC or ELRS TX module plugged in via
USB) instead of WiFi/UDP - list available ports first:

```bash
python main.py --list-ports
python main.py --connection usb --protocol mavlink --serial-port COM5
python main.py --connection usb --protocol crsf --serial-port COM5 --baud 420000
```

More options: `python main.py --help` (including `--cells`,
`--low-cell-voltage`, `--critical-cell-voltage` for the battery warning,
`--demo-center lat,lon` for the simulation's starting point, and
`--lang de|en` for the UI's starting language).

On startup (unless `--demo` is given), a popup first appears to choose the
connection (WiFi/UDP or USB) and protocol (MAVLink or CRSF) - Cancel just
keeps whatever was passed on the command line/the defaults, and an extra
button starts demo mode directly.

While the app is running:
- **File → Export Flight Path as GPX/KML** saves every GPS point recorded
  so far during the current flight (or use the map's track overlay below,
  which also offers CSV).
- **Route → Waypoint Mode** turns on click-to-add mode on the map; clicking
  an existing waypoint removes it again. **Route → Remove Last Waypoint /
  Clear Route** for the rest of the editing. **Right-clicking** the map
  always opens a menu (independent of Waypoint Mode) for Waypoint/Start
  Point/End Point, "Set as Home", and a "View" submenu.
- **Route → Show Waypoint Editor** toggles the editor overlay on the map
  (also available under Settings → View) - shows waypoint count/total
  distance above an editable table of altitude, name, INAV action, speed,
  and P1-P3; edits apply immediately, no confirmation needed. Its buttons
  export/import the route as INAV `.mission` JSON and check it against
  terrain elevation (red = collision, yellow = tight, green = clear).
- **Route → Import/Export Route...** loads or saves a waypoint list as
  GPX, CSV, iNav `.mission` (classic MW-XML or modern JSON format,
  auto-detected on import), or generic XML.
- **Map → Map Type** switches between OpenStreetMap and Esri satellite
  imagery. **Map → Load No-Fly Zones...** imports restricted areas from
  GeoJSON/CSV, **Show No-Fly Zones** toggles them.
- **The track overlay** (on the map) starts/pauses flight-path recording
  independently of the live display - the map always draws the trail, but
  points only end up in the export while recording is active.
  **Export...** asks for the desired format (GPX/KML/CSV).
- **Flight Log → Log Settings...** picks which telemetry fields get
  recorded and at what interval (0.1-60s). **Flight Log → Logging Active**
  asks for a target path and then keeps writing one CSV row per interval
  until unchecked again.
- **Settings → Connection...** switches at runtime between WiFi/UDP and
  USB/serial as well as between MAVLink and CRSF, including host/port or
  serial port + baud rate - without restarting the app. Automatically
  stops a running demo mode.
- **Settings → Battery Alert...** picks LiPo or Li-Ion (pre-filling
  matching default thresholds) plus cell count and the exact warning/
  critical voltages per cell.
- **Settings → Home Position...** sets where the map centers on the next
  launch (lat/lon entry, or "use current position"); alternatively,
  right-click the map → "Set as Home" to teach it right where you're
  looking.
- **Settings → Customize Dashboard...** shows/hides individual dashboard
  fields (not just whole groups) - the selection is saved as your personal
  default under `~/.elrs_ground_station/dashboard_fields.json` and loaded
  again automatically next launch.
- **Settings → View → Auto-Center** toggles automatically re-centering the
  map on the current position (also reachable via the lock button directly
  on the map, Google-Maps style).
- **Settings → View → Jump to Current Position** (`Ctrl+Home`) immediately
  centers the map on the last known position, independent of Auto-Center.
- **Settings → View → Vehicle Type** picks the map marker: quadcopter,
  wing (flying wing), or airplane.
- **Settings → View → Show Artificial Horizon** toggles the horizon
  overlay; it can also be dragged directly with the mouse on the map and
  resized from a corner grip, and **Position**/**Size** additionally offer
  fixed corner/zoom-level presets.
- **Settings → View → Show Waypoint Editor** and **Show Coordinates Under
  Cursor** toggle the respective map overlays (see above).
- A second fixed button on the map switches between north-up and
  heading-up; in the latter mode, the whole map rotates to match the
  current course.
- **Settings → Language → Deutsch/English** switches the entire UI (menus,
  dashboard, dialogs, spoken warnings) instantly, no restart needed.
- **Simulation → Demo Mode / Plan Mode** switches at runtime between real
  telemetry, simulated data, and the telemetry-free plan mode; both are
  also directly selectable from the startup connection popup.

## Setting up an ELRS TX/RX for WiFi telemetry

ELRS hardware itself doesn't natively speak "telemetry over WiFi" - an
ELRS module's built-in WiFi (TX module or RX) primarily serves flashing/
configuration (access point `ExpressLRS TX`/`ExpressLRS RX`, default
password `expresslrs`, reachable at `http://10.0.0.1` or via mDNS). To
actually get telemetry to this app over UDP, you need a bridge - two
common paths:

### Path 1: MAVLink over WiFi (recommended, `--protocol mavlink`)

Requires a flight controller (ArduPilot/iNav/Betaflight with MAVLink)
connected to the ELRS receiver via CRSF telemetry. The flight controller
itself outputs MAVLink over its telemetry UART; that serial stream needs
to be brought to UDP port `14550` via a WiFi bridge (e.g. an ESP32/ESP8266
running `MAVESP8266` firmware, or a telemetry radio with a WiFi module).
Once the PC and bridge are on the same WLAN, the app listens via `udpin`
(default) for incoming packets - no manual connecting needed. If the
bridge instead needs to actively connect to the PC, use `--udp-mode
connect --host <bridge-IP>`.

### Path 2: Raw CRSF/TBS Crossfire over WiFi (`--protocol crsf`)

Some ELRS "backpack" bridges (ESP32-based) forward the raw CRSF byte
stream of the receiver's telemetry directly over UDP, without going
through MAVLink. CRSF was originally TBS's (Team BlackSheep) Crossfire
protocol; ExpressLRS deliberately uses the same frame format, so this mode
works equally well with genuine TBS Crossfire hardware. Give the target
port configured in the backpack settings via `--port` (example default
here: `14551` - adjust per bridge firmware). This mode covers GPS
(including groundspeed), battery (voltage/current/remaining%/mAh
consumed), link statistics (RSSI/LQ/SNR/TX power), attitude (roll/pitch),
and - if sent by the TX/FC - vario, baro altitude, RPM, temperature, and
cell voltages. Flight mode is only transmitted if the bridge forwards CRSF
flight-mode frames.

In both cases, the PC (running this app) and the bridge/ELRS module need
to be on the same network - either both on the same home WiFi, or the PC
connects directly to the module's access point.

### Path 3: USB/serial (`--connection usb`)

An alternative without WiFi: plug the flight controller or ELRS TX module
directly into the PC via USB cable. Windows assigns a COM port for this
(e.g. `COM5`); `python main.py --list-ports` lists every detected port
with its description. Then:

- `--connection usb --protocol mavlink --serial-port COM5` - default baud
  rate 57600 (overridable via `--baud`), matching the flight controller's
  MAVLink telemetry output.
- `--connection usb --protocol crsf --serial-port COM5` - default baud
  rate 420000 (the standard baud rate for CRSF UARTs), for a directly
  connected ELRS module or a receiver UART hanging off a USB-serial
  adapter on the PC.

This connection type is a replacement for Path 1/2, not an addition -
`--connection` picks UDP (default) or USB, independent of the chosen
`--protocol`.

## Compiling to a .exe (Windows)

```bash
cd elrs_ground_station
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt pyinstaller
pyinstaller --name ELRS_GroundStation --onedir main.py
```

Result lands at `dist\ELRS_GroundStation\ELRS_GroundStation.exe` - the
whole `dist\ELRS_GroundStation` folder (exe + `_internal` directory with
Qt/WebEngine resources, ~500 MB) has to be distributed together, not just
the .exe alone. `--onedir` (rather than `--onefile`) is recommended since
QtWebEngine needs its own helper process plus resource files, which a
single-file exe would have to unpack into a temp directory on every
launch - that works, but is slower to start and more failure-prone.

The exe keeps its console (no `--windowed`), so `--list-ports`, `--demo`
etc. remain usable normally from the command line; double-clicking also
opens a console window in the background.

## Architecture

```
elrs_ground_station/
  main.py                  CLI entry point
  core/
    telemetry_state.py     shared data model
    route.py                waypoint/route data model (RouteManager), incl. INAV
                             mission fields (action/speed/P1-P3) and typed
                             waypoints (waypoint/start/end) from the right-click menu
    geo.py                   haversine distance + bearing (long-range readout)
    nfz.py                    no-fly-zone data model (NoFlyZoneManager)
    terrain.py                 terrain elevation lookup (Open-Elevation API) + collision check
    dashboard_config.py      persists the chosen dashboard fields
    home_config.py            persists the configured home/startup position
    i18n.py                 DE/EN strings + runtime language switch
  telemetry/
    base_worker.py             shared QThread interface
    mavlink_worker.py          MAVLink receiver (pymavlink), UDP or USB/serial
    crsf_parser.py             CRSF frame parser (GPS/Battery/LinkStats/Attitude/
                                Vario/Baro/RPM/Temp/Cells/FlightMode)
    crsf_transport_worker.py   shared receive loop for CRSF (UDP + USB)
    crsf_worker.py             CRSF UDP receiver
    crsf_serial_worker.py      CRSF USB/serial receiver (pyserial)
    serial_ports.py            helper for --list-ports
    demo_worker.py              simulated telemetry
  ui/
    main_window.py           main window, wires workers <-> UI, menus, startup popup,
                              plan mode, right-click/view-action dispatch
    connection_dialog.py     WiFi/USB + protocol switch dialog (also used as startup
                              popup, incl. demo/plan mode buttons)
    battery_settings_dialog.py  LiPo/Li-Ion chemistry + cell count + thresholds
    dashboard_settings_dialog.py  show/hide dashboard fields
    home_position_dialog.py   set home/startup position (lat/lon or current position)
    flight_log_dialog.py     flight-log field selection + interval
    map_widget.py            QWebEngineView wrapper around the Leaflet map + QWebChannel,
                              overlay stacking/positioning
    map_template.py          self-contained Leaflet/OSM+satellite HTML+JS (vehicle
                              markers, home marker, route/NFZ layers, right-click menu,
                              map rotation for heading-up, coordinate readout)
    map_buttons.py            fixed Google-Maps-style map buttons (auto-center lock,
                              map orientation)
    route_bridge.py          QWebChannel bridge for waypoint/context-menu/coordinate
                              events (JS -> Python)
    draggable_overlay.py      base class for draggable/resizable map overlays
                              (corner resize grip)
    horizon_widget.py        artificial horizon (QPainter, draggable/resizable overlay)
    route_editor_overlay.py   waypoint editor as a live overlay (table, INAV mission
                              export/import, terrain check)
    track_overlay.py          start/pause/export overlay for track recording
    dashboard.py             fully configurable telemetry bar with status icons
    icons.py                  QPainter-drawn dashboard icons (no image files)
  export/
    track_export.py         GPX/KML/CSV export of the flown path
    route_export.py          GPX/CSV export of the planned route
    route_import.py          route import: GPX, iNav .mission (MW-XML + JSON,
                              auto-detected), generic XML, CSV
    inav_mission.py           INAV .mission JSON export/import/validation
    nfz_import.py             no-fly-zone import: GeoJSON, CSV
    flight_logger.py          continuous CSV flight log (QTimer-based)
  alerts/tts_alert.py        battery voice warning (pyttsx3, own thread, i18n text,
                              LiPo/Li-Ion thresholds)
```

All the network/parsing work runs in its own `QThread`s (`MAVLinkWorker`,
`CRSFWorker`, `CRSFSerialWorker`, `DemoWorker`), which all implement the
same signal interface (`telemetry_received`, `connection_changed`,
`error_occurred`) - so the GUI never blocks and doesn't know where the
data comes from. Malformed/incomplete packets are caught and skipped per
message, without stopping the worker.
