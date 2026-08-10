import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication

from core.route import Waypoint
from telemetry.mavlink_mission import (
    MAV_MISSION_ACCEPTED,
    MissionDownloadSession,
    MissionUploadSession,
    mission_item_params_to_waypoint,
    waypoint_to_mission_item_params,
)

_app = QApplication.instance() or QApplication([])


class WaypointMissionItemMappingTest(unittest.TestCase):
    def test_plain_waypoint_maps_to_nav_waypoint_command(self):
        wp = Waypoint(lat=47.5, lon=9.7, alt=50.0, action="WAYPOINT", p1=3)
        params = waypoint_to_mission_item_params(wp)
        self.assertEqual(params["command"], 16)  # MAV_CMD_NAV_WAYPOINT
        self.assertAlmostEqual(params["param1"], 3.0)  # hold time
        self.assertEqual(params["x"], round(47.5 * 1e7))
        self.assertEqual(params["y"], round(9.7 * 1e7))
        self.assertAlmostEqual(params["z"], 50.0)

    def test_rth_maps_to_return_to_launch(self):
        wp = Waypoint(lat=0.0, lon=0.0, action="RTH")
        params = waypoint_to_mission_item_params(wp)
        self.assertEqual(params["command"], 20)  # MAV_CMD_NAV_RETURN_TO_LAUNCH

    def test_land_maps_to_nav_land(self):
        wp = Waypoint(lat=47.5, lon=9.7, action="LAND")
        self.assertEqual(waypoint_to_mission_item_params(wp)["command"], 21)

    def test_jump_carries_target_and_repeat_count(self):
        wp = Waypoint(lat=0.0, lon=0.0, action="JUMP", p1=2, p2=5)
        params = waypoint_to_mission_item_params(wp)
        self.assertEqual(params["command"], 177)  # MAV_CMD_DO_JUMP
        self.assertAlmostEqual(params["param1"], 2.0)
        self.assertAlmostEqual(params["param2"], 5.0)

    def test_unknown_action_falls_back_to_waypoint(self):
        wp = Waypoint(lat=0.0, lon=0.0, action="SOMETHING_FUTURE")
        self.assertEqual(waypoint_to_mission_item_params(wp)["command"], 16)

    def test_round_trip_waypoint(self):
        original = Waypoint(lat=47.123456, lon=9.654321, alt=88.0, action="WAYPOINT", p1=7)
        params = waypoint_to_mission_item_params(original)
        restored = mission_item_params_to_waypoint(
            params["command"], params["param1"], params["param2"], params["x"], params["y"], params["z"]
        )
        self.assertAlmostEqual(restored.lat, original.lat, places=5)
        self.assertAlmostEqual(restored.lon, original.lon, places=5)
        self.assertAlmostEqual(restored.alt, original.alt)
        self.assertEqual(restored.action, "WAYPOINT")
        self.assertEqual(restored.p1, 7)

    def test_round_trip_jump(self):
        original = Waypoint(lat=0.0, lon=0.0, action="JUMP", p1=3, p2=9)
        params = waypoint_to_mission_item_params(original)
        restored = mission_item_params_to_waypoint(
            params["command"], params["param1"], params["param2"], params["x"], params["y"], params["z"]
        )
        self.assertEqual(restored.action, "JUMP")
        self.assertEqual(restored.p1, 3)
        self.assertEqual(restored.p2, 9)


class _FakeMav:
    def __init__(self, sent: list) -> None:
        self._sent = sent

    def __getattr__(self, name):
        def _record(*args, **kwargs):
            self._sent.append((name, args, kwargs))
        return _record


class _FakeConnection:
    def __init__(self, sent: list) -> None:
        self.mav = _FakeMav(sent)


class _FakeWorker:
    """enqueue_send() runs synchronously here (no real thread) - fine for
    testing protocol logic, which never assumes async delivery timing."""

    def __init__(self) -> None:
        self.sent: list = []
        self.connection = _FakeConnection(self.sent)

    def enqueue_send(self, send_fn) -> None:
        send_fn()


def _msg(msg_type: str, **fields):
    ns = SimpleNamespace(**fields)
    ns.get_type = lambda: msg_type
    return ns


class MissionUploadSessionTest(unittest.TestCase):
    def setUp(self):
        self.worker = _FakeWorker()
        self.waypoints = [Waypoint(lat=47.0 + i * 0.001, lon=9.0, alt=50.0) for i in range(3)]
        self.session = MissionUploadSession(self.worker, self.waypoints)
        self.results = []
        self.session.finished.connect(lambda ok, msg: self.results.append((ok, msg)))

    def test_empty_waypoint_list_fails_immediately(self):
        session = MissionUploadSession(self.worker, [])
        results = []
        session.finished.connect(lambda ok, msg: results.append((ok, msg)))
        session.start()
        self.assertEqual(results, [(False, "Keine Wegpunkte zum Hochladen.")])

    def test_start_sends_mission_count(self):
        self.session.start()
        self.assertEqual(self.worker.sent[0][0], "mission_count_send")
        self.assertEqual(self.worker.sent[0][1][2], 3)  # count

    def test_full_happy_path_uploads_all_items_and_succeeds(self):
        self.session.start()
        for seq in range(3):
            self.session.handle_message(_msg("MISSION_REQUEST_INT", seq=seq))
        self.session.handle_message(_msg("MISSION_ACK", type=MAV_MISSION_ACCEPTED))
        self.assertEqual(self.results, [(True, "Mission erfolgreich hochgeladen.")])
        item_sends = [s for s in self.worker.sent if s[0] == "mission_item_int_send"]
        self.assertEqual(len(item_sends), 3)

    def test_rejection_ack_fails_with_code_in_message(self):
        self.session.start()
        self.session.handle_message(_msg("MISSION_ACK", type=4))
        self.assertEqual(len(self.results), 1)
        self.assertFalse(self.results[0][0])
        self.assertIn("4", self.results[0][1])

    def test_progress_signal_fires_per_item(self):
        progress = []
        self.session.progress.connect(lambda i, total: progress.append((i, total)))
        self.session.start()
        self.session.handle_message(_msg("MISSION_REQUEST_INT", seq=0))
        self.session.handle_message(_msg("MISSION_REQUEST_INT", seq=1))
        self.assertEqual(progress, [(0, 3), (1, 3)])

    def test_out_of_range_seq_is_ignored_not_crashing(self):
        self.session.start()
        self.session.handle_message(_msg("MISSION_REQUEST_INT", seq=99))  # must not raise
        self.assertEqual(self.results, [])

    def test_messages_after_finish_are_ignored(self):
        self.session.start()
        self.session.handle_message(_msg("MISSION_ACK", type=MAV_MISSION_ACCEPTED))
        sent_count_before = len(self.worker.sent)
        self.session.handle_message(_msg("MISSION_REQUEST_INT", seq=0))
        self.assertEqual(len(self.worker.sent), sent_count_before)


class MissionDownloadSessionTest(unittest.TestCase):
    def setUp(self):
        self.worker = _FakeWorker()
        self.session = MissionDownloadSession(self.worker)
        self.results = []
        self.session.finished.connect(lambda ok, msg, wps: self.results.append((ok, msg, wps)))

    def test_start_sends_request_list(self):
        self.session.start()
        self.assertEqual(self.worker.sent[0][0], "mission_request_list_send")

    def test_zero_count_finishes_successfully_with_no_waypoints(self):
        self.session.start()
        self.session.handle_message(_msg("MISSION_COUNT", count=0))
        self.assertEqual(len(self.results), 1)
        ok, msg, wps = self.results[0]
        self.assertTrue(ok)
        self.assertEqual(wps, [])

    def test_full_happy_path_downloads_all_items_in_order(self):
        self.session.start()
        self.session.handle_message(_msg("MISSION_COUNT", count=2))
        self.session.handle_message(_msg("MISSION_ITEM_INT", seq=0, command=16, param1=0, param2=0, x=470000000, y=90000000, z=10.0))
        self.session.handle_message(_msg("MISSION_ITEM_INT", seq=1, command=16, param1=0, param2=0, x=470010000, y=90000000, z=20.0))
        self.assertEqual(len(self.results), 1)
        ok, msg, wps = self.results[0]
        self.assertTrue(ok)
        self.assertEqual(len(wps), 2)
        self.assertAlmostEqual(wps[0].alt, 10.0)
        self.assertAlmostEqual(wps[1].alt, 20.0)
        ack_sends = [s for s in self.worker.sent if s[0] == "mission_ack_send"]
        self.assertEqual(len(ack_sends), 1)

    def test_progress_signal_fires_per_item(self):
        progress = []
        self.session.progress.connect(lambda i, total: progress.append((i, total)))
        self.session.start()
        self.session.handle_message(_msg("MISSION_COUNT", count=2))
        self.session.handle_message(_msg("MISSION_ITEM_INT", seq=0, command=16, param1=0, param2=0, x=0, y=0, z=0))
        self.assertEqual(progress, [(1, 2)])


if __name__ == "__main__":
    unittest.main()
