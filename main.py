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
    parser.add_argument("--host", default="0.0.0.0", help="Lokale Bind-Adresse fuer den UDP-Empfang")
    parser.add_argument("--port", type=int, default=None,
                         help="UDP-Port (Standard: 14550 fuer MAVLink, 14551 fuer CRSF)")
    parser.add_argument("--udp-mode", choices=["listen", "connect"], default="listen",
                         help="MAVLink: 'listen' wartet auf eingehende Pakete, 'connect' verbindet aktiv zu --host:--port")

    parser.add_argument("--cells", type=int, default=4, help="Anzahl LiPo-Zellen fuer die Akku-Warnschwellen")
    parser.add_argument("--low-cell-voltage", type=float, default=3.6, help="Zellspannung fuer 'niedrig'-Warnung")
    parser.add_argument("--critical-cell-voltage", type=float, default=3.5, help="Zellspannung fuer 'kritisch'-Warnung")

    parser.add_argument("--demo-center", default="48.1372,11.5756",
                         help="Mittelpunkt der Demo-Flugbahn als 'lat,lon'")

    args = parser.parse_args(argv)

    if args.port is None:
        args.port = 14550 if args.protocol == "mavlink" else 14551

    lat_str, lon_str = args.demo_center.split(",")
    args.demo_center = (float(lat_str), float(lon_str))

    return args


def main() -> int:
    args = parse_args()

    from PyQt6.QtWidgets import QApplication

    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow(args)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
