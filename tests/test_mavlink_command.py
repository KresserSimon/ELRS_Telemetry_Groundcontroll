import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PyQt6.QtWidgets import QApplication

from telemetry.mavlink_command import (
    COPTER_MODES,
    MAV_CMD_DO_SET_MODE,
    MAV_CMD_NAV_RETURN_TO_LAUNCH,
    MAV_RESULT_ACCEPTED,
    PLANE_MODES,
    CommandSession,
    modes_for_vehicle_type,
    rth_command_session,
    set_mode_command_session,
)

_app = QApplication.instance() or QApplication([])


class ModesForVehicleTypeTest(unittest.TestCase):
    def test_quad_uses_copter_modes(self):
        self.assertEqual(modes_for_vehicle_type("quad"), COPTER_MODES)

    def test_wing_uses_plane_modes(self):
        self.assertEqual(modes_for_vehicle_type("wing"), PLANE_MODES)

    def test_plane_uses_plane_modes(self):
        self.assertEqual(modes_for_vehicle_type("plane"), PLANE_MODES)

    def test_unknown_falls_back_to_plane_modes(self):
        self.assertEqual(modes_for_vehicle_type("something_future"), PLANE_MODES)


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
    def __init__(self) -> None:
        self.sent: list = []
        self.connection = _FakeConnection(self.sent)

    def enqueue_send(self, send_fn) -> None:
        send_fn()


class CommandSessionTest(unittest.TestCase):
    def setUp(self):
        self.worker = _FakeWorker()

    def test_start_sends_command_long_with_given_id(self):
        session = CommandSession(self.worker, MAV_CMD_NAV_RETURN_TO_LAUNCH, description="RTH")
        session.start()
        self.assertEqual(len(self.worker.sent), 1)
        name, args, kwargs = self.worker.sent[0]
        self.assertEqual(name, "command_long_send")
        self.assertEqual(args[2], MAV_CMD_NAV_RETURN_TO_LAUNCH)

    def test_accepted_ack_finishes_successfully(self):
        session = CommandSession(self.worker, MAV_CMD_NAV_RETURN_TO_LAUNCH, description="RTH")
        results = []
        session.finished.connect(lambda ok, msg: results.append((ok, msg)))
        session.start()
        session.handle_ack(MAV_CMD_NAV_RETURN_TO_LAUNCH, MAV_RESULT_ACCEPTED)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0][0])

    def test_rejected_ack_fails_with_code_in_message(self):
        session = CommandSession(self.worker, MAV_CMD_NAV_RETURN_TO_LAUNCH, description="RTH")
        results = []
        session.finished.connect(lambda ok, msg: results.append((ok, msg)))
        session.start()
        session.handle_ack(MAV_CMD_NAV_RETURN_TO_LAUNCH, 4)
        self.assertFalse(results[0][0])
        self.assertIn("4", results[0][1])

    def test_ack_for_a_different_command_is_ignored(self):
        session = CommandSession(self.worker, MAV_CMD_NAV_RETURN_TO_LAUNCH, description="RTH")
        results = []
        session.finished.connect(lambda ok, msg: results.append((ok, msg)))
        session.start()
        session.handle_ack(MAV_CMD_DO_SET_MODE, MAV_RESULT_ACCEPTED)
        self.assertEqual(results, [])

    def test_messages_after_finish_are_ignored(self):
        session = CommandSession(self.worker, MAV_CMD_NAV_RETURN_TO_LAUNCH, description="RTH")
        results = []
        session.finished.connect(lambda ok, msg: results.append((ok, msg)))
        session.start()
        session.handle_ack(MAV_CMD_NAV_RETURN_TO_LAUNCH, MAV_RESULT_ACCEPTED)
        session.handle_ack(MAV_CMD_NAV_RETURN_TO_LAUNCH, 4)
        self.assertEqual(len(results), 1)


class RthAndSetModeFactoryTest(unittest.TestCase):
    def setUp(self):
        self.worker = _FakeWorker()

    def test_rth_session_sends_return_to_launch_command(self):
        session = rth_command_session(self.worker)
        session.start()
        name, args, kwargs = self.worker.sent[0]
        self.assertEqual(args[2], MAV_CMD_NAV_RETURN_TO_LAUNCH)

    def test_set_mode_session_sends_do_set_mode_with_custom_mode_param(self):
        session = set_mode_command_session(self.worker, custom_mode=6)
        session.start()
        name, args, kwargs = self.worker.sent[0]
        self.assertEqual(args[2], MAV_CMD_DO_SET_MODE)
        self.assertEqual(args[4], 1)  # MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
        self.assertEqual(args[5], 6)  # custom_mode


if __name__ == "__main__":
    unittest.main()
