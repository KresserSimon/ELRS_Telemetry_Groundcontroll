import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.model_profiles import ModelProfile, load_profiles, save_profiles


class ModelProfilesRoundTripTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._config_path = Path(self._tmpdir.name) / "nested" / "model_profiles.json"
        self._patcher = mock.patch("core.model_profiles.CONFIG_PATH", self._config_path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()

    def test_load_missing_file_returns_empty_dict(self):
        self.assertEqual(load_profiles(), {})

    def test_save_then_load_round_trips(self):
        profiles = {
            "Quad 5\"": ModelProfile(
                name="Quad 5\"",
                battery_chemistry="lipo",
                battery_cells=6,
                battery_low_v=3.5,
                battery_critical_v=3.3,
                dashboard_visible_fields=["dash_lat", "dash_lon"],
                dashboard_group_order=["dash_gps", "dash_battery"],
                dashboard_rows=2,
            )
        }
        save_profiles(profiles)
        loaded = load_profiles()
        self.assertEqual(loaded, profiles)

    def test_save_creates_parent_directory(self):
        self.assertFalse(self._config_path.parent.exists())
        save_profiles({"A": ModelProfile(name="A")})
        self.assertTrue(self._config_path.exists())

    def test_load_ignores_malformed_entries(self):
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            json.dumps({"good": {"battery_cells": 4}, "bad": "not a dict"}), encoding="utf-8"
        )
        loaded = load_profiles()
        self.assertIn("good", loaded)
        self.assertNotIn("bad", loaded)

    def test_load_corrupt_json_returns_empty_dict(self):
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text("{not valid json", encoding="utf-8")
        self.assertEqual(load_profiles(), {})


if __name__ == "__main__":
    unittest.main()
