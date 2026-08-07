"""Minimal DE/EN translation layer: a flat string table plus a global switch.

Not a full Qt Linguist (.ts/.qm) setup - the app's text surface is small
enough that a plain dict stays easy to audit and needs no extra build step.
Widgets that must update live when the user switches language register a
retranslate callback via on_language_changed().
"""
from __future__ import annotations

from typing import Callable, List, Tuple

_LANGUAGES: Tuple[str, ...] = ("de", "en")
_current = "de"
_listeners: List[Callable[[], None]] = []

_STRINGS = {
    "de": {
        "menu_file": "&Datei",
        "menu_file_export_gpx": "Flugpfad als GPX exportieren...",
        "menu_file_export_kml": "Flugpfad als KML exportieren...",
        "menu_file_exit": "Beenden",
        "menu_settings": "&Einstellungen",
        "menu_connection_settings": "Verbindung...",
        "menu_view": "&Ansicht",
        "menu_view_auto_center": "Auto-Center",
        "menu_view_jump": "Aktuelle Position anspringen",
        "menu_view_vehicle": "Fahrzeugtyp",
        "vehicle_quad": "Quadrocopter",
        "vehicle_wing": "Wing (Nurflügler)",
        "vehicle_plane": "Flugzeug",
        "menu_view_horizon_toggle": "Künstlicher Horizont anzeigen",
        "menu_view_horizon_position": "Horizont-Position",
        "horizon_top_left": "Oben links",
        "horizon_top_right": "Oben rechts",
        "horizon_bottom_left": "Unten links",
        "horizon_bottom_right": "Unten rechts",
        "menu_simulation": "&Simulation",
        "menu_simulation_demo": "Demo-Modus",
        "menu_language": "&Sprache",
        "language_de": "Deutsch",
        "language_en": "Englisch",
        "status_demo_started": "Demo-Modus gestartet",
        "status_waiting_usb": "Warte auf Telemetrie ({protocol} ueber USB, {port})...",
        "status_waiting_udp": "Warte auf Telemetrie ({protocol} ueber UDP, Port {port})...",
        "status_connected": "Telemetrie verbunden",
        "status_disconnected": "Telemetrie getrennt",
        "status_track_saved": "Flugpfad gespeichert: {path}",
        "msgbox_no_track_title": "Kein Flugpfad",
        "msgbox_no_track_body": "Es wurden noch keine GPS-Punkte aufgezeichnet.",
        "msgbox_export_failed_title": "Export fehlgeschlagen",
        "msgbox_no_usb_title": "Kein USB-Port",
        "msgbox_no_usb_body": "Bitte einen seriellen Port waehlen oder eingeben.",
        "export_gpx_filter": "GPX-Datei (*.gpx)",
        "export_kml_filter": "KML-Datei (*.kml)",
        "export_dialog_title": "Flugpfad exportieren",
        "dash_gps": "GPS",
        "dash_lat": "Lat",
        "dash_lon": "Lon",
        "dash_alt": "Höhe (m)",
        "dash_sats": "Sats",
        "dash_status": "Status",
        "dash_flight_mode": "Flugmodus",
        "dash_link": "Link",
        "dash_rssi": "RSSI (dBm)",
        "dash_lq": "LQ (%)",
        "dash_snr": "SNR (dB)",
        "dash_tx_power": "Sendeleistung (mW)",
        "dash_battery": "Akku",
        "dash_voltage": "Spannung (V)",
        "dash_remaining": "Restkapazität (%)",
        "dash_connection": "Verbindung",
        "dash_connected": "Verbunden",
        "dash_disconnected": "Getrennt",
        "conn_dialog_title": "Verbindungseinstellungen",
        "conn_startup_title": "Verbindung & Protokoll wählen",
        "conn_protocol_box": "Protokoll",
        "conn_mavlink": "MAVLink",
        "conn_crsf": "CRSF (roh)",
        "conn_transport_box": "Transport",
        "conn_udp_radio": "WiFi / UDP",
        "conn_usb_radio": "USB / Seriell",
        "conn_udp_group": "WiFi / UDP",
        "conn_host_label": "Host:",
        "conn_port_label": "Port:",
        "conn_mode_label": "Modus:",
        "conn_usb_group": "USB / Seriell",
        "conn_refresh_btn": "USB-Geräte suchen",
        "conn_baud_label": "Baudrate:",
        "conn_connect_btn": "Verbinden",
        "conn_demo_btn": "Demo-Modus starten",
        "tts_low": "Warnung. Akkuspannung niedrig.",
        "tts_critical": "Warnung. Akku kritisch niedrig. Bitte sofort landen.",
    },
    "en": {
        "menu_file": "&File",
        "menu_file_export_gpx": "Export Flight Path as GPX...",
        "menu_file_export_kml": "Export Flight Path as KML...",
        "menu_file_exit": "Exit",
        "menu_settings": "&Settings",
        "menu_connection_settings": "Connection...",
        "menu_view": "&View",
        "menu_view_auto_center": "Auto-Center",
        "menu_view_jump": "Jump to Current Position",
        "menu_view_vehicle": "Vehicle Type",
        "vehicle_quad": "Quadcopter",
        "vehicle_wing": "Wing (Flying Wing)",
        "vehicle_plane": "Airplane",
        "menu_view_horizon_toggle": "Show Artificial Horizon",
        "menu_view_horizon_position": "Horizon Position",
        "horizon_top_left": "Top Left",
        "horizon_top_right": "Top Right",
        "horizon_bottom_left": "Bottom Left",
        "horizon_bottom_right": "Bottom Right",
        "menu_simulation": "&Simulation",
        "menu_simulation_demo": "Demo Mode",
        "menu_language": "&Language",
        "language_de": "German",
        "language_en": "English",
        "status_demo_started": "Demo mode started",
        "status_waiting_usb": "Waiting for telemetry ({protocol} via USB, {port})...",
        "status_waiting_udp": "Waiting for telemetry ({protocol} via UDP, port {port})...",
        "status_connected": "Telemetry connected",
        "status_disconnected": "Telemetry disconnected",
        "status_track_saved": "Flight path saved: {path}",
        "msgbox_no_track_title": "No Flight Path",
        "msgbox_no_track_body": "No GPS points have been recorded yet.",
        "msgbox_export_failed_title": "Export Failed",
        "msgbox_no_usb_title": "No USB Port",
        "msgbox_no_usb_body": "Please select or enter a serial port.",
        "export_gpx_filter": "GPX File (*.gpx)",
        "export_kml_filter": "KML File (*.kml)",
        "export_dialog_title": "Export Flight Path",
        "dash_gps": "GPS",
        "dash_lat": "Lat",
        "dash_lon": "Lon",
        "dash_alt": "Alt (m)",
        "dash_sats": "Sats",
        "dash_status": "Status",
        "dash_flight_mode": "Flight Mode",
        "dash_link": "Link",
        "dash_rssi": "RSSI (dBm)",
        "dash_lq": "LQ (%)",
        "dash_snr": "SNR (dB)",
        "dash_tx_power": "TX Power (mW)",
        "dash_battery": "Battery",
        "dash_voltage": "Voltage (V)",
        "dash_remaining": "Remaining (%)",
        "dash_connection": "Connection",
        "dash_connected": "Connected",
        "dash_disconnected": "Disconnected",
        "conn_dialog_title": "Connection Settings",
        "conn_startup_title": "Choose Connection & Protocol",
        "conn_protocol_box": "Protocol",
        "conn_mavlink": "MAVLink",
        "conn_crsf": "CRSF (raw)",
        "conn_transport_box": "Transport",
        "conn_udp_radio": "WiFi / UDP",
        "conn_usb_radio": "USB / Serial",
        "conn_udp_group": "WiFi / UDP",
        "conn_host_label": "Host:",
        "conn_port_label": "Port:",
        "conn_mode_label": "Mode:",
        "conn_usb_group": "USB / Serial",
        "conn_refresh_btn": "Search USB Devices",
        "conn_baud_label": "Baud Rate:",
        "conn_connect_btn": "Connect",
        "conn_demo_btn": "Start Demo Mode",
        "tts_low": "Warning. Battery voltage low.",
        "tts_critical": "Warning. Battery critically low. Land immediately.",
    },
}


def available_languages() -> Tuple[str, ...]:
    return _LANGUAGES


def get_language() -> str:
    return _current


def set_language(lang: str) -> None:
    global _current
    if lang not in _STRINGS or lang == _current:
        return
    _current = lang
    for callback in list(_listeners):
        callback()


def on_language_changed(callback: Callable[[], None]) -> None:
    _listeners.append(callback)


def tr(key: str, **kwargs) -> str:
    text = _STRINGS.get(_current, _STRINGS["de"]).get(key, _STRINGS["de"].get(key, key))
    return text.format(**kwargs) if kwargs else text
