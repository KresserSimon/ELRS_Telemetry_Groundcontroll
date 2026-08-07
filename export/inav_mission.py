"""INAV mission (.mission) JSON import/export.

This is INAV Configurator's modern JSON-based mission format (schema
"version": "1.0"), distinct from the older MW-XML .mission format that
export.route_import.import_inav_mission() reads (used by mwp/older
Configurator versions/ezgui). Both share the .mission extension; callers
that need to accept either should sniff the content first (see
export.route_import.import_route_file(), which does exactly that).

Schema::

    {
      "version": "1.0",
      "mission": [
        {"action": "WAYPOINT", "lat": 47.348210, "lon": 9.619120, "alt": 50,
         "speed": 0, "p1": 0, "p2": 0, "p3": 0}
      ]
    }

core.route.Waypoint carries the action/speed/p1/p2/p3 fields directly (with
WAYPOINT/0/0/0/0 defaults so every other import/export path, which knows
nothing about INAV missions, is unaffected) - so this module reads and
writes plain List[Waypoint], the same type the rest of the app's route
tooling (RouteManager, GPX/CSV import/export, the waypoint editor) already
works with.
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import List

from core.route import Waypoint

SCHEMA_VERSION = "1.0"


class MissionAction(str, Enum):
    """Supported INAV mission item actions and what their p1/p2/p3 mean.

    WAYPOINT: p1 = hold time in seconds (0 = pass-through, no hover).
    HOLD:     p1 = hold duration in seconds.
    RTH:      return to home; lat/lon/alt may legitimately be 0.
    SET_POI:  lat/lon/alt define the camera point-of-interest; p1-p3 unused.
    JUMP:     p1 = target mission-item index (1-based), p2 = repeat count.
    LAND:     automatic landing at lat/lon.
    """

    WAYPOINT = "WAYPOINT"
    HOLD = "HOLD"
    RTH = "RTH"
    SET_POI = "SET_POI"
    JUMP = "JUMP"
    LAND = "LAND"


# Actions after which a vehicle has well-defined behaviour with nothing
# further scheduled - used by validate_mission() to flag a mission that
# would otherwise "fall off the end" with undefined behaviour.
TERMINAL_ACTIONS = (MissionAction.RTH, MissionAction.LAND, MissionAction.HOLD)

_REQUIRED_FIELDS = ("action", "lat", "lon", "alt")


class MissionValidationError(ValueError):
    """A .mission JSON file is corrupt, incomplete, or uses an incompatible
    schema version. The message always names the offending field/entry."""


# ------------------------------------------------------------------ export

def export_inav_mission(waypoints: List[Waypoint], path: str) -> None:
    """Write waypoints as a pretty-printed INAV .mission JSON file.

    Raises MissionValidationError if any waypoint's `action` isn't one of
    MissionAction's values (guards against silently writing a file INAV
    itself would then reject).
    """
    items = []
    for index, wp in enumerate(waypoints):
        try:
            action = MissionAction(wp.action)
        except ValueError as exc:
            valid = ", ".join(a.value for a in MissionAction)
            raise MissionValidationError(
                f"Wegpunkt {index}: unbekannte Aktion '{wp.action}' (erlaubt: {valid})."
            ) from exc
        items.append({
            "action": action.value,
            "lat": float(wp.lat),
            "lon": float(wp.lon),
            "alt": wp.alt if wp.alt is not None else 0.0,
            "speed": wp.speed,
            "p1": wp.p1,
            "p2": wp.p2,
            "p3": wp.p3,
        })

    payload = {"version": SCHEMA_VERSION, "mission": items}
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ import

def import_inav_mission_json(path: str) -> List[Waypoint]:
    """Read and validate an INAV .mission JSON file into a Waypoint list.

    Validates, in order: the file is valid JSON: a top-level 'version' field
    is present and equals SCHEMA_VERSION; 'mission' is a non-empty array;
    every entry is an object with the required action/lat/lon/alt fields and
    a recognised action. Raises MissionValidationError with a message that
    pinpoints the problem on any failure - never returns a partial result.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise MissionValidationError(f"Ungueltiges JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise MissionValidationError(f"Datei konnte nicht gelesen werden: {exc}") from exc

    if not isinstance(data, dict):
        raise MissionValidationError("Mission-Datei muss ein JSON-Objekt auf oberster Ebene sein.")

    version = data.get("version")
    if version is None:
        raise MissionValidationError("Fehlendes Pflichtfeld 'version'.")
    if str(version) != SCHEMA_VERSION:
        raise MissionValidationError(
            f"Nicht unterstuetzte Mission-Schema-Version '{version}' (erwartet '{SCHEMA_VERSION}')."
        )

    raw_items = data.get("mission")
    if not isinstance(raw_items, list) or not raw_items:
        raise MissionValidationError("'mission' muss ein nicht-leeres Array sein.")

    waypoints: List[Waypoint] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise MissionValidationError(f"Mission-Eintrag {index} ist kein Objekt.")

        missing = [field for field in _REQUIRED_FIELDS if field not in raw]
        if missing:
            raise MissionValidationError(f"Mission-Eintrag {index}: Pflichtfeld(er) fehlen: {', '.join(missing)}.")

        try:
            action = MissionAction(str(raw["action"]))
        except ValueError as exc:
            valid = ", ".join(a.value for a in MissionAction)
            raise MissionValidationError(
                f"Mission-Eintrag {index}: unbekannte Aktion '{raw['action']}' (erlaubt: {valid})."
            ) from exc

        try:
            lat = float(raw["lat"])
            lon = float(raw["lon"])
            alt = float(raw["alt"])
        except (TypeError, ValueError) as exc:
            raise MissionValidationError(f"Mission-Eintrag {index}: lat/lon/alt muessen Zahlen sein.") from exc

        try:
            speed = float(raw.get("speed", 0) or 0)
            p1 = int(raw.get("p1", 0) or 0)
            p2 = int(raw.get("p2", 0) or 0)
            p3 = int(raw.get("p3", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise MissionValidationError(f"Mission-Eintrag {index}: speed/p1/p2/p3 muessen Zahlen sein.") from exc

        waypoints.append(Waypoint(
            lat=lat, lon=lon, alt=alt, name=f"{action.value} {index + 1}",
            action=action.value, speed=speed, p1=p1, p2=p2, p3=p3,
        ))

    return waypoints


# ----------------------------------------------------------------- helpers

def validate_mission(waypoints: List[Waypoint]) -> List[str]:
    """Best-effort pre-export sanity checks.

    Returns a list of human-readable warnings (empty if none found). Never
    raises and never blocks - the caller decides whether to still proceed,
    e.g. by showing the warnings and letting the user confirm.
    """
    warnings: List[str] = []
    if not waypoints:
        warnings.append("Mission enthaelt keine Wegpunkte.")
        return warnings

    try:
        last_action = MissionAction(waypoints[-1].action)
    except ValueError:
        last_action = None
    if last_action not in TERMINAL_ACTIONS:
        warnings.append(
            "Mission endet nicht mit RTH, LAND oder HOLD - das Fahrzeug haette nach dem "
            "letzten Wegpunkt kein definiertes Verhalten mehr."
        )

    for index, wp in enumerate(waypoints):
        if wp.action == MissionAction.JUMP.value and not (1 <= wp.p1 <= len(waypoints)):
            warnings.append(
                f"Wegpunkt {index + 1}: JUMP-Ziel {wp.p1} liegt ausserhalb der Mission (1-{len(waypoints)})."
            )

    return warnings
