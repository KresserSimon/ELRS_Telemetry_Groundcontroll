import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.ui_state_config import load_ui_state, save_ui_state


class UiStateConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._config_path = Path(self._tmpdir.name) / "nested" / "ui_state.json"
        self._patcher = mock.patch("core.ui_state_config.CONFIG_PATH", self._config_path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()

    def test_load_missing_file_returns_empty_dict(self):
        self.assertEqual(load_ui_state(), {})

    def test_save_then_load_round_trips(self):
        state = {"auto_center": True, "language": "en", "horizon_scale": 1.5}
        save_ui_state(state)
        self.assertEqual(load_ui_state(), state)

    def test_save_creates_parent_directory(self):
        self.assertFalse(self._config_path.parent.exists())
        save_ui_state({"a": 1})
        self.assertTrue(self._config_path.exists())

    def test_load_corrupt_json_returns_empty_dict(self):
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text("{not valid", encoding="utf-8")
        self.assertEqual(load_ui_state(), {})

    def test_load_non_dict_json_returns_empty_dict(self):
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(load_ui_state(), {})


if __name__ == "__main__":
    unittest.main()
