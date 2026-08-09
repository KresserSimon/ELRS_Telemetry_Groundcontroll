import unittest

from PyQt6.QtCore import QUrl

from ui.tile_cache_handler import _cache_path, parse_tile_url, upstream_url


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


if __name__ == "__main__":
    unittest.main()
