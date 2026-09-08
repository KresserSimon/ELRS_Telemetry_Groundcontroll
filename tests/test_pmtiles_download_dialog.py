import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PyQt6 import QtWebEngineWidgets  # noqa: F401 - must precede QApplication, see other offscreen tests
from PyQt6.QtWidgets import QApplication, QMessageBox

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


class ImportPmtilesTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._patcher = patch.object(dialog_module, "pmtiles_dir", return_value=Path(self._tmpdir.name))
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

        self._src_tmpdir = TemporaryDirectory()
        self.addCleanup(self._src_tmpdir.cleanup)
        self._region = KNOWN_REGIONS[0]

    def _write_source_file(self, filename: str) -> Path:
        path = Path(self._src_tmpdir.name) / filename
        path.write_bytes(b"fake pmtiles data")
        return path

    def test_filename_matching_known_region_is_auto_detected(self):
        source = self._write_source_file(self._region.filename)
        dlg = PMTilesDownloadDialog()
        with patch.object(dialog_module.QFileDialog, "getOpenFileName", return_value=(str(source), "")):
            dlg._import_pmtiles()
        dest = Path(self._tmpdir.name) / self._region.filename
        self.assertTrue(dest.is_file())
        self.assertIn("✓", dlg._region_list.item(0).text())
        dlg.close()

    def test_unrecognized_filename_prompts_for_region(self):
        source = self._write_source_file("some_download.pmtiles")
        dlg = PMTilesDownloadDialog()
        region_name = i18n_display_name(self._region)
        with patch.object(dialog_module.QFileDialog, "getOpenFileName", return_value=(str(source), "")), \
             patch.object(dialog_module.QInputDialog, "getItem", return_value=(region_name, True)):
            dlg._import_pmtiles()
        dest = Path(self._tmpdir.name) / self._region.filename
        self.assertTrue(dest.is_file())
        dlg.close()

    def test_cancelling_file_dialog_does_nothing(self):
        dlg = PMTilesDownloadDialog()
        with patch.object(dialog_module.QFileDialog, "getOpenFileName", return_value=("", "")):
            dlg._import_pmtiles()
        self.assertEqual(list(Path(self._tmpdir.name).iterdir()), [])
        dlg.close()

    def test_cancelling_region_picker_does_not_copy(self):
        source = self._write_source_file("some_download.pmtiles")
        dlg = PMTilesDownloadDialog()
        with patch.object(dialog_module.QFileDialog, "getOpenFileName", return_value=(str(source), "")), \
             patch.object(dialog_module.QInputDialog, "getItem", return_value=("", False)):
            dlg._import_pmtiles()
        self.assertEqual(list(Path(self._tmpdir.name).iterdir()), [])
        dlg.close()

    def test_declining_overwrite_confirmation_keeps_existing_file(self):
        existing_dest = Path(self._tmpdir.name) / self._region.filename
        existing_dest.write_bytes(b"original data")
        source = self._write_source_file(self._region.filename)
        source.write_bytes(b"new data")
        dlg = PMTilesDownloadDialog()
        with patch.object(dialog_module.QFileDialog, "getOpenFileName", return_value=(str(source), "")), \
             patch.object(dialog_module.QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            dlg._import_pmtiles()
        self.assertEqual(existing_dest.read_bytes(), b"original data")
        dlg.close()


def i18n_display_name(region) -> str:
    from core import i18n
    return i18n.tr(region.label_key)


if __name__ == "__main__":
    unittest.main()
