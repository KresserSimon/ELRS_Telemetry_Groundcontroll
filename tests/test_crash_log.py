import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from core.crash_log import MAX_ENTRIES, install_crash_logger


class CrashLogTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._log_path = Path(self._tmpdir.name) / "nested" / "crash_log.txt"
        self._patcher = mock.patch("core.crash_log.CRASH_LOG_PATH", self._log_path)
        self._patcher.start()
        # install_crash_logger() mutates process-global hooks - every test
        # must restore the real ones, or a later, unrelated test's own
        # uncaught exception would get logged into this test's tmpdir (or
        # worse, into whatever the next test patches CRASH_LOG_PATH to).
        # Replacing the "previous" hook with a Mock before installing also
        # keeps every test from actually printing a real traceback to
        # stderr as noise.
        self._real_sys_hook = sys.excepthook
        self._real_threading_hook = threading.excepthook
        sys.excepthook = mock.Mock()
        threading.excepthook = mock.Mock()

    def tearDown(self):
        sys.excepthook = self._real_sys_hook
        threading.excepthook = self._real_threading_hook
        self._patcher.stop()
        self._tmpdir.cleanup()

    def _raise_and_capture(self, message: str = "boom"):
        try:
            raise ValueError(message)
        except ValueError:
            return sys.exc_info()

    def test_creates_parent_directory_and_writes_entry(self):
        install_crash_logger()
        self.assertFalse(self._log_path.parent.exists())
        sys.excepthook(*self._raise_and_capture())
        self.assertTrue(self._log_path.is_file())
        content = self._log_path.read_text(encoding="utf-8")
        self.assertIn("ValueError", content)
        self.assertIn("boom", content)

    def test_sys_excepthook_still_calls_the_previous_hook(self):
        previous = sys.excepthook  # the Mock() set in setUp
        install_crash_logger()
        exc_type, exc_value, exc_tb = self._raise_and_capture()
        sys.excepthook(exc_type, exc_value, exc_tb)
        previous.assert_called_once_with(exc_type, exc_value, exc_tb)

    def test_threading_excepthook_writes_entry_and_calls_previous_hook(self):
        previous = threading.excepthook  # the Mock() set in setUp
        install_crash_logger()
        exc_type, exc_value, exc_tb = self._raise_and_capture()
        args = threading.ExceptHookArgs((exc_type, exc_value, exc_tb, threading.current_thread()))
        threading.excepthook(args)
        previous.assert_called_once_with(args)
        content = self._log_path.read_text(encoding="utf-8")
        self.assertIn("ValueError", content)

    def test_multiple_crashes_all_recorded(self):
        install_crash_logger()
        for i in range(3):
            sys.excepthook(*self._raise_and_capture(f"boom-{i}"))
        content = self._log_path.read_text(encoding="utf-8")
        for i in range(3):
            self.assertIn(f"boom-{i}", content)

    def test_entries_beyond_max_are_trimmed(self):
        install_crash_logger()
        for i in range(MAX_ENTRIES + 5):
            sys.excepthook(*self._raise_and_capture(f"boom-{i}"))
        content = self._log_path.read_text(encoding="utf-8")
        self.assertNotIn("boom-0\n", content)
        self.assertIn(f"boom-{MAX_ENTRIES + 4}", content)


if __name__ == "__main__":
    unittest.main()
