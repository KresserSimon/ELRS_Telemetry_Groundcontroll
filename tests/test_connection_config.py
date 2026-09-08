import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.connection_config import load_connection_settings, save_connection_settings


class ConnectionConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._config_path = Path(self._tmpdir.name) / "nested" / "connection_settings.json"
        self._patcher = mock.patch("core.connection_config.CONFIG_PATH", self._config_path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()

    def test_load_missing_file_returns_empty_dict(self):
        self.assertEqual(load_connection_settings(), {})

    def test_save_then_load_round_trips(self):
        settings = {
            "protocol": "crsf",
            "connection": "usb",
            "host": "0.0.0.0",
            "port": 14551,
            "udp_mode": "listen",
            "serial_port": "COM5",
            "baud": 420000,
        }
        save_connection_settings(settings)
        self.assertEqual(load_connection_settings(), settings)

    def test_save_creates_parent_directory(self):
        self.assertFalse(self._config_path.parent.exists())
        save_connection_settings({"protocol": "crsf"})
        self.assertTrue(self._config_path.exists())

    def test_load_corrupt_json_returns_empty_dict(self):
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text("{not valid", encoding="utf-8")
        self.assertEqual(load_connection_settings(), {})

    def test_load_non_dict_json_returns_empty_dict(self):
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(load_connection_settings(), {})


if __name__ == "__main__":
    unittest.main()
