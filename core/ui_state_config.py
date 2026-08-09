"""Persists the app's runtime view/UI state - menu toggle states, overlay
sizes/positions/dock state, base layer, vehicle type, language - as one
JSON blob, so restarting the app restores the workspace as it was left.
Follows the same load_*/save_* pattern as every other core/*_config.py
module; unlike some of those, this one is a single flat dict rather than
per-setting files, since the number of individually small UI toggles here
would otherwise mean a JSON file per checkbox.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

CONFIG_PATH = Path.home() / ".elrs_ground_station" / "ui_state.json"


def load_ui_state() -> Dict[str, Any]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_ui_state(state: Dict[str, Any]) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass
