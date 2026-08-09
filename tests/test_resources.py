import sys
import unittest
from pathlib import Path
from unittest import mock

from core.resources import resource_path


class ResourcePathTest(unittest.TestCase):
    def test_source_run_resolves_relative_to_project_root(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            path = resource_path("docs", "manual.pdf")
        self.assertEqual(path.name, "manual.pdf")
        self.assertTrue(str(path).endswith(str(Path("docs") / "manual.pdf")))

    def test_frozen_run_resolves_relative_to_meipass(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "_MEIPASS", r"C:\bundled", create=True):
            path = resource_path("assets", "app_icon.ico")
        self.assertEqual(path, Path(r"C:\bundled") / "assets" / "app_icon.ico")


if __name__ == "__main__":
    unittest.main()
