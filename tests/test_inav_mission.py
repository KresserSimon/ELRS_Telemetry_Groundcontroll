import json
import os
import tempfile
import unittest

from core.route import Waypoint
from export.inav_mission import (
    MissionAction,
    MissionValidationError,
    export_inav_mission,
    import_inav_mission_json,
    validate_mission,
)


class InavMissionRoundTripTest(unittest.TestCase):
    def _roundtrip(self, waypoints):
        fd, path = tempfile.mkstemp(suffix=".mission")
        os.close(fd)
        try:
            export_inav_mission(waypoints, path)
            return import_inav_mission_json(path), path
        finally:
            os.remove(path)

    def test_roundtrip_all_action_types(self):
        waypoints = [
            Waypoint(47.348210, 9.619120, 50, "wp1", action="WAYPOINT", speed=5, p1=3),
            Waypoint(47.349000, 9.620000, 60, "hold1", action="HOLD", p1=10),
            Waypoint(0, 0, 0, "rth", action="RTH"),
            Waypoint(47.350000, 9.621000, 40, "poi", action="SET_POI"),
            Waypoint(47.348210, 9.619120, 50, "jump1", action="JUMP", p1=1, p2=2),
            Waypoint(47.351000, 9.622000, 0, "land", action="LAND"),
        ]
        result, _ = self._roundtrip(waypoints)
        self.assertEqual(len(result), len(waypoints))
        for original, restored in zip(waypoints, result):
            self.assertAlmostEqual(original.lat, restored.lat)
            self.assertAlmostEqual(original.lon, restored.lon)
            self.assertAlmostEqual(original.alt, restored.alt)
            self.assertEqual(original.action, restored.action)
            self.assertAlmostEqual(original.speed, restored.speed)
            self.assertEqual(original.p1, restored.p1)
            self.assertEqual(original.p2, restored.p2)
            self.assertEqual(original.p3, restored.p3)

    def test_export_writes_expected_schema(self):
        waypoints = [Waypoint(47.348210, 9.619120, 50, "wp1")]
        fd, path = tempfile.mkstemp(suffix=".mission")
        os.close(fd)
        try:
            export_inav_mission(waypoints, path)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["version"], "1.0")
            self.assertEqual(len(data["mission"]), 1)
            item = data["mission"][0]
            self.assertEqual(item["action"], "WAYPOINT")
            self.assertIsInstance(item["lat"], float)
            self.assertIsInstance(item["lon"], float)
            self.assertEqual(item["p1"], 0)
        finally:
            os.remove(path)

    def test_export_rejects_unknown_action(self):
        waypoints = [Waypoint(1, 2, 3, action="FLY_TO_MOON")]
        fd, path = tempfile.mkstemp(suffix=".mission")
        os.close(fd)
        try:
            with self.assertRaises(MissionValidationError):
                export_inav_mission(waypoints, path)
        finally:
            os.remove(path)


class InavMissionImportValidationTest(unittest.TestCase):
    def _write(self, payload) -> str:
        fd, path = tempfile.mkstemp(suffix=".mission")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            if isinstance(payload, str):
                f.write(payload)
            else:
                json.dump(payload, f)
        self.addCleanup(os.remove, path)
        return path

    def test_missing_version(self):
        path = self._write({"mission": [{"action": "WAYPOINT", "lat": 1, "lon": 2, "alt": 3}]})
        with self.assertRaises(MissionValidationError):
            import_inav_mission_json(path)

    def test_wrong_version(self):
        path = self._write({"version": "2.0", "mission": [{"action": "WAYPOINT", "lat": 1, "lon": 2, "alt": 3}]})
        with self.assertRaises(MissionValidationError):
            import_inav_mission_json(path)

    def test_missing_mission_array(self):
        path = self._write({"version": "1.0"})
        with self.assertRaises(MissionValidationError):
            import_inav_mission_json(path)

    def test_empty_mission_array(self):
        path = self._write({"version": "1.0", "mission": []})
        with self.assertRaises(MissionValidationError):
            import_inav_mission_json(path)

    def test_missing_required_field(self):
        path = self._write({"version": "1.0", "mission": [{"action": "WAYPOINT", "lat": 1, "lon": 2}]})
        with self.assertRaises(MissionValidationError):
            import_inav_mission_json(path)

    def test_unknown_action(self):
        path = self._write({"version": "1.0", "mission": [{"action": "TELEPORT", "lat": 1, "lon": 2, "alt": 3}]})
        with self.assertRaises(MissionValidationError):
            import_inav_mission_json(path)

    def test_corrupt_json(self):
        path = self._write("{ this is not valid json")
        with self.assertRaises(MissionValidationError):
            import_inav_mission_json(path)

    def test_defaults_applied_when_optional_fields_missing(self):
        path = self._write({"version": "1.0", "mission": [{"action": "WAYPOINT", "lat": 1, "lon": 2, "alt": 3}]})
        result = import_inav_mission_json(path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].speed, 0.0)
        self.assertEqual(result[0].p1, 0)
        self.assertEqual(result[0].p2, 0)
        self.assertEqual(result[0].p3, 0)


class ValidateMissionTest(unittest.TestCase):
    def test_empty_mission_warns(self):
        self.assertTrue(validate_mission([]))

    def test_non_terminal_ending_warns(self):
        warnings = validate_mission([Waypoint(1, 2, 3, action="WAYPOINT")])
        self.assertTrue(any("RTH" in w for w in warnings))

    def test_terminal_ending_no_warning_about_ending(self):
        warnings = validate_mission([
            Waypoint(1, 2, 3, action="WAYPOINT"),
            Waypoint(1, 2, 0, action="RTH"),
        ])
        self.assertFalse(any("RTH" in w for w in warnings))

    def test_jump_target_out_of_range_warns(self):
        warnings = validate_mission([
            Waypoint(1, 2, 3, action="JUMP", p1=99),
            Waypoint(1, 2, 0, action="RTH"),
        ])
        self.assertTrue(any("JUMP" in w for w in warnings))

    def test_jump_target_in_range_no_warning(self):
        warnings = validate_mission([
            Waypoint(1, 2, 3, action="JUMP", p1=1),
            Waypoint(1, 2, 0, action="RTH"),
        ])
        self.assertFalse(any("JUMP" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
