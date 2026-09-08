import csv
import json
import os
import unittest
from tempfile import NamedTemporaryFile

from export.nfz_import import import_nfz_file


class ImportNfzFileDispatchTest(unittest.TestCase):
    def _write(self, suffix, writer):
        with NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8", newline="") as f:
            writer(f)
            path = f.name
        self.addCleanup(os.unlink, path)
        return path

    def test_csv_extension_uses_csv_parser(self):
        def write_csv(f):
            w = csv.writer(f)
            w.writerow(["name", "lat", "lon", "radius_m"])
            w.writerow(["Test Zone", "48.2", "16.4", "300"])

        path = self._write(".csv", write_csv)
        zones = import_nfz_file(path)
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0].kind, "circle")

    def test_geojson_feature_collection_still_works(self):
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"name": "Test Polygon"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[16.0, 48.0], [16.1, 48.0], [16.1, 48.1], [16.0, 48.0]]],
                    },
                }
            ],
        }
        path = self._write(".json", lambda f: json.dump(geojson, f))
        zones = import_nfz_file(path)
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0].name, "Test Polygon")
        self.assertEqual(zones[0].kind, "polygon")

    def test_acg_zone_array_is_auto_detected(self):
        acg_data = [
            {
                "zoneId": "test",
                "name": "LOAA",
                "restriction": "PROHIBITED",
                "message": "Test Sperrzone",
                "geometry": [
                    {
                        "horizontalProjection": {
                            "type": "Polygon",
                            "coordinates": [[[16.0, 48.0], [16.1, 48.0], [16.1, 48.1], [16.0, 48.0]]],
                        }
                    }
                ],
            }
        ]
        path = self._write(".json", lambda f: json.dump(acg_data, f))
        zones = import_nfz_file(path)
        self.assertEqual(len(zones), 1)
        self.assertIn("Flugverbot", zones[0].name)
        self.assertIn("Test Sperrzone", zones[0].name)


if __name__ == "__main__":
    unittest.main()
