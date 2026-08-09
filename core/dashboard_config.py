"""Persists which dashboard fields the user wants shown, and in what order/
how many rows the groups are arranged ("their standard") across runs, in
small JSON files under the user's home directory.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Set, Tuple

CONFIG_PATH = Path.home() / ".elrs_ground_station" / "dashboard_fields.json"
LAYOUT_CONFIG_PATH = Path.home() / ".elrs_ground_station" / "dashboard_layout.json"
POSITION_CONFIG_PATH = Path.home() / ".elrs_ground_station" / "dashboard_position.json"

VALID_POSITIONS = ("top", "bottom", "left", "right")
# A right-hand sidebar is the default so the artificial horizon/altitude
# track (docked into the telemetry panel by default too, see
# MainWindow._set_horizon_docked/_set_altitude_track_docked) sit in a
# proper "Telemetrieleiste" alongside the field matrix, not a thin strip
# under the map.
DEFAULT_POSITION = "right"


def load_visible_fields() -> Optional[Set[str]]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, list) and all(isinstance(k, str) for k in data):
        return set(data)
    return None


def save_visible_fields(keys: Set[str]) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(sorted(keys), indent=2), encoding="utf-8")
    except OSError:
        pass


def load_dashboard_layout() -> Optional[Tuple[List[str], int]]:
    try:
        data = json.loads(LAYOUT_CONFIG_PATH.read_text(encoding="utf-8"))
        group_order = data["group_order"]
        rows = int(data["rows"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if isinstance(group_order, list) and all(isinstance(k, str) for k in group_order) and rows >= 1:
        return group_order, rows
    return None


def save_dashboard_layout(group_order: List[str], rows: int) -> None:
    try:
        LAYOUT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {"group_order": group_order, "rows": rows}
        LAYOUT_CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def load_dashboard_position() -> str:
    try:
        data = json.loads(POSITION_CONFIG_PATH.read_text(encoding="utf-8"))
        position = data["position"]
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_POSITION
    return position if position in VALID_POSITIONS else DEFAULT_POSITION


def save_dashboard_position(position: str) -> None:
    try:
        POSITION_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        POSITION_CONFIG_PATH.write_text(json.dumps({"position": position}, indent=2), encoding="utf-8")
    except OSError:
        pass
