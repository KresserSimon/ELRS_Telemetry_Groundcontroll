import json
import tempfile
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest import mock

from core.openaip_cache import cache_key, get_cached_geojson, load_openaip_cache, store_geojson
from core.openaip_import import OpenAipError, fetch_airspaces_geojson

_FC = {"type": "FeatureCollection", "features": []}


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class OpenAipCacheRoundTripTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._cache_path = Path(self._tmpdir.name) / "openaip_cache.json"
        self._patcher = mock.patch("core.openaip_cache.CACHE_PATH", self._cache_path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()

    def test_load_missing_file_returns_empty_dict(self):
        self.assertEqual(load_openaip_cache(), {})

    def test_store_then_get_round_trips(self):
        store_geojson("https://api.example/airspaces", 48.1, 11.5, _FC)
        self.assertEqual(get_cached_geojson("https://api.example/airspaces", 48.1, 11.5), _FC)

    def test_get_missing_region_returns_none(self):
        self.assertIsNone(get_cached_geojson("https://api.example/airspaces", 1.0, 1.0))

    def test_cache_key_rounds_coarsely(self):
        self.assertEqual(cache_key("u", 48.123, 11.987), cache_key("u", 48.126, 11.981))


class FetchAirspacesCachingTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._cache_path = Path(self._tmpdir.name) / "openaip_cache.json"
        self._patcher = mock.patch("core.openaip_cache.CACHE_PATH", self._cache_path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()

    def test_successful_fetch_populates_cache(self):
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse(_FC)):
            result = fetch_airspaces_geojson("https://api.example/airspaces", "", 48.1, 11.5)
        self.assertEqual(result, _FC)
        self.assertEqual(get_cached_geojson("https://api.example/airspaces", 48.1, 11.5), _FC)

    def test_network_failure_falls_back_to_cache(self):
        store_geojson("https://api.example/airspaces", 48.1, 11.5, _FC)
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            result = fetch_airspaces_geojson("https://api.example/airspaces", "", 48.1, 11.5)
        self.assertEqual(result, _FC)

    def test_network_failure_without_cache_raises(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            with self.assertRaises(OpenAipError):
                fetch_airspaces_geojson("https://api.example/airspaces", "", 5.0, 5.0)


if __name__ == "__main__":
    unittest.main()
