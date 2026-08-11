import unittest

from telemetry.mavlink_worker import MAVLinkWorker


class _FakeStatusTextMsg:
    def __init__(self, severity, text):
        self.severity = severity
        self.text = text

    def get_type(self):
        return "STATUSTEXT"


class StatusTextParsingTest(unittest.TestCase):
    def setUp(self):
        self.worker = MAVLinkWorker()
        self.received = []
        self.worker.status_text_received.connect(lambda severity, text: self.received.append((severity, text)))

    def test_statustext_emits_signal_with_severity_and_text(self):
        self.worker._apply_message(_FakeStatusTextMsg(4, "PreArm: Battery low"))
        self.assertEqual(self.received, [(4, "PreArm: Battery low")])

    def test_statustext_decodes_bytes(self):
        self.worker._apply_message(_FakeStatusTextMsg(6, b"EKF variance"))
        self.assertEqual(self.received, [(6, "EKF variance")])

    def test_statustext_strips_trailing_nul_padding(self):
        self.worker._apply_message(_FakeStatusTextMsg(6, "Mode: LOITER" + "\x00" * 20))
        self.assertEqual(self.received, [(6, "Mode: LOITER")])

    def test_statustext_does_not_mutate_telemetry_state(self):
        state_before = self.worker._state.copy()
        self.worker._apply_message(_FakeStatusTextMsg(0, "Emergency"))
        state_after = self.worker._state
        # Only the timestamp field is expected to legitimately differ (it's
        # regenerated on every .copy()/access) - everything else in
        # TelemetryState must be untouched by a pure event message.
        self.assertEqual(state_before.lat, state_after.lat)
        self.assertEqual(state_before.battery_voltage, state_after.battery_voltage)
        self.assertEqual(state_before.flight_mode, state_after.flight_mode)


class _FakeVfrHudMsg:
    def __init__(self, climb, groundspeed, airspeed):
        self.climb = climb
        self.groundspeed = groundspeed
        self.airspeed = airspeed

    def get_type(self):
        return "VFR_HUD"


class VfrHudParsingTest(unittest.TestCase):
    def setUp(self):
        self.worker = MAVLinkWorker()

    def test_parses_vario_groundspeed_and_airspeed(self):
        self.worker._apply_message(_FakeVfrHudMsg(climb=1.5, groundspeed=12.0, airspeed=9.0))
        self.assertEqual(self.worker._state.vario, 1.5)
        self.assertEqual(self.worker._state.groundspeed, 12.0)
        self.assertEqual(self.worker._state.airspeed, 9.0)


class _FakeNamedValueMsg:
    def __init__(self, msg_type, name, value):
        self._msg_type = msg_type
        self.name = name
        self.value = value

    def get_type(self):
        return self._msg_type


class NamedValueParsingTest(unittest.TestCase):
    def setUp(self):
        self.worker = MAVLinkWorker()

    def test_named_value_float_is_written_into_extra(self):
        self.worker._apply_message(_FakeNamedValueMsg("NAMED_VALUE_FLOAT", "esc_temp", 42.5))
        self.assertEqual(self.worker._state.extra, {"esc_temp": 42.5})

    def test_named_value_int_is_written_into_extra_as_float(self):
        self.worker._apply_message(_FakeNamedValueMsg("NAMED_VALUE_INT", "loop_count", 1200))
        self.assertEqual(self.worker._state.extra, {"loop_count": 1200.0})

    def test_decodes_bytes_name_and_strips_nul_padding(self):
        self.worker._apply_message(_FakeNamedValueMsg("NAMED_VALUE_FLOAT", b"esc_temp" + b"\x00" * 8, 42.5))
        self.assertEqual(self.worker._state.extra, {"esc_temp": 42.5})

    def test_multiple_names_accumulate_across_messages(self):
        self.worker._apply_message(_FakeNamedValueMsg("NAMED_VALUE_FLOAT", "esc_temp", 42.5))
        self.worker._apply_message(_FakeNamedValueMsg("NAMED_VALUE_FLOAT", "vtx_temp", 55.0))
        self.assertEqual(self.worker._state.extra, {"esc_temp": 42.5, "vtx_temp": 55.0})

    def test_same_name_again_updates_rather_than_duplicates(self):
        self.worker._apply_message(_FakeNamedValueMsg("NAMED_VALUE_FLOAT", "esc_temp", 42.5))
        self.worker._apply_message(_FakeNamedValueMsg("NAMED_VALUE_FLOAT", "esc_temp", 46.0))
        self.assertEqual(self.worker._state.extra, {"esc_temp": 46.0})

    def test_empty_name_is_ignored(self):
        self.worker._apply_message(_FakeNamedValueMsg("NAMED_VALUE_FLOAT", "\x00" * 8, 42.5))
        self.assertEqual(self.worker._state.extra, {})


class SendQueueTest(unittest.TestCase):
    def setUp(self):
        self.worker = MAVLinkWorker()
        self.errors = []
        self.worker.error_occurred.connect(self.errors.append)

    def test_connection_is_none_before_run(self):
        self.assertIsNone(self.worker.connection)

    def test_enqueued_callable_runs_on_drain(self):
        calls = []
        self.worker.enqueue_send(lambda: calls.append("sent"))
        self.worker._drain_send_queue()
        self.assertEqual(calls, ["sent"])

    def test_drain_is_a_no_op_when_queue_is_empty(self):
        self.worker._drain_send_queue()  # must not raise/block
        self.assertEqual(self.errors, [])

    def test_multiple_queued_callables_run_in_order(self):
        calls = []
        self.worker.enqueue_send(lambda: calls.append(1))
        self.worker.enqueue_send(lambda: calls.append(2))
        self.worker.enqueue_send(lambda: calls.append(3))
        self.worker._drain_send_queue()
        self.assertEqual(calls, [1, 2, 3])

    def test_exception_in_callable_reports_error_instead_of_raising(self):
        def _boom():
            raise RuntimeError("socket closed")

        self.worker.enqueue_send(_boom)
        self.worker._drain_send_queue()  # must not raise
        self.assertEqual(len(self.errors), 1)
        self.assertIn("socket closed", self.errors[0])

    def test_error_in_one_callable_does_not_block_the_next(self):
        calls = []

        def _boom():
            raise RuntimeError("boom")

        self.worker.enqueue_send(_boom)
        self.worker.enqueue_send(lambda: calls.append("still ran"))
        self.worker._drain_send_queue()
        self.assertEqual(calls, ["still ran"])
        self.assertEqual(len(self.errors), 1)


if __name__ == "__main__":
    unittest.main()
