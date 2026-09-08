import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PyQt6 import QtWebEngineWidgets  # noqa: F401 - must precede QApplication, see other offscreen tests
from PyQt6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_app = QApplication.instance() or QApplication(sys.argv)

from core.pmtiles_extract import KNOWN_REGIONS
import ui.pmtiles_download_dialog as dialog_module
from ui.pmtiles_download_dialog import PMTilesDownloadDialog


class ItemDownloadedStatusTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._patcher = patch.object(dialog_module, "pmtiles_dir", return_value=Path(self._tmpdir.name))
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self._region = KNOWN_REGIONS[0]

    def test_not_downloaded_shows_plain_name(self):
        dlg = PMTilesDownloadDialog()
        text = dlg._item_text(self._region)
        self.assertNotIn("✓", text)
        dlg.close()

    def test_downloaded_shows_suffix_with_date(self):
        (Path(self._tmpdir.name) / self._region.filename).write_bytes(b"fake pmtiles data")
        dlg = PMTilesDownloadDialog()
        text = dlg._item_text(self._region)
        self.assertIn("✓", text)
        dlg.close()

    def test_downloaded_timestamp_none_when_missing(self):
        dlg = PMTilesDownloadDialog()
        self.assertIsNone(dlg._downloaded_timestamp(self._region))
        dlg.close()

    def test_downloaded_timestamp_present_when_file_exists(self):
        (Path(self._tmpdir.name) / self._region.filename).write_bytes(b"fake pmtiles data")
        dlg = PMTilesDownloadDialog()
        self.assertIsNotNone(dlg._downloaded_timestamp(self._region))
        dlg.close()

    def test_refresh_item_text_updates_after_download_completes(self):
        dlg = PMTilesDownloadDialog()
        item = dlg._region_list.item(0)
        self.assertNotIn("✓", item.text())

        (Path(self._tmpdir.name) / KNOWN_REGIONS[0].filename).write_bytes(b"fake pmtiles data")
        dlg._refresh_item_text(KNOWN_REGIONS[0])

        self.assertIn("✓", dlg._region_list.item(0).text())
        dlg.close()


if __name__ == "__main__":
    unittest.main()
