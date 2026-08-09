import unittest

from ui.map_widget import _DEV_DATA_DIR, _select_pmtiles_region


class SelectPmtilesRegionTest(unittest.TestCase):
    def test_munich_selects_germany(self):
        self.assertEqual(_select_pmtiles_region(48.1372, 11.5756), _DEV_DATA_DIR / "germany.pmtiles")

    def test_vienna_selects_austria(self):
        self.assertEqual(_select_pmtiles_region(48.2082, 16.3738), _DEV_DATA_DIR / "austria.pmtiles")

    def test_bern_selects_switzerland(self):
        # Not Zurich: at 47.3769 it falls inside Germany's bbox too (these
        # are plain rectangles, not real country outlines, so border-area
        # overlap is expected and resolved by fixed check order) - Bern is
        # comfortably south of Germany's bbox and unambiguous.
        self.assertEqual(_select_pmtiles_region(46.9480, 7.4474), _DEV_DATA_DIR / "switzerland.pmtiles")

    def test_rome_selects_italy(self):
        self.assertEqual(_select_pmtiles_region(41.9028, 12.4964), _DEV_DATA_DIR / "italy.pmtiles")

    def test_no_home_position_falls_back_to_germany(self):
        self.assertEqual(_select_pmtiles_region(None, None), _DEV_DATA_DIR / "germany.pmtiles")

    def test_position_outside_all_regions_falls_back_to_germany(self):
        # Tokyo - nowhere near any of the four extracted regions.
        self.assertEqual(_select_pmtiles_region(35.6762, 139.6503), _DEV_DATA_DIR / "germany.pmtiles")


if __name__ == "__main__":
    unittest.main()
