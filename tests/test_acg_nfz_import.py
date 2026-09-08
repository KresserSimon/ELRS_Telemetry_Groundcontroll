import json
import unittest
from tempfile import NamedTemporaryFile

from core.acg_nfz_import import (
    is_acg_zone_format,
    load_bundled_austria_zones,
    import_acg_zone_file,
    zones_from_acg_data,
)


def _zone(restriction, name, lon=16.0, lat=48.0, size=0.1):
    return {
        "zoneId": "test-1",
        "identifier": "acg_test",
        "name": name,
        "restriction": restriction,
        "message": f"{name} message",
        "geometry": [
            {
                "upperLimit": 100,
                "lowerLimit": 0,
                "horizontalProjection": {
                    "type": "Polygon",
                    "coordinates": [[
                        [lon, lat],
                        [lon + size, lat],
                        [lon + size, lat + size],
                        [lon, lat + size],
                        [lon, lat],
                    ]],
                },
            }
        ],
    }


class IsAcgZoneFormatTest(unittest.TestCase):
    def test_recognizes_zone_array(self):
        self.assertTrue(is_acg_zone_format([_zone("PROHIBITED", "X")]))

    def test_rejects_geojson_feature_collection(self):
        self.assertFalse(is_acg_zone_format({"type": "FeatureCollection", "features": []}))

    def test_rejects_empty_list(self):
        self.assertFalse(is_acg_zone_format([]))

    def test_rejects_list_of_non_dicts(self):
        self.assertFalse(is_acg_zone_format([1, 2, 3]))

    def test_rejects_dict_missing_restriction_or_geometry(self):
        self.assertFalse(is_acg_zone_format([{"name": "no restriction key"}]))


class ZonesFromAcgDataTest(unittest.TestCase):
    def test_prohibited_and_req_authorisation_and_conditional_are_kept(self):
        data = [
            _zone("PROHIBITED", "Seibersdorf"),
            _zone("REQ_AUTHORISATION", "Ottenschlag"),
            _zone("CONDITIONAL", "Graz Airport"),
        ]
        zones = zones_from_acg_data(data)
        self.assertEqual(len(zones), 3)
        labels = {z.name.split(":")[0] for z in zones}
        self.assertEqual(labels, {"Flugverbot", "Genehmigungspflichtig", "Flugplatzzone"})

    def test_no_restriction_is_excluded(self):
        data = [_zone("NO_RESTRICTION", "Modellfluggebiet Fraham")]
        self.assertEqual(zones_from_acg_data(data), [])

    def test_message_used_as_label_text(self):
        zones = zones_from_acg_data([_zone("PROHIBITED", "Seibersdorf")])
        self.assertIn("Seibersdorf message", zones[0].name)

    def test_polygon_points_are_lat_lon_pairs(self):
        zones = zones_from_acg_data([_zone("PROHIBITED", "X", lon=16.5, lat=48.2, size=0.05)])
        first_point = zones[0].points[0]
        self.assertAlmostEqual(first_point[0], 48.2)  # lat
        self.assertAlmostEqual(first_point[1], 16.5)  # lon

    def test_non_dict_entries_are_skipped(self):
        zones = zones_from_acg_data(["not a dict", _zone("PROHIBITED", "X")])
        self.assertEqual(len(zones), 1)

    def test_restriction_missing_geometry_entries_produces_no_zones(self):
        zone = _zone("PROHIBITED", "X")
        zone["geometry"] = []
        self.assertEqual(zones_from_acg_data([zone]), [])


class ImportAcgZoneFileTest(unittest.TestCase):
    def test_valid_file_round_trips(self):
        data = [_zone("REQ_AUTHORISATION", "Ottenschlag")]
        with NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            path = f.name
        try:
            zones = import_acg_zone_file(path)
            self.assertEqual(len(zones), 1)
        finally:
            import os
            os.unlink(path)

    def test_non_list_json_raises(self):
        with NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": []}, f)
            path = f.name
        try:
            with self.assertRaises(ValueError):
                import_acg_zone_file(path)
        finally:
            import os
            os.unlink(path)

    def test_all_zones_excluded_raises(self):
        data = [_zone("NO_RESTRICTION", "Modellfluggebiet")]
        with NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            path = f.name
        try:
            with self.assertRaises(ValueError):
                import_acg_zone_file(path)
        finally:
            import os
            os.unlink(path)


class BundledAustriaZonesTest(unittest.TestCase):
    def test_real_bundled_file_parses(self):
        # Uses the actual assets/nfz/austria_uas_zones.json shipped with the
        # repo (a real Austro Control Dronespace export), not a fake -
        # confirms the bundled data itself is well-formed and non-empty.
        zones = load_bundled_austria_zones()
        self.assertGreater(len(zones), 100)
        for zone in zones:
            self.assertTrue(zone.name)
            self.assertGreaterEqual(len(zone.points), 3)

    def test_no_restriction_zones_are_not_included(self):
        zones = load_bundled_austria_zones()
        # Model-flying areas ("Modellfluggebiet") are NO_RESTRICTION and
        # must never show up labelled as a no-fly zone.
        self.assertFalse(any("Modellfluggebiet" in z.name and z.name.startswith("Flugverbot") for z in zones))


if __name__ == "__main__":
    unittest.main()
