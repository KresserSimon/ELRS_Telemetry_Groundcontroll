import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from PyQt6.QtCore import QUrl

import ui.tile_cache_handler as tile_cache_handler
from ui.tile_cache_handler import _cache_path, _fetch_tile_bytes, parse_tile_url, upstream_url


class ParseTileUrlTest(unittest.TestCase):
    def test_valid_osm_url(self):
        result = parse_tile_url(QUrl("elrstile://osm/5/16/10.png"))
        self.assertEqual(result, ("osm", "5", "16", "10"))

    def test_valid_satellite_url(self):
        result = parse_tile_url(QUrl("elrstile://satellite/3/2/1.png"))
        self.assertEqual(result, ("satellite", "3", "2", "1"))

    def test_unknown_layer_rejected(self):
        self.assertIsNone(parse_tile_url(QUrl("elrstile://bogus/5/16/10.png")))

    def test_wrong_path_depth_rejected(self):
        self.assertIsNone(parse_tile_url(QUrl("elrstile://osm/5/16.png")))
        self.assertIsNone(parse_tile_url(QUrl("elrstile://osm/5/16/10/2.png")))

    def test_missing_extension_rejected(self):
        self.assertIsNone(parse_tile_url(QUrl("elrstile://osm/5/16/10")))

    def test_non_numeric_components_rejected(self):
        self.assertIsNone(parse_tile_url(QUrl("elrstile://osm/z/16/10.png")))
        self.assertIsNone(parse_tile_url(QUrl("elrstile://osm/5/../10.png")))


class UpstreamUrlTest(unittest.TestCase):
    def test_osm_keeps_zxy_order(self):
        url = upstream_url("osm", "5", "16", "10")
        self.assertEqual(url, "https://tile.openstreetmap.org/5/16/10.png")

    def test_satellite_swaps_x_and_y(self):
        url = upstream_url("satellite", "5", "16", "10")
        self.assertIn("/5/10/16", url)


class CachePathTest(unittest.TestCase):
    def test_layout_is_layer_z_x_y(self):
        path = _cache_path("osm", "5", "16", "10")
        self.assertEqual(path.parts[-4:], ("osm", "5", "16", "10.tile"))


class FetchTileBytesTest(unittest.TestCase):
    """_fetch_tile_bytes() is the pure cache-or-network function the
    concurrent QThreadPool worker (_TileFetchTask) runs off the GUI thread -
    it must never touch any Qt/WebEngine job object itself, only return
    plain bytes or None, since that's what makes running it on an arbitrary
    worker thread safe."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patcher = mock.patch.object(tile_cache_handler, "CACHE_DIR", Path(self._tmpdir.name))
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()

    def test_cache_hit_returns_cached_bytes_without_network_call(self):
        cache_file = _cache_path("osm", "5", "16", "10")
        cache_file.parent.mkdir(parents=True)
        cache_file.write_bytes(b"cached-tile-bytes")
        with mock.patch("urllib.request.urlopen") as urlopen:
            result = _fetch_tile_bytes("osm", "5", "16", "10")
        urlopen.assert_not_called()
        self.assertEqual(result, b"cached-tile-bytes")

    def test_cache_miss_fetches_from_network_and_writes_cache(self):
        response = mock.MagicMock()
        response.read.return_value = b"downloaded-tile-bytes"
        response.__enter__.return_value = response
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            result = _fetch_tile_bytes("osm", "5", "16", "10")
        urlopen.assert_called_once()
        self.assertEqual(result, b"downloaded-tile-bytes")
        self.assertEqual(_cache_path("osm", "5", "16", "10").read_bytes(), b"downloaded-tile-bytes")

    def test_network_failure_returns_none(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no connection")):
            result = _fetch_tile_bytes("osm", "5", "16", "10")
        self.assertIsNone(result)

    def test_corrupt_cache_read_falls_back_to_network(self):
        cache_file = _cache_path("osm", "5", "16", "10")
        cache_file.parent.mkdir(parents=True)
        cache_file.write_bytes(b"stale")
        response = mock.MagicMock()
        response.read.return_value = b"fresh-tile-bytes"
        response.__enter__.return_value = response
        with mock.patch.object(Path, "read_bytes", side_effect=OSError("locked")):
            with mock.patch("urllib.request.urlopen", return_value=response):
                result = _fetch_tile_bytes("osm", "5", "16", "10")
        self.assertEqual(result, b"fresh-tile-bytes")


if __name__ == "__main__":
    unittest.main()
