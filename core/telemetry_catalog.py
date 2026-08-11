"""Registry of auto-detected telemetry variables beyond the fixed
TelemetryState schema (see docs/feature_plan.md's "Telemetrie-Variablen-
Editor") - currently populated from MAVLink NAMED_VALUE_FLOAT/INT
(telemetry/mavlink_worker.py writes into TelemetryState.extra).

Two different lifetimes on purpose: which *keys* have been seen and their
last value are session-scoped (cleared on every new connection/demo/replay
start, like the live track - see clear()), but a user's custom display
name or "delete" (hidden) decision for a given key is a real, deliberate
preference and persists across restarts, same as dashboard_fields.json.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Set

OVERRIDES_PATH = Path.home() / ".elrs_ground_station" / "telemetry_variable_overrides.json"


@dataclass
class DiscoveredVariable:
    key: str
    last_value: float
    first_seen: float
    display_name: str = ""
    hidden: bool = False

    @property
    def label(self) -> str:
        return self.display_name or self.key


class TelemetryVariableCatalog:
    def __init__(self) -> None:
        self._variables: Dict[str, DiscoveredVariable] = {}
        overrides = _load_overrides()
        self._display_names: Dict[str, str] = dict(overrides.get("display_names", {}))
        self._hidden: Set[str] = set(overrides.get("hidden", []))

    def observe(self, extra: Mapping[str, float]) -> None:
        """Called with TelemetryState.extra on every telemetry tick -
        cheap no-op when empty (the common case: CRSF/demo without any
        NAMED_VALUE_* traffic, or a MAVLink source that simply doesn't
        send any)."""
        if not extra:
            return
        now = time.time()
        for key, value in extra.items():
            existing = self._variables.get(key)
            if existing is None:
                self._variables[key] = DiscoveredVariable(
                    key=key,
                    last_value=value,
                    first_seen=now,
                    display_name=self._display_names.get(key, ""),
                    hidden=key in self._hidden,
                )
            else:
                existing.last_value = value

    def variables(self, include_hidden: bool = False) -> List[DiscoveredVariable]:
        items = self._variables.values() if include_hidden else (v for v in self._variables.values() if not v.hidden)
        return sorted(items, key=lambda v: v.key)

    def set_display_name(self, key: str, name: str) -> None:
        variable = self._variables.get(key)
        if variable is None:
            return
        name = name.strip()
        variable.display_name = name
        if name:
            self._display_names[key] = name
        else:
            self._display_names.pop(key, None)
        self._save_overrides()

    def set_hidden(self, key: str, hidden: bool) -> None:
        variable = self._variables.get(key)
        if variable is None:
            return
        variable.hidden = hidden
        if hidden:
            self._hidden.add(key)
        else:
            self._hidden.discard(key)
        self._save_overrides()

    def clear(self) -> None:
        """Discovered keys/values are session-scoped (see the module
        docstring) - called on every new connection/demo/replay start,
        same as the live track recorder."""
        self._variables.clear()

    def _save_overrides(self) -> None:
        _save_overrides({"display_names": self._display_names, "hidden": sorted(self._hidden)})


def _load_overrides() -> dict:
    try:
        return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_overrides(data: dict) -> None:
    try:
        OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
        OVERRIDES_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass
