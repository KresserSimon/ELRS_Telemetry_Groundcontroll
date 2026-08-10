# Feature-Implementierungsplan

Status: Planung, kein Code geschrieben. Referenzen sind `datei:zeile` Stand zum
Zeitpunkt der Analyse.

## Schritt 1 — Bestehende Architektur

### Telemetriefluss

Jedes Empfänger-Backend (`telemetry/mavlink_worker.py`, `telemetry/crsf_worker.py`,
`telemetry/crsf_serial_worker.py`, `telemetry/demo_worker.py`) ist ein `QThread`,
das von `telemetry/base_worker.py:TelemetryWorker` erbt und genau drei Signale
kennt:

```
telemetry_received = pyqtSignal(object)   # TelemetryState
connection_changed = pyqtSignal(bool)
error_occurred = pyqtSignal(str)
```

Es gibt **keine zentrale State-Klasse** außerhalb des jeweiligen Workers - jeder
Worker hält seinen eigenen `TelemetryState` (`core/telemetry_state.py`, ein
flaches Dataclass mit optionalen Feldern) und sendet bei jedem neuen Datenpaket
eine Kopie (`state.copy()`) über `telemetry_received`. `ui/main_window.py`
erzeugt in `_start_worker()` (main_window.py:720) je nach `--protocol` /
`--connection` / `--demo` genau einen der vier Worker, verbindet die drei
Signale auf `_on_telemetry` / `_on_connection_changed` / `_on_error` und startet
ihn. Beim Umschalten (Verbindungsdialog, Demo-Toggle) wird der alte Worker
gestoppt und ein neuer erzeugt - es existiert immer höchstens ein aktiver
Worker.

`_on_telemetry()` (main_window.py:1221) ist der **einzige Andockpunkt**, an dem
jedes Telemetriepaket in der laufenden App ankommt, und macht dort in dieser
Reihenfolge:
1. `self._dashboard.update_state(state)` - Feldwerte, inkl. der intern in
   `Dashboard` gehaltenen "Home"-Referenz (siehe unten)
2. `self._horizon.update_attitude(state.roll, state.pitch)`
3. bei GPS-Fix: `self._map.update_position(...)`, Track-Aufzeichnung,
   Höhenverlauf-Sample
4. `self._battery_monitor.check(state)` - kann TTS auslösen
5. `self._check_nfz_proximity(state)` - kann TTS + Statuszeile auslösen
6. `self._tracker_output_sender.send(state)` - sendet aktiv an ein externes
   Gerät, falls aktiv

**Wichtig für Log-Replay:** Schritte 4-6 sind Seiteneffekte, keine reinen
Anzeige-Updates. Jedes Feature, das `TelemetryState`-Objekte "künstlich"
einspeist (Replay, später ggf. Tests), darf nicht einfach `_on_telemetry()`
wiederverwenden, ohne diese drei Seiteneffekte gezielt abzuschalten - siehe
Replay-Feature und den Refactoring-Abschnitt am Ende.

**Zwei bestehende "Home"-Konzepte, die schon heute unterschiedlich sind**
(im Rückfragen-Schritt vom Nutzer bestätigt: die für dieses Dokument relevante
ist die erste):
- **Flugstart-Referenz** (`ui/dashboard.py:134,532-537`): `Dashboard._home`
  wird beim ersten GPS-Fix der laufenden Session gesetzt, bei jedem
  `reset_session()` (= jedem `_start_worker()`-Aufruf) wieder auf `None`
  zurückgesetzt. Daraus werden "Entfernung Heim" / "Peilung Heim" im
  Dashboard berechnet, mit `core/geo.py:haversine_distance_m` /
  `bearing_deg`. Rein session-lokal, nirgends persistiert.
- **Karten-Startposition** (`core/home_config.py`): persistiert unter
  `~/.elrs_ground_station/home_position.json`, bestimmt nur, wo die Karte
  beim Programmstart zentriert ist, bevor der erste Fix da ist. Hat mit der
  obigen Distanz/Peilung-Berechnung nichts zu tun.

Für die neue **Bodenstations-Position** (P2, siehe unten) heißt das: es ist ein
echtes drittes Konzept (wo *der Pilot* physisch steht), nicht identisch mit
Flugstart oder Karten-Startposition. Es ersetzt laut Rückfrage-Antwort **nicht**
"Entfernung/Peilung Heim" - das bleibt unverändert die Flugstart-Referenz.

### Bidirektionalität

Aktuell **nur Empfang** bei den Telemetrie-Workern: `mavlink_worker.py` und
`crsf_worker.py`/`crsf_serial_worker.py` rufen ausschließlich `recv_match()`
bzw. parsen eingehende Bytes; keiner ruft je eine `_send()`-Funktion auf.

Es gibt aber bereits einen funktionierenden **Sendepfad mit pymavlink** an
anderer Stelle: `core/tracker_output.py:TrackerOutputSender` öffnet eine
eigene `mavutil.mavlink_connection(...)` und ruft
`self._mavlink_conn.mav.global_position_int_send(...)` auf (tracker_output.py:152) -
das beweist, dass ausgehende MAVLink-Nachrichten mit dem vorhandenen Stack
grundsätzlich einfach sind. Für den geplanten **MAVLink-Rückkanal** (Mission
Upload/Download, RTH, Moduswechsel) ist der relevante Unterschied: der
Connection-Handle in `MAVLinkWorker.run()` (`conn`, mavlink_worker.py:53-55)
ist eine **lokale Variable im Thread**, nicht auf `self` gespeichert - für
Senden aus dem GUI-Thread muss das neu gelöst werden (siehe
Refactoring-Abschnitt).

CRSF hat kein Analogon zu MAVLinks Missions-/Kommando-Protokoll; ein
CRSF-Rückkanal ist außerhalb des Scopes dieses Plans (deckt sich mit der
Vorgabe, den Rückkanal bei aktivem CRSF-Protokoll klar zu deaktivieren).

### Overlays, Menüs, Settings, i18n, Sprache - die Muster, an die sich neue Features halten sollen

- **Overlays**: draggable/dockbare Widgets (`ui/draggable_overlay.py` als
  Basisklasse, z.B. `ui/track_overlay.py`, `ui/altitude_track_overlay.py`,
  `ui/route_editor_overlay.py`) werden über `MapWidget.add_overlay(widget,
  corner)` auf der Karte plaziert, Größe/Position wird pro Overlay in
  `ui_state.json` gespeichert (z.B. `route_editor_size`,
  `track_overlay_size`). Ein neues Overlay (z.B. für Log-Replay-Transportleiste
  oder Modell-verloren-Anzeige) folgt exakt diesem Muster.
- **Menüs**: `MainWindow._build_menu()` baut 7 Top-Level-Menüs
  (`Datei`, `Route & Planung`, `Anzeige & Karte`, `Telemetrie & Hardware`,
  `Tools & Simulation`, `Einstellungen`, `Hilfe`); jede `QAction` wird über
  `self._i18n_actions.append((action, key))` registriert und in
  `_retranslate_menu()` neu beschriftet, wenn die Sprache wechselt. Neue
  Menüpunkte reihen sich in eine der bestehenden 7 Gruppen ein (siehe
  Zuordnung je Feature unten).
- **Settings-Persistenz**: durchgängig `core/<name>_config.py`-Module mit
  `load_*()`/`save_*()`, JSON unter `~/.elrs_ground_station/*.json`, robust
  gegen fehlende/kaputte Dateien (`except (OSError, ValueError, ...): return
  default`). `ui_state.json` (`core/ui_state_config.py`) ist ein einzelner
  flacher Dict für alle Menü-Toggle-Zustände; `model_profiles.json`
  (`core/model_profiles.py`) ist ein Dict `name -> ModelProfile`-Dataclass.
  Neue Settings folgen exakt diesem Muster - eigene Datei bei eigenständigem
  Feature (z.B. `geofence_config.py`, `gs_position_config.py`), oder neues
  Feld in `ui_state.json`/`ModelProfile` bei einem einfachen Toggle/Wert.
- **i18n**: `core/i18n.py`, ein flaches DE/EN-String-Dict (`_STRINGS["de"][key]`
  / `_STRINGS["en"][key]`), `i18n.tr(key, **kwargs)` für `{platzhalter}`-
  Interpolation, `i18n.on_language_changed(callback)` für Live-Retranslate.
  Jeder neue UI-String bekommt einen Key in beiden Sprachen - das bestehende
  Abdeckungs-Script (`tests`-nahes Skript, prüft "jeder `i18n.tr()`-Call hat
  einen DE+EN-Key") sollte für neue Features mitlaufen.
- **Sprachausgabe**: `alerts/tts_alert.py` - ein `TTSWorker`-QThread mit
  `say(text)`-Queue (pyttsx3/SAPI5, komplett offline) plus ein pro Feature
  eigener State-Machine-Monitor (`BatteryAlertMonitor` dort, oder
  `core/nfz_proximity.py:NfzProximityMonitor`), der Hysterese + Re-Announce-
  Cooldown (typ. 30s) implementiert, damit eine Dauerwarnung nicht auf jedem
  Telemetrie-Tick erneut spricht. Jedes neue Sprachwarnungs-Feature
  (Modell-verloren, Energiebudget-Umkehrpunkt, Geofence-Verletzung) bekommt
  einen eigenen kleinen Monitor nach genau diesem Muster, keinen gemeinsamen.

## Schritt 2 — Features

---

### P1: Modell-verloren-Modus

**Ziel:** Erkennt Telemetrieabriss per konfigurierbarem Timeout, friert die
letzte gültige Position ein, zeigt sie prominent an, warnt per Sprache, zeigt
Peilung+Distanz vom Bodenstations-Referenzpunkt, exportiert als GPX und in die
Zwischenablage - komplett offline.

**Betroffene bestehende Dateien:**
- `ui/main_window.py` - `_check_heartbeat()` (main_window.py:1262) ist
  **bereits genau der richtige Hook**: läuft schon periodisch (vermutlich
  über einen QTimer, prüft `time.time() - self._last_telemetry_time >
  HEARTBEAT_TIMEOUT_S`), heute nur um `dashboard.set_connection_status(False)`
  zu setzen. Wird erweitert, um den neuen Monitor zu füttern.
- `ui/dashboard.py` - `set_connection_status()` existiert schon; neue
  Anzeige (eingefrorene Position + Zeit seit Verlust) wahrscheinlich als
  eigenes kleines Overlay statt Dashboard-Feld, da es *prominent*, nicht nur
  ein Zahlenfeld sein soll (siehe UI unten).
- `export/track_export.py` - `TrackRecorder.export_gpx()` ist bereits eine
  fertige Single-Point-taugliche GPX-Schreibfunktion; für den Export der
  eingefrorenen Position reicht ein `TrackRecorder` mit einem Punkt, kein
  neuer XML-Code nötig.

**Neue Module:**
- `core/lost_model_monitor.py` - State-Machine nach dem
  `NfzProximityMonitor`-Muster: `check(state, timeout_s)`, hält
  `frozen_state: Optional[TelemetryState]`, `lost_since: Optional[float]`,
  triggert TTS einmalig beim Übergang + Re-Announce-Cooldown.
- `ui/lost_model_overlay.py` - Draggable/dockbares Overlay (wie
  `track_overlay.py`), zeigt eingefrorene Lat/Lon, Distanz+Peilung vom
  Referenzpunkt, "seit wann verloren", Buttons "Als GPX exportieren" /
  "Koordinaten kopieren". Nur sichtbar/aktiv, solange der Zustand "verloren"
  aktiv ist (oder manuell einblendbar zur Kontrolle).

**Datenfluss/Integrationspunkt:** `_check_heartbeat()` → `LostModelMonitor.check()`
mit dem letzten bekannten `TelemetryState` (`self._last_telemetry_state`,
existiert schon, main_window.py:1223) → bei Zustandswechsel Signal an
`LostModelOverlay` + `tts.say(...)`. Referenzpunkt für Distanz/Peilung: falls
Bodenstations-Position (P2) gesetzt ist, diese; sonst Fallback auf
`Dashboard._home` (Flugstart-Referenz) - siehe Abhängigkeits-Hinweis in
Phase 4.

**UI-/Menüänderungen:** Neuer Menüpunkt "Modell-verloren-Timeout..." unter
`Telemetrie & Hardware` (kleiner Dialog: Timeout-Sekunden, an-/ausschaltbar).
Overlay-Sichtbarkeit als Checkbox unter `Anzeige & Karte`, gleiche Stelle wie
andere Overlay-Toggles.

**Neue Settings-Keys:** `ui_state.json`: `lost_model_timeout_s` (Zahl),
`lost_model_overlay_visible` (bool), `lost_model_overlay_size`/`_docked` wie
bei den anderen Overlays.

**Risiken/Sonderfälle:**
- Timeout darf nicht mit dem bestehenden `HEARTBEAT_TIMEOUT_S` (Verbindungs-
  Statusanzeige) kollidieren/verwechselt werden - eigener, separat
  konfigurierbarer Wert, sinnvoll länger oder gleich dem Verbindungs-Timeout.
- `frozen_state` muss bei `_start_worker()` (neue Verbindung/Demo-Neustart)
  explizit zurückgesetzt werden, sonst zeigt ein neuer Flug fälschlich die
  alte eingefrorene Position.
- GPX-Export eines Einzelpunkts ist ein Sonderfall von `TrackRecorder` (nur
  1 `trkpt`) - kurz gegen leeres/entartetes GPX prüfen (valide XML, importierbar).

**Testansatz:** Unit-Test für `LostModelMonitor` mit synthetischen
Telemetrie-Timestamps (kein Timer nötig, `check()` nimmt `now` als Parameter
wie bei `NfzProximityMonitor`). Demo-Modus-Erweiterung: neuer
`--demo-drop-signal-after=N` o.ä., der `DemoWorker` nach N Sekunden aufhören
lässt, `telemetry_received` zu emittieren, um den Zustand ohne echte Hardware
zu erzwingen.

**Handbuch-Abschnitt:** Neuer Abschnitt "Modell-verloren-Modus" im Kapitel
"Sicherheit/Alarme" (dort, wo Akku- und Sperrzonen-Warnungen dokumentiert sind).

**Grober Aufwand:** 1.5-2 Tage.

---

### P1: Heimkehr-Energiebudget

**Ziel:** Schätzt aus Distanz zu Home, Akkuverbrauch/-Nennkapazität,
Geschwindigkeit und Verbrauchsrate die Rest-Reichweite und die für die
Heimkehr benötigte Kapazität, zeigt eine Reserve-Ampel und warnt per Sprache
beim empfohlenen Umkehrpunkt.

**Formel (vorgeschlagen, im Plan explizit begründet):**

```
Verbrauchsrate:
  falls state.battery_current vorhanden:
      rate_mAh_pro_s = battery_current[A] * 1000 / 3600
  sonst falls battery_capacity_used über die Zeit bekannt (zwei Samples):
      rate_mAh_pro_s = Δ(battery_capacity_used) / Δt   (gleitendes Fenster, z.B. letzte 10s)
  sonst: keine Rate ableitbar → Feature zeigt "n/v", keine Warnung (siehe Risiken)

Benötigte mAh für Heimkehr:
  home_time_s = distance_home_m / max(groundspeed, MIN_SPEED_ASSUMPTION_M_S)
  mah_for_home = home_time_s * rate_mAh_pro_s

Reserve:
  remaining_mah = capacity_mah * (battery_remaining / 100)   # falls battery_remaining vorhanden
                  ODER capacity_mah - battery_capacity_used   # sonst, falls capacity_used vorhanden
  reserve_mah = remaining_mah - mah_for_home
  reserve_pct_of_capacity = reserve_mah / capacity_mah * 100

Ampel:
  grün   falls reserve_pct_of_capacity >= GREEN_THRESHOLD (z.B. 30%)
  gelb   falls reserve_pct_of_capacity >= YELLOW_THRESHOLD (z.B. 15%)
  rot    sonst
  Sprachwarnung einmalig beim Übergang grün→gelb ("Umkehrpunkt erreicht")
  und gelb→rot, mit Re-Announce-Cooldown wie bei BatteryAlertMonitor.
```

`MIN_SPEED_ASSUMPTION_M_S` ist nötig, weil `groundspeed` bei Schweben/Steigen
gegen 0 gehen kann, was `home_time_s` gegen unendlich treibt - ein Fallback-
Wert (z.B. 5 m/s oder ein konfigurierbarer "erwartete RTH-Geschwindigkeit"-
Wert) verhindert das, ist aber selbst eine Annahme, die im Handbuch explizit
als solche benannt werden muss (die Schätzung ist eine Heuristik, kein
Garantiewert - das muss in der UI selbst auch klar stehen, nicht nur im
Handbuch, sonst Sicherheitsrisiko durch Übervertrauen).

**Verhalten bei fehlenden Feldern (explizit, nicht optional geraten):**
- Kein `battery_current`-Sensor (viele FCs liefern das nicht ohne
  Power-Modul): Rate wird aus der Ableitung von `battery_capacity_used`
  geschätzt, falls vorhanden; sonst komplett "n/v" - **keine Warnung wird
  synthetisiert**, denn eine erfundene Zahl ist hier gefährlicher als keine.
- Keine `battery_capacity_mah` im aktiven Profil (Default ist 1300, siehe
  `ModelProfile`, aber ggf. falsch für das reale Pack): UI muss den Wert
  prominent zeigen/editierbar machen, nicht nur im Profil-Dialog vergraben,
  da eine falsche Nennkapazität die ganze Rechnung verfälscht.
- Kein GPS-Fix (`distance_home` unbekannt): Feature zeigt "n/v", keine Ampel.

**Betroffene bestehende Dateien:**
- `core/model_profiles.py` - `battery_capacity_mah` existiert bereits
  (Zeile 24), keine Schema-Änderung nötig, nur Wiederverwendung.
- `ui/dashboard.py` - neue Felder (Restreichweite, benötigte mAh, Ampel)
  fügen sich in die bestehende `_Field`/Gruppen-Struktur ein (wie
  `distance_home`/`bearing_home`, dashboard.py:223-224).
- `ui/main_window.py` - `_on_telemetry()` bekommt einen weiteren Aufruf
  `self._energy_budget_monitor.check(state, self._dashboard._home,
  capacity_mah)`, analog zu `_battery_monitor.check(state)`.

**Neue Module:** `core/energy_budget.py` - reine Rechenfunktion(en) (leicht
testbar ohne Qt) + ein kleiner State-Monitor für die Ampel-Hysterese/TTS,
wieder nach dem `BatteryAlertMonitor`-Muster.

**UI-/Menüänderungen:** Keine neuen Menüpunkte nötig - Ampel/Reichweite sind
neue Dashboard-Felder (über den bestehenden Dashboard-Einstellungen-Dialog
ein-/ausblendbar, wie jedes andere Feld auch). Ggf. ein Einstellungs-Eintrag
unter `Einstellungen` für die "erwartete RTH-Geschwindigkeit"-Annahme und die
Ampel-Schwellwerte.

**Neue Settings-Keys:** `ModelProfile` (neues Feld, sinnvoll da modellspezifisch):
`energy_rth_speed_assumption_ms`. Global in `ui_state.json`:
`energy_reserve_yellow_pct`, `energy_reserve_green_pct` (Schwellwerte, eher
globale Präferenz als modellspezifisch).

**Risiken/Sonderfälle:** Rate-Schätzung aus `battery_capacity_used`-Ableitung
ist verrauscht bei sehr kurzen Zeitfenstern - gleitender Durchschnitt/Mindest-
Fensterlänge nötig, sonst flackert die Ampel. Muss bei Session-Reset
(`_start_worker`) sauber neu initialisiert werden wie `Dashboard._home`.

**Testansatz:** Unit-Tests für die reinen Rechenfunktionen in
`core/energy_budget.py` (Tabellen bekannter Eingaben → erwartete Ampel/mAh),
inkl. expliziter Tests für jeden "fehlendes Feld"-Fall aus der Liste oben.
Demo-Modus: `DemoWorker` liefert schon `battery_current`/`battery_capacity_used`
(zu prüfen/ergänzen), damit das Feature im Demo-Betrieb sichtbar ist.

**Handbuch-Abschnitt:** Neuer Unterabschnitt im Akku-Kapitel, mit explizitem
Warnhinweis, dass es sich um eine Schätzung auf Annahmen-Basis handelt.

**Grober Aufwand:** 2 Tage (die Formel-Robustheit gegen fehlende Felder ist
der zeitaufwändige Teil, nicht die UI).

---

### P1: Eigener Geofence

**Ziel:** Konfigurierbarer Max-Radius und Max-Höhe relativ zu Home
(Vorbelegung 120 m), als Ring/Warnschwelle auf der Karte, mit Sprach- und
Statuszeilen-Warnung bei Verletzung; zusätzlich Prüfung der geplanten Route
gegen Geofence + geladene Sperrzonen schon beim Planen.

**Scope-Entscheidung (per Rückfrage nicht festgelegt - eigene Empfehlung):**
Pro Modell-Profil (wie `battery_capacity_mah`), da unterschiedliche Modelle
plausibel unterschiedliche Zulassungs-/Einsatzradien haben. Leicht auf
"global" umstellbar, falls das in der Praxis nicht gebraucht wird - betrifft
nur, ob das Feld in `ModelProfile` oder in `ui_state.json` landet, sonst
keine Architekturauswirkung.

**Betroffene bestehende Dateien:**
- `core/nfz_proximity.py` - **nicht** direkt wiederverwendet für die Live-
  Verletzungsprüfung (Geofence ist "raus = schlecht", NFZ ist "rein = schlecht" -
  andere Logik), aber `distance_to_zone_m()`/`_point_to_segment_distance_m`
  als Vorbild; ein Kreis mit Center=Home, Radius=Grenze lässt sich mit
  `haversine_distance_m` und einem einzigen Vergleich prüfen (`distance_home
  > geofence_radius_m` ⇒ Verletzung) - deutlich simpler als NFZ-Polygone.
- `ui/map_widget.py` / `ui/map_template.py` / `ui/maplibre_template.py` -
  neue, eigene Render-Funktion `setGeofence(center_lat, center_lon, radius_m)`
  statt Wiederverwendung von `setNoFlyZones()`: der Geofence ist konzeptionell
  "meine eigene Grenze" (typischerweise Ring/gestrichelt, eigene Farbe, z.B.
  Blau), nicht "importierte Sperrzone" (rot gefüllt) - beide sollen
  unabhängig voneinander ein-/ausblendbar bleiben (der Nutzer könnte NFZ-
  Anzeige ausblenden, den eigenen Geofence aber sichtbar lassen wollen).
  Muss in **beiden** Templates (Leaflet + MapLibre) ergänzt werden.
- `ui/main_window.py` - `_on_telemetry()` bekommt
  `self._geofence_monitor.check(state, self._dashboard._home,
  radius_m, max_alt_m)`.
- Route-Planung: `core/route.py`/`RouteManager` - neue Prüfung beim Ändern
  der Route (`changed`-Signal, schon verkabelt für `_on_route_changed`,
  main_window.py:1270), die jeden Wegpunkt gegen Geofence-Radius/-Höhe UND
  gegen `NoFlyZoneManager.zones()` matched, Ergebnis als Warnliste im
  Wegpunkt-Editor (`ui/route_editor_overlay.py`) - z.B. eine rote Markierung
  pro Zeile, die außerhalb liegt.

**Neue Module:** `core/geofence.py` (Datenmodell + reine Prüfunktion,
analog `core/nfz.py`), `core/geofence_monitor.py` (Live-Verletzungs-
State-Machine mit TTS, wie `NfzProximityMonitor`).

**UI-/Menüänderungen:** Neuer Eintrag "Geofence..." Dialog (Radius, Max-Höhe,
an/aus) - im Modell-Profil-Dialog *oder* unter `Einstellungen`, je nach
Scope-Entscheidung oben. Sichtbarkeits-Toggle unter `Anzeige & Karte`, analog
zum bestehenden "Sperrzonen sichtbar".

**Neue Settings-Keys:** `ModelProfile`: `geofence_radius_m` (Default 120),
`geofence_max_alt_m`, `geofence_enabled`. `ui_state.json`:
`geofence_visible` (Anzeige-Toggle, unabhängig von "aktiv/prüft").

**Risiken/Sonderfälle:**
- Referenzpunkt für den Geofence-Mittelpunkt ist wieder die Flugstart-
  Referenz (`Dashboard._home`), nicht die Bodenstations-Position - ein
  Geofence "um mich als Piloten" wäre ein anderes (denkbares, aber hier
  nicht gefordertes) Feature.
- Vorab-Routenprüfung (Planung) vs. Live-Prüfung (Flug) müssen denselben
  `core/geofence.py`-Code nutzen, sonst können beide Prüfungen bei einer
  künftigen Änderung auseinanderlaufen.
- 120 m Default ist EU/CH-"offene Kategorie", aber KEIN Ersatz für die
  tatsächliche rechtliche Prüfung durch den Piloten - Hinweistext in der UI
  nötig (wie beim Energiebudget: Software-Grenze, keine Rechtsauskunft).

**Testansatz:** Unit-Tests für `core/geofence.py` (Punkt innerhalb/außerhalb
Radius, Höhe über/unter Limit) und für die Routenprüfung (Wegpunkte-Liste mit
bekannten In-/Out-of-bounds-Punkten). Demo-Modus: `DemoWorker`s Kreisbahn-
Radius ist bekannt (siehe `telemetry/demo_worker.py`) - ein Demo-Preset mit
Radius > 120 m macht die Live-Warnung ohne echte Hardware testbar.

**Handbuch-Abschnitt:** Neuer Abschnitt "Geofence" im Sicherheits-Kapitel,
direkt neben Sperrzonen (NFZ), mit klarer Abgrenzung beider Konzepte.

**Grober Aufwand:** 2-2.5 Tage (Routenprüfung + zwei Kartentemplates sind der
größere Teil, nicht die Live-Prüfung selbst).

---

### P2: Log-Replay

**Ziel:** Lädt eine bestehende Fluglog-CSV (`export/flight_logger.py`) und
spielt sie mit Zeitleiste (Play/Pause/Speed/Scrubbing) über dieselben Widgets
wie im Live-Betrieb ab, plus automatische Flugzusammenfassung als Dialog und
Textexport.

**Zentrale Architekturentscheidung: Telemetriequelle abstrahieren (siehe auch
Refactoring-Liste unten).** Aktuell erzeugt nur ein `TelemetryWorker`-Thread
`TelemetryState`-Objekte. Eine `ReplayWorker(TelemetryWorker)`-Klasse, die
CSV-Zeilen zurück in `TelemetryState` parst und sie zeitgesteuert (mit
Play/Pause/Speed) über exakt dasselbe `telemetry_received`-Signal emittiert,
lässt sich **ohne jede Änderung an Dashboard/Karte/Horizont/Höhenverlauf**
integrieren, weil die alle bereits nur auf dieses eine Signal reagieren -
das ist der stärkste Hebel in diesem ganzen Plan.

**CSV-Rückkompatibilität:** `FlightLogger` schreibt eine **konfigurierbare**
Spaltenauswahl aus `ALL_FIELDS` (flight_logger.py:17-24), `timestamp` als
lokale `%Y-%m-%dT%H:%M:%S`-Zeichenkette (Sekundengenauigkeit, keine Zeitzone).
Der Replay-Parser muss:
- jede Spalte aus `ALL_FIELDS` als optional behandeln (fehlt sie im
  CSV-Header, bleibt das Feld `None` in `TelemetryState`, wie im Live-Betrieb
  bei fehlenden Sensoren auch),
- unbekannte/zusätzliche Spalten ignorieren statt zu scheitern,
- **Sekundengranularität als bekannte Grenze akzeptieren** - Scrubbing/
  Wiedergabe zwischen zwei Sekunden-Zeitstempeln kann nur interpolieren oder
  auf den letzten bekannten Wert springen, nicht "genauer" abspielen als die
  Quelle es hergibt. Das gehört ins Handbuch, nicht nur in den Code-Kommentar.

**Muss zwingend abgeschaltet werden während Replay (siehe Rückfrage-Antwort:
"Stumm während Replay"):** TTS-Warnungen (`_battery_monitor`,
`_nfz_proximity_monitor`, und die neuen Monitore aus den P1-Features oben),
`_tracker_output_sender.send()`, `_track_recorder.add_point()`/Live-
Track-Aufzeichnung. Der sauberste Weg: `_on_telemetry()` bekommt einen
`is_replay: bool`-Kontext (z.B. über `state.source == "replay"`, das Feld
existiert schon als freier String, main_window.py:41) und schützt die
Seiteneffekt-Aufrufe mit `if state.source != "replay":`. Reine
Anzeige-Updates (Dashboard/Karte/Horizont/Höhenverlauf) laufen unverändert
durch.

**Betroffene bestehende Dateien:**
- `ui/main_window.py` - `_on_telemetry()` wie oben beschrieben um die
  `state.source == "replay"`-Guards ergänzt; `_start_worker()` bekommt einen
  dritten Zweig `if replay_path: self._worker = ReplayWorker(...)`.
- `ui/flight_log_dialog.py` - vermutlich Vorbild für einen neuen
  `ui/replay_dialog.py` (Datei wählen, Play/Pause/Speed/Scrubbing-Slider).

**Neue Module:**
- `telemetry/replay_worker.py` - `ReplayWorker(TelemetryWorker)`, liest die
  CSV einmal komplett in eine Liste `TelemetryState` ein, läuft dann in
  `run()` eine zeitgesteuerte Schleife (`QThread` + `time.sleep`-basiert
  analog zu `DemoWorker`s Tick-Rate, aber mit variablem Timing aus den
  echten Zeitstempeln × Geschwindigkeitsfaktor).
- `ui/replay_dialog.py` / `ui/replay_transport_overlay.py` - Datei-Öffnen +
  Transportleiste (Play/Pause/Speed/Scrub), als Overlay auf der Karte nach
  bestehendem Muster.
- `core/flight_summary.py` - reine Funktion `summarize(states: List[
  TelemetryState]) -> FlightSummary` (Dauer, max. Höhe, max. Distanz, min. LQ,
  verbrauchte mAh, Ø-/Max-Speed), aufrufbar sowohl nach einem Live-Flug als
  auch nach einem geladenen Replay - ein Dialog + Textexport-Knopf.

**UI-/Menüänderungen:** Neuer Eintrag "Log wiedergeben..." unter
`Tools & Simulation`, neben "Demo-Modus"/"Plan-Modus" (konzeptionell die
dritte "keine echte Hardware nötig"-Betriebsart). "Flugzusammenfassung..."
als weiterer Eintrag dort, verfügbar sowohl nach Live-Flug als auch nach
Replay.

**Neue Settings-Keys:** `ui_state.json`: `replay_last_speed`,
`replay_overlay_size`/`_docked` wie üblich. Kein neues Modell-Profil-Feld.

**Risiken/Sonderfälle:**
- `_check_heartbeat()`/Verbindungsstatus darf während Replay nicht
  "getrennt" anzeigen, nur weil `_last_telemetry_time` nicht kontinuierlich
  wie live tickt - entweder heartbeat-Check während Replay pausieren, oder
  `ReplayWorker` hält `connection_changed=True` konstant und aktualisiert
  `_last_telemetry_time` bei jedem wiedergegebenen Paket normal mit.
- Pause/Scrub muss den internen Play-Zustand von `ReplayWorker` threadsicher
  ändern (Qt-Signal vom GUI-Thread in den Worker-Thread, nicht direkter
  Attributzugriff über Threads hinweg).
- Sehr große CSVs (lange Flüge, hohe Lograte) komplett in den Speicher zu
  laden ist meist unkritisch (Zahlen-Dataclasses, keine Bilder), aber bei
  extremen Logs (>>1h bei hoher Rate) ggf. worth revisiting.

**Testansatz:** Unit-Tests für den CSV→TelemetryState-Parser (inkl. Spalten-
Subset-Fälle) und `core/flight_summary.py` (bekannte Eingabe-Listen →
erwartete Kennzahlen). Kein Demo-Modus-Zusatz nötig, da Replay selbst schon
ein Offline-Modus ist - stattdessen: eine kleine Beispiel-CSV im
Test-Fixture-Verzeichnis.

**Handbuch-Abschnitt:** Neues Kapitel "Log-Wiedergabe", referenziert vom
bestehenden Fluglog-Kapitel.

**Grober Aufwand:** 3-4 Tage (Zeitsteuerung/Scrubbing + die
Seiteneffekt-Isolation in `_on_telemetry()` sind die kniffligen Teile).

---

### P2: MAVLink-Rückkanal

**Ziel:** Mission direkt zur Flugsteuerung hochladen/herunterladen
(MISSION_COUNT/MISSION_ITEM_INT/MISSION_REQUEST_INT/MISSION_ACK), Basisbefehle
RTH und Modus-Wechsel senden.

**Architekturproblem (siehe Schritt 1):** `MAVLinkWorker.run()` hält die
`conn` (die `mavutil.mavlink_connection`) nur als lokale Variable im
Thread. Für Senden aus dem GUI-Thread heraus gibt es zwei Optionen:

1. **Empfohlen:** `conn` wird `self._conn` im Worker; Senden läuft über eine
   Qt-Queued-Connection - eine neue `send_request = pyqtSignal(object)` am
   Worker, verbunden mit einem Slot **im Worker-Thread selbst**
   (`Qt.ConnectionType.QueuedConnection`, automatisch bei Cross-Thread-Signalen),
   der dort `self._conn.mav.xxx_send(...)` aufruft. Damit bleibt jeder
   tatsächliche Socket-Zugriff im selben Thread, der auch `recv_match()`
   aufruft - kein Daten-Race auf `conn`.
2. Zweite, unabhängige `mavutil.mavlink_connection` nur zum Senden (wie
   `TrackerOutputSender` es schon tut) - einfacher, aber bei `--udp-mode
   listen` (Empfangs-Socket ist gebunden, nicht verbunden) müsste die
   Sende-Verbindung wissen, wohin sie senden soll (Ziel-IP oft erst aus dem
   ersten empfangenen Paket bekannt) - mehr Sonderfall-Logik als Option 1.

Empfehlung: Option 1, siehe Refactoring-Liste.

**Sicherheitskonzept (wie gefordert):**
- Jeder Sende-Befehl (RTH, Modus-Wechsel, Mission-Upload-Start) zeigt einen
  `QMessageBox`-Bestätigungsdialog mit Klartext ("Rückkehr zum Startpunkt
  auslösen?"), analog zu bestehenden kritischen Aktionen im Code (z.B.
  Lösch-Bestätigungen).
- Der komplette Menüpunkt/Button-Satz ist **deaktiviert** (nicht nur
  versteckt, damit sichtbar ist *warum* nicht verfügbar), wenn
  `args.protocol != "mavlink"` oder wenn der Worker nur Downlink kann
  (aktuell: das ist eigentlich nie der Fall bei MAVLink, aber falls eine
  zukünftige reine "MAVLink-Log"-Quelle o.ä. dazukommt).
- MISSION_ACK mit Fehlercode wird als sichtbare Fehlermeldung angezeigt,
  nicht nur geloggt - ein stiller Fehlschlag bei einem Missions-Upload ist
  ein Sicherheitsrisiko.

**Betroffene bestehende Dateien:** `telemetry/mavlink_worker.py` (Umbau nach
Option 1 oben), `ui/main_window.py` (neue Menüeinträge + Verkabelung),
`core/route.py`/`RouteManager` (Quelle der hochzuladenden Wegpunkte - schon
vorhanden, keine Änderung nötig, nur neuer Konsument).

**Neue Module:** `telemetry/mavlink_mission.py` - reine Protokolllogik
(MISSION_COUNT/ITEM_INT/REQUEST_INT/ACK-Sequenz als kleine State-Machine,
Timeout+Retry), von `mavlink_worker.py` benutzt, aber unabhängig testbar
ohne echte Verbindung (Mock der `.mav.xxx_send`-Aufrufe).
`ui/mavlink_command_dialog.py` - RTH/Modus-Wechsel-Buttons mit
Bestätigungsdialogen.

**UI-/Menüänderungen:** Neue Einträge unter `Route & Planung`
("Mission hochladen...", "Mission herunterladen...") und unter
`Telemetrie & Hardware` ("RTH auslösen", "Modus wechseln...").

**Neue Settings-Keys:** Keine Persistenz nötig (Aktionen, keine Zustände) -
höchstens `ui_state.json`: `mavlink_command_confirm_dialogs_enabled` falls
die Bestätigung optional abschaltbar sein soll (eher nicht empfohlen).

**Risiken/Sonderfälle:** Mission-Download während eine Route bereits im
Editor offen ist - Konflikt/Merge-Frage (überschreiben vs. abfragen) muss
im UI klar sein. Upload einer sehr langen Route kann mehrere Sekunden
dauern (viele Request/Ack-Zyklen) - braucht Fortschrittsanzeige, kein
blockierendes UI.

**Testansatz:** Unit-Tests für `mavlink_mission.py`s State-Machine mit
gemockten Send-Aufrufen und synthetischen eingehenden
MISSION_REQUEST_INT/ACK-Nachrichten. Kein Demo-Modus-Äquivalent sinnvoll
(Demo hat keine echte FC) - stattdessen ein einfacher lokaler MAVLink-
Echo-Test-Helper (SITL-artig, aber minimal) als manueller Testweg,
dokumentiert statt automatisiert.

**Handbuch-Abschnitt:** Neues Kapitel "Mission-Upload/-Download und
Flugsteuerungs-Befehle" mit explizitem Sicherheitshinweis.

**Grober Aufwand:** 4-5 Tage (Protokoll-State-Machine + Fehlerfälle sind der
größte Teil).

---

### P2: Position der Bodenstation

**Ziel:** Eigene GS-Position aus serieller GPS-Maus (NMEA) oder manueller
Eingabe, unabhängig vom ersten GPS-Fix des Modells (siehe Rückfrage-Klärung:
Flugstart-Referenz bleibt unverändert bestehen). Daraus Azimut/Elevation zum
Modell als neue Dashboard-Anzeige, primär für manuelles Antennen-Zeigen
(Yagi etc.) gedacht.

**Wichtige Scope-Klärung:** Die bestehenden Ausgabeformate in
`core/tracker_output.py` (MAVLink `GLOBAL_POSITION_INT`, NMEA `$GPGGA`)
übertragen beide die **absolute Position des Modells** - ein physischer
Antennen-Tracker berechnet Azimut/Elevation selbst, aus seiner eigenen
(im Tracker konfigurierten) Position. Die neue GS-Position ändert an diesen
beiden Ausgabeformaten nichts inhaltlich - sie ist eine reine **App-lokale
Zusatzanzeige** für den Piloten (manuelles Zeigen einer Antenne von Hand),
plus Referenzpunkt für Modell-verloren (P1, siehe dort).

**Betroffene bestehende Dateien:**
- `telemetry/serial_ports.py` - `list_serial_ports()` existiert schon
  (genutzt in `ui/connection_dialog.py`), direkt wiederverwendbar für eine
  GPS-Maus-Port-Auswahl.
- `ui/dashboard.py` - zwei neue Felder Azimut/Elevation vom Boden, wie
  `distance_home`/`bearing_home` strukturiert, plus Elevationswinkel-
  Berechnung (neu: braucht `state.alt` UND eine bekannte
  Boden-Ellipsoidhöhe/Referenzhöhe der GS-Position - siehe Risiken).
- `ui/main_window.py` - neuer Menüpunkt + Wiring, analog zu
  `home_position_dialog.py`.

**Neue Module:**
- `core/gs_position.py` - Persistenz (`gs_position.json`, wie
  `home_config.py`) + reine Azimut/Elevations-Berechnung
  (`core/geo.py:bearing_deg` für Azimut; Elevation neu:
  `atan2(alt_diff, horizontal_distance_m)`).
- `telemetry/nmea_gps_reader.py` - liest eine serielle NMEA-GPS-Maus
  (`$GPGGA`/`$GPRMC`), separat vom Telemetrie-Worker (läuft parallel, nicht
  Teil des Modell-Telemetriepfads) - eigener kleiner `QThread` oder
  `QTimer`+nicht-blockierendes Polling.
- `ui/gs_position_dialog.py` - manuelle Eingabe (Lat/Lon/Höhe) ODER
  "von GPS-Maus übernehmen"-Knopf.

**UI-/Menüänderungen:** Neuer Eintrag "Bodenstations-Position..." unter
`Einstellungen`, neben "Home-Position" (dort ist der Nutzer es schon
gewohnt, Positions-Dialoge zu finden).

**Neue Settings-Keys:** Neue Datei `gs_position.json`:
`{lat, lon, alt, source: "manual"|"gps"}`.

**Risiken/Sonderfälle:**
- Elevationswinkel braucht eine Referenzhöhe der GS-Position - bei rein
  manueller Eingabe ohne Höhenangabe (nur Lat/Lon) ist Elevation nicht
  sauber berechenbar; UI muss Höhe als eigenes (optionales, mit Warnhinweis
  bei Fehlen) Feld anbieten, nicht nur Lat/Lon.
- GPS-Maus und der Modell-Telemetrie-Worker könnten sich denselben seriellen
  Port streitig machen, wenn versehentlich beide auf denselben COM-Port
  zeigen - Validierung/klare Fehlermeldung nötig, kein stiller Konflikt.
- `core/tracker_output.py` bewusst NICHT ändern (siehe Scope-Klärung oben) -
  Versuchung, dort "GS-relative Winkel senden" zu ergänzen, ist ein
  Scope-Erweiterung, nicht Teil dieses Features.

**Testansatz:** Unit-Tests für Azimut/Elevation-Berechnung
(`core/gs_position.py`, bekannte Dreiecks-Geometrien → erwartete Winkel).
NMEA-Parser separat testbar mit aufgezeichneten Beispielsätzen (kein
echtes GPS-Gerät nötig). Demo-Modus: GS-Position lässt sich unabhängig vom
Telemetrie-Worker testen (reiner Rechen-/Anzeige-Layer), kein
Demo-Worker-Zusatz nötig.

**Handbuch-Abschnitt:** Neuer Abschnitt "Bodenstations-Position" im
Kapitel zu Antennen-Tracker/Verbindung, mit der Klarstellung aus der
Scope-Klärung oben.

**Grober Aufwand:** 2.5-3 Tage.

---

### P2: MAVLink-STATUSTEXT-Konsole

**Ziel:** Eingehende STATUSTEXT-Meldungen (Prearm, EKF, Modus-Gründe) in
einem scrollbaren Panel mit Severity-Farben, Filter, Kopierfunktion, statt
sie wie heute stillschweigend zu verwerfen.

**Bestätigt:** `mavlink_worker.py:_apply_message()` (Zeile 98-157) hat
aktuell **keinen** `STATUSTEXT`-Zweig - jede STATUSTEXT-Nachricht wird von
`_apply_message()` komplett ignoriert (nicht in `TelemetryState` abgebildet,
da es kein Zeitreihen-Feld ist, sondern ein Ereignis-Log).

**Betroffene bestehende Dateien:** `telemetry/mavlink_worker.py` - neuer
`elif msg_type == "STATUSTEXT":`-Zweig, der aber NICHT `self._state`
mutiert (STATUSTEXT ist kein persistentes Feld), sondern ein zusätzliches
Signal emittiert.

**Neue Module:** `ui/statustext_console.py` - Overlay/Dock-Panel (wie
`ui/track_overlay.py`), `QListWidget` oder `QPlainTextEdit` mit
Severity-Färbung (MAVLink `severity` 0-7, EMERGENCY..DEBUG), Textfilter,
"Kopieren"-Knopf.

**Datenfluss/Integrationspunkt:** `TelemetryWorker` bekommt ein neues Signal
`status_text_received = pyqtSignal(int, str)` (severity, text) - **nicht**
über `telemetry_received`/`TelemetryState`, da STATUSTEXT ein Ereignis ist,
kein Zustandsfeld (Vermischen würde `TelemetryState` mit Log-Historie
überladen). CRSF hat kein STATUSTEXT-Äquivalent - Signal wird dort nie
emittiert, Panel bleibt leer/inaktiv (nicht ausgegraut nötig, füllt sich
einfach nicht).

**UI-/Menüänderungen:** Neuer Sichtbarkeits-Toggle unter
`Telemetrie & Hardware`, Panel als dockbares Overlay wie die anderen.

**Neue Settings-Keys:** `ui_state.json`: `statustext_console_visible`,
`_size`/`_docked` wie üblich, `statustext_min_severity` (Filter-Voreinstellung).

**Risiken/Sonderfälle:** Sehr gesprächige FCs können viele STATUSTEXT/s
senden - Panel braucht eine Obergrenze (wie `MAX_PATH_POINTS` beim
Flugpfad) gegen unbegrenztes Wachstum.

**Testansatz:** Unit-Test für den neuen `_apply_message()`-Zweig (Severity/
Text korrekt extrahiert, `TelemetryState` bleibt unverändert). Demo-Modus:
`DemoWorker` bekommt optional ein paar synthetische STATUSTEXT-artige
Beispielmeldungen (rotierend), damit das Panel im Demo-Betrieb sichtbar ist.

**Handbuch-Abschnitt:** Neuer Abschnitt im Telemetrie-Kapitel.

**Grober Aufwand:** 1-1.5 Tage (kleinstes der P2-Features).

---

### P2: Erweiterter Modell-Editor

**Ziel:** Ein einziger, direkter Editor für die Parameter eines Modell-Profils
(Akkutyp inkl. Zellenzahl 1S-8S und Chemie LiPo/Li-Ion, Fahrzeugtyp
Quad/Wing/Plane, plus die bereits vorhandenen Geofence-/Energiebudget-Felder),
erreichbar sowohl über das Dropdown im Telemetriebereich als auch über den
Modell-Manager - statt wie heute indirekt über mehrere separate Dialoge plus
"aktuellen Live-Zustand speichern".

**Bestätigter Ist-Zustand (Grund, warum das ein eigenes Feature ist, kein
Bugfix):** Es gibt aktuell **keinen** Dialog, der Modell-Parameter direkt
bearbeitet. `ui/model_profile_dialog.py`s `ModelProfileDialog` ist nur eine
Liste (Speichern/Laden/Löschen); die tatsächlichen Werte kommen aus dem
*aktuell laufenden* Live-Zustand der App (`MainWindow._build_current_model_profile()`,
main_window.py) - Akku-Chemie/-Zellen/-Spannungen über `BatterySettingsDialog`,
Geofence über `GeofenceSettingsDialog`, Energiebudget-Geschwindigkeitsannahme
über `EnergyBudgetSettingsDialog`, jeweils eigene Menüpunkte unter
`Telemetrie & Hardware`. Ein Profil "bearbeiten" heißt heute: laden, in
mehreren verschiedenen Dialogen ändern, erneut unter demselben Namen
speichern. Und: **`vehicle_type` ist aktuell gar kein `ModelProfile`-Feld** -
es ist eine rein globale Menüeinstellung (`MainWindow._vehicle_group`,
main_window.py:623ff, `VEHICLE_TYPES = (("vehicle_quad","quad"),
("vehicle_wing","wing"),("vehicle_plane","plane"))`), unabhängig davon,
welches Modell gerade im Dropdown ausgewählt ist - genau die Lücke, die die
Anforderung "Type Wing/Quad soll mit dem Map Vehicle Type verbunden sein"
schließt.

**Betroffene bestehende Dateien:**
- `core/model_profiles.py` - neues Feld `vehicle_type: str = "quad"` auf
  `ModelProfile` (Batterie-Zellenzahl/-Chemie-Felder existieren schon,
  keine Schema-Änderung dort nötig, nur eine engere UI-Beschränkung auf
  1-8S statt des aktuellen `BatterySettingsDialog`-Bereichs 1-24).
- `ui/main_window.py` - `_build_current_model_profile()` /
  `_apply_model_profile()` um `vehicle_type` erweitern (exakt das gleiche
  Muster wie beim Geofence-`enabled`-Merge diese Session: das Menü-
  Actiongroup bleibt einzige Quelle der Wahrheit, `_apply_model_profile()`
  ruft `self._vehicle_group`s passende Action's `setChecked(True)` auf,
  nicht direkt `self._map.set_vehicle_type(...)`, damit Menü-Häkchen und
  Live-Zustand nie auseinanderlaufen - siehe `_on_geofence_enabled_toggled`
  als Vorbild).
- `ui/dashboard.py` - Dropdown bekommt einen zusätzlichen "Bearbeiten"-Weg
  (siehe UI unten); `_on_model_combo_activated()` ist die Stelle, an der
  heute schon zwischen "neues Profil" (Sentinel) und "Profil laden"
  unterschieden wird.
- `ui/model_profile_dialog.py` - bekommt einen "Bearbeiten..."-Button
  neben Laden/Löschen, der den neuen Editor-Dialog für das in der Liste
  markierte Profil öffnet, ohne es erst in den Live-Zustand zu laden.

**Neue Module:** `ui/model_editor_dialog.py` - ein `QDialog`, der die Felder
direkt auf einem `ModelProfile`-Objekt bearbeitet (nicht auf Live-App-
Zustand!) und ein bearbeitetes `ModelProfile` zurückgibt:
- Batterie: Chemie (LiPo/Li-Ion, wie `BatterySettingsDialog`) + Zellenzahl
  als `QComboBox` mit Einträgen "1S".."8S" statt freiem Spinbox-Bereich +
  Nennkapazität (mAh) - Warn-/Kritisch-Spannung pro Zelle entweder wie
  bisher separat editierbar oder (einfacher, empfohlen) automatisch aus
  `CHEMISTRY_DEFAULTS` (`alerts/tts_alert.py`) vorbelegt, wenn die Chemie
  gewechselt wird - exakt die Logik, die `BatterySettingsDialog._apply_chemistry_defaults()`
  heute schon hat, hier wiederverwendet statt dupliziert.
- Fahrzeugtyp: `QComboBox`/Radiogroup Quad/Wing/Plane, mit den bereits
  vorhandenen SVG-Icons aus `ui/map_template.py`s `vehicleIcons` (bzw.
  `ui/maplibre_template.py`s Äquivalent) als Vorschau - kein neues
  Icon-Set nötig.
- Geofence + Energiebudget-Geschwindigkeitsannahme: dieselben Felder wie
  in `GeofenceSettingsDialog`/`EnergyBudgetSettingsDialog`, hier
  konsolidiert - jene beiden Dialoge könnten danach entweder bestehen
  bleiben (schnelle Einzel-Anpassung ohne den großen Editor zu öffnen)
  oder entfernt werden; Empfehlung: bestehen lassen, da sie klein sind
  und "schnell nur die Geofence-Reichweite ändern" nicht den großen
  Editor erfordern sollte.

**Datenfluss/Integrationspunkt:**
- Dropdown-Weg: neuer Menüpunkt/Knopf "Modell bearbeiten..." direkt neben
  dem Dropdown (`ui/dashboard.py`), aktiv wenn ein echtes Profil (nicht
  "kein Profil"/"Neu") gewählt ist - öffnet `ModelEditorDialog` mit dem
  aktuell geladenen `ModelProfile` (via `load_profiles()[name]`), auf
  "Speichern" wird `save_profiles()` aktualisiert UND, falls es das gerade
  aktive Profil ist, sofort per `_apply_model_profile()` live angewendet
  (Fahrzeugtyp auf der Karte wechselt sofort, wie es die Anforderung
  "soll mit dem Map Vehicle Type verbunden sein" erwarten lässt).
- Modell-Manager-Weg: `ModelProfileDialog` bekommt denselben
  `ModelEditorDialog`, aufgerufen für das markierte (nicht notwendig
  aktive) Profil in der Liste - Bearbeiten eines *nicht* geladenen
  Profils ändert nur die gespeicherte Datei, keinen Live-Zustand.
- Neu angelegte Profile ("+ Neues Modell anlegen"): statt wie heute nur
  den aktuellen Live-Zustand unter neuem Namen zu speichern, öffnet der
  Sentinel-Eintrag künftig direkt den `ModelEditorDialog` mit
  Default-Werten - der Nutzer definiert ein neues Modell, statt vorher
  erst alle Einzeldialoge durchzuklicken.

**UI-/Menüänderungen:** Kein neuer Top-Level-Menüpunkt nötig - "Bearbeiten"
ist ein Knopf/Icon direkt neben dem Dashboard-Dropdown und ein Button im
Modell-Manager-Dialog.

**Neue Settings-Keys:** `ModelProfile.vehicle_type: str = "quad"` (einziges
neues Feld - alle anderen Editor-Felder existieren im Schema schon).

**Risiken/Sonderfälle:**
- Zellenzahl-Range einschränken (1-8S) ist eine bewusste UX-Vereinfachung,
  aber ein Bruch mit dem bisherigen `BatterySettingsDialog`-Bereich
  (1-24) - falls ein Nutzer real >8S fliegt, bräuchte es einen Fallback
  (z.B. "8S+" mit weiterhin freiem Spinbox-Feld) - im Zweifel beim
  Umsetzen gegenprüfen, ob 8S als Hard-Cap wirklich gewünscht ist oder nur
  als UI-Vorbelegung/Regel-Fall.
- Fahrzeugtyp-Wechsel für das *aktive* Profil muss denselben Sync-Pfad wie
  jeder andere Menü-getriebene Wechsel nehmen (Actiongroup zuerst, Karte
  reagiert auf deren Signal) - nicht direkt `self._map.set_vehicle_type()`
  aus dem neuen Dialog heraus aufrufen, sonst laufen Menü-Häkchen und
  Karte auseinander (derselbe Bug-Typ, den der Geofence-`enabled`-Merge
  diese Session bewusst vermieden hat).
- Bearbeiten eines Profils, das gerade NICHT aktiv ist, darf keinerlei
  Live-Zustand (Dashboard-Felder, Karte, Akku-Monitor) berühren - nur die
  gespeicherte Datei.

**Testansatz:** Unit-Tests für `ModelEditorDialog`s Rückgabewert (reines
`ModelProfile`-Objekt, kein Qt-Live-Zustand nötig zum Testen der
Feld-zu-Profil-Zuordnung) und für die Chemie→Default-Spannungen-Vorbelegung
(Wiederverwendung von `CHEMISTRY_DEFAULTS`). Manueller Test für den
Live-Sync-Pfad (Fahrzeugtyp-Änderung am aktiven Profil ändert sofort das
Kartensymbol + das Menü-Häkchen bleibt konsistent).

**Handbuch-Abschnitt:** Bestehenden Abschnitt zu Modell-Profilen erweitern
statt neuen Abschnitt anzulegen.

**Grober Aufwand:** 2.5-3 Tage.

---

### Kleinere Menü-Aufräumarbeiten (im Rahmen von P2 miterledigen)

Beide sind reine Standortverschiebungen bestehender Menüpunkte in
`ui/main_window.py`, keine Verhaltensänderung - passend zu erledigen, wenn
für den Modell-Editor/STATUSTEXT-Konsole ohnehin an denselben Menüs
gearbeitet wird:

- **"Zeiteinheit (Höhenverlauf)"** (`altitude_track_unit_menu`, aktuell unter
  `Anzeige & Karte` / `view_map_menu`, main_window.py:592) nach
  `Telemetrie & Hardware` (`telemetry_menu`) verschieben.
- **"Dashboard anpassen..."** (`self._dashboard_settings_action`, aktuell
  als *eine* QAction in zwei Menüs gleichzeitig eingehängt - `Einstellungen`
  und `Anzeige & Karte`, main_window.py:747-751) zusätzlich auch in
  `Telemetrie & Hardware` einhängen (`telemetry_menu.addAction(self._dashboard_settings_action)`,
  gleiches Wiederverwendungs-Muster wie die bestehende Doppel-Einhängung -
  eine dritte `addAction()` auf dieselbe Instanz, keine neue Action nötig).

---

### P3 — nur grob skizziert

Ausgewählt für die nächste Umsetzungsrunde (die übrigen, ursprünglich hier
grob skizzierten Punkte wurden nach P4 verschoben, siehe unten):

- **Windschätzung**: aus Ground-/Airspeed-Differenz falls beide vorhanden
  (aktuell nur `groundspeed` in `TelemetryState` - Airspeed müsste als neues
  Feld dazukommen, falls MAVLink `VFR_HUD.airspeed` ausgewertet wird, was
  `_apply_message()` aktuell nicht tut).
- **PMTiles-Bündelung/Pfadauflösung für die .exe reparieren** (aktuell
  ein echter, im Betrieb entdeckter Defekt, kein Wunsch-Feature): Die
  Vektorkarte (MapLibre) rendert in der gebauten `.exe` permanent
  schwarz, weil zwei Dinge zusammenkommen: (1) `dev_data/pmtiles/*.pmtiles`
  ist per `.gitignore` bewusst nicht versioniert und wird von
  `ELRS_GroundStation.spec` nicht als PyInstaller-`datas`-Eintrag
  mitgebündelt, und (2) selbst wenn eine Datei manuell danebengelegt
  würde, ist `ui/map_widget.py`s `_DEV_DATA_DIR = Path(__file__).resolve()
  .parent.parent / "dev_data" / "pmtiles"` relativ zur (eingefrorenen)
  Quellstruktur berechnet, nicht relativ zum tatsächlichen `.exe`-
  Verzeichnis - in einer PyInstaller-`.exe` zeigt `Path(__file__)` in den
  temporären Extraktionsordner (`sys._MEIPASS`), sodass der Pfad dort
  ohnehin nie existiert. Beide Punkte müssen behoben werden: (a)
  Pfadauflösung umstellen auf einen Ordner neben der echten
  `.exe`/`sys.executable` (via `sys.frozen`-Check, analog zu
  `core/resources.py:resource_path()`s vermutlich schon vorhandenem
  Muster für gebündelte Assets - prüfen und wiederverwenden statt
  duplizieren), und (b) eine echte Auslieferung der Regionsdaten klären:
  entweder mindestens eine Region als PyInstaller-`datas`-Eintrag
  mitbündeln (vergrößert die `.exe` erheblich, siehe Dateigrößen in
  Schritt 1 der ursprünglichen MapLibre-Analyse), oder - vermutlich
  sinnvoller - einen "Region herunterladen/auswählen"-Dialog bauen, der
  in ein Nutzerverzeichnis (`~/.elrs_ground_station/pmtiles/`, analog zu
  `tile_cache/`) lädt, statt überhaupt etwas mitzuliefern. Bis dahin
  bleibt "Vektorkarte" in `menu_geofence_visible`-ähnlichem Sinne ein rein
  Quellcode-/Entwicklungsmodus-Feature - sollte im Kartentyp-Menü oder im
  Handbuch als "experimentell, nur aus dem Quellcode lauffähig" markiert
  werden, bis dieser Punkt umgesetzt ist.

### P4 — zurückgestellt, nur grob skizziert

Ursprünglich Teil der P3-Skizze, auf Nutzerentscheidung zurückgestellt, bis
P3 (Windschätzung, PMTiles-Fix) abgeschlossen ist:

- **Auto-Reconnect/Watchdog**: `_start_worker()` neu aufrufen nach
  UDP/Serial-Abriss, mit Backoff; Hook: `error_occurred`/`connection_changed`
  in `main_window.py`.
- **Zusätzliche Sprachwarnungen** (LQ-Schwelle, GPS-Fix verloren,
  Modus-Wechsel): je ein kleiner Monitor nach dem etablierten Muster,
  gehängt an `_on_telemetry()`.
- **HDOP/Fix-Typ im Dashboard**: `GPS_RAW_INT.eph` (HDOP) wird aktuell nicht
  geparst - kleine Ergänzung in `_apply_message()` + neues
  `TelemetryState`-Feld.
- **Distanzringe auf der Karte**: reine JS-Ergänzung in beiden
  Kartentemplates, kein Backend nötig.
- **OSD-Overlay-Export aus dem Fluglog**: neues `export/`-Modul, nutzt
  dieselbe CSV wie Log-Replay.
- **Metrisch/Imperial-Umschaltung**: durchzieht praktisch jede
  Zahlenanzeige (Dashboard-Felder, Overlays, Exporte) - größerer,
  aber mechanischer Umbau; am ehesten sinnvoll als zentrale
  Formatierungsfunktion statt Umbau jeder einzelnen Anzeigestelle.

## Schritt 4 — Umsetzungsreihenfolge und Refactorings

### Nötige Refactorings vor/während der Umsetzung

1. **Telemetriequelle abstrahieren für Replay** (blockiert Log-Replay):
   `TelemetryState.source` existiert schon als freies Feld - Konvention
   `source == "replay"` einführen und `_on_telemetry()` an den drei
   Seiteneffekt-Stellen (Batterie-TTS, NFZ-Proximity-TTS, Tracker-Output,
   Live-Track-Aufzeichnung) davor schützen. Kleiner, gezielter Eingriff,
   keine große Abstraktionsschicht nötig - `TelemetryWorker`s Signal-Contract
   ist bereits generisch genug.
2. **MAVLink-Connection-Handle auf Instanzebene heben** (blockiert
   MAVLink-Rückkanal): `conn` in `MAVLinkWorker.run()` wird `self._conn`,
   Senden über eine neue gequeuete Signal/Slot-Verbindung statt direktem
   Cross-Thread-Zugriff (siehe Feature-Abschnitt oben für Details).
3. **Kein Refactoring nötig, aber Wiederholungsmuster ausnutzen**: jedes der
   drei neuen Sprachwarnungs-Features (Modell-verloren, Energiebudget-
   Umkehrpunkt, Geofence) braucht einen eigenen kleinen State-Monitor nach
   exakt dem `NfzProximityMonitor`/`BatteryAlertMonitor`-Muster - kein
   gemeinsamer Basis-Refactor nötig, da die Duplikation hier klein und die
   Logik pro Feature leicht unterschiedlich ist (Hysterese-Bedingung
   unterscheidet sich); eine gemeinsame Basisklasse wäre vorzeitige
   Abstraktion für drei Fälle.

### Abhängigkeiten zwischen Features

- **Modell-verloren-Modus (P1)** nutzt bevorzugt die Bodenstations-Position
  (P2) als Referenzpunkt, fällt aber sauber auf die bestehende
  Flugstart-Referenz zurück, solange P2 nicht existiert - **kein harter
  Blocker**, kann eigenständig zuerst gebaut werden.
- **Log-Replay (P2)** braucht Refactoring #1 zuerst.
- **MAVLink-Rückkanal (P2)** braucht Refactoring #2 zuerst.
- **Geofence (P1)** und **Energiebudget (P1)** haben keine Abhängigkeiten
  zu anderen Features hier.
- **STATUSTEXT-Konsole (P2)** ist komplett unabhängig, kleinster Aufwand -
  guter Kandidat, um früh Sicherheit über den i18n-/Overlay-Patternfit zu
  gewinnen, bevor die größeren Features drankommen.

### Vorgeschlagene Phasenreihenfolge

1. **Phase 1** (keine Abhängigkeiten, größter Sicherheitsnutzen zuerst):
   Geofence, Energiebudget, Modell-verloren-Modus (mit Flugstart-Referenz-
   Fallback) - alle drei P1, unabhängig voneinander parallelisierbar.
2. **Phase 2**: STATUSTEXT-Konsole (klein, unabhängig, guter Pattern-Check)
   + Refactoring #1, direkt gefolgt von Log-Replay.
3. **Phase 3**: Bodenstations-Position (schließt danach automatisch an
   Modell-verloren aus Phase 1 an, verbessert dessen Referenzpunkt
   rückwirkend ohne Codeänderung an Modell-verloren selbst).
4. **Phase 4**: Refactoring #2 + MAVLink-Rückkanal (größtes, riskantestes
   Feature, bewusst zuletzt).
5. **Phase 5**: P3-Punkte nach Bedarf/Priorität, unabhängig voneinander.

Jede Phase endet mit: i18n-Abdeckungscheck, vollem Testlauf, echtem
Demo-Start-Rauchtest, und - wo ein Feature das Kartentemplate ändert (NFZ/
Geofence-Rendering) - Test in **beiden** Renderern (Leaflet und das
experimentelle MapLibre), da beide Templates parallel gepflegt werden.
