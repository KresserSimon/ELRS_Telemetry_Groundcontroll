import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from alerts.tts_alert import BatteryAlertMonitor, TTSWorker
from core.telemetry_state import TelemetryState


class _FakeTts:
    def __init__(self) -> None:
        self.calls = []

    def say(self, text: str, key=None) -> None:
        self.calls.append((text, key))


def _state(battery_remaining=None, timestamp=0.0):
    s = TelemetryState()
    s.battery_remaining = battery_remaining
    s.timestamp = timestamp
    return s


class SayEnqueuesKeyTest(unittest.TestCase):
    def test_say_puts_text_and_key_on_queue(self):
        worker = TTSWorker()
        worker.say("hello", key="tts_low")
        self.assertEqual(worker._queue.get_nowait(), ("hello", "tts_low"))

    def test_say_defaults_key_to_none(self):
        worker = TTSWorker()
        worker.say("hello")
        self.assertEqual(worker._queue.get_nowait(), ("hello", None))


class PlaySoundTest(unittest.TestCase):
    def test_non_windows_platform_returns_false(self):
        with patch.object(sys, "platform", "linux"):
            self.assertFalse(TTSWorker._play_sound(Path("whatever.wav")))

    def test_windows_success_returns_true(self):
        with patch.object(sys, "platform", "win32"):
            fake_winsound = MagicMock()
            with patch.dict(sys.modules, {"winsound": fake_winsound}):
                self.assertTrue(TTSWorker._play_sound(Path("some.wav")))
                fake_winsound.PlaySound.assert_called_once()

    def test_windows_exception_returns_false(self):
        with patch.object(sys, "platform", "win32"):
            fake_winsound = MagicMock()
            fake_winsound.PlaySound.side_effect = RuntimeError("boom")
            with patch.dict(sys.modules, {"winsound": fake_winsound}):
                self.assertFalse(TTSWorker._play_sound(Path("some.wav")))


class BatteryAlertMonitorKeyTest(unittest.TestCase):
    def test_low_level_announces_with_low_key(self):
        tts = _FakeTts()
        monitor = BatteryAlertMonitor(tts, low_percent=25, critical_percent=12)
        monitor.check(_state(battery_remaining=20, timestamp=0.0))
        self.assertEqual(len(tts.calls), 1)
        self.assertEqual(tts.calls[0][1], "tts_low")

    def test_critical_level_announces_with_critical_key(self):
        tts = _FakeTts()
        monitor = BatteryAlertMonitor(tts, low_percent=25, critical_percent=12)
        monitor.check(_state(battery_remaining=5, timestamp=0.0))
        self.assertEqual(len(tts.calls), 1)
        self.assertEqual(tts.calls[0][1], "tts_critical")

    def test_none_level_does_not_announce(self):
        tts = _FakeTts()
        monitor = BatteryAlertMonitor(tts, low_percent=25, critical_percent=12)
        monitor.check(_state(battery_remaining=80, timestamp=0.0))
        self.assertEqual(tts.calls, [])


if __name__ == "__main__":
    unittest.main()
