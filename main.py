#!/usr/bin/env python3
"""ELRS Ground Station - lightweight telemetry receiver + live map dashboard.

Usage examples:
    python main.py --demo
    python main.py --protocol mavlink --host 0.0.0.0 --port 14550
    python main.py --protocol crsf --host 0.0.0.0 --port 14551
"""
from __future__ import annotations

import argparse
import sys


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ELRS Ground Station")

    parser.add_argument("--demo", action="store_true", help="Im Simulationsmodus starten (keine Hardware noetig)")
    parser.add_argument("--protocol", choices=["mavlink", "crsf"], default="mavlink",
                         help="Telemetrieprotokoll (Standard: mavlink)")
    parser.add_argument("--lang", choices=["de", "en"], default=None,
                         help="UI-Sprache (Standard: zuletzt gespeicherte Sprache, sonst Deutsch; "
                              "auch zur Laufzeit ueber Menue -> Sprache umschaltbar)")

    parser.add_argument("--connection", choices=["udp", "usb"], default="udp",
                         help="Transportweg: 'udp' fuer WiFi-Bridge, 'usb' fuer direkte USB/seriell-Verbindung")
    parser.add_argument("--host", default="0.0.0.0", help="Lokale Bind-Adresse fuer den UDP-Empfang")
    parser.add_argument("--port", type=int, default=None,
                         help="UDP-Port (Standard: 14550 fuer MAVLink, 14551 fuer CRSF)")
    parser.add_argument("--udp-mode", choices=["listen", "connect"], default="listen",
                         help="MAVLink: 'listen' wartet auf eingehende Pakete, 'connect' verbindet aktiv zu --host:--port")

    parser.add_argument("--serial-port", default="",
                         help="USB/seriell-Port bei --connection usb, z.B. COM5")
    parser.add_argument("--baud", type=int, default=None,
                         help="Baudrate bei --connection usb (Standard: 57600 fuer MAVLink, 420000 fuer CRSF)")
    parser.add_argument("--list-ports", action="store_true",
                         help="Verfuegbare USB/seriell-Ports auflisten und beenden")

    parser.add_argument("--cells", type=int, default=4, help="Anzahl LiPo-Zellen fuer die Akku-Warnschwellen")
    parser.add_argument("--low-cell-voltage", type=float, default=3.6, help="Zellspannung fuer 'niedrig'-Warnung")
    parser.add_argument("--critical-cell-voltage", type=float, default=3.5, help="Zellspannung fuer 'kritisch'-Warnung")

    parser.add_argument("--demo-center", default="48.1372,11.5756",
                         help="Mittelpunkt der Demo-Flugbahn als 'lat,lon'")

    args = parser.parse_args(argv)

    if args.port is None:
        args.port = 14550 if args.protocol == "mavlink" else 14551

    if args.baud is None:
        args.baud = 57600 if args.protocol == "mavlink" else 420000

    if args.connection == "usb" and not args.serial_port and not args.list_ports and not args.demo:
        parser.error("--connection usb erfordert --serial-port (siehe --list-ports)")

    lat_str, lon_str = args.demo_center.split(",")
    args.demo_center = (float(lat_str), float(lon_str))

    return args


def _print_serial_ports(lang: str) -> None:
    from telemetry.serial_ports import list_serial_ports

    ports = list_serial_ports()
    if not ports:
        print("No USB/serial ports found." if lang == "en" else "Keine USB/seriell-Ports gefunden.")
        return
    for p in ports:
        print(f"{p.device}\t{p.description}")


def main() -> int:
    args = parse_args()

    if args.list_ports:
        _print_serial_ports(args.lang)
        return 0

    from PyQt6.QtWidgets import QApplication

    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow(args)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
