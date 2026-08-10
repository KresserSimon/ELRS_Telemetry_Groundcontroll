"""Rough wind estimate from the ground-/airspeed difference - see
docs/feature_plan.md's "Windschaetzung". Only meaningful on a fixed-wing
with a real airspeed sensor: most multirotor firmware has no airspeed
sensor and mirrors groundspeed into MAVLink VFR_HUD.airspeed, which would
otherwise look like a (false) zero-wind reading - estimate_wind_component()
treats a (near-)equal pair as "no real airspeed data" instead.

Deliberately a scalar along-track component, not a full wind vector (speed
+ direction) - a true wind vector needs heading/multiple headings over
time, which is a materially bigger feature than what "aus der Differenz"
describes.
"""
from __future__ import annotations

from typing import Optional

# groundspeed/airspeed closer than this look mirrored (no real sensor), not
# a genuine (near-)zero-wind measurement - small enough to not swallow a
# real light-wind reading from an actual airspeed sensor.
_MIRRORED_EPSILON_MS = 0.05


def estimate_wind_component(groundspeed: Optional[float], airspeed: Optional[float]) -> Optional[float]:
    """Wind component along the current track, in m/s. Positive = tailwind
    (groundspeed exceeds airspeed), negative = headwind. None if either
    value is missing, or they're close enough to look mirrored rather than
    a genuine independent airspeed reading."""
    if groundspeed is None or airspeed is None:
        return None
    if abs(groundspeed - airspeed) < _MIRRORED_EPSILON_MS:
        return None
    return groundspeed - airspeed
