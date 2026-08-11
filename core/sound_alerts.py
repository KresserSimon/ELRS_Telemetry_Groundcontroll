"""Maps warning events to a custom EdgeTX sound file instead of (or in
addition to, as a fallback) the spoken TTS phrase - see alerts/tts_alert.py,
which is the actual playback point, and ui/sound_alert_settings_dialog.py,
which is the settings UI built on top of this module.

The available sounds are the EdgeTX voice-pack .wav files bundled under
assets/en/ (root + SCRIPTS/ + SYSTEM/ subfolders) - the same pack EdgeTX
radios ship with, so filenames are already meaningful to anyone who has
flown with EdgeTX (e.g. "batlow.wav", "crshof.wav").

Two different lifetimes on purpose, mirroring core/telemetry_catalog.py:
the sound catalog (which files exist) is derived fresh from disk every
time, but which sound a user picked per warning key is a real, deliberate
preference and persists across restarts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.resources import resource_path

OVERRIDES_PATH = Path.home() / ".elrs_ground_station" / "sound_alert_settings.json"

SOUNDS_DIR_PARTS: Tuple[str, ...] = ("assets", "en")


@dataclass(frozen=True)
class WarningType:
    key: str  # matches the tts_* i18n key used at the alerts.tts_alert.TTSWorker.say() call sites
    label_key: str  # short UI label i18n key (the tts_* text itself is a full spoken sentence, not a good label)


WARNING_TYPES: Tuple[WarningType, ...] = (
    WarningType("tts_low", "warnsound_type_battery_low"),
    WarningType("tts_critical", "warnsound_type_battery_critical"),
    WarningType("tts_geofence_breach", "warnsound_type_geofence_breach"),
    WarningType("tts_nfz_proximity", "warnsound_type_nfz_proximity"),
    WarningType("tts_energy_budget_low", "warnsound_type_energy_low"),
    WarningType("tts_energy_budget_critical", "warnsound_type_energy_critical"),
    WarningType("tts_model_lost", "warnsound_type_model_lost"),
)

_WARNING_KEYS = frozenset(w.key for w in WARNING_TYPES)

# Factory defaults, chosen and confirmed by the user out of the bundled
# EdgeTX pack - used whenever a warning has no entry yet in the user's own
# overrides file. Warnings not listed here still default to plain TTS.
DEFAULT_SOUND_OVERRIDES: Dict[str, str] = {
    "tts_low": "SCRIPTS/YAAPU/lowbat.wav",
    "tts_critical": "SCRIPTS/INAV/batcrt.wav",
    "tts_energy_budget_low": "SCRIPTS/YAAPU/bat50.wav",
    "tts_model_lost": "SYSTEM/telemok.wav",
}


@dataclass(frozen=True)
class SoundAsset:
    relative_path: str  # forward-slash path relative to assets/en/, used as the on-disk lookup key
    display_name: str  # e.g. "SYSTEM / crshof"


def list_available_sounds() -> List[SoundAsset]:
    base = resource_path(*SOUNDS_DIR_PARTS)
    if not base.is_dir():
        return []
    assets = []
    for path in base.rglob("*.wav"):
        rel = path.relative_to(base).as_posix()
        folder = "/".join(rel.split("/")[:-1])
        stem = path.stem
        display_name = f"{folder} / {stem}" if folder else stem
        assets.append(SoundAsset(relative_path=rel, display_name=display_name))
    return sorted(assets, key=lambda a: a.display_name.lower())


def get_sound_path(key: Optional[str]) -> Optional[Path]:
    if not key:
        return None
    overrides = load_overrides()
    # A key present in overrides always wins, even as "" (the user
    # explicitly picked "Text-to-speech (default)", overriding a factory
    # default sound for that warning) - only a key absent entirely falls
    # back to DEFAULT_SOUND_OVERRIDES.
    if key in overrides:
        relative_path = overrides[key]
    else:
        relative_path = DEFAULT_SOUND_OVERRIDES.get(key, "")
    if not relative_path:
        return None
    candidate = resource_path(*SOUNDS_DIR_PARTS, *relative_path.split("/"))
    return candidate if candidate.is_file() else None


def set_sound(key: str, relative_path: Optional[str]) -> None:
    if key not in _WARNING_KEYS:
        return
    overrides = load_overrides()
    overrides[key] = relative_path or ""
    _save_overrides(overrides)


def load_overrides() -> Dict[str, str]:
    try:
        data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def _save_overrides(overrides: Dict[str, str]) -> None:
    try:
        OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
        OVERRIDES_PATH.write_text(json.dumps(overrides, indent=2), encoding="utf-8")
    except OSError:
        pass
