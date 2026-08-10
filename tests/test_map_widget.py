import sys
import tempfile
import unittest
from pathlib import Path

import ui.map_widget as map_widget_module
from ui.map_widget import _select_pmtiles_region, pmtiles_dir


class SelectPmtilesRegionTest(unittest.TestCase):
    def test_munich_selects_germany(self):
        self.assertEqual(_select_pmtiles_region(48.1372, 11.5756), pmtiles_dir() / "germany.pmtiles")

    def test_vienna_selects_austria(self):
        self.assertEqual(_select_pmtiles_region(48.2082, 16.3738), pmtiles_dir() / "austria.pmtiles")

    def test_bern_selects_switzerland(self):
        # Not Zurich: at 47.3769 it falls inside Germany's bbox too (these
        # are plain rectangles, not real country outlines, so border-area
        # overlap is expected and resolved by fixed check order) - Bern is
        # comfortably south of Germany's bbox and unambiguous.
        self.assertEqual(_select_pmtiles_region(46.9480, 7.4474), pmtiles_dir() / "switzerland.pmtiles")

    def test_rome_selects_italy(self):
        self.assertEqual(_select_pmtiles_region(41.9028, 12.4964), pmtiles_dir() / "italy.pmtiles")

    def test_no_home_position_falls_back_to_germany(self):
        self.assertEqual(_select_pmtiles_region(None, None), pmtiles_dir() / "germany.pmtiles")

    def test_position_outside_all_regions_falls_back_to_germany(self):
        # Tokyo - nowhere near any of the four extracted regions.
        self.assertEqual(_select_pmtiles_region(35.6762, 139.6503), pmtiles_dir() / "germany.pmtiles")


class SelectPmtilesRegionFallbackTest(unittest.TestCase):
    """A region file can live in pmtiles_dir() (the writable folder the
    download dialog uses) or under a bundled assets/pmtiles next to the
    exe (the assets/ convention already used for the icon/logo, which
    some people place region files under by hand instead) - both must be
    searched, primary location first."""

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

    def test_prefers_the_primary_writable_directory_when_present_in_both(self):
        (Path(self.primary_dir.name) / "germany.pmtiles").write_bytes(b"primary")
        (Path(self.bundled_dir.name) / "germany.pmtiles").write_bytes(b"bundled")
        result = map_widget_module._select_pmtiles_region(48.1372, 11.5756)
        self.assertEqual(result, Path(self.primary_dir.name) / "germany.pmtiles")

    def test_falls_back_to_the_bundled_assets_directory(self):
        (Path(self.bundled_dir.name) / "germany.pmtiles").write_bytes(b"bundled")
        result = map_widget_module._select_pmtiles_region(48.1372, 11.5756)
        self.assertEqual(result, Path(self.bundled_dir.name) / "germany.pmtiles")

    def test_missing_everywhere_points_at_the_primary_directory(self):
        result = map_widget_module._select_pmtiles_region(48.1372, 11.5756)
        self.assertEqual(result, Path(self.primary_dir.name) / "germany.pmtiles")


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
