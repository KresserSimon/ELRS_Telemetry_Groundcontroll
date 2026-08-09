import unittest

from core.geo import haversine_distance_m
from core.nfz import NoFlyZone
from core.nfz_proximity import (
    NfzProximityMonitor,
    distance_to_zone_m,
    nearest_zone,
)
from core.telemetry_state import TelemetryState


class _FakeTts:
    def __init__(self) -> None:
        self.messages = []

    def say(self, text: str) -> None:
        self.messages.append(text)


def _state(lat, lon, timestamp=0.0):
    s = TelemetryState()
    s.lat, s.lon, s.timestamp = lat, lon, timestamp
    return s


class DistanceToZoneTest(unittest.TestCase):
    def test_circle_outside_matches_haversine_minus_radius(self):
        zone = NoFlyZone(name="Z", kind="circle", center=(47.0, 9.0), radius_m=200.0)
        expected = haversine_distance_m(47.01, 9.0, 47.0, 9.0) - 200.0
        self.assertAlmostEqual(distance_to_zone_m(47.01, 9.0, zone), expected, delta=0.5)

    def test_circle_inside_is_zero(self):
        zone = NoFlyZone(name="Z", kind="circle", center=(47.0, 9.0), radius_m=500.0)
        self.assertEqual(distance_to_zone_m(47.0001, 9.0001, zone), 0.0)

    def test_polygon_point_inside_is_zero(self):
        # A small square roughly centred on (47.0, 9.0).
        zone = NoFlyZone(
            name="Z", kind="polygon",
            points=[(46.999, 8.999), (47.001, 8.999), (47.001, 9.001), (46.999, 9.001)],
        )
        self.assertEqual(distance_to_zone_m(47.0, 9.0, zone), 0.0)

    def test_polygon_point_outside_is_positive_and_reasonable(self):
        zone = NoFlyZone(
            name="Z", kind="polygon",
            points=[(46.999, 8.999), (47.001, 8.999), (47.001, 9.001), (46.999, 9.001)],
        )
        # Roughly 222m north of the polygon's northern edge (~111m per 0.001 deg lat).
        distance = distance_to_zone_m(47.003, 9.0, zone)
        self.assertGreater(distance, 150.0)
        self.assertLess(distance, 300.0)

    def test_zone_without_geometry_is_infinite(self):
        zone = NoFlyZone(name="Z", kind="circle")  # no center/radius set
        self.assertEqual(distance_to_zone_m(47.0, 9.0, zone), float("inf"))


class NearestZoneTest(unittest.TestCase):
    def test_picks_the_closest_zone(self):
        near = NoFlyZone(name="Near", kind="circle", center=(47.0, 9.0), radius_m=10.0)
        far = NoFlyZone(name="Far", kind="circle", center=(48.0, 10.0), radius_m=10.0)
        result = nearest_zone(47.0, 9.0, [far, near])
        self.assertIsNotNone(result)
        self.assertEqual(result[0].name, "Near")

    def test_empty_list_returns_none(self):
        self.assertIsNone(nearest_zone(47.0, 9.0, []))


class NfzProximityMonitorTest(unittest.TestCase):
    def setUp(self):
        self.tts = _FakeTts()
        self.zone = NoFlyZone(name="Z", kind="circle", center=(47.0, 9.0), radius_m=50.0)
        self.monitor = NfzProximityMonitor(self.tts, threshold_m=50.0)

    def test_no_zones_never_speaks(self):
        self.monitor.check(_state(47.0, 9.0, 0.0), [])
        self.assertEqual(self.tts.messages, [])

    def test_no_gps_fix_never_speaks(self):
        state = TelemetryState()  # lat/lon stay None -> has_gps_fix() False
        self.monitor.check(state, [self.zone])
        self.assertEqual(self.tts.messages, [])

    def test_far_away_never_speaks(self):
        self.monitor.check(_state(48.0, 10.0, 0.0), [self.zone])
        self.assertEqual(self.tts.messages, [])

    def test_entering_threshold_speaks_once(self):
        self.monitor.check(_state(47.0, 9.0, 0.0), [self.zone])
        self.assertEqual(len(self.tts.messages), 1)
        # Still inside shortly after -> no repeat before the cooldown.
        self.monitor.check(_state(47.0, 9.0, 5.0), [self.zone])
        self.assertEqual(len(self.tts.messages), 1)

    def test_reannounces_after_cooldown(self):
        self.monitor.check(_state(47.0, 9.0, 0.0), [self.zone])
        self.monitor.check(_state(47.0, 9.0, 31.0), [self.zone])
        self.assertEqual(len(self.tts.messages), 2)

    def test_leaving_and_reentering_speaks_again(self):
        self.monitor.check(_state(47.0, 9.0, 0.0), [self.zone])
        self.assertEqual(len(self.tts.messages), 1)
        self.monitor.check(_state(48.0, 10.0, 1.0), [self.zone])  # far away -> resets
        self.monitor.check(_state(47.0, 9.0, 2.0), [self.zone])  # back in range
        self.assertEqual(len(self.tts.messages), 2)

    def test_last_result_reflects_most_recent_check(self):
        self.monitor.check(_state(47.0, 9.0, 0.0), [self.zone])
        result = self.monitor.last_result()
        self.assertIsNotNone(result)
        self.assertEqual(result[0].name, "Z")
        self.assertEqual(result[1], 0.0)


if __name__ == "__main__":
    unittest.main()
