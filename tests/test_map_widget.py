import sys
import tempfile
import unittest
from pathlib import Path

import ui.map_widget as map_widget_module
from ui.map_widget import pmtiles_dir


class ListDownloadedPmtilesTest(unittest.TestCase):
    """All currently-downloaded regions load simultaneously and are layered
    on the map (see maplibre_template.py:buildMap()) - _list_downloaded_pmtiles()
    just decides the order (priority region first, i.e. drawn on top), it
    no longer picks a single "the" region."""

    def setUp(self):
        self._real_pmtiles_dir = map_widget_module.pmtiles_dir
        self._real_resource_path = map_widget_module.resource_path
        self.primary_dir = tempfile.TemporaryDirectory()
        self.bundled_dir = tempfile.TemporaryDirectory()
        map_widget_module.pmtiles_dir = lambda: Path(self.primary_dir.name)
        map_widget_module.resource_path = lambda *parts: Path(self.bundled_dir.name)

    def tearDown(self):
        map_widget_module.pmtiles_dir = self._real_pmtiles_dir
        map_widget_module.resource_path = self._real_resource_path
        self.primary_dir.cleanup()
        self.bundled_dir.cleanup()

    def _write(self, directory: str, filename: str, size: int) -> Path:
        path = Path(directory) / filename
        path.write_bytes(b"x" * size)
        return path

    def test_nothing_downloaded_returns_empty_list(self):
        self.assertEqual(map_widget_module._list_downloaded_pmtiles(), [])

    def test_single_downloaded_region_is_returned(self):
        path = self._write(self.primary_dir.name, "germany.pmtiles", 100)
        self.assertEqual(map_widget_module._list_downloaded_pmtiles(), [path])

    def test_default_priority_is_austria_regardless_of_size(self):
        # Austria is this app's primary use case (see DEFAULT_PRIORITY_REGION)
        # - it must be drawn on top even though it's the smallest file here,
        # i.e. its priority isn't just an accident of the size-based
        # ordering used for everything else.
        austria = self._write(self.primary_dir.name, "austria.pmtiles", 10)
        germany = self._write(self.primary_dir.name, "germany.pmtiles", 1_000_000)
        self.assertEqual(map_widget_module._list_downloaded_pmtiles(), [austria, germany])

    def test_non_priority_regions_ordered_by_ascending_size(self):
        big = self._write(self.primary_dir.name, "germany.pmtiles", 3000)
        small = self._write(self.primary_dir.name, "switzerland.pmtiles", 100)
        medium = self._write(self.primary_dir.name, "italy.pmtiles", 1000)
        self.assertEqual(map_widget_module._list_downloaded_pmtiles(), [small, medium, big])

    def test_explicit_priority_filename_overrides_the_austria_default(self):
        austria = self._write(self.primary_dir.name, "austria.pmtiles", 10)
        switzerland = self._write(self.primary_dir.name, "switzerland.pmtiles", 3000)
        result = map_widget_module._list_downloaded_pmtiles(priority_filename="switzerland.pmtiles")
        self.assertEqual(result, [switzerland, austria])

    def test_priority_filename_not_downloaded_falls_back_to_size_order(self):
        germany = self._write(self.primary_dir.name, "germany.pmtiles", 100)
        result = map_widget_module._list_downloaded_pmtiles(priority_filename="austria.pmtiles")
        self.assertEqual(result, [germany])

    def test_prefers_the_primary_writable_directory_when_present_in_both(self):
        primary_copy = self._write(self.primary_dir.name, "germany.pmtiles", 100)
        self._write(self.bundled_dir.name, "germany.pmtiles", 100)
        self.assertEqual(map_widget_module._list_downloaded_pmtiles(), [primary_copy])

    def test_falls_back_to_the_bundled_assets_directory(self):
        bundled_copy = self._write(self.bundled_dir.name, "germany.pmtiles", 100)
        self.assertEqual(map_widget_module._list_downloaded_pmtiles(), [bundled_copy])

    def test_files_from_both_directories_are_combined(self):
        primary_copy = self._write(self.primary_dir.name, "austria.pmtiles", 10)
        bundled_copy = self._write(self.bundled_dir.name, "germany.pmtiles", 100)
        self.assertEqual(map_widget_module._list_downloaded_pmtiles(), [primary_copy, bundled_copy])


class PmtilesDirTest(unittest.TestCase):
    def setUp(self):
        # sys.frozen/_MEIPASS don't exist unless PyInstaller's bootloader
        # set them - clean up whatever a test adds so it can't leak.
        self._had_frozen = hasattr(sys, "frozen")
        self._frozen_before = getattr(sys, "frozen", None)
        self._had_meipass = hasattr(sys, "_MEIPASS")
        self._meipass_before = getattr(sys, "_MEIPASS", None)

    def tearDown(self):
        if self._had_frozen:
            sys.frozen = self._frozen_before
        elif hasattr(sys, "frozen"):
            del sys.frozen
        if self._had_meipass:
            sys._MEIPASS = self._meipass_before
        elif hasattr(sys, "_MEIPASS"):
            del sys._MEIPASS

    def test_dev_mode_uses_dev_data_pmtiles(self):
        if hasattr(sys, "frozen"):
            del sys.frozen
        result = pmtiles_dir()
        self.assertTrue(str(result).replace("\\", "/").endswith("dev_data/pmtiles"))

    def test_frozen_mode_uses_user_home_directory_not_meipass(self):
        # A frozen build ships no region files at all (see
        # docs/feature_plan.md) - even with _MEIPASS pointing into the
        # (read-only, temporary) bundle, frozen mode must resolve to a
        # real, permanent, user-writable folder instead.
        sys.frozen = True
        sys._MEIPASS = r"C:\some\temp\bundle\dir"
        result = pmtiles_dir()
        self.assertEqual(result, Path.home() / ".elrs_ground_station" / "pmtiles")
        self.assertNotIn("temp", str(result).lower())


if __name__ == "__main__":
    unittest.main()
