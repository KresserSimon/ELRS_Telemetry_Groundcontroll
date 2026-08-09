import base64
import tempfile
import unittest
from pathlib import Path

from ui.pmtiles_bridge import PMTilesBridge


class PMTilesBridgeTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._file_path = Path(self._tmpdir.name) / "sample.pmtiles"
        self._file_path.write_bytes(bytes(range(256)) * 4)  # 1024 distinct-ish bytes
        self._bridge = PMTilesBridge()

    def tearDown(self):
        self._bridge.close()
        self._tmpdir.cleanup()

    def test_get_key_empty_before_open(self):
        self.assertEqual(self._bridge.get_key(), "")

    def test_read_range_empty_before_open(self):
        self.assertEqual(self._bridge.read_range(0, 10), "")

    def test_get_key_is_the_opened_path(self):
        self._bridge.open(self._file_path)
        self.assertEqual(self._bridge.get_key(), str(self._file_path))

    def test_read_range_returns_correct_base64_bytes(self):
        self._bridge.open(self._file_path)
        result = self._bridge.read_range(10, 20)
        expected = (bytes(range(256)) * 4)[10:30]
        self.assertEqual(base64.b64decode(result), expected)

    def test_read_range_at_offset_zero(self):
        self._bridge.open(self._file_path)
        result = self._bridge.read_range(0, 5)
        self.assertEqual(base64.b64decode(result), bytes(range(5)))

    def test_read_range_past_end_of_file_returns_truncated_bytes(self):
        self._bridge.open(self._file_path)
        result = self._bridge.read_range(1020, 100)
        self.assertEqual(base64.b64decode(result), (bytes(range(256)) * 4)[1020:])

    def test_open_again_switches_file_and_closes_previous_handle(self):
        self._bridge.open(self._file_path)
        other_path = Path(self._tmpdir.name) / "other.pmtiles"
        other_path.write_bytes(b"different-content")
        self._bridge.open(other_path)
        self.assertEqual(self._bridge.get_key(), str(other_path))
        result = self._bridge.read_range(0, 9)
        self.assertEqual(base64.b64decode(result), b"different")

    def test_close_resets_state(self):
        self._bridge.open(self._file_path)
        self._bridge.close()
        self.assertEqual(self._bridge.get_key(), "")
        self.assertEqual(self._bridge.read_range(0, 10), "")


if __name__ == "__main__":
    unittest.main()
