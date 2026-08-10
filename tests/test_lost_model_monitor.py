import unittest

from core.lost_model_monitor import LostModelMonitor
from core.telemetry_state import TelemetryState

# check()'s last_telemetry_time==0 guard mirrors MainWindow._last_telemetry_time's
# real "no packet received yet" startup sentinel (see
# MainWindow._check_heartbeat()) - real time.time() values are always huge
# and nonzero, so it never collides in production. Tests must use a
# realistic nonzero base timestamp too, or they'd spuriously hit that guard.
T0 = 1000.0


class _FakeTts:
    def __init__(self) -> None:
        self.messages = []

    def say(self, text: str) -> None:
        self.messages.append(text)


def _state(lat=47.0, lon=9.0, timestamp=T0):
    s = TelemetryState()
    s.lat, s.lon, s.timestamp = lat, lon, timestamp
    return s


class LostModelMonitorTest(unittest.TestCase):
    def setUp(self):
        self.tts = _FakeTts()
        self.monitor = LostModelMonitor(self.tts)

    def test_no_frozen_state_never_speaks(self):
        self.monitor.check(now=T0 + 100.0, last_telemetry_time=T0 + 90.0, timeout_s=5.0)
        self.assertEqual(self.tts.messages, [])
        self.assertFalse(self.monitor.is_lost())

    def test_within_timeout_is_not_lost(self):
        self.monitor.note_telemetry(_state(timestamp=T0))
        self.monitor.check(now=T0 + 3.0, last_telemetry_time=T0, timeout_s=10.0)
        self.assertFalse(self.monitor.is_lost())
        self.assertEqual(self.tts.messages, [])

    def test_past_timeout_freezes_and_speaks_once(self):
        self.monitor.note_telemetry(_state(lat=47.5, lon=9.5, timestamp=T0))
        self.monitor.check(now=T0 + 15.0, last_telemetry_time=T0, timeout_s=10.0)
        self.assertTrue(self.monitor.is_lost())
        self.assertEqual(len(self.tts.messages), 1)

        # Still lost shortly after -> no repeat before the cooldown.
        self.monitor.check(now=T0 + 16.0, last_telemetry_time=T0, timeout_s=10.0)
        self.assertEqual(len(self.tts.messages), 1)

    def test_reannounces_after_cooldown(self):
        self.monitor.note_telemetry(_state(timestamp=T0))
        self.monitor.check(now=T0 + 15.0, last_telemetry_time=T0, timeout_s=10.0)
        self.monitor.check(now=T0 + 46.0, last_telemetry_time=T0, timeout_s=10.0)
        self.assertEqual(len(self.tts.messages), 2)

    def test_fresh_packet_clears_lost_state(self):
        self.monitor.note_telemetry(_state(timestamp=T0))
        self.monitor.check(now=T0 + 15.0, last_telemetry_time=T0, timeout_s=10.0)
        self.assertTrue(self.monitor.is_lost())

        self.monitor.note_telemetry(_state(timestamp=T0 + 15.0))
        self.assertFalse(self.monitor.is_lost())

    def test_info_freezes_last_gps_fix_not_a_fix_less_packet(self):
        self.monitor.note_telemetry(_state(lat=47.1, lon=9.1, timestamp=T0))
        no_fix = TelemetryState()  # lat/lon None -> has_gps_fix() False
        no_fix.timestamp = T0 + 1.0
        self.monitor.note_telemetry(no_fix)
        self.monitor.check(now=T0 + 20.0, last_telemetry_time=T0 + 1.0, timeout_s=10.0)

        info = self.monitor.info(reference=(47.0, 9.0))
        self.assertIsNotNone(info)
        self.assertEqual((info.frozen_state.lat, info.frozen_state.lon), (47.1, 9.1))

    def test_info_computes_distance_and_bearing_from_reference(self):
        self.monitor.note_telemetry(_state(lat=47.01, lon=9.0, timestamp=T0))
        self.monitor.check(now=T0 + 15.0, last_telemetry_time=T0, timeout_s=10.0)

        info = self.monitor.info(reference=(47.0, 9.0))
        self.assertIsNotNone(info)
        self.assertGreater(info.distance_m, 0.0)
        # Model is due north of the reference -> bearing close to 0 degrees.
        self.assertLess(info.bearing_deg, 5.0)

    def test_info_without_reference_has_no_distance_or_bearing(self):
        self.monitor.note_telemetry(_state(timestamp=T0))
        self.monitor.check(now=T0 + 15.0, last_telemetry_time=T0, timeout_s=10.0)

        info = self.monitor.info(reference=None)
        self.assertIsNotNone(info)
        self.assertIsNone(info.distance_m)
        self.assertIsNone(info.bearing_deg)

    def test_info_none_when_not_lost(self):
        self.monitor.note_telemetry(_state(timestamp=T0))
        self.assertIsNone(self.monitor.info(reference=(47.0, 9.0)))

    def test_reset_clears_everything(self):
        self.monitor.note_telemetry(_state(timestamp=T0))
        self.monitor.check(now=T0 + 15.0, last_telemetry_time=T0, timeout_s=10.0)
        self.monitor.reset()
        self.assertFalse(self.monitor.is_lost())
        self.assertIsNone(self.monitor.info(reference=(47.0, 9.0)))


if __name__ == "__main__":
    unittest.main()
