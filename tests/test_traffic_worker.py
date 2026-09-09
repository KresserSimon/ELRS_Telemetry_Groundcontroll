import unittest

from core.traffic_config import ALTITUDE_MODE_AGL, ALTITUDE_MODE_MSL
from core.traffic_import import AircraftState
from core.traffic_worker import _passes_altitude_filter


def _aircraft(alt_m):
    return AircraftState(
        icao24="abc", callsign="TEST1", lat=48.0, lon=11.0,
        alt_m=alt_m, heading_deg=90.0, groundspeed_ms=100.0, vertical_rate_ms=0.0,
    )


class PassesAltitudeFilterTest(unittest.TestCase):
    def test_unknown_altitude_is_never_hidden(self):
        self.assertTrue(_passes_altitude_filter(_aircraft(None), 1500.0, ALTITUDE_MODE_MSL, None))
        self.assertTrue(_passes_altitude_filter(_aircraft(None), 1500.0, ALTITUDE_MODE_AGL, 500.0))

    def test_msl_mode_compares_raw_altitude(self):
        self.assertTrue(_passes_altitude_filter(_aircraft(1400.0), 1500.0, ALTITUDE_MODE_MSL, 500.0))
        self.assertFalse(_passes_altitude_filter(_aircraft(1600.0), 1500.0, ALTITUDE_MODE_MSL, 500.0))

    def test_agl_mode_subtracts_ground_reference(self):
        # 2000 m MSL over 500 m ground = 1500 m AGL -> exactly at the limit, passes
        self.assertTrue(_passes_altitude_filter(_aircraft(2000.0), 1500.0, ALTITUDE_MODE_AGL, 500.0))
        # An airliner cruising at 10,000 m MSL over the same terrain is far above the AGL limit
        self.assertFalse(_passes_altitude_filter(_aircraft(10000.0), 1500.0, ALTITUDE_MODE_AGL, 500.0))

    def test_agl_mode_without_ground_reference_falls_back_to_raw_altitude(self):
        # No ground elevation available (e.g. offline, uncached point) -
        # core/traffic_worker.py's _poll_once() documents this as a
        # deliberate MSL fallback for that poll rather than hiding everything.
        self.assertTrue(_passes_altitude_filter(_aircraft(1400.0), 1500.0, ALTITUDE_MODE_AGL, None))
        self.assertFalse(_passes_altitude_filter(_aircraft(1600.0), 1500.0, ALTITUDE_MODE_AGL, None))

    def test_ground_on_or_above_aircraft_still_passes_at_zero_agl(self):
        self.assertTrue(_passes_altitude_filter(_aircraft(500.0), 1500.0, ALTITUDE_MODE_AGL, 500.0))


class LoadTrafficConfigTest(unittest.TestCase):
    def test_missing_config_file_defaults_to_agl(self):
        import pathlib
        from unittest.mock import patch

        from core.traffic_config import load_traffic_config

        with patch("core.traffic_config.CONFIG_PATH", pathlib.Path("/nonexistent/traffic_config.json")):
            config = load_traffic_config()
        self.assertEqual(config["altitude_mode"], ALTITUDE_MODE_AGL)
        self.assertFalse(config["enabled"])


if __name__ == "__main__":
    unittest.main()
