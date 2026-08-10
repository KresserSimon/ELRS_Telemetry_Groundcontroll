import tempfile
import unittest
from pathlib import Path

import core.gs_position as gs_position_module
from core.gs_position import (
    GsPosition,
    clear_gs_position,
    compute_azimuth_elevation,
    load_gs_position,
    save_gs_position,
)


class ComputeAzimuthElevationTest(unittest.TestCase):
    def test_model_due_north_gives_zero_azimuth(self):
        result = compute_azimuth_elevation(47.0, 9.0, 500.0, 47.01, 9.0, 600.0)
        self.assertLess(result.azimuth_deg, 2.0)

    def test_model_due_east_gives_ninety_azimuth(self):
        result = compute_azimuth_elevation(47.0, 9.0, 500.0, 47.0, 9.02, 500.0)
        self.assertAlmostEqual(result.azimuth_deg, 90.0, delta=2.0)

    def test_missing_ground_altitude_gives_no_elevation(self):
        result = compute_azimuth_elevation(47.0, 9.0, None, 47.01, 9.0, 600.0)
        self.assertIsNone(result.elevation_deg)

    def test_missing_model_altitude_gives_no_elevation(self):
        result = compute_azimuth_elevation(47.0, 9.0, 500.0, 47.01, 9.0, None)
        self.assertIsNone(result.elevation_deg)

    def test_model_higher_than_ground_gives_positive_elevation(self):
        result = compute_azimuth_elevation(47.0, 9.0, 500.0, 47.001, 9.0, 700.0)
        self.assertIsNotNone(result.elevation_deg)
        self.assertGreater(result.elevation_deg, 0.0)

    def test_model_lower_than_ground_gives_negative_elevation(self):
        result = compute_azimuth_elevation(47.0, 9.0, 700.0, 47.001, 9.0, 500.0)
        self.assertIsNotNone(result.elevation_deg)
        self.assertLess(result.elevation_deg, 0.0)

    def test_directly_overhead_gives_elevation_near_ninety(self):
        result = compute_azimuth_elevation(47.0, 9.0, 500.0, 47.0, 9.0, 1500.0)
        self.assertGreater(result.elevation_deg, 80.0)


class PersistenceTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_path = gs_position_module.CONFIG_PATH
        gs_position_module.CONFIG_PATH = Path(self._tmpdir.name) / "gs_position.json"

    def tearDown(self):
        gs_position_module.CONFIG_PATH = self._orig_path
        self._tmpdir.cleanup()

    def test_load_missing_file_returns_none(self):
        self.assertIsNone(load_gs_position())

    def test_save_then_load_round_trips(self):
        save_gs_position(GsPosition(lat=47.5, lon=9.7, alt=430.0, source="manual"))
        loaded = load_gs_position()
        self.assertIsNotNone(loaded)
        self.assertAlmostEqual(loaded.lat, 47.5)
        self.assertAlmostEqual(loaded.lon, 9.7)
        self.assertAlmostEqual(loaded.alt, 430.0)
        self.assertEqual(loaded.source, "manual")

    def test_save_without_altitude_round_trips_none(self):
        save_gs_position(GsPosition(lat=47.5, lon=9.7, alt=None))
        loaded = load_gs_position()
        self.assertIsNotNone(loaded)
        self.assertIsNone(loaded.alt)

    def test_clear_removes_the_file(self):
        save_gs_position(GsPosition(lat=47.5, lon=9.7))
        clear_gs_position()
        self.assertIsNone(load_gs_position())

    def test_clear_when_nothing_saved_does_not_raise(self):
        clear_gs_position()  # must not raise


if __name__ == "__main__":
    unittest.main()
