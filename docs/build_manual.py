"""Regenerates docs/ELRS_Ground_Station_Benutzerhandbuch.pdf from the
content defined below. Run with: python docs/build_manual.py

Needs reportlab (`pip install reportlab`) - a doc-build tool, not a
runtime dependency of the app itself, so it's deliberately not listed in
requirements.txt. This script (plus its content list, kept in this same
file rather than a separate source format) is itself the manual's
"source" going forward - edit here and re-run, instead of editing the
compiled PDF directly (which isn't practically possible without it).
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

OUTPUT_PATH = Path(__file__).resolve().parent / "ELRS_Ground_Station_Benutzerhandbuch.pdf"
SCREENSHOTS_DIR = Path(__file__).resolve().parent / "screenshots"

# ----------------------------------------------------------------- styles

_base = getSampleStyleSheet()
STYLES = {
    "title": ParagraphStyle("title", parent=_base["Title"], fontSize=24, spaceAfter=6),
    "subtitle": ParagraphStyle("subtitle", parent=_base["Normal"], fontSize=13, alignment=1, spaceAfter=4),
    "meta": ParagraphStyle("meta", parent=_base["Normal"], fontSize=10, alignment=1, textColor=colors.grey),
    "h1": ParagraphStyle(
        "h1", parent=_base["Heading1"], fontSize=15, spaceBefore=14, spaceAfter=8, textColor=colors.HexColor("#1a3a5c")
    ),
    "h2": ParagraphStyle(
        "h2", parent=_base["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#1a3a5c")
    ),
    "body": ParagraphStyle("body", parent=_base["Normal"], fontSize=9.5, leading=13.5, spaceAfter=6),
    "bullet": ParagraphStyle(
        "bullet", parent=_base["Normal"], fontSize=9.5, leading=13.5, leftIndent=14, bulletIndent=4, spaceAfter=3
    ),
    "code": ParagraphStyle(
        "code", parent=_base["Normal"], fontName="Courier", fontSize=8.5, leading=11,
        backColor=colors.HexColor("#f2f2f2"), borderPadding=6, spaceAfter=8,
    ),
    "toc": ParagraphStyle("toc", parent=_base["Normal"], fontSize=10, leading=15, leftIndent=8),
    "caption": ParagraphStyle(
        "caption", parent=_base["Normal"], fontName="Helvetica-Oblique", fontSize=8, alignment=1,
        textColor=colors.grey, spaceBefore=2, spaceAfter=10,
    ),
}


def P(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, STYLES[style])


def bullets(items, style: str = "bullet"):
    return [Paragraph(f"&bull;&nbsp;&nbsp;{item}", STYLES[style]) for item in items]


def code(text: str) -> Preformatted:
    return Preformatted(text, STYLES["code"])


def figure(filename: str, caption: str, max_width_mm: float = 150):
    """A screenshot (docs/screenshots/<filename>) plus an italic caption
    beneath it, scaled to at most `max_width_mm` wide with its aspect
    ratio preserved (read from the actual PNG rather than guessed, so a
    re-cropped/re-taken screenshot never silently comes out stretched)."""
    path = SCREENSHOTS_DIR / filename
    intrinsic_width, intrinsic_height = ImageReader(str(path)).getSize()
    width = min(max_width_mm * mm, intrinsic_width)
    height = width * (intrinsic_height / intrinsic_width)
    img = Image(str(path), width=width, height=height)
    img.hAlign = "CENTER"
    return [Spacer(1, 4), img, P(caption, "caption")]


def simple_table(rows, col_widths=None):
    t = Table(rows, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe9f2")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b5c6d6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


# ---------------------------------------------------------------- content

TOC_ENTRIES = [
    "1. Einleitung",
    "2. Installation",
    "3. Erste Schritte",
    "4. Verbindung zur Telemetrie herstellen (inkl. Antennen-Tracker-Ausgabe, Modell-Profile)",
    "5. Offline-Nutzung (Longrange ohne Internet)",
    "6. Die Benutzeroberfläche",
    "7. Kartenoptionen (Vektorkarte als Standard, Satellitenbild/OpenStreetMap, Sperrzonen inkl. OpenAIP und Austro Control, Rechtsklick-Menü, Home-Position, Flugverkehr/ADS-B nur online)",
    "8. Route/Wegpunkte planen, Höhenprofil, Grid-Muster, INAV-Mission-Export",
    "9. Flugpfad-Aufzeichnung (Start/Pause/Export)",
    "10. Fluglog (CSV-Aufzeichnung)",
    "11. Plan-Modus",
    "12. Die Menüs im Detail",
    "13. Akkuwarnung: LiPo vs. Li-Ion",
    "14. Als eigenständige .exe kompilieren",
    "15. Anhang: Kommandozeilen-Referenz",
]

CLI_REFERENCE_ROWS = [
    ["Option", "Beschreibung"],
    ["--demo", "Im Simulationsmodus starten, keine Hardware nötig."],
    ["--protocol {mavlink,crsf}", "Telemetrieprotokoll (Standard: zuletzt verwendet, sonst CRSF/ExpressLRS)."],
    ["--connection {udp,usb}", "Transportweg (Standard: zuletzt verwendet, sonst USB)."],
    ["--host", "Bind-Adresse für UDP-Empfang (Standard: zuletzt verwendet, sonst 0.0.0.0)."],
    ["--port", "UDP-Port (Standard: zuletzt verwendet, sonst 14550 MAVLink / 14551 CRSF)."],
    ["--udp-mode {listen,connect}", "listen wartet auf Pakete, connect verbindet aktiv zu Host:Port (Standard: zuletzt verwendet, sonst listen)."],
    ["--serial-port", "USB/seriell-Port bei --connection usb, z. B. COM5 (Standard: zuletzt verwendeter Port)."],
    ["--baud", "Baudrate bei USB (Standard: zuletzt verwendet, sonst 57600 MAVLink / 420000 CRSF)."],
    ["--list-ports", "Verfügbare USB/seriell-Ports auflisten und beenden."],
    ["--cells", "Anzahl LiPo/Li-Ion-Zellen für die Akku-Warnschwellen."],
    ["--low-cell-voltage", 'Zellspannung für die "niedrig"-Warnung.'],
    ["--critical-cell-voltage", 'Zellspannung für die "kritisch"-Warnung.'],
    ["--demo-center lat,lon", "Mittelpunkt der Demo-Flugbahn."],
    ["--lang {de,en}", "Startsprache der Oberfläche."],
]


def build_story():
    story = []

    # --- title page ---
    story.append(Spacer(1, 60 * mm))
    story.append(P("ELRS Ground Station", "title"))
    story.append(P("Benutzerhandbuch", "subtitle"))
    story.append(P("Ein schlanker Ground-Control-Bildschirm für", "subtitle"))
    story.append(P("ExpressLRS (ELRS) Modelle", "subtitle"))
    story.append(Spacer(1, 10 * mm))
    story.append(P("Stand: September 2026", "meta"))
    story.append(P("github.com/KresserSimon/ELRS_Telemetry_Groundcontroll", "meta"))
    story.append(PageBreak())

    # --- table of contents ---
    story.append(P("Inhalt", "h1"))
    for entry in TOC_ENTRIES:
        story.append(P(f"&bull;&nbsp;&nbsp;{entry}", "toc"))
    story.append(NextPageTemplate("content"))
    story.append(PageBreak())

    # --- 1. Einleitung ---
    story.append(P("1. Einleitung", "h1"))
    story.append(P(
        "ELRS Ground Station ist eine leichtgewichtige Alternative zu Mission Planner oder "
        "QGroundControl für Modelle mit ExpressLRS (ELRS). Die App zeigt live auf einer "
        "Vektorkarte (Standard) oder einer OpenStreetMap-/Satellitenkarte, wo sich das Modell "
        "befindet, stellt alle wichtigen Telemetriedaten (GPS, Akku, Funkverbindung, Sensoren) in "
        "einem übersichtlichen Dashboard dar, warnt per Sprachausgabe bei niedrigem Akkustand und "
        "erlaubt es, Flugpfade aufzuzeichnen, Routen/Wegpunkte zu planen und als INAV-Mission zu "
        "exportieren."
    ))
    story.append(P("Die App funktioniert mit zwei Telemetrie-Protokollen:"))
    story.extend(bullets([
        "<b>MAVLink</b> - ausgegeben von Flugsteuerungen wie ArduPilot, iNav oder Betaflight, die "
        "per CRSF-Telemetrie mit dem ELRS-Empfänger verbunden sind.",
        "<b>CRSF (Crossfire)</b> - das native Telemetrieprotokoll von ExpressLRS. CRSF wurde "
        "ursprünglich von TBS (Team BlackSheep) für deren Crossfire-Funksystem entwickelt; "
        "ExpressLRS verwendet bewusst dasselbe Frameformat, sodass die App auch mit echter "
        "TBS-Crossfire-Hardware funktioniert.",
    ]))
    story.append(P(
        "Beide Protokolle lassen sich sowohl über WiFi (UDP) als auch über eine direkte "
        "USB/seriell-Verbindung empfangen, umschaltbar zur Laufzeit ohne Neustart der App."
    ))

    # --- 2. Installation ---
    story.append(P("2. Installation", "h1"))
    story.append(P("Voraussetzung ist Python 3.10 oder neuer. Im Projektordner:"))
    story.append(code(
        "cd elrs_ground_station\n"
        "python -m venv .venv\n"
        ".venv\\Scripts\\activate\n"
        "pip install -r requirements.txt"
    ))
    story.append(P(
        "Die requirements.txt installiert PyQt6 (inkl. WebEngine für die Karte und WebChannel für "
        "die Interaktion mit der Karte), pymavlink, pyttsx3 (Sprachausgabe), pyserial "
        "(USB-Verbindungen) und pmtiles (Lesen/Extrahieren von Vektorkarten-Regionsdateien). Unter "
        "Windows nutzt pyttsx3 die eingebaute SAPI5-Sprachausgabe - es sind keine zusätzlichen "
        "Systempakete nötig."
    ))
    story.append(P(
        "Alternativ steht eine fertig kompilierte .exe zur Verfügung (siehe Abschnitt 14), die "
        "ohne Python-Installation läuft."
    ))

    # --- 3. Erste Schritte ---
    story.append(P("3. Erste Schritte", "h1"))
    story.append(P("Zum unverbindlichen Ausprobieren ohne jegliche Hardware:"))
    story.append(code("python main.py --demo"))
    story.append(P(
        "Der Demo-Modus simuliert einen Loiter-Kreisflug inklusive Akku-Entladung, "
        "Roll/Pitch-Bewegung, wechselnden Flugmodi und schwankender Funkverbindung, sodass sich "
        "alle Funktionen der App - einschließlich der Sprachwarnung bei niedrigem Akku - ohne "
        "echtes Modell testen lassen."
    ))
    story.append(P(
        "Wird die App ohne --demo gestartet, öffnet sich zunächst ein Popup zur Auswahl von "
        "Verbindung (WiFi/UDP oder USB) und Protokoll (MAVLink oder CRSF). Ein Klick auf "
        "Abbrechen übernimmt einfach die per Kommandozeile übergebenen bzw. die "
        "Standard-Einstellungen; zwei eigene Buttons im Popup starten stattdessen direkt den "
        "Demo- bzw. den Plan-Modus (siehe Abschnitt 11) - ohne jede Telemetrieverbindung."
    ))
    story.append(P(
        "Das Popup merkt sich die zuletzt tatsächlich verwendete Verbindung (Protokoll, "
        "Transportweg, USB-Port/Baudrate bzw. Host/Port/Modus bei WiFi) und schlägt sie beim "
        "nächsten Start automatisch wieder vor - ein erneutes Durchklicken jedes Mal ist nicht "
        "nötig. Wurde noch nie eine Verbindung hergestellt (z. B. direkt nach der Installation), "
        "sind CRSF (ExpressLRS) und USB/Seriell voreingestellt, da das der für die meisten "
        "ELRS-Nutzer naheliegendste Startpunkt ist. Über die Kommandozeile explizit übergebene "
        "Optionen (z. B. --protocol mavlink) haben immer Vorrang vor der gemerkten Einstellung."
    ))

    # --- 4. Verbindung zur Telemetrie herstellen ---
    story.append(P("4. Verbindung zur Telemetrie herstellen", "h1"))
    story.append(P(
        "ELRS-Hardware spricht kein natives 'Telemetrie-über-WiFi' - das eingebaute WiFi eines "
        "ELRS-Moduls dient primär dem Flashen/Konfigurieren (Access Point ExpressLRS "
        "TX/ExpressLRS RX, Standardpasswort expresslrs). Um Telemetrie tatsächlich zu dieser App "
        "zu bekommen, gibt es drei Wege:"
    ))
    story.append(P("Weg 1: MAVLink über WiFi (empfohlen)", "h2"))
    story.append(P(
        "Voraussetzung ist eine Flugsteuerung mit MAVLink-Ausgabe, die per CRSF-Telemetrie mit "
        "dem ELRS-Empfänger verbunden ist. Der serielle MAVLink-Strom der Flugsteuerung muss per "
        "WiFi-Bridge (z. B. ein ESP32/ESP8266 mit MAVESP8266-Firmware) auf UDP-Port 14550 "
        "gebracht werden."
    ))
    story.append(code("python main.py --protocol mavlink --host 0.0.0.0 --port 14550"))
    story.append(P("Muss die Bridge stattdessen aktiv eine Verbindung zum PC aufbauen: --udp-mode connect --host &lt;IP-der-Bridge&gt;"))
    story.append(P("Weg 2: Rohes CRSF/TBS-Crossfire über WiFi", "h2"))
    story.append(P(
        "Manche ELRS-'Backpack'-Bridges (ESP32-basiert) leiten den rohen CRSF-Bytestrom direkt "
        "per UDP weiter, ohne Umweg über MAVLink."
    ))
    story.append(code("python main.py --protocol crsf --host 0.0.0.0 --port 14551"))
    story.append(P(
        "Dieser Modus deckt GPS (inkl. Geschwindigkeit), Akku (Spannung/Strom/Restkapazität/"
        "verbrauchte mAh), Link-Statistiken, Attitude (Roll/Pitch) sowie - falls gesendet - "
        "Vario, Baro-Höhe, RPM, Temperatur und Zellspannungen ab."
    ))
    story.append(P("Weg 3: USB/seriell", "h2"))
    story.append(P("Flugsteuerung oder ELRS TX-Modul per USB-Kabel direkt an den PC anschließen. Verfügbare Ports zunächst auflisten:"))
    story.append(code(
        "python main.py --list-ports\n"
        "python main.py --connection usb --protocol mavlink --serial-port COM5\n"
        "python main.py --connection usb --protocol crsf --serial-port COM5 --baud 420000"
    ))
    story.append(P(
        "Standard-Baudrate: 57600 für MAVLink, 420000 für CRSF (jeweils per --baud "
        "überschreibbar). Diese Verbindungsart ersetzt Weg 1/2, ist kein Zusatz dazu."
    ))
    story.append(P(
        "Die Port-Liste im Verbindungs-Popup wird beim Öffnen automatisch aktualisiert. "
        "Schlägt die Windows-USB-Geräteerkennung dabei für ein angeschlossenes Gerät fehl "
        "(kam z. B. bei manchen RadioMaster-Sendern im Joystick/Seriell-Kombimodus vor und "
        "ließ die App beim Start abstürzen), bleibt die Liste für den betroffenen Port "
        "seit diesem Fix einfach leer, statt die App zu beenden."
    ))
    story.append(P(
        "In allen WiFi-Fällen müssen PC und Bridge/Modul im selben Netzwerk sein. Alle drei Wege "
        "lassen sich auch nachträglich über Telemetrie & Hardware -&gt; Verbindung... ändern, "
        "ohne die App neu zu starten."
    ))
    story.append(P("4.4 Antennen-Tracker-Ausgabe", "h2"))
    story.append(P(
        "Telemetrie & Hardware -&gt; Antennen-Tracker / Telemetrie-Ausgabe... sendet die "
        "Live-Position laufend an ein externes Antennen-Tracker-Gerät weiter - nützlich, um eine "
        "gerichtete Empfangsantenne automatisch dem Modell nachführen zu lassen. Zwei Formate "
        "stehen zur Wahl:"
    ))
    story.extend(bullets([
        "<b>MAVLink</b> (GLOBAL_POSITION_INT) - das Format, das z. B. ArduPilot-Antenna-Tracker-Firmware erwartet.",
        "<b>NMEA</b> ($GPGGA) - ein weit verbreitetes GPS-Sentenzformat mit Prüfsumme, das viele einfachere Tracker verstehen.",
    ]))
    story.append(P(
        "Beide Formate lassen sich wahlweise über einen seriellen Port oder per UDP senden. "
        "Start und Stopp erfolgen direkt im Dialog, ohne die App neu zu starten; die Ausgabe "
        "läuft dann bei jedem eingehenden Telemetrie-Update automatisch mit."
    ))
    story.append(P("4.5 Modell-Profile", "h2"))
    story.append(P(
        "Wer mehrere Modelle mit unterschiedlichen Akkus und Dashboard-Vorlieben fliegt, kann "
        "diese unter Telemetrie & Hardware -&gt; Modell-Profile verwalten... als benannte Profile "
        "speichern: jedes Profil bündelt Akku-Chemie, Zellenzahl, die genauen "
        "Warn-/Kritisch-Spannungen, die Nennkapazität des Akkus (mAh), Fahrzeugtyp (Quadrocopter/"
        "Wing/Flugzeug) sowie die aktuelle Dashboard-Feldauswahl und -Anordnung. Ein Klick auf "
        "Laden wendet ein gespeichertes Profil sofort an - genau dieselben Einstellungen, die "
        "auch die Dialoge Akkuwarnung... und Dashboard anpassen... einzeln setzen würden."
    ))
    story.append(P(
        "Schneller geht es über das Modellauswahl-Dropdown direkt oben in der Telemetrie-Leiste "
        "(siehe Abschnitt 6.2): ein gespeichertes Profil auswählen wendet sofort dessen "
        "Akku-Schwellwerte auf Anzeige und Sprachwarnung an, ohne den Dialog überhaupt zu "
        "öffnen. Der kleine Stift-Button daneben öffnet den erweiterten Modell-Editor direkt für "
        "das gewählte Profil (Akku-Chemie, Zellenzahl, Fahrzeugtyp und Geofence-Werte auf einen "
        "Blick). Der Eintrag \"+ Neues Modell anlegen\" im selben Dropdown öffnet direkt den "
        "Modell-Editor zum Anlegen eines neuen Profils."
    ))

    # --- 5. Offline-Nutzung ---
    story.append(P("5. Offline-Nutzung (Longrange ohne Internet)", "h1"))
    story.append(P(
        "Die App ist für den Feldeinsatz gebaut, wo oft kein Internet zur Verfügung steht. "
        "Telemetrieempfang, Dashboard, künstlicher Horizont, Wegpunkt-Planung/-Editor, "
        "Sperrzonen-Anzeige und -Distanzwarnung, Sprachwarnungen, Fluglog, Track-Aufzeichnung, "
        "Antennen-Tracker-Ausgabe und Modell-Profile funktionieren vollständig ohne "
        "Internetverbindung - auch die Karte selbst ist fest in die App eingebettet und lädt "
        "nicht mehr von einem CDN nach. Drei Dinge brauchen ursprünglich eine Verbindung, werden "
        "inzwischen aber alle auf die Festplatte gecacht und danach auch offline aus dem Cache "
        "bedient - jeder erfolgreiche Online-Abruf aktualisiert den jeweiligen Cache automatisch "
        "für das nächste Mal:"
    ))
    story.extend(bullets([
        "<b>Kartenkacheln</b> (OpenStreetMap/Satellit) - jede einmal angezeigte Kachel landet "
        "unter ~/.elrs_ground_station/tile_cache und wird beim nächsten Aufruf, auch offline, "
        "von dort geladen statt erneut vom Kartenserver abgerufen zu werden. Nur Gebiete, die "
        "noch nie online angezeigt wurden, bleiben ohne Internet leer/grau.",
        "<b>Höhenprofil der Route</b> (Open-Elevation-Abfrage, siehe Abschnitt 8.4) - bereits "
        "abgefragte Punkte werden unter ~/.elrs_ground_station/elevation_cache.json gecacht; nur "
        "wirklich neue Punkte brauchen einen erneuten Online-Abruf, schlägt dieser fehl, "
        "erscheint im Dialog eine Fehlermeldung statt eines Absturzes.",
        "<b>OpenAIP-Sperrzonen laden</b> (siehe Abschnitt 7.2) - die zuletzt heruntergeladenen "
        "Zonen für eine Region werden unter ~/.elrs_ground_station/openaip_cache.json gecacht; "
        "schlägt ein erneuter Download fehl, werden automatisch die zwischengespeicherten Zonen "
        "weiterverwendet.",
    ]))
    story.append(P(
        "Empfohlen für den Longrange-Einsatz: die App vor der Abfahrt einmal zuhause mit "
        "Internetverbindung im geplanten Fluggebiet öffnen (Karte ansehen, Höhenprofil/"
        "OpenAIP-Zonen laden), damit die Caches gefüllt sind und im Feld alles ohne Verbindung "
        "verfügbar ist."
    ))
    story.append(P(
        "Die Vektorkarte (siehe Abschnitt 7.1, der Standard-Kartentyp) hat eine andere "
        "Offline-Logik als die Raster-Karte oben: eine Regions-Datei enthält von vornherein die "
        "kompletten Kartendaten für das ganze Land, es muss also - anders als beim Kachel-Cache "
        "oben - vorher gar nichts online besucht werden, sobald die Region einmal heruntergeladen "
        "ist. Der Download selbst (Anzeige & Karte -&gt; Kartentyp -&gt; Vektorkarten-Region "
        "herunterladen...) braucht naturgemäß einmalig eine Internetverbindung; danach ist die "
        "Region dauerhaft offline nutzbar, ohne erneuten Download."
    ))

    # --- 6. Die Benutzeroberfläche ---
    story.append(P("6. Die Benutzeroberfläche", "h1"))
    story.append(P("6.1 Die Karte", "h2"))
    story.append(P(
        "Zeigt die Live-Position des Modells auf der Karte (Vektorkarte als Standard, alternativ "
        "OpenStreetMap oder Esri-Satellitenbild - Anzeige & Karte -&gt; Kartentyp), mit:"
    ))
    story.extend(bullets([
        "Nachgezogenem, orangefarbenem Flugpfad seit Verbindungsbeginn.",
        "Einem Häuschen-Symbol an der Home-Position (dem ersten empfangenen GPS-Fix der laufenden Sitzung).",
        "Einem wählbaren Fahrzeugsymbol (Quadrocopter, Wing, Flugzeug), das sich mit der Kompassrichtung mitdreht.",
        "<b>Auto-Center</b>: die Karte folgt automatisch der aktuellen Position - abschaltbar per "
        "Menü oder per Klick auf den Lock-Button direkt auf der Karte (Google-Maps-Stil).",
        "<b>Kartenausrichtung</b>: ein zweiter fixer Kartenbutton schaltet zwischen Norden-oben "
        "und Drohnenrichtung-oben um. Im letzteren Modus dreht sich die gesamte Karte "
        "kontinuierlich mit dem aktuellen Kurs, während das Drohnensymbol selbst immer nach oben "
        "zeigt.",
        "Einer optionalen, per Klick oder Rechtsklick gezeichneten bzw. importierten Route "
        "(grün, gestrichelt, nummerierte Wegpunkte).",
        "Optional angezeigten No-Fly-Zones (rote Kreise/Polygone, siehe Abschnitt 7.2).",
    ]))
    story.append(P(
        "Home-Symbol, Wegpunkt-Nummern, Segment-Distanzangaben und Sperrzonen-Namen bleiben bei "
        "gedrehter Karte stets aufrecht und lesbar. Bei den Raster-Karten (OpenStreetMap/"
        "Satellit) drehen sich die in die Kartenkacheln selbst eingebrannten Orts-/Straßennamen "
        "zwangsläufig mit der Karte mit, da sie Teil des Kachelbilds sind - das betrifft jede "
        "rasterbild-basierte Kartendrehung, auch bei Luftfahrt- und Marine-Navigationsgeräten. "
        "Bei der Vektorkarte (siehe Abschnitt 7.1, Standard) bleiben auch die Orts-/Straßennamen "
        "selbst aufrecht."
    ))
    story.append(P("6.2 Das Dashboard", "h2"))
    story.append(P(
        "Oben in der Telemetrie-Leiste sitzt ein Modellauswahl-Dropdown: es listet alle "
        "gespeicherten Modell-Profile (siehe Abschnitt 4.5), eine Auswahl wendet sofort die "
        "passenden Akku-Schwellwerte an, und ein Eintrag \"+ Neues Modell anlegen\" öffnet direkt "
        "den Modell-Editor. Darunter zeigt die Telemetrie-Leiste alle Telemetriedaten gruppiert an:"
    ))
    story.append(simple_table(
        [
            ["Gruppe", "Felder"],
            ["GPS", "Breitengrad, Längengrad, Höhe, Satellitenanzahl"],
            ["Status", "Flugmodus"],
            ["Link", "RSSI, Link-Qualität (LQ), SNR, Sendeleistung"],
            ["Akku", "Spannung, Restkapazität, Min-Zellspannung, Strom, verbrauchte Kapazität (mAh)"],
            ["Sensoren", "Vario, Baro-Höhe, RPM, Temperatur"],
            ["Long-Range", "Geschwindigkeit, Wind, Entfernung/Peilung zur Home-Position, Flugzeit, Energiebudget, Azimut/Elevation (Bodenstation)"],
            ["Verbindung", "Status-LED + Text (Verbunden/Getrennt)"],
        ],
        col_widths=[35 * mm, 120 * mm],
    ))
    story.append(Spacer(1, 6))
    story.append(P(
        "Jedes einzelne Feld - nicht nur ganze Gruppen - lässt sich über Einstellungen -&gt; "
        "Dashboard anpassen... (auch unter Anzeige & Karte gespiegelt) ein- oder ausblenden. Der "
        "gleiche Dialog erlaubt zusätzlich, die Reihenfolge der Gruppen per Ziehen neu zu "
        "sortieren, festzulegen, auf wie viele Zeilen bzw. Spalten (1-4) sie verteilt werden - "
        "praktisch, wenn viele Felder gleichzeitig sichtbar sein sollen - und zu wählen, an "
        "welcher Seite des Fensters das Dashboard angedockt ist: oben, unten, links oder rechts "
        "(Standard). Die Startgröße beträgt dabei ca. 20&#37; der Fensterbreite (bzw. -höhe bei "
        "oben/unten-Andockung), wächst aber automatisch mit, falls die gewählte Spaltenzahl mehr "
        "Platz braucht; wie bei jedem anderen Fenster-Trennbalken lässt sich die Größe des "
        "Dashboard-Bereichs danach jederzeit frei mit der Maus ziehen. Passt der gesamte Inhalt "
        "nicht in die verfügbare Fensterhöhe, wird das Dashboard vertikal scrollbar, statt das "
        "Fenster über den Bildschirm hinaus zu vergrößern. Sichtbarkeit, Reihenfolge, Zeilenanzahl "
        "und Andock-Position werden als persönlicher Standard in "
        "~/.elrs_ground_station/dashboard_fields.json, dashboard_layout.json bzw. "
        "dashboard_position.json gespeichert und bei jedem weiteren Start automatisch wieder "
        "geladen. Ist das Dashboard links oder rechts angedockt, ordnen sich die Felder innerhalb "
        "jeder Gruppe automatisch untereinander statt nebeneinander an, damit sie in die schmalere "
        "Spalte passen."
    ))
    story.append(P(
        "Unter Telemetrie & Hardware -&gt; Dashboard-Größe lässt sich zusätzlich die Schrift-, "
        "Icon- und Abstandsgröße der gesamten Telemetrie-Leiste einstellen - standardmäßig "
        "<b>Automatisch</b>: die Größe wird laufend an die tatsächliche Breite und Höhe des "
        "Telemetrie-Bereichs angepasst, sodass alle sichtbaren Felder ohne Scrollen hineinpassen, "
        "egal wie schmal/breit oder hoch/niedrig der Bereich gerade gezogen ist - beim Ziehen des "
        "Trennbalkens, beim Ändern der Fenstergröße und beim Ein-/Ausblenden einzelner Felder "
        "(Abschnitt 6.2) passt sich die Größe jeweils sofort neu an. Die drei festen Stufen "
        "darunter (Klein 75&#37;, Mittel 100&#37;, Groß 125&#37;) bleiben als bewusste, feste "
        "Wahl verfügbar - wird eine davon gewählt, schaltet sich die automatische Anpassung ab, "
        "bis wieder Automatisch gewählt wird. Ist selbst die kleinstmögliche automatische Größe "
        "noch zu groß für den verfügbaren Platz, greift wie gehabt die vertikale Bildlaufleiste."
    ))
    story.extend(figure(
        "dashboard_autofit_wide.png",
        "Automatische Größe bei einem breiten, links angedockten Telemetrie-Bereich - "
        "zweispaltig, große Schrift.",
        max_width_mm=95,
    ))
    story.extend(figure(
        "dashboard_autofit_narrow.png",
        "Derselbe Bereich, nur der Trennbalken auf ca. ein Drittel der Breite gezogen - "
        "Schrift, Symbole und Abstände verkleinern sich automatisch, die Feldgruppen "
        "brauchen dabei keine Bildlaufleiste.",
        max_width_mm=70,
    ))
    story.append(P(
        "Künstlicher Horizont und Höhenverlauf sind standardmäßig direkt oben in die "
        "Telemetrie-Leiste eingebettet (nebeneinander in einer eigenen Zeile über den "
        "Feldgruppen), lassen sich aber jederzeit wieder als freie Karten-Overlays lösen; der "
        "Wegpunkt-Editor lässt sich wahlweise unterhalb der Feldgruppen andocken - siehe "
        "Abschnitt 6.3."
    ))
    story.append(P("6.3 Verschieb- und größenveränderbare Karten-Overlays", "h2"))
    story.append(P(
        "Der künstliche Horizont, der Wegpunkt-Editor, die Tracking-Aufzeichnung und der "
        "Höhenverlauf (siehe 6.6) erscheinen als eigene Panels direkt auf der Karte - wie kleine "
        "Fenster, nicht als separate Dialoge. Jedes davon:"
    ))
    story.extend(bullets([
        "lässt sich frei verschieben - einfach an einer nicht-interaktiven Stelle (Titelzeile) anklicken und ziehen,",
        "lässt sich an einer kleinen Anfassmarke in der unteren rechten Ecke mit der Maus größer oder kleiner ziehen, wie bei einem Fenster,",
        "lässt sich über ein kleines Schließen-Symbol (x) in der oberen rechten Ecke ausblenden - "
        "der zugehörige Menüpunkt wird dabei automatisch abgehakt entfernt, sodass es von dort "
        "wieder eingeblendet werden kann,",
        "lässt sich über Anzeige & Karte bzw. das jeweilige Menü komplett ein-/ausblenden.",
    ]))
    story.append(P("6.4 Künstlicher Horizont", "h2"))
    story.append(P(
        "Zeigt Roll und Pitch als klassischer Fluglageanzeiger, gespeist aus MAVLink- oder "
        "CRSF-Attitude-Daten. Standardmäßig im Telemetrie-Panel angedockt (Größe passt sich "
        "dabei automatisch der Panel-Breite an); lässt er sich lösen, bietet Anzeige & Karte "
        "zusätzlich feste Ecken-Presets (oben links/rechts, unten links/rechts) sowie feste "
        "Größenstufen (75&#37;-200&#37;) für die freie Positionierung auf der Karte."
    ))
    story.append(P("6.5 RSSI/LQ-Heatmap", "h2"))
    story.append(P(
        "Anzeige & Karte -&gt; RSSI/LQ Heatmap aktivieren färbt den live geflogenen Pfad nach "
        "der aktuellen Verbindungsqualität ein - grün (LQ &gt;= 80&#37;), gelb (LQ &gt;= "
        "50&#37;) oder rot (darunter), grau, solange kein Wert vorliegt."
    ))
    story.append(P("6.6 Live-Höhenverlauf", "h2"))
    story.append(P(
        "Anzeige & Karte -&gt; Höhenverlauf anzeigen blendet ein Diagramm ein (standardmäßig im "
        "Telemetrie-Panel eingebettet), das die tatsächlich geflogene Höhe fortlaufend über die "
        "verstrichene Zeit aufzeichnet. Die Zeiteinheit der X-Achse lässt sich zwischen Sekunden, "
        "Minuten und Stunden umschalten."
    ))
    story.append(P("6.7 Telemetrie-Variablen-Editor und eigene Dashboard-Felder", "h2"))
    story.append(P(
        "Telemetrie & Hardware -&gt; Telemetrie-Variablen-Editor... zeigt Telemetriewerte an, die "
        "außerhalb der festen Dashboard-Felder aus Abschnitt 6.2 empfangen werden - bei MAVLink "
        "z. B. benutzerdefinierte NAMED_VALUE_FLOAT/NAMED_VALUE_INT-Werte, wie sie manche "
        "Flugsteuerungs-Firmwares für zusätzliche Sensoren (ESC-Temperatur, VTX-Temperatur, "
        "eigene Skript-Variablen, ...) senden. Jede so erkannte Variable erscheint automatisch als "
        "eigene Zeile, sobald sie das erste Mal empfangen wird - Wert live, mit editierbarem "
        "Anzeigename und einem Löschen/Wiederherstellen-Knopf, falls einzelne Variablen dauerhaft "
        "ignoriert werden sollen. Anzeigename und Löschstatus bleiben über Neustarts hinweg "
        "gespeichert."
    ))
    story.append(P(
        "Die Spalte <b>Dashboard</b> macht eine erkannte Variable zusätzlich zu einem eigenen "
        "Feld in der Telemetrie-Leiste - in einer neuen Gruppe \"Benutzerdefiniert\", die "
        "automatisch erscheint, sobald mindestens eine Variable angehakt ist, und wie jede andere "
        "Feldgruppe an der automatischen Dashboard-Größe (Abschnitt 6.2), an der Ein-/Ausblend- "
        "und Sortierfunktion (Dashboard anpassen..., Abschnitt 6.2) sowie an der Links/Rechts-"
        "Andockung teilnimmt. Das Anhaken wirkt sofort - auch ohne aktive Telemetrieverbindung, "
        "z. B. während des Einrichtens am Schreibtisch. Wird eine Variable wieder abgehakt oder "
        "eine neue Verbindung/der Demo-Modus gestartet (wodurch die Liste erkannter Variablen neu "
        "beginnt, siehe oben), verschwindet ihr Dashboard-Feld automatisch wieder; ein erneut "
        "empfangener, weiterhin angehakter Schlüssel bekommt sein Feld genauso automatisch zurück."
    ))
    story.extend(figure(
        "variable_editor_pin.png",
        "Telemetrie-Variablen-Editor: zwei erkannte NAMED_VALUE-Variablen, beide über die "
        "Dashboard-Spalte als eigenes Feld angeheftet.",
        max_width_mm=140,
    ))
    story.extend(figure(
        "dashboard_extra_field.png",
        "Ergebnis in der Telemetrie-Leiste: die neue Gruppe \"Benutzerdefiniert\" mit den beiden "
        "angehefteten Variablen, inklusive automatischer Größenanpassung.",
        max_width_mm=85,
    ))

    # --- 7. Kartenoptionen ---
    story.append(P("7. Kartenoptionen", "h1"))
    story.append(P("7.1 Kartentyp: Vektorkarte (Standard), OpenStreetMap oder Satellit", "h2"))
    story.append(P(
        "Anzeige & Karte -&gt; Kartentyp schaltet zwischen der Vektorkarte (MapLibre, Standard) "
        "und den klassischen Raster-Layern OpenStreetMap sowie Esri-Satellitenbild um."
    ))
    story.append(P(
        "Die Vektorkarte nutzt - im Gegensatz zu OpenStreetMap/Satellit - keine Bildkacheln, "
        "sondern echte Vektor-Kartendaten (MapLibre GL). Die Kartendrehung bei "
        "Drohnenrichtung-oben läuft dabei nativ, und selbst die Orts-/Straßennamen auf der Karte "
        "selbst bleiben aufrecht/lesbar - die einzige Einschränkung der Raster-Karte (siehe "
        "Hinweis in Abschnitt 6.1), die es hier nicht gibt. Live-Position, Wegpunkt-Bearbeitung, "
        "Sperrzonen und RSSI/LQ-Heatmap funktionieren genauso wie bei der Raster-Karte; nur der "
        "Kartentyp-Wechsel selbst braucht einen Neustart der App."
    ))
    story.append(P(
        "Kartendaten für die Vektorkarte kommen aus lokalen Regions-Dateien (siehe auch Abschnitt "
        "5 zur Offline-Nutzung). Alle bereits heruntergeladenen Regionen werden gleichzeitig "
        "geladen und übereinandergelegt - es muss also nicht mehr eine \"passende\" Region für die "
        "aktuelle Position ausgewählt werden, an einer Landesgrenze rendern einfach beide Länder "
        "nahtlos nebeneinander. Diese Dateien lassen sich direkt in der App herunterladen: "
        "Anzeige & Karte -&gt; Kartentyp -&gt; "
        "Vektorkarten-Region herunterladen... öffnet einen Dialog mit einer Länderliste (Ankreuz"
        "feld pro Land, Suchfeld, Alle auswählen/Auswahl aufheben) - aktuell knapp 38 europäische "
        "Länder/Regionen, von Portugal bis in die Ukraine, von Island bis Griechenland. Mehrere "
        "Länder lassen sich gleichzeitig ankreuzen und werden dann automatisch nacheinander "
        "heruntergeladen; pro Region lädt die App per HTTP-Range-Requests nur deren eigene "
        "Kacheln aus Protomaps' öffentlichem Kartendaten-Archiv - nicht die komplette Weltkarte. "
        "Ein Fortschrittsbalken zeigt den Downloadstand der aktuellen Region (bei mehreren "
        "Regionen zusätzlich \"Region X/N\"), ein Klick auf Abbrechen bricht die laufende Region "
        "ab und überspringt alle noch nicht gestarteten. Der Dialog ist nicht-modal: die "
        "restliche App (Karte, Telemetrie, Fliegen) bleibt während eines laufenden Downloads "
        "voll bedienbar - der eigentliche Download läuft ohnehin schon in einem eigenen "
        "Hintergrund-Thread, nicht auf dem GUI-Thread. Ist noch keine passende Region vorhanden, "
        "bleibt die Karte beim Start leer und ein Dialog erklärt, wie eine heruntergeladen wird. "
        "Es gibt kein automatisches Hintergrund-Update - bei Bedarf einfach erneut über denselben "
        "Menüpunkt herunterladen."
    ))
    story.append(P(
        "Die Länderliste im Download-Dialog zeigt zu jedem bereits heruntergeladenen Land direkt "
        "neben dem Namen ein Häkchen mit dem Downloaddatum an, sodass auf einen Blick erkennbar "
        "ist, welche Regionen schon lokal vorliegen. Ein Ordner-öffnen-Knopf im selben Dialog "
        "öffnet den Speicherort der Regions-Dateien (%USERPROFILE%\\.elrs_ground_station\\pmtiles\\) "
        "direkt im Windows-Explorer."
    ))
    story.append(P(
        "Ein Importieren...-Knopf daneben erlaubt es, eine bereits vorhandene .pmtiles-Datei "
        "(z. B. von einem anderen Rechner oder einem USB-Stick übertragen) direkt einzubinden, "
        "ohne sie erneut herunterzuladen. Trägt die gewählte Datei bereits den Namen einer der "
        "unterstützten Regionen (z. B. austria.pmtiles), wird sie automatisch zugeordnet; "
        "andernfalls fragt ein kleiner Dialog, für welches Land die Datei gedacht ist. In beiden "
        "Fällen landet die Datei am selben Speicherort wie bei einem regulären Download und wird "
        "sofort in der Länderliste als heruntergeladen markiert."
    ))
    story.append(P(
        "Sowohl beim Start aus dem Quellcode (python main.py) als auch in der kompilierten .exe "
        "funktioniert die Vektorkarte identisch, sobald eine Region heruntergeladen wurde (siehe "
        "auch Abschnitt 14). Die neu hinzugekommenen europäischen Regionen jenseits von "
        "Deutschland/Österreich/Schweiz/Italien nutzen näherungsweise Bounding-Boxen (nicht "
        "einzeln gegen echte Regions-Header verifiziert) - der reale Download-Ausschnitt kann "
        "dadurch am Rand geringfügig größer oder kleiner ausfallen als das jeweilige Land."
    ))
    story.append(P(
        "Da alle heruntergeladenen Regionen gleichzeitig geladen und übereinandergelegt werden, "
        "muss an einer Landesgrenze (z. B. Bodensee-Region: Deutschland, Österreich und die "
        "Schweiz grenzen dort direkt aneinander) entschieden werden, welche Region \"oben liegt\", "
        "falls sich zwei Regionen an der Grenze tatsächlich überschneiden. Anzeige & Karte -&gt; "
        "Kartentyp -&gt; Vektorkarten-Region legt diese Priorität fest (Automatisch = Österreich "
        "zuerst, falls heruntergeladen, sonst keine feste Priorität; oder eine der bereits "
        "heruntergeladenen Länder als feste oberste Ebene). Alle übrigen heruntergeladenen "
        "Regionen darunter werden nach Dateigröße aufsteigend gestapelt. Wie beim "
        "Kartentyp-Wechsel selbst wird die Änderung erst nach einem Neustart der App wirksam."
    ))
    story.append(P("7.2 No-Fly-Zones, Distanz-Warnung und OpenAIP", "h2"))
    story.append(P(
        "Alle Sperrzonen-Funktionen sitzen im Untermenü Anzeige & Karte -&gt; Sperrzonen (nicht "
        "als eigene, oberste Menügruppe), da sie inhaltlich zur Kartendarstellung gehören."
    ))
    story.append(P(
        "Anzeige & Karte -&gt; Sperrzonen -&gt; Sperrzonen laden... importiert Sperrzonen aus "
        "einer GeoJSON- oder CSV-Datei und zeigt sie als rote Kreise (CSV mit Radius) bzw. "
        "Polygone (GeoJSON Polygon/MultiPolygon) auf der Karte an. Sperrzonen anzeigen blendet "
        "sie ein/aus, ohne die geladenen Zonen zu verwerfen."
    ))
    story.append(P(
        "Distanz-Warnung aktivieren (50m) löst - sobald das Modell sich einer geladenen "
        "Sperrzone auf 50 Meter nähert - eine Sprachwarnung sowie eine Meldung in der "
        "Statusleiste aus. Zusätzlich zeigt ein zentraler Warnbanner auf der Karte alle aktuell "
        "aktiven Warnungen (Akku, Sperrzonen, Energiebudget) gebündelt an."
    ))
    story.append(P(
        "OpenAIP-Einstellungen... hinterlegt einen optionalen OpenAIP-API-Key sowie die "
        "gewünschten Luftraumtypen (z. B. CTR, Restricted, Prohibited). OpenAIP Zonen laden lädt "
        "anschließend automatisch passende Luftraumdaten für die aktuelle Home-Position herunter "
        "und zeigt sie wie manuell importierte Sperrzonen an."
    ))
    story.append(P(
        "Österreich-Flugbeschränkungszonen laden (Austro Control) lädt ohne Dateiauswahl direkt "
        "den mit der App mitgelieferten, offiziellen Datensatz der Austro Control (UAS-Zonen "
        "gemäß EU-Durchführungsverordnung, Stand des Downloads: September 2026). Genehmigungs"
        "pflichtige Zonen, bedingt nutzbare Zonen und echte Flugverbote werden jeweils mit "
        "passendem Namenspräfix (Genehmigungspflichtig / Flugplatzzone / Flugverbot) übernommen; "
        "reine Modellfluggebiete (ohne Einschränkung) werden bewusst nicht angezeigt, da sie "
        "keine echte Sperrzone darstellen, sondern nur auf vermehrten Drohnenverkehr hinweisen."
    ))
    story.append(P("7.3 Rechtsklick-Menü", "h2"))
    story.append(P("Ein Rechtsklick auf die Karte öffnet - unabhängig vom Wegpunkt-Modus - ein Kontextmenü mit folgenden Punkten:"))
    story.extend(bullets([
        "<b>Wegpunkt / Startpunkt / Endpunkt</b> - fügt an der angeklickten Stelle einen entsprechenden Punkt zur Route hinzu (siehe Abschnitt 8).",
        "<b>Als Home setzen</b> - teacht die Home-/Startposition (siehe 7.5) direkt an der angeklickten Stelle, ohne einen Dialog öffnen zu müssen.",
        "<b>Ansicht</b> (Untermenü) - Schnellzugriff auf Auto-Center, Kartenausrichtung, "
        "Wegpunkt-Editor anzeigen, Koordinaten anzeigen und RSSI/LQ-Heatmap.",
    ]))
    story.append(P("7.4 Koordinatenanzeige", "h2"))
    story.append(P(
        "Anzeige & Karte -&gt; Koordinaten anzeigen blendet ein kleines Overlay ein, das Lat/Lon "
        "direkt neben dem Mauszeiger anzeigt, während dieser sich über der Karte bewegt. "
        "Standardmäßig ausgeblendet."
    ))
    story.append(P("7.5 Home-/Startposition und Bodenstations-Position", "h2"))
    story.append(P(
        "Einstellungen -&gt; Home-Position... legt fest, wo die Karte beim nächsten Start "
        "zentriert ist - unabhängig von der live ermittelten Flugstart-Referenz (immer der erste "
        "GPS-Fix der laufenden Sitzung), die für die Entfernungs-/Peilungsanzeige im Dashboard "
        "verwendet wird. Neben der manuellen Lat/Lon-Eingabe und \"Aktuelle Position übernehmen\" "
        "(nur bei laufender Telemetrie verfügbar) bietet der Dialog \"Standort per IP ermitteln\": "
        "eine grobe, Stadt-genaue Positionsbestimmung über einen Online-Dienst, ganz ohne "
        "GPS-Fix - praktisch fürs einmalige Einrichten zuhause. Da diese Positionsangabe auch "
        "bestimmt, wo die Karte beim Start zentriert ist (siehe Abschnitt 7.1), lohnt es sich, "
        "hier den tatsächlichen Wohn-/Startort einzutragen, statt es beim App-Standardwert zu "
        "belassen."
    ))
    story.append(P(
        "Eine dritte, ebenfalls unabhängige Position ist die eigene Bodenstations-Position "
        "(Einstellungen -&gt; Bodenstations-Position..., manuelle Lat/Lon/Höhe-Eingabe) - sie "
        "dient als Referenzpunkt für die Azimut/Elevation-Anzeige im Dashboard, gedacht zum "
        "manuellen Ausrichten einer Richtantenne."
    ))
    story.append(P("7.6 Karten-Performance", "h2"))
    story.append(P(
        "Die Karte ist auf flüssige Darstellung auch bei hoher Telemetrierate optimiert: "
        "GPU-beschleunigtes Rendering, ein 500-MB-Festplatten-Cache und eine auf maximal 5 Hz "
        "gedrosselte Positionsaktualisierung. Einstellbar über Anzeige & Karte -&gt; "
        "Karten-Performance..."
    ))
    story.append(P("7.7 Flugverkehr (ADS-B) - nur online", "h2"))
    story.append(P(
        "Einstellungen -&gt; Flugverkehr-Einstellungen... aktiviert eine optionale Anzeige "
        "bemannten Flugverkehrs (ADS-B) in der Nähe der Boden-/Flugposition, abgerufen von "
        "airplanes.live (Standard, ohne API-Key) oder wahlweise OpenSky Network. Anders als die "
        "Sperrzonen-Anzeige (Abschnitt 7.2) ist dies eine reine Online-Funktion: ohne "
        "Internetverbindung bleiben einfach keine Kontakte sichtbar, es wird nie ein veralteter "
        "Stand weiter angezeigt, da Flugverkehr-Positionen innerhalb von Sekunden veralten "
        "würden. Der Dialog erlaubt außerdem Radius, Abrufintervall und die Basis-URL (falls ein "
        "anderer Endpunkt/Proxy genutzt werden soll) einzustellen."
    ))
    story.append(P(
        "Maximalhöhe blendet Kontakte oberhalb einer einstellbaren Schwelle aus - ohne diesen "
        "Filter wäre die Anzeige durch Linienverkehr im Reiseflug (mehrere Kilometer Höhe) "
        "praktisch nutzlos für den eigenen Flugbetrieb. Der Höhenbezug ist standardmäßig "
        "<b>Höhe über Grund (AGL)</b>, umschaltbar auf Höhe über Meer (MSL): AGL vergleicht die "
        "gemeldete Flughöhe gegen eine einzelne Bodenreferenzhöhe an der Boden-/Flugposition "
        "(dieselbe Geländehöhen-Abfrage wie beim Höhenprofil, Abschnitt 8), nicht gegen das "
        "Gelände unter jedem einzelnen Kontakt - für den Zweck \"keinen Linienverkehr sehen\" "
        "ausreichend genau, ohne für jeden Kontakt einzeln eine Geländehöhe abzufragen. Ist beim "
        "Wechsel auf AGL gerade keine Geländehöhe verfügbar (z. B. kurzzeitig offline), wird für "
        "diesen einen Abruf automatisch auf einen MSL-Vergleich zurückgefallen - kenntlich an "
        "einer kurzen Statuszeilen-Meldung -, statt Kontakte fälschlich auszublenden."
    ))
    story.append(P(
        "Anzeige & Karte -&gt; Flugverkehr anzeigen blendet die Kontakte ein/aus, unabhängig "
        "davon, ob der Abruf selbst aktiviert ist (analog zum Geofence-Muster in Abschnitt 7.2: "
        "Sichtbarkeit und Aktivierung sind zwei getrennte Schalter). Jeder Kontakt erscheint als "
        "kleines, nach Peilung gedrehtes Flugzeug-Symbol; ein Mauszeiger darüber zeigt Rufzeichen "
        "und Höhe."
    ))
    story.append(P(
        "<b>Wichtig:</b> Diese Anzeige ist eine Zusatzinformation, kein Ersatz für offizielle "
        "Luftraumbeobachtung, Sichtflugregeln oder ein zugelassenes Kollisionswarnsystem - nicht "
        "jedes Luftfahrzeug sendet ADS-B (z. B. viele Segelflieger, Ballone, Militär), und ein "
        "fehlender Kontakt bedeutet nicht \"kein Verkehr vorhanden\"."
    ))

    # --- 8. Route/Wegpunkte ---
    story.append(P("8. Route/Wegpunkte planen, importieren und als INAV-Mission exportieren", "h1"))
    story.append(P(
        "Neben der live aufgezeichneten Flugspur (orange) kann eine unabhängige, geplante Route "
        "(grün, gestrichelt, mit nummerierten Wegpunkt-Markern) auf der Karte angezeigt werden - "
        "entweder von Hand gezeichnet (Route & Planung -&gt; Wegpunkt-Modus, oder per Rechtsklick "
        "-&gt; Wegpunkt/Startpunkt/Endpunkt) oder importiert aus einer Datei (Route & Planung "
        "-&gt; Route importieren...)."
    ))
    story.append(P("8.1 Unterstützte Import-/Exportformate", "h2"))
    story.append(simple_table(
        [
            ["Format", "Beschreibung"],
            [".gpx", "Liest bzw. schreibt Routenpunkte (&lt;rte&gt;); beim Import ersatzweise Track-Punkte oder einzelne Wegpunkte."],
            [".mission (JSON)", "Modernes INAV-Missionsformat (Schema-Version 1.0), siehe Abschnitt 8.3."],
            [".mission (XML)", "Älteres 'MW XML'-Missionsformat von mwp/iNav Configurator/ezgui."],
            [".xml", "Generischer Fallback: durchsucht beliebige XML-Strukturen nach erkennbaren Lat/Lon/Alt/Name-Bezeichnungen."],
            [".csv", "Erkennt Spalten wie lat/latitude, lon/longitude, optional alt und name."],
        ],
        col_widths=[32 * mm, 125 * mm],
    ))
    story.append(Spacer(1, 6))
    story.append(P("8.2 Der Wegpunkt-Editor", "h2"))
    story.append(P(
        "Route & Planung -&gt; Wegpunkt-Editor anzeigen blendet ein Overlay direkt auf der Karte "
        "ein. Oben zeigt es Wegpunktanzahl und Gesamtdistanz, darunter eine Tabelle mit je einer "
        "Zeile pro Wegpunkt. Der Editor ist vollständig interaktiv und mit den "
        "Wegpunkt-Markern auf der Karte verzahnt (Auswahl, Bearbeiten, Löschen, Verschieben per "
        "Maus, Umsortieren per Drag & Drop)."
    ))
    story.append(P("8.3 INAV-Mission (.mission JSON)", "h2"))
    story.append(P("Unterstützte Aktionen:"))
    story.append(simple_table(
        [
            ["Aktion", "Bedeutung von P1/P2/P3"],
            ["WAYPOINT", "P1 = Wartezeit in Sekunden (0 = Durchflug ohne Halt)."],
            ["HOLD", "P1 = Haltedauer in Sekunden."],
            ["RTH", "Rückkehr zur Home-Position; Lat/Lon/Alt dürfen 0 sein."],
            ["SET_POI", "Lat/Lon/Alt definieren das Kameraziel."],
            ["JUMP", "P1 = Ziel-Wegpunktindex (1-basiert), P2 = Wiederholungsanzahl."],
            ["LAND", "Automatische Landung an Lat/Lon."],
        ],
        col_widths=[28 * mm, 129 * mm],
    ))
    story.append(Spacer(1, 6))
    story.append(P("8.4 Höhenprofil der Route", "h2"))
    story.append(P(
        "Tools & Simulation -&gt; Höhenprofil der Route anzeigen öffnet ein Diagramm, das für "
        "die aktuelle Route die Geländehöhe (braun) und die geplante Flughöhe (türkis) über der "
        "zurückgelegten Distanz darstellt."
    ))
    story.append(P("8.5 Grid-/Suchmuster-Generator", "h2"))
    story.append(P(
        "Route & Planung -&gt; Grid-/Suchmuster erzeugen... erstellt automatisch eine "
        "Zickzack-Absuchroute (Boustrophedon-Muster) über zwei Eckpunkte oder Mittelpunkt+Radius."
    ))

    # --- 9/10/11 ---
    story.append(P("9. Flugpfad-Aufzeichnung (Start/Pause/Export)", "h1"))
    story.append(P(
        "Ein eigenes Overlay auf der Karte startet und pausiert die Aufzeichnung des geflogenen "
        "Pfads unabhängig von der Live-Anzeige. Exportieren... im Overlay fragt zunächst das "
        "gewünschte Format ab - GPX, KML oder CSV."
    ))
    story.append(P(
        "Diese Aufzeichnung ist unabhängig vom Fluglog (Abschnitt 10): das Tracking speichert "
        "nur Positionspunkte für einen späteren Pfad-Export, das Fluglog schreibt alle "
        "Telemetriefelder kontinuierlich als Zeitreihe in eine CSV-Datei."
    ))
    story.append(P("10. Fluglog (CSV-Aufzeichnung)", "h1"))
    story.append(P(
        "Das Fluglog zeichnet - unabhängig von der Flugpfad-Aufzeichnung aus Abschnitt 9 - "
        "sämtliche Telemetriedaten als Zeitreihe in einer CSV-Datei auf. Über Telemetrie & "
        "Hardware -&gt; Log-Einstellungen... lässt sich sowohl die Menge der aufgezeichneten "
        "Spalten als auch das Aufzeichnungsintervall (0,1 bis 60 Sekunden) frei wählen. Eine "
        "aufgezeichnete Log-Datei lässt sich später über Tools & Simulation -&gt; Flug abspielen... "
        "wieder einladen und wie eine Live-Verbindung durch die App abspielen (Log-Replay), "
        "inklusive Wiedergabegeschwindigkeit, Sprungmarke und einer abschließenden "
        "Flugzusammenfassung."
    ))
    story.append(P("11. Plan-Modus", "h1"))
    story.append(P(
        "Der Plan-Modus erlaubt es, Routen zu planen und Wegpunkte zu setzen, ohne dass "
        "irgendeine Telemetrieverbindung - echt oder simuliert - läuft. Aktivierbar über Tools & "
        "Simulation -&gt; Plan-Modus oder direkt im Verbindungs-Popup beim Programmstart."
    ))

    # --- 12. Menüs im Detail ---
    story.append(P("12. Die Menüs im Detail", "h1"))
    story.append(P(
        "Die Menüleiste ist in sieben Gruppen sortiert: Datei | Route & Planung | Anzeige & "
        "Karte | Telemetrie & Hardware | Tools & Simulation | Einstellungen | Hilfe."
    ))
    story.append(P("12.1 Datei", "h2"))
    story.extend(bullets([
        "Flugpfad als GPX exportieren... / als KML exportieren...",
        "Beenden",
    ]))
    story.append(P("12.2 Route & Planung", "h2"))
    story.extend(bullets([
        "Wegpunkt-Modus, Letzten Wegpunkt entfernen / Route löschen",
        "Wegpunkt-Editor anzeigen / im Dashboard andocken",
        "Route importieren... / Route exportieren...",
        "Grid-/Suchmuster erzeugen...",
        "Mission hochladen... / Mission herunterladen... (MAVLink, siehe Abschnitt 4)",
    ]))
    story.append(P("12.3 Anzeige & Karte", "h2"))
    story.extend(bullets([
        "Kartentyp -&gt; Vektorkarte (MapLibre, Standard) / OpenStreetMap / Satellit (Esri) "
        "(Neustart bei Wechsel erforderlich) sowie Vektorkarten-Region herunterladen... und "
        "Vektorkarten-Region (Grenz-Priorität: Automatisch/Land) - siehe Abschnitt 7.1.",
        "Sperrzonen (Untermenü): Sperrzonen laden... / Sperrzonen anzeigen, Distanz-Warnung "
        "aktivieren (50m), OpenAIP-Einstellungen... / OpenAIP Zonen laden, "
        "Österreich-Flugbeschränkungszonen laden (Austro Control) - siehe Abschnitt 7.2.",
        "Flugverkehr anzeigen - blendet ADS-B-Kontakte ein/aus (Aktivierung/Konfiguration unter "
        "Einstellungen -&gt; Flugverkehr-Einstellungen...) - siehe Abschnitt 7.7.",
        "Auto-Center, Drohnenrichtung/Norden oben, Aktuelle Position anspringen (Strg+Pos1).",
        "Wegpunkt-Editor anzeigen, Karten-Performance..., Tracking-Overlay anzeigen, "
        "Höhenverlauf anzeigen, Koordinaten anzeigen, RSSI/LQ Heatmap aktivieren.",
        "Fahrzeugtyp, Künstlicher Horizont anzeigen/Position/Größe.",
        "Dashboard anpassen... - hier zur schnellen Erreichbarkeit gespiegelt (siehe Abschnitt 6.2).",
    ]))
    story.append(P("12.4 Telemetrie & Hardware", "h2"))
    story.extend(bullets([
        "Verbindung... - wechselt zur Laufzeit zwischen WiFi/UDP und USB/Seriell sowie zwischen MAVLink und CRSF.",
        "Log-Einstellungen... / Logging aktiv - siehe Abschnitt 10.",
        "Akkuwarnung... - siehe Abschnitt 13.",
        "Warntöne... - siehe Abschnitt 13.1.",
        "MAVLink-STATUSTEXT-Konsole anzeigen - Rohtext-Meldungen der Flugsteuerung, farblich nach Schweregrad.",
        "Telemetrie-Variablen-Editor... - siehe Abschnitt 6.7.",
        "Dashboard-Größe -&gt; Klein (75&#37;) / Mittel (100&#37;) / Groß (125&#37;) - skaliert "
        "Schrift, Icons und Abstände der gesamten Telemetrie-Leiste; wird beim ersten Start "
        "automatisch anhand der Bildschirmgröße vorbelegt (siehe Abschnitt 6.2).",
        "Antennen-Tracker / Telemetrie-Ausgabe... - siehe Abschnitt 4.4.",
        "Modell-Profile verwalten... - siehe Abschnitt 4.5.",
        "RTH auslösen / Modus wechseln... (nur bei aktiver MAVLink-Verbindung, mit Bestätigungsdialog).",
    ]))
    story.append(P("12.5 Tools & Simulation", "h2"))
    story.extend(bullets([
        "Demo-Modus - schaltet zur Laufzeit zwischen echter Telemetrie und simulierten Daten um.",
        "Plan-Modus - siehe Abschnitt 11.",
        "Flug abspielen... - lädt ein aufgezeichnetes Fluglog (Abschnitt 10) und spielt es wie eine Live-Verbindung ab.",
        "Höhenprofil der Route anzeigen - siehe Abschnitt 8.4.",
    ]))
    story.append(P("12.6 Einstellungen", "h2"))
    story.extend(bullets([
        "Home-Position... - siehe Abschnitt 7.5.",
        "Bodenstations-Position... - siehe Abschnitt 7.5.",
        "Flugverkehr-Einstellungen... - Anbieter, Radius, Abrufintervall, Höhenbezug "
        "(AGL/MSL) und Maximalhöhe - siehe Abschnitt 7.7.",
        "Dashboard anpassen... - siehe Abschnitt 6.2.",
        "Sprache -&gt; Deutsch/English, wechselt die komplette Oberfläche sofort ohne Neustart.",
    ]))
    story.append(P("12.7 Hilfe", "h2"))
    story.extend(bullets([
        "Benutzerhandbuch öffnen... - öffnet dieses Handbuch als PDF im Standard-PDF-Betrachter des Systems.",
    ]))

    # --- 13. Akkuwarnung ---
    story.append(P("13. Akkuwarnung: LiPo vs. Li-Ion", "h1"))
    story.append(P(
        "Sobald der Akku niedrig oder kritisch niedrig wird, gibt die App eine Sprachwarnung aus "
        "(offline, über die Windows-SAPI5-Sprachausgabe). Da sich die sichere "
        "Entladeschlussspannung von LiPo- und Li-Ion-Zellen deutlich unterscheidet, lässt sich "
        "die Chemie unter Telemetrie & Hardware -&gt; Akkuwarnung... auswählen:"
    ))
    story.append(simple_table(
        [
            ["Chemie", "Warnung (V/Zelle)", "Kritisch (V/Zelle)"],
            ["LiPo", "3,6 V", "3,5 V"],
            ["Li-Ion", "3,3 V", "3,0 V"],
        ],
        col_widths=[40 * mm, 55 * mm, 55 * mm],
    ))
    story.append(Spacer(1, 6))
    story.append(P(
        "Die Auswahl der Chemie füllt automatisch passende Standardwerte vor; Zellenzahl, die "
        "genauen Warn-/Kritisch-Spannungen sowie die Nennkapazität des Akkus (mAh) lassen sich "
        "zusätzlich frei einstellen. Steht eine echte Zellspannungsmessung zur Verfügung "
        "(CRSF-Cells-Frame oder MAVLink BATTERY_STATUS), verwendet die App die tatsächliche "
        "niedrigste Zellspannung für die Warnung."
    ))
    story.append(P("13.1 Warntöne (EdgeTX-Sounds)", "h2"))
    story.append(P(
        "Standardmäßig werden alle Warnungen der App - Akku niedrig/kritisch, Geofence "
        "verletzt, Sperrzone nähert sich, Umkehrpunkt erreicht, Energiereserve kritisch, "
        "Telemetrie verloren - per Sprachausgabe (SAPI5) angesagt. Über Telemetrie & Hardware "
        "-&gt; Warntöne... lässt sich jeder dieser sieben Warnungen stattdessen ein konkreter "
        "Sound aus dem mitgelieferten EdgeTX-Sprachpaket zuordnen (assets/en, dieselben "
        "System- und Skript-Sounds, mit denen EdgeTX-Sender ausgeliefert werden - ca. 730 "
        "Dateien)."
    ))
    story.append(P(
        "Der Dialog zeigt pro Warnung ein durchsuchbares Auswahlfeld (Freitext filtert die "
        "Liste) sowie einen Vorhören-Knopf. Änderungen werden sofort übernommen, es gibt keinen "
        "OK/Abbrechen-Schritt. Bleibt eine Warnung auf \"Sprachausgabe (Standard)\" stehen, "
        "verhält sie sich unverändert wie bisher. Die Sound-Wiedergabe funktioniert nur unter "
        "Windows (über die Windows-eigene winsound-API); unter anderen Betriebssystemen fällt "
        "die App automatisch auf die Sprachausgabe zurück."
    ))
    story.append(P(
        "Ab Werk sind bereits sinnvolle EdgeTX-Sounds für vier der sieben Warnungen "
        "vorbelegt (Akku niedrig, Akku kritisch, Energiereserve kritisch, Modell verloren) - "
        "die übrigen drei Warnungen nutzen weiterhin die Sprachausgabe, bis eigene Sounds "
        "ausgewählt werden. Jede Vorbelegung lässt sich jederzeit im selben Dialog ändern."
    ))

    # --- 14. Exe ---
    story.append(P("14. Als eigenständige .exe kompilieren", "h1"))
    story.append(code(
        "cd elrs_ground_station\n"
        "python -m venv .venv\n"
        ".venv\\Scripts\\activate\n"
        "pip install -r requirements.txt pyinstaller\n"
        "pyinstaller --name ELRS_GroundStation --onedir --icon assets/app_icon.ico \\\n"
        "    --add-data \"docs;docs\" --add-data \"assets;assets\" main.py"
    ))
    story.append(P(
        "--add-data \"docs;docs\" bündelt das PDF-Handbuch mit in die Exe, damit Hilfe -&gt; "
        "Benutzerhandbuch öffnen... es auch dort findet. --add-data \"assets;assets\" bündelt "
        "App-Icon, Logo und das komplette EdgeTX-Soundpaket (assets/en, für Abschnitt 13.1); "
        "--icon assets/app_icon.ico setzt zusätzlich das Icon der Exe-Datei selbst."
    ))
    story.append(P(
        "Das Ergebnis liegt unter dist\\ELRS_GroundStation\\ELRS_GroundStation.exe. Der gesamte "
        "Ordner dist\\ELRS_GroundStation (Exe plus _internal-Verzeichnis, ca. 500 MB) muss "
        "zusammen weitergegeben werden, nicht nur die .exe-Datei allein."
    ))
    story.append(P(
        "Die Exe behält bewusst die Konsole (kein --windowed), damit --list-ports, --demo usw. "
        "weiterhin normal über die Kommandozeile nutzbar sind; beim Doppelklick öffnet sich "
        "zusätzlich ein Konsolenfenster im Hintergrund."
    ))
    story.append(P(
        "Die Vektorkarte (siehe Abschnitt 7.1) funktioniert auch in der Exe, benötigt dort aber - "
        "genau wie beim Start aus dem Quellcode - eine heruntergeladene Regions-Datei (Anzeige & "
        "Karte -&gt; Kartentyp -&gt; Vektorkarten-Region herunterladen...); die Regions-Dateien "
        "selbst sind mehrere GB pro Land groß und werden bewusst nicht mit --add-data gebündelt. "
        "Gesucht wird zuerst unter %USERPROFILE%\\.elrs_ground_station\\pmtiles\\ (dort landen "
        "auch neu heruntergeladene Regionen), ersatzweise unter "
        "dist\\ELRS_GroundStation\\_internal\\assets\\pmtiles\\, falls dort von Hand "
        "*.pmtiles-Dateien abgelegt wurden. Fehlt eine passende Datei, erklärt ein Dialog beim "
        "Start, wo eine hingehört, und die Karte bleibt bis dahin leer."
    ))

    # --- 15. CLI reference ---
    story.append(P("15. Anhang: Kommandozeilen-Referenz", "h1"))
    story.append(simple_table(CLI_REFERENCE_ROWS, col_widths=[55 * mm, 100 * mm]))
    story.append(Spacer(1, 10))
    story.append(P(
        "Vollständige Projektdokumentation, Quellcode und Architektur-Details: "
        "github.com/KresserSimon/ELRS_Telemetry_Groundcontroll"
    ))

    return story


# ------------------------------------------------------------- page frames

def _on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(20 * mm, 12 * mm, "ELRS Ground Station - Benutzerhandbuch")
    canvas.drawRightString(190 * mm, 12 * mm, str(doc.page - 1))
    canvas.restoreState()


def _on_title_page(canvas, doc):
    pass


def build_pdf() -> None:
    doc = BaseDocTemplate(
        str(OUTPUT_PATH),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="ELRS Ground Station Benutzerhandbuch",
        author="ELRS Ground Station",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    title_template = PageTemplate(id="title", frames=[frame], onPage=_on_title_page)
    content_template = PageTemplate(id="content", frames=[frame], onPage=_on_page)
    doc.addPageTemplates([title_template, content_template])
    doc.build(build_story())
    print(f"Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    build_pdf()
