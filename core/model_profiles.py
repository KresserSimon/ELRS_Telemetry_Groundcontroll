"""Named, saveable bundles of per-model settings (battery + dashboard
layout) so a pilot switching between aircraft can reload the right setup
in one click instead of re-entering it. Persisted as a JSON dict of
name -> profile fields, following the same load_*/save_* pattern as
core/dashboard_config.py and core/home_config.py.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List

CONFIG_PATH = Path.home() / ".elrs_ground_station" / "model_profiles.json"


@dataclass
class ModelProfile:
    name: str
    battery_chemistry: str = "lipo"
    battery_cells: int = 4
    battery_low_v: float = 3.5
    battery_critical_v: float = 3.3
    battery_capacity_mah: int = 1300
    dashboard_visible_fields: List[str] = field(default_factory=list)
    dashboard_group_order: List[str] = field(default_factory=list)
    dashboard_rows: int = 1


def load_profiles() -> Dict[str, ModelProfile]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    profiles: Dict[str, ModelProfile] = {}
    for name, fields_dict in data.items():
        if not isinstance(fields_dict, dict):
            continue
        try:
            profiles[name] = ModelProfile(name=name, **{
                k: v for k, v in fields_dict.items() if k in ModelProfile.__dataclass_fields__ and k != "name"
            })
        except TypeError:
            continue
    return profiles


def save_profiles(profiles: Dict[str, ModelProfile]) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {name: asdict(profile) for name, profile in profiles.items()}
        CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass
