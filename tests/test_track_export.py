import csv
import tempfile
import unittest
from pathlib import Path

from core.telemetry_state import TelemetryState
from export.flight_logger import ALL_FIELDS, field_value
from export.track_export import TrackRecorder
from telemetry.replay_worker import parse_flight_log_csv


def _state(**kwargs) -> TelemetryState:
    defaults = dict(lat=47.5, lon=9.7, alt=100.0, timestamp=1_700_000_000.0)
    defaults.update(kwargs)
    return TelemetryState(**defaults)


class FieldValueTest(unittest.TestCase):
    def test_timestamp_formats_as_local_iso_without_z(self):
        value = field_value(_state(timestamp=1_700_000_000.0), "timestamp")
        self.assertNotIn("Z", value)
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

    def test_cell_voltages_join_with_pipe(self):
        value = field_value(_state(cell_voltages=[4.1, 4.05, 4.08]), "cell_voltages")
        self.assertEqual(value, "4.100|4.050|4.080")

    def test_missing_cell_voltages_is_empty_string(self):
        self.assertEqual(field_value(_state(cell_voltages=None), "cell_voltages"), "")

    def test_none_field_is_empty_string(self):
        self.assertEqual(field_value(_state(battery_voltage=None), "battery_voltage"), "")

    def test_plain_field_passes_through(self):
        self.assertEqual(field_value(_state(rssi=-55), "rssi"), -55)


class TrackRecorderCsvTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._path = str(Path(self._tmpdir.name) / "track.csv")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_add_point_without_gps_fix_is_ignored(self):
        recorder = TrackRecorder()
        recorder.add_point(_state(lat=None, lon=None))
        self.assertEqual(len(recorder), 0)

    def test_add_point_with_fix_is_kept(self):
        recorder = TrackRecorder()
        recorder.add_point(_state())
        self.assertEqual(len(recorder), 1)

    def test_csv_header_is_all_fields_not_just_position(self):
        recorder = TrackRecorder()
        recorder.add_point(_state())
        recorder.export_csv(self._path)
        with open(self._path, encoding="utf-8") as f:
            header = next(csv.reader(f))
        self.assertEqual(tuple(header), ALL_FIELDS)
        self.assertIn("battery_voltage", header)
        self.assertIn("rssi", header)

    def test_csv_carries_full_telemetry_not_just_lat_lon_alt(self):
        # The point of this feature: a "Flugpfad als CSV exportieren" file
        # previously only had timestamp/lat/lon/alt - battery, link
        # quality etc. were silently discarded even though they were
        # right there on the TelemetryState the whole time.
        recorder = TrackRecorder()
        recorder.add_point(_state(battery_voltage=16.7, rssi=-52, link_quality=88, flight_mode="LOITER"))
        recorder.export_csv(self._path)
        with open(self._path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["battery_voltage"], "16.7")
        self.assertEqual(row["rssi"], "-52")
        self.assertEqual(row["link_quality"], "88")
        self.assertEqual(row["flight_mode"], "LOITER")

    def test_exported_csv_round_trips_through_replay_parser(self):
        recorder = TrackRecorder()
        recorder.add_point(_state(timestamp=1_700_000_000.0, battery_voltage=16.7, satellites=11))
        recorder.add_point(_state(timestamp=1_700_000_001.0, battery_voltage=16.6, satellites=11))
        recorder.export_csv(self._path)

        states = parse_flight_log_csv(self._path)
        self.assertEqual(len(states), 2)
        self.assertAlmostEqual(states[0].battery_voltage, 16.7)
        self.assertEqual(states[0].satellites, 11)
        self.assertAlmostEqual(states[1].timestamp - states[0].timestamp, 1.0)

    def test_multiple_points_preserve_order(self):
        recorder = TrackRecorder()
        for lat in (47.1, 47.2, 47.3):
            recorder.add_point(_state(lat=lat))
        recorder.export_csv(self._path)
        with open(self._path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual([row["lat"] for row in rows], ["47.1", "47.2", "47.3"])


class TrackRecorderGpxKmlTest(unittest.TestCase):
    """GPX/KML export is unaffected by the CSV change - a quick regression
    smoke test that switching TrackRecorder to store full TelemetryState
    objects instead of the old narrow TrackPoint didn't break these."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_export_gpx_contains_the_recorded_position(self):
        path = str(Path(self._tmpdir.name) / "track.gpx")
        recorder = TrackRecorder()
        recorder.add_point(_state(lat=47.123456, lon=9.654321, alt=88.5))
        recorder.export_gpx(path)
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn('lat="47.1234560"', content)
        self.assertIn('lon="9.6543210"', content)

    def test_export_kml_contains_the_recorded_position(self):
        path = str(Path(self._tmpdir.name) / "track.kml")
        recorder = TrackRecorder()
        recorder.add_point(_state(lat=47.123456, lon=9.654321, alt=88.5))
        recorder.export_kml(path)
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn("9.6543210,47.1234560,88.5", content)


if __name__ == "__main__":
    unittest.main()
