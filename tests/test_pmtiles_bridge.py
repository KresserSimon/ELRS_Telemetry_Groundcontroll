import base64
import json
import tempfile
import unittest
from pathlib import Path

from ui.pmtiles_bridge import PMTilesBridge


class PMTilesBridgeTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._file_path = Path(self._tmpdir.name) / "austria.pmtiles"
        self._file_path.write_bytes(bytes(range(256)) * 4)  # 1024 distinct-ish bytes
        self._bridge = PMTilesBridge()

    def tearDown(self):
        self._bridge.close()
        self._tmpdir.cleanup()

    def test_get_keys_json_empty_before_open(self):
        self.assertEqual(json.loads(self._bridge.get_keys_json()), [])

    def test_read_range_empty_before_open(self):
        self.assertEqual(self._bridge.read_range("austria", 0, 10), "")

    def test_read_range_for_unknown_key_returns_empty(self):
        self._bridge.open_all([self._file_path])
        self.assertEqual(self._bridge.read_range("germany", 0, 10), "")

    def test_get_keys_json_is_the_opened_filename_stems_in_order(self):
        self._bridge.open_all([self._file_path])
        self.assertEqual(json.loads(self._bridge.get_keys_json()), ["austria"])

    def test_read_range_returns_correct_base64_bytes(self):
        self._bridge.open_all([self._file_path])
        result = self._bridge.read_range("austria", 10, 20)
        expected = (bytes(range(256)) * 4)[10:30]
        self.assertEqual(base64.b64decode(result), expected)

    def test_read_range_at_offset_zero(self):
        self._bridge.open_all([self._file_path])
        result = self._bridge.read_range("austria", 0, 5)
        self.assertEqual(base64.b64decode(result), bytes(range(5)))

    def test_read_range_past_end_of_file_returns_truncated_bytes(self):
        self._bridge.open_all([self._file_path])
        result = self._bridge.read_range("austria", 1020, 100)
        self.assertEqual(base64.b64decode(result), (bytes(range(256)) * 4)[1020:])

    def test_open_all_with_multiple_files_keeps_order_and_reads_the_right_one(self):
        other_path = Path(self._tmpdir.name) / "germany.pmtiles"
        other_path.write_bytes(b"different-content")
        self._bridge.open_all([self._file_path, other_path])
        self.assertEqual(json.loads(self._bridge.get_keys_json()), ["austria", "germany"])
        result = self._bridge.read_range("germany", 0, 9)
        self.assertEqual(base64.b64decode(result), b"different")
        # The first archive is still independently readable, not shadowed
        # by the second open_all() call.
        result = self._bridge.read_range("austria", 0, 5)
        self.assertEqual(base64.b64decode(result), bytes(range(5)))

    def test_open_all_again_replaces_the_previous_set_and_closes_old_handles(self):
        self._bridge.open_all([self._file_path])
        other_path = Path(self._tmpdir.name) / "germany.pmtiles"
        other_path.write_bytes(b"different-content")
        self._bridge.open_all([other_path])
        self.assertEqual(json.loads(self._bridge.get_keys_json()), ["germany"])
        self.assertEqual(self._bridge.read_range("austria", 0, 10), "")

    def test_close_resets_state(self):
        self._bridge.open_all([self._file_path])
        self._bridge.close()
        self.assertEqual(json.loads(self._bridge.get_keys_json()), [])
        self.assertEqual(self._bridge.read_range("austria", 0, 10), "")


if __name__ == "__main__":
    unittest.main()
