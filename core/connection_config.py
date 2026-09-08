"""Persists the last-used connection settings (protocol, transport, host/
port, serial port, baud) across restarts, so the startup connection dialog
reopens pre-filled with whatever was actually used last time instead of a
fixed CLI default. Follows the same load_*/save_* JSON-under-home-dir
pattern as every other core/*_config.py module.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

CONFIG_PATH = Path.home() / ".elrs_ground_station" / "connection_settings.json"


def load_connection_settings() -> Dict[str, Any]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_connection_settings(settings: Dict[str, Any]) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError:
        pass
