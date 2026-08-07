# ELRS Ground Station

Eine schlanke Alternative zu Mission Planner / QGroundControl für ExpressLRS
(ELRS) Telemetrie: Live-Karte (OpenStreetMap/Leaflet), Telemetrie-Dashboard,
GPX/KML-Export des Flugpfads und Sprachwarnung bei niedrigem Akkustand.

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

Weitere Optionen: `python main.py --help` (u. a. `--cells`,
`--low-cell-voltage`, `--critical-cell-voltage` für die Akkuwarnung und
`--demo-center lat,lon` für den Startpunkt der Simulation).

Im laufenden Programm:
- **Datei → Flugpfad als GPX/KML exportieren** speichert alle bisher
  aufgezeichneten GPS-Punkte des aktuellen Fluges.
- **Ansicht → Auto-Center** schaltet das automatische Nachführen der Karte
  auf die aktuelle Position ein/aus.
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

## Architektur

```
elrs_ground_station/
  main.py                  CLI-Einstieg
  core/telemetry_state.py  gemeinsames Datenmodell
  telemetry/
    base_worker.py         gemeinsames QThread-Interface
    mavlink_worker.py       MAVLink-UDP-Empfänger (pymavlink)
    crsf_parser.py          CRSF-Frame-Parser (GPS/Battery/LinkStats/FlightMode)
    crsf_worker.py           CRSF-UDP-Empfänger
    demo_worker.py           Simulierte Telemetrie
  ui/
    main_window.py          Hauptfenster, verbindet Worker <-> UI
    map_widget.py            QWebEngineView-Wrapper um die Leaflet-Karte
    map_template.py          Self-contained Leaflet/OSM HTML+JS
    dashboard.py              Telemetrie-Leiste
  export/track_export.py    GPX/KML-Export
  alerts/tts_alert.py        Akku-Sprachwarnung (pyttsx3, eigener Thread)
```

Die komplette Netzwerk-/Parsing-Arbeit läuft in eigenen `QThread`s
(`MAVLinkWorker`, `CRSFWorker`, `DemoWorker`), die alle dasselbe
Signal-Interface (`telemetry_received`, `connection_changed`,
`error_occurred`) implementieren – die GUI blockiert dadurch nie und weiß
nicht, woher die Daten kommen. Fehlerhafte/unvollständige Pakete werden pro
Nachricht abgefangen und übersprungen, ohne den Worker zu beenden.
