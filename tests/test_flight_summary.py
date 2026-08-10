import unittest

from core.flight_summary import format_summary_text, summarize
from core.telemetry_state import TelemetryState


def _state(**kwargs):
    s = TelemetryState()
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


class SummarizeTest(unittest.TestCase):
    def test_empty_list_returns_none(self):
        self.assertIsNone(summarize([]))

    def test_duration_is_last_minus_first_timestamp(self):
        states = [_state(timestamp=100.0), _state(timestamp=160.0)]
        result = summarize(states)
        self.assertAlmostEqual(result.duration_s, 60.0)

    def test_sample_count(self):
        states = [_state(timestamp=float(i)) for i in range(5)]
        self.assertEqual(summarize(states).sample_count, 5)

    def test_max_altitude_ignores_missing_values(self):
        states = [_state(timestamp=0.0, alt=10.0), _state(timestamp=1.0, alt=None), _state(timestamp=2.0, alt=50.0)]
        self.assertAlmostEqual(summarize(states).max_altitude_m, 50.0)

    def test_max_altitude_none_when_never_reported(self):
        states = [_state(timestamp=0.0), _state(timestamp=1.0)]
        self.assertIsNone(summarize(states).max_altitude_m)

    def test_max_distance_from_first_fix(self):
        states = [
            _state(timestamp=0.0, lat=47.0, lon=9.0),
            _state(timestamp=1.0, lat=47.01, lon=9.0),  # ~1.1 km north
            _state(timestamp=2.0, lat=47.0, lon=9.0),  # back at start
        ]
        result = summarize(states)
        self.assertIsNotNone(result.max_distance_m)
        self.assertGreater(result.max_distance_m, 1000.0)
        self.assertLess(result.max_distance_m, 1300.0)

    def test_max_distance_none_without_any_gps_fix(self):
        states = [_state(timestamp=0.0), _state(timestamp=1.0)]
        self.assertIsNone(summarize(states).max_distance_m)

    def test_min_link_quality(self):
        states = [_state(timestamp=0.0, link_quality=90), _state(timestamp=1.0, link_quality=40)]
        self.assertEqual(summarize(states).min_link_quality, 40)

    def test_capacity_used_is_max_not_sum(self):
        # battery_capacity_used is cumulative - summing would double count.
        states = [
            _state(timestamp=0.0, battery_capacity_used=100.0),
            _state(timestamp=1.0, battery_capacity_used=250.0),
            _state(timestamp=2.0, battery_capacity_used=400.0),
        ]
        self.assertAlmostEqual(summarize(states).capacity_used_mah, 400.0)

    def test_avg_and_max_speed(self):
        states = [
            _state(timestamp=0.0, groundspeed=10.0),
            _state(timestamp=1.0, groundspeed=20.0),
            _state(timestamp=2.0, groundspeed=30.0),
        ]
        result = summarize(states)
        self.assertAlmostEqual(result.avg_speed_ms, 20.0)
        self.assertAlmostEqual(result.max_speed_ms, 30.0)

    def test_format_summary_text_handles_missing_fields(self):
        states = [_state(timestamp=0.0), _state(timestamp=10.0)]
        text = format_summary_text(summarize(states))
        self.assertIn("n/a", text)
        self.assertIn("Duration", text)


if __name__ == "__main__":
    unittest.main()
