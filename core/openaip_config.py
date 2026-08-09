"""Persists the user's OpenAIP integration settings (API key, base URL
override, preferred airspace type codes) across runs, in a small JSON file
under the user's home directory - same pattern as core/home_config.py and
core/dashboard_config.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, TypedDict

from core.openaip_import import DEFAULT_BASE_URL

CONFIG_PATH = Path.home() / ".elrs_ground_station" / "openaip_config.json"


class OpenAipConfig(TypedDict):
    api_key: str
    base_url: str
    preferred_types: List[str]


def load_openaip_config() -> OpenAipConfig:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    preferred = data.get("preferred_types")
    return {
        "api_key": str(data.get("api_key", "")),
        "base_url": str(data.get("base_url") or DEFAULT_BASE_URL),
        "preferred_types": list(preferred) if isinstance(preferred, list) else [],
    }


def save_openaip_config(api_key: str, base_url: str, preferred_types: List[str]) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {"api_key": api_key, "base_url": base_url, "preferred_types": preferred_types}
        CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass
