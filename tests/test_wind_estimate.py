import unittest

from core.wind_estimate import estimate_wind_component


class EstimateWindComponentTest(unittest.TestCase):
    def test_none_when_groundspeed_missing(self):
        self.assertIsNone(estimate_wind_component(None, 10.0))

    def test_none_when_airspeed_missing(self):
        self.assertIsNone(estimate_wind_component(10.0, None))

    def test_none_when_both_missing(self):
        self.assertIsNone(estimate_wind_component(None, None))

    def test_tailwind_is_positive(self):
        # groundspeed exceeds airspeed - wind pushing along the track
        self.assertAlmostEqual(estimate_wind_component(15.0, 10.0), 5.0)

    def test_headwind_is_negative(self):
        self.assertAlmostEqual(estimate_wind_component(10.0, 15.0), -5.0)

    def test_mirrored_values_treated_as_no_real_sensor(self):
        # Multirotor firmware without an airspeed sensor mirrors
        # groundspeed into VFR_HUD.airspeed - must not look like zero wind.
        self.assertIsNone(estimate_wind_component(12.34, 12.34))

    def test_near_mirrored_within_epsilon_is_none(self):
        self.assertIsNone(estimate_wind_component(12.340, 12.341))

    def test_just_outside_epsilon_is_a_real_reading(self):
        result = estimate_wind_component(12.30, 12.40)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, -0.1, places=5)


if __name__ == "__main__":
    unittest.main()
