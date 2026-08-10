import tempfile
import unittest
from pathlib import Path

from telemetry.replay_worker import ReplayWorker, parse_flight_log_csv
from core.telemetry_state import TelemetryState


class ParseFlightLogCsvTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _write(self, header, rows) -> str:
        path = Path(self._tmpdir.name) / "log.csv"
        lines = [",".join(header)]
        for row in rows:
            lines.append(",".join(row))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(path)

    def test_empty_file_returns_empty_list(self):
        path = Path(self._tmpdir.name) / "empty.csv"
        path.write_text("", encoding="utf-8")
        self.assertEqual(parse_flight_log_csv(str(path)), [])

    def test_header_only_returns_empty_list(self):
        path = self._write(["timestamp", "lat", "lon"], [])
        self.assertEqual(parse_flight_log_csv(path), [])

    def test_full_row_parses_correctly(self):
        path = self._write(
            ["timestamp", "lat", "lon", "alt", "satellites", "link_quality", "flight_mode", "connected", "cell_voltages"],
            [["2026-01-01T12:00:00", "47.5", "9.7", "123.4", "11", "88", "LOITER", "True", "4.100|4.050|4.080"]],
        )
        states = parse_flight_log_csv(path)
        self.assertEqual(len(states), 1)
        s = states[0]
        self.assertEqual(s.source, "replay")
        self.assertAlmostEqual(s.lat, 47.5)
        self.assertAlmostEqual(s.lon, 9.7)
        self.assertAlmostEqual(s.alt, 123.4)
        self.assertEqual(s.satellites, 11)
        self.assertEqual(s.link_quality, 88)
        self.assertEqual(s.flight_mode, "LOITER")
        self.assertTrue(s.connected)
        self.assertEqual(s.cell_voltages, [4.100, 4.050, 4.080])

    def test_partial_columns_leave_other_fields_none(self):
        path = self._write(["timestamp", "lat", "lon"], [["2026-01-01T12:00:00", "47.5", "9.7"]])
        states = parse_flight_log_csv(path)
        self.assertEqual(len(states), 1)
        self.assertIsNone(states[0].battery_voltage)
        self.assertIsNone(states[0].rssi)

    def test_empty_cell_stays_none_not_zero(self):
        path = self._write(["timestamp", "alt"], [["2026-01-01T12:00:00", ""]])
        self.assertIsNone(parse_flight_log_csv(path)[0].alt)

    def test_missing_timestamp_column_gets_synthetic_increasing_values(self):
        path = self._write(["lat", "lon"], [["47.0", "9.0"], ["47.1", "9.1"], ["47.2", "9.2"]])
        states = parse_flight_log_csv(path)
        timestamps = [s.timestamp for s in states]
        self.assertEqual(timestamps, [0.0, 1.0, 2.0])

    def test_timestamps_round_trip_through_the_real_logger_format(self):
        # Matches export/flight_logger.py's exact strftime format.
        path = self._write(["timestamp"], [["2026-03-15T08:30:45"]])
        states = parse_flight_log_csv(path)
        self.assertEqual(len(states), 1)
        self.assertGreater(states[0].timestamp, 0)

    def test_rows_stay_in_file_order(self):
        path = self._write(
            ["timestamp", "lat"],
            [["2026-01-01T12:00:00", "1.0"], ["2026-01-01T12:00:01", "2.0"], ["2026-01-01T12:00:02", "3.0"]],
        )
        states = parse_flight_log_csv(path)
        self.assertEqual([s.lat for s in states], [1.0, 2.0, 3.0])


class ReplayWorkerControlQueueTest(unittest.TestCase):
    def _states(self, n):
        return [TelemetryState(source="replay", timestamp=float(i)) for i in range(n)]

    def test_construct_with_empty_states_does_not_raise(self):
        ReplayWorker([])  # just constructing must be safe

    def test_speed_is_clamped_to_a_minimum(self):
        worker = ReplayWorker(self._states(3), speed=0.0)
        self.assertGreater(worker._speed, 0.0)

    def test_control_queue_applies_speed_change(self):
        worker = ReplayWorker(self._states(3))
        worker.set_speed(2.5)
        worker._drain_control_queue()
        self.assertAlmostEqual(worker._speed, 2.5)

    def test_control_queue_applies_pause(self):
        worker = ReplayWorker(self._states(3))
        worker.set_paused(True)
        worker._drain_control_queue()
        self.assertTrue(worker._paused)
        worker.set_paused(False)
        worker._drain_control_queue()
        self.assertFalse(worker._paused)

    def test_control_queue_applies_seek(self):
        worker = ReplayWorker(self._states(10))
        worker.seek(5)
        worker._drain_control_queue()
        self.assertEqual(worker._seek_to, 5)

    def test_multiple_queued_controls_apply_in_order(self):
        worker = ReplayWorker(self._states(10))
        worker.set_speed(1.0)
        worker.set_speed(3.0)
        worker.set_paused(True)
        worker._drain_control_queue()
        self.assertAlmostEqual(worker._speed, 3.0)
        self.assertTrue(worker._paused)


if __name__ == "__main__":
    unittest.main()
