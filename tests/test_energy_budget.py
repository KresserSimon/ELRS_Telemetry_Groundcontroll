import unittest

from core.energy_budget import (
    LEVEL_GREEN,
    LEVEL_RED,
    ConsumptionRateEstimator,
    EnergyBudgetMonitor,
    consumption_rate_from_current,
    estimate,
)
from core.telemetry_state import TelemetryState


class _FakeTts:
    def __init__(self) -> None:
        self.messages = []

    def say(self, text: str) -> None:
        self.messages.append(text)


def _state(lat=47.0, lon=9.0, groundspeed=10.0, battery_current=None,
           battery_remaining=None, battery_capacity_used=None, timestamp=0.0):
    s = TelemetryState()
    s.lat, s.lon = lat, lon
    s.groundspeed = groundspeed
    s.battery_current = battery_current
    s.battery_remaining = battery_remaining
    s.battery_capacity_used = battery_capacity_used
    s.timestamp = timestamp
    return s


class ConsumptionRateFromCurrentTest(unittest.TestCase):
    def test_none_current_is_none(self):
        self.assertIsNone(consumption_rate_from_current(None))

    def test_converts_amps_to_mah_per_second(self):
        # 36 A -> 36000 mAh/h -> 10 mAh/s
        self.assertAlmostEqual(consumption_rate_from_current(36.0), 10.0, places=6)


class ConsumptionRateEstimatorTest(unittest.TestCase):
    def test_single_sample_is_not_enough(self):
        est = ConsumptionRateEstimator(window_s=10.0)
        self.assertIsNone(est.add_sample(0.0, 100.0))

    def test_slope_over_window(self):
        est = ConsumptionRateEstimator(window_s=10.0)
        est.add_sample(0.0, 100.0)
        rate = est.add_sample(5.0, 150.0)  # +50 mAh over 5s -> 10 mAh/s
        self.assertAlmostEqual(rate, 10.0, places=6)

    def test_old_samples_drop_out_of_window(self):
        est = ConsumptionRateEstimator(window_s=10.0)
        est.add_sample(0.0, 100.0)
        # 20s later is outside the 10s window - the t=0 sample must have
        # been dropped, so the slope below is computed from just these two
        # in-window samples (10 mAh over 1s), not the much larger jump
        # since t=0 (200 mAh over 20s) that a non-windowed average would give.
        est.add_sample(20.0, 300.0)
        rate = est.add_sample(21.0, 310.0)
        self.assertAlmostEqual(rate, 10.0, places=3)

    def test_missing_capacity_used_returns_none(self):
        est = ConsumptionRateEstimator()
        self.assertIsNone(est.add_sample(0.0, None))


class EstimateTest(unittest.TestCase):
    def test_missing_distance_is_not_computable(self):
        result = estimate(None, 10.0, 5.0, 1300.0, 80, None)
        self.assertIsNone(result.level)

    def test_missing_rate_is_not_computable(self):
        result = estimate(500.0, 10.0, None, 1300.0, 80, None)
        self.assertIsNone(result.level)

    def test_missing_remaining_and_used_is_not_computable_but_has_mah_for_home(self):
        result = estimate(500.0, 10.0, 5.0, 1300.0, None, None)
        self.assertIsNone(result.level)
        self.assertIsNotNone(result.mah_for_home)

    def test_uses_min_speed_assumption_when_near_hover(self):
        # groundspeed ~0 -> falls back to min_speed_assumption_ms, not division by ~0.
        result = estimate(100.0, 0.0, 5.0, 1300.0, 80, None, min_speed_assumption_ms=5.0)
        self.assertAlmostEqual(result.mah_for_home, (100.0 / 5.0) * 5.0, places=3)

    def test_high_reserve_is_green(self):
        # 1300 mAh capacity, 90% remaining = 1170 mAh, home costs little.
        result = estimate(50.0, 10.0, 1.0, 1300.0, 90, None, min_speed_assumption_ms=5.0,
                           yellow_threshold_pct=15.0, green_threshold_pct=30.0)
        self.assertEqual(result.level, LEVEL_GREEN)

    def test_low_reserve_is_red(self):
        result = estimate(5000.0, 10.0, 10.0, 1300.0, 20, None, min_speed_assumption_ms=5.0,
                           yellow_threshold_pct=15.0, green_threshold_pct=30.0)
        self.assertEqual(result.level, LEVEL_RED)

    def test_uses_capacity_used_fallback_when_no_remaining_pct(self):
        result = estimate(50.0, 10.0, 1.0, 1300.0, None, 100.0, min_speed_assumption_ms=5.0)
        self.assertIsNotNone(result.level)
        self.assertAlmostEqual(result.remaining_mah, 1200.0, places=3)


class EnergyBudgetMonitorTest(unittest.TestCase):
    def setUp(self):
        self.tts = _FakeTts()
        self.monitor = EnergyBudgetMonitor(self.tts)

    def test_no_home_reference_never_speaks(self):
        self.monitor.check(_state(battery_current=10.0, timestamp=0.0), None, 1300.0, 5.0, 15.0, 30.0)
        self.assertEqual(self.tts.messages, [])

    def test_transition_to_red_speaks(self):
        home = (47.0, 9.0)
        # Far from home, high drain, low remaining -> red immediately.
        state = _state(lat=48.0, lon=10.0, groundspeed=10.0, battery_current=50.0,
                        battery_remaining=15, timestamp=0.0)
        self.monitor.check(state, home, 1300.0, 5.0, 15.0, 30.0)
        self.assertEqual(len(self.tts.messages), 1)

    def test_staying_green_never_speaks(self):
        home = (47.0, 9.0)
        state = _state(lat=47.001, lon=9.001, groundspeed=10.0, battery_current=1.0,
                        battery_remaining=95, timestamp=0.0)
        self.monitor.check(state, home, 1300.0, 5.0, 15.0, 30.0)
        self.assertEqual(self.tts.messages, [])

    def test_reset_clears_level(self):
        home = (47.0, 9.0)
        state = _state(lat=48.0, lon=10.0, battery_current=50.0, battery_remaining=15, timestamp=0.0)
        self.monitor.check(state, home, 1300.0, 5.0, 15.0, 30.0)
        self.monitor.reset()
        self.assertIsNone(self.monitor.last_result().level)


if __name__ == "__main__":
    unittest.main()
