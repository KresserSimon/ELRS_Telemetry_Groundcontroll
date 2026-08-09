import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.elevation_cache import cache_key, load_elevation_cache, save_elevation_cache
from core.terrain import TerrainLookupError, fetch_elevations


class ElevationCacheRoundTripTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._cache_path = Path(self._tmpdir.name) / "elevation_cache.json"
        self._patcher = mock.patch("core.elevation_cache.CACHE_PATH", self._cache_path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()

    def test_load_missing_file_returns_empty_dict(self):
        self.assertEqual(load_elevation_cache(), {})

    def test_save_then_load_round_trips(self):
        save_elevation_cache({cache_key(48.1, 11.5): 520.0})
        self.assertEqual(load_elevation_cache(), {cache_key(48.1, 11.5): 520.0})

    def test_cache_key_rounds_to_fixed_precision(self):
        self.assertEqual(cache_key(48.123456789, 11.987654321), cache_key(48.12346, 11.98765))

    def test_load_corrupt_json_returns_empty_dict(self):
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text("{not valid", encoding="utf-8")
        self.assertEqual(load_elevation_cache(), {})


class FetchElevationsCachingTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._cache_path = Path(self._tmpdir.name) / "elevation_cache.json"
        self._patcher = mock.patch("core.elevation_cache.CACHE_PATH", self._cache_path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()

    def test_fully_cached_points_need_no_network_call(self):
        save_elevation_cache({cache_key(1.0, 2.0): 100.0, cache_key(3.0, 4.0): 200.0})
        with mock.patch("core.terrain._fetch_elevations_online") as fetch_mock:
            result = fetch_elevations([(1.0, 2.0), (3.0, 4.0)])
        fetch_mock.assert_not_called()
        self.assertEqual(result, [100.0, 200.0])

    def test_missing_points_trigger_network_and_populate_cache(self):
        with mock.patch("core.terrain._fetch_elevations_online", return_value=[42.0]) as fetch_mock:
            result = fetch_elevations([(5.0, 6.0)])
        fetch_mock.assert_called_once_with([(5.0, 6.0)])
        self.assertEqual(result, [42.0])
        self.assertEqual(load_elevation_cache()[cache_key(5.0, 6.0)], 42.0)

    def test_mixed_cached_and_missing_only_fetches_missing(self):
        save_elevation_cache({cache_key(1.0, 2.0): 100.0})
        with mock.patch("core.terrain._fetch_elevations_online", return_value=[55.0]) as fetch_mock:
            result = fetch_elevations([(1.0, 2.0), (7.0, 8.0)])
        fetch_mock.assert_called_once_with([(7.0, 8.0)])
        self.assertEqual(result, [100.0, 55.0])

    def test_network_failure_with_missing_points_still_raises(self):
        with mock.patch("core.terrain._fetch_elevations_online", side_effect=TerrainLookupError("offline")):
            with self.assertRaises(TerrainLookupError):
                fetch_elevations([(9.0, 9.0)])

    def test_empty_points_returns_empty_without_touching_cache(self):
        with mock.patch("core.terrain._fetch_elevations_online") as fetch_mock:
            self.assertEqual(fetch_elevations([]), [])
        fetch_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
