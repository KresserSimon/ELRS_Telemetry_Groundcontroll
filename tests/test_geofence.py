import unittest
from dataclasses import dataclass
from typing import Optional

from core.geofence import check_geofence, find_out_of_bounds
from core.geofence_monitor import GeofenceMonitor
from core.telemetry_state import TelemetryState


class _FakeTts:
    def __init__(self) -> None:
        self.messages = []

    def say(self, text: str) -> None:
        self.messages.append(text)


@dataclass
class _FakeWaypoint:
    lat: float
    lon: float
    alt: Optional[float] = None


def _state(lat, lon, alt=None, timestamp=0.0):
    s = TelemetryState()
    s.lat, s.lon, s.alt, s.timestamp = lat, lon, alt, timestamp
    return s


class CheckGeofenceTest(unittest.TestCase):
    def test_inside_radius_and_altitude_is_not_breached(self):
        breach = check_geofence(47.0001, 9.0001, 50.0, (47.0, 9.0), 120.0, 120.0)
        self.assertFalse(breach.breached())

    def test_outside_radius_is_breached(self):
        breach = check_geofence(47.01, 9.0, 50.0, (47.0, 9.0), 120.0, 120.0)
        self.assertTrue(breach.outside_radius)
        self.assertTrue(breach.breached())

    def test_over_altitude_is_breached(self):
        breach = check_geofence(47.0, 9.0, 200.0, (47.0, 9.0), 120.0, 120.0)
        self.assertTrue(breach.over_altitude)
        self.assertTrue(breach.breached())

    def test_no_altitude_limit_never_flags_altitude(self):
        breach = check_geofence(47.0, 9.0, 5000.0, (47.0, 9.0), 120.0, None)
        self.assertFalse(breach.over_altitude)

    def test_missing_alt_reading_never_flags_altitude(self):
        breach = check_geofence(47.0, 9.0, None, (47.0, 9.0), 120.0, 120.0)
        self.assertFalse(breach.over_altitude)


class FindOutOfBoundsTest(unittest.TestCase):
    def test_flags_only_the_out_of_bounds_waypoints(self):
        waypoints = [
            _FakeWaypoint(47.0001, 9.0001, 50.0),   # inside
            _FakeWaypoint(48.0, 10.0, 50.0),        # far outside radius
            _FakeWaypoint(47.0, 9.0, 500.0),        # inside radius, over altitude
        ]
        result = find_out_of_bounds(waypoints, (47.0, 9.0), 120.0, 120.0)
        self.assertEqual(result, [1, 2])

    def test_empty_route_returns_empty(self):
        self.assertEqual(find_out_of_bounds([], (47.0, 9.0), 120.0, 120.0), [])


class GeofenceMonitorTest(unittest.TestCase):
    def setUp(self):
        self.tts = _FakeTts()
        self.monitor = GeofenceMonitor(self.tts)

    def test_disabled_never_speaks(self):
        self.monitor.check(_state(48.0, 10.0, 50.0, 0.0), (47.0, 9.0), 120.0, 120.0, enabled=False)
        self.assertEqual(self.tts.messages, [])
        self.assertIsNone(self.monitor.last_result())

    def test_no_reference_never_speaks(self):
        self.monitor.check(_state(48.0, 10.0, 50.0, 0.0), None, 120.0, 120.0, enabled=True)
        self.assertEqual(self.tts.messages, [])

    def test_within_bounds_never_speaks(self):
        self.monitor.check(_state(47.0001, 9.0001, 50.0, 0.0), (47.0, 9.0), 120.0, 120.0, enabled=True)
        self.assertEqual(self.tts.messages, [])

    def test_breach_speaks_once_then_cooldown(self):
        self.monitor.check(_state(48.0, 10.0, 50.0, 0.0), (47.0, 9.0), 120.0, 120.0, enabled=True)
        self.assertEqual(len(self.tts.messages), 1)
        self.monitor.check(_state(48.0, 10.0, 50.0, 5.0), (47.0, 9.0), 120.0, 120.0, enabled=True)
        self.assertEqual(len(self.tts.messages), 1)

    def test_reannounces_after_cooldown(self):
        self.monitor.check(_state(48.0, 10.0, 50.0, 0.0), (47.0, 9.0), 120.0, 120.0, enabled=True)
        self.monitor.check(_state(48.0, 10.0, 50.0, 31.0), (47.0, 9.0), 120.0, 120.0, enabled=True)
        self.assertEqual(len(self.tts.messages), 2)

    def test_returning_inside_then_breaching_again_speaks_again(self):
        self.monitor.check(_state(48.0, 10.0, 50.0, 0.0), (47.0, 9.0), 120.0, 120.0, enabled=True)
        self.assertEqual(len(self.tts.messages), 1)
        self.monitor.check(_state(47.0001, 9.0001, 50.0, 1.0), (47.0, 9.0), 120.0, 120.0, enabled=True)
        self.monitor.check(_state(48.0, 10.0, 50.0, 2.0), (47.0, 9.0), 120.0, 120.0, enabled=True)
        self.assertEqual(len(self.tts.messages), 2)

    def test_reset_clears_state(self):
        self.monitor.check(_state(48.0, 10.0, 50.0, 0.0), (47.0, 9.0), 120.0, 120.0, enabled=True)
        self.monitor.reset()
        self.assertIsNone(self.monitor.last_result())


if __name__ == "__main__":
    unittest.main()
