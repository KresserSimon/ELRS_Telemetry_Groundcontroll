"""Dialog to download one region's vector-map tiles (see
core/pmtiles_extract.py) into pmtiles_dir() - a one-shot download, not a
live/auto-updating subscription (see docs/feature_plan.md's "PMTiles-Region
herunterladen" for the P5 follow-up note on that).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from core import i18n
from core.pmtiles_extract import MAX_EXTRACT_ZOOM, KNOWN_REGIONS
from ui.map_widget import pmtiles_dir
from ui.pmtiles_download_worker import PMTilesDownloadWorker


class PMTilesDownloadDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("pmtilesdownload_dialog_title"))
        self.setMinimumWidth(420)

        self._hint_label = QLabel(i18n.tr("pmtilesdownload_hint"))
        self._hint_label.setWordWrap(True)

        self._region_combo = QComboBox()
        for region in KNOWN_REGIONS:
            self._region_combo.addItem(i18n.tr(region.label_key), region)

        self._folder_label = QLabel(str(pmtiles_dir()))
        self._folder_label.setWordWrap(True)
        self._folder_label.setStyleSheet("color: palette(mid);")

        form = QFormLayout()
        form.addRow(i18n.tr("pmtilesdownload_region_label"), self._region_combo)
        form.addRow(i18n.tr("pmtilesdownload_folder_label"), self._folder_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)

        self._start_button = QPushButton(i18n.tr("pmtilesdownload_start_btn"))
        self._start_button.clicked.connect(self._on_start)
        self._cancel_button = QPushButton(i18n.tr("pmtilesdownload_cancel_btn"))
        self._cancel_button.setVisible(False)
        self._cancel_button.clicked.connect(self._on_cancel)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        self._close_button = button_box.button(QDialogButtonBox.StandardButton.Close)

        layout = QVBoxLayout(self)
        layout.addWidget(self._hint_label)
        layout.addLayout(form)
        layout.addWidget(self._start_button)
        layout.addWidget(self._cancel_button)
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._status_label)
        layout.addWidget(button_box)

        self._worker: Optional[PMTilesDownloadWorker] = None

    def _selected_region(self):
        return self._region_combo.currentData()

    def _on_start(self) -> None:
        region = self._selected_region()
        output_path = pmtiles_dir() / region.filename
        if output_path.exists():
            confirm = QMessageBox.question(
                self, i18n.tr("pmtilesdownload_dialog_title"),
                i18n.tr("pmtilesdownload_confirm_overwrite", filename=region.filename),
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        self._region_combo.setEnabled(False)
        self._start_button.setVisible(False)
        self._cancel_button.setVisible(True)
        self._close_button.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)  # indeterminate until the first real progress tick
        self._status_label.setText(i18n.tr("pmtilesdownload_status_finding_build"))

        self._worker = PMTilesDownloadWorker(region, output_path, MAX_EXTRACT_ZOOM, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished_ok)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.start()

    def _on_progress(self, done: int, total: int) -> None:
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(done)
        self._status_label.setText(i18n.tr("pmtilesdownload_status_downloading", done=done, total=total))

    def _on_finished_ok(self, output_path: str) -> None:
        self._status_label.setText(i18n.tr("pmtilesdownload_status_done", path=output_path))
        self._reset_controls()

    def _on_failed(self, message: str) -> None:
        self._status_label.setText(i18n.tr("pmtilesdownload_status_failed", error=message))
        self._reset_controls()

    def _on_cancelled(self) -> None:
        self._status_label.setText(i18n.tr("pmtilesdownload_status_cancelled"))
        self._reset_controls()

    def _on_cancel(self) -> None:
        if self._worker is not None:
            self._cancel_button.setEnabled(False)
            self._status_label.setText(i18n.tr("pmtilesdownload_status_cancelling"))
            self._worker.cancel()

    def _reset_controls(self) -> None:
        self._region_combo.setEnabled(True)
        self._start_button.setVisible(True)
        self._cancel_button.setVisible(False)
        self._cancel_button.setEnabled(True)
        self._close_button.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._worker = None

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        super().closeEvent(event)
