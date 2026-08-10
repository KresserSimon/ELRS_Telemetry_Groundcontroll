"""Computes a summary (duration, extremes, consumption) from a sequence of
TelemetryState samples - usable both for a completed live flight (load
whatever flight-log CSV was recorded, see
telemetry/replay_worker.py:parse_flight_log_csv()) and for a loaded replay,
since both are ultimately just a List[TelemetryState].
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core.geo import haversine_distance_m
from core.telemetry_state import TelemetryState


@dataclass
class FlightSummary:
    duration_s: float
    sample_count: int
    max_altitude_m: Optional[float]
    max_distance_m: Optional[float]
    min_link_quality: Optional[int]
    capacity_used_mah: Optional[float]
    avg_speed_ms: Optional[float]
    max_speed_ms: Optional[float]


def summarize(states: List[TelemetryState]) -> Optional[FlightSummary]:
    if not states:
        return None

    duration_s = max(0.0, states[-1].timestamp - states[0].timestamp)

    altitudes = [s.alt for s in states if s.alt is not None]
    max_altitude_m = max(altitudes) if altitudes else None

    fixes = [s for s in states if s.has_gps_fix()]
    max_distance_m = None
    if fixes:
        origin = fixes[0]
        max_distance_m = max(haversine_distance_m(origin.lat, origin.lon, s.lat, s.lon) for s in fixes)

    link_qualities = [s.link_quality for s in states if s.link_quality is not None]
    min_link_quality = min(link_qualities) if link_qualities else None

    # battery_capacity_used is cumulative (mAh consumed so far), so the
    # flight's total usage is its max, not a sum - summing would double
    # count every sample.
    capacities = [s.battery_capacity_used for s in states if s.battery_capacity_used is not None]
    capacity_used_mah = max(capacities) if capacities else None

    speeds = [s.groundspeed for s in states if s.groundspeed is not None]
    avg_speed_ms = sum(speeds) / len(speeds) if speeds else None
    max_speed_ms = max(speeds) if speeds else None

    return FlightSummary(
        duration_s=duration_s,
        sample_count=len(states),
        max_altitude_m=max_altitude_m,
        max_distance_m=max_distance_m,
        min_link_quality=min_link_quality,
        capacity_used_mah=capacity_used_mah,
        avg_speed_ms=avg_speed_ms,
        max_speed_ms=max_speed_ms,
    )


def format_summary_text(summary: FlightSummary) -> str:
    """Plain-text export, deliberately not localized via i18n so an
    exported file stays readable regardless of what language the app is
    running in whenever it's opened later."""
    lines = [
        f"Duration: {summary.duration_s:.0f} s ({summary.duration_s / 60:.1f} min)",
        f"Samples: {summary.sample_count}",
        f"Max altitude: {summary.max_altitude_m:.1f} m" if summary.max_altitude_m is not None else "Max altitude: n/a",
        f"Max distance from start: {summary.max_distance_m:.0f} m" if summary.max_distance_m is not None else "Max distance from start: n/a",
        f"Min link quality: {summary.min_link_quality}%" if summary.min_link_quality is not None else "Min link quality: n/a",
        f"Capacity used: {summary.capacity_used_mah:.0f} mAh" if summary.capacity_used_mah is not None else "Capacity used: n/a",
        f"Avg speed: {summary.avg_speed_ms * 3.6:.1f} km/h" if summary.avg_speed_ms is not None else "Avg speed: n/a",
        f"Max speed: {summary.max_speed_ms * 3.6:.1f} km/h" if summary.max_speed_ms is not None else "Max speed: n/a",
    ]
    return "\n".join(lines)
