import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.dashboard_config import DEFAULT_POSITION, load_dashboard_position, save_dashboard_position


class DashboardPositionTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._config_path = Path(self._tmpdir.name) / "dashboard_position.json"
        self._patcher = mock.patch("core.dashboard_config.POSITION_CONFIG_PATH", self._config_path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()

    def test_load_missing_file_returns_default(self):
        self.assertEqual(load_dashboard_position(), DEFAULT_POSITION)

    def test_save_then_load_round_trips(self):
        save_dashboard_position("left")
        self.assertEqual(load_dashboard_position(), "left")

    def test_load_invalid_value_falls_back_to_default(self):
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text('{"position": "diagonal"}', encoding="utf-8")
        self.assertEqual(load_dashboard_position(), DEFAULT_POSITION)

    def test_load_corrupt_json_falls_back_to_default(self):
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text("{not valid json", encoding="utf-8")
        self.assertEqual(load_dashboard_position(), DEFAULT_POSITION)


if __name__ == "__main__":
    unittest.main()
