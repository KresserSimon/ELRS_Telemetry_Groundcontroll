# ELRS Ground Station

Ein schlanker Ground-Control-Bildschirm für Modelle mit ExpressLRS (ELRS):
zeigt live, wo das Modell gerade fliegt und wie es ihm geht, ohne die
Komplexität von Mission Planner oder QGroundControl. Gedacht für alle, die
im Feld nur "wo ist mein Flieger und wie steht's um Akku/Funkverbindung"
auf einen Blick sehen wollen.

## Was die App kann

- **Live-Position auf einer OpenStreetMap-Karte**, mit nachgezogenem
  Flugpfad und wählbarem Fahrzeugsymbol (Quadrocopter, Wing, Flugzeug).
- **Ein Blick-Dashboard** für GPS (Position/Höhe/Satelliten), Funkverbindung
  (RSSI/LQ/SNR/Sendeleistung), Akku (Spannung/Restkapazität) und
  Verbindungsstatus – jeweils mit einem eigenen Statussymbol.
- **Sprachansage**, sobald der Akku niedrig oder kritisch wird, damit man
  nicht ständig auf den Bildschirm schauen muss.
- **Flugpfad-Export als GPX oder KML** nach dem Flug, zum Auswerten in
  anderen Karten-/Analysetools.
- **WiFi (UDP) oder direktes USB-Kabel** als Verbindungsweg zur Telemetrie,
  zur Laufzeit umschaltbar – ebenso wie das Protokoll (MAVLink oder rohes
  CRSF) und die Sprache der Oberfläche (Deutsch/Englisch).
- **Demo-Modus** mit einer simulierten Flugbahn, um die App komplett ohne
  Modell oder ELRS-Hardware auszuprobieren.
- **Künstlicher Horizont** als frei verschiebbares Overlay auf der Karte
  (Roll/Pitch aus MAVLink- oder CRSF-Attitude-Daten).
- **Route/Wegpunkte auf der Karte planen**: per Klick zeichnen oder aus
  GPX, iNav `.mission`, generischem XML oder CSV importieren – als
  eigene, von der geflogenen Spur unabhängige Referenzlinie.

Funktioniert mit Flugsteuerungen (ArduPilot/Betaflight/iNav), die ihre
Telemetrie per MAVLink ausgeben, ebenso wie mit dem rohen CRSF-Telemetrie-
strom direkt vom ELRS-Empfänger.

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
  aufgezeichneten GPS-Punkte des aktuellen Fluges.
- **Route → Wegpunkt-Modus** schaltet den Klick-zum-Hinzufügen-Modus auf
  der Karte ein; ein Klick auf einen bestehenden Wegpunkt entfernt ihn
  wieder. **Route → Letzten Wegpunkt entfernen / Route löschen** für die
  restliche Bearbeitung.
- **Route → Route importieren...** lädt eine Wegpunktliste aus GPX,
  iNav `.mission`, generischem XML oder CSV und zeichnet sie als
  gestrichelte grüne Linie mit nummerierten Punkten auf der Karte (CSV
  braucht Spalten wie `lat`/`lon`/`latitude`/`longitude`, `alt` optional).
- **Einstellungen → Verbindung...** wechselt zur Laufzeit zwischen
  WiFi/UDP und USB/Seriell sowie zwischen MAVLink und CRSF, inkl.
  Host/Port bzw. seriellem Port + Baudrate — ohne die App neu zu starten.
  Beendet dabei automatisch einen laufenden Demo-Modus.
- **Einstellungen → Ansicht → Auto-Center** schaltet das automatische
  Nachführen der Karte auf die aktuelle Position ein/aus.
- **Einstellungen → Ansicht → Aktuelle Position anspringen** (`Strg+Pos1`)
  zentriert die Karte sofort auf die letzte bekannte Position, unabhängig
  von Auto-Center.
- **Einstellungen → Ansicht → Fahrzeugtyp** wählt das Kartensymbol:
  Quadrocopter, Wing (Nurflügler) oder Flugzeug.
- **Einstellungen → Sprache → Deutsch/English** wechselt die komplette
  Oberfläche (Menüs, Dashboard, Dialoge, Sprachwarnungen) sofort ohne
  Neustart.
- **Simulation → Demo-Modus** schaltet zur Laufzeit zwischen echter
  Telemetrie und simulierten Daten um.

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

### Weg 2: Rohes CRSF über WiFi (`--protocol crsf`)

Manche ELRS-"Backpack"-Bridges (ESP32-basiert) leiten den rohen CRSF-
Bytestrom der Empfänger-Telemetrie direkt per UDP weiter, ohne Umweg über
MAVLink. Den in der Backpack-Konfiguration eingestellten Ziel-Port mit
`--port` angeben (Beispiel-Default hier: `14551` – je nach Bridge-Firmware
anpassen). Dieser Modus deckt GPS, Akku (Spannung/Restkapazität) und
Link-Statistiken (RSSI/LQ/SNR/TX-Power) ab; Flight-Mode wird nur übertragen,
wenn die Bridge CRSF-Flight-Mode-Frames weiterleitet.

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
    route.py                Wegpunkt/Routen-Datenmodell (RouteManager)
    i18n.py                 DE/EN-Strings + Laufzeit-Sprachumschaltung
  telemetry/
    base_worker.py             gemeinsames QThread-Interface
    mavlink_worker.py          MAVLink-Empfänger (pymavlink), UDP oder USB/seriell
    crsf_parser.py             CRSF-Frame-Parser (GPS/Battery/LinkStats/FlightMode)
    crsf_transport_worker.py   gemeinsame Empfangsschleife fuer CRSF (UDP + USB)
    crsf_worker.py             CRSF-UDP-Empfänger
    crsf_serial_worker.py      CRSF-USB/seriell-Empfänger (pyserial)
    serial_ports.py            Hilfsfunktion fuer --list-ports
    demo_worker.py              Simulierte Telemetrie
  ui/
    main_window.py           Hauptfenster, verbindet Worker <-> UI, Menüs, Startpopup
    connection_dialog.py     Dialog zum Wechsel WiFi/USB + Protokoll (auch als Startpopup)
    map_widget.py            QWebEngineView-Wrapper um die Leaflet-Karte + QWebChannel
    map_template.py          Self-contained Leaflet/OSM HTML+JS (Fahrzeugsymbole, Routen-Layer)
    route_bridge.py          QWebChannel-Bruecke fuer Wegpunkt-Klicks (JS -> Python)
    horizon_widget.py        Kuenstlicher Horizont (QPainter, frei verschiebbares Overlay)
    dashboard.py             Telemetrie-Leiste mit Status-Icons
    icons.py                  QPainter-gezeichnete Dashboard-Icons (keine Bilddateien)
  export/
    track_export.py         GPX/KML-Export des geflogenen Pfads
    route_import.py          Routen-Import: GPX, iNav .mission, generisches XML, CSV
  alerts/tts_alert.py        Akku-Sprachwarnung (pyttsx3, eigener Thread, i18n-Texte)
```

Die komplette Netzwerk-/Parsing-Arbeit läuft in eigenen `QThread`s
(`MAVLinkWorker`, `CRSFWorker`, `CRSFSerialWorker`, `DemoWorker`), die alle dasselbe
Signal-Interface (`telemetry_received`, `connection_changed`,
`error_occurred`) implementieren – die GUI blockiert dadurch nie und weiß
nicht, woher die Daten kommen. Fehlerhafte/unvollständige Pakete werden pro
Nachricht abgefangen und übersprungen, ohne den Worker zu beenden.
