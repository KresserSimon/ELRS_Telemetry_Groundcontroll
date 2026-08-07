"""Persists which dashboard fields the user wants shown ("their standard")
across runs, in a small JSON file under the user's home directory.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Set

CONFIG_PATH = Path.home() / ".elrs_ground_station" / "dashboard_fields.json"


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
