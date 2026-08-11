"""Dialog to download one or more regions' vector-map tiles (see
core/pmtiles_extract.py) into pmtiles_dir() - a one-shot download, not a
live/auto-updating subscription (see docs/feature_plan.md's "PMTiles-Region
herunterladen" for the P5 follow-up note on that).

Multiple regions can be checked at once; they are downloaded sequentially
(one PMTilesDownloadWorker at a time, queued) rather than in parallel, to
stay well within Protomaps' fair-use expectations for the free daily build.
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from core import i18n
from core.pmtiles_extract import MAX_EXTRACT_ZOOM, KNOWN_REGIONS, RegionSpec
from ui.map_widget import pmtiles_dir
from ui.pmtiles_download_worker import PMTilesDownloadWorker


class PMTilesDownloadDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("pmtilesdownload_dialog_title"))
        self.setMinimumSize(460, 480)

        self._hint_label = QLabel(i18n.tr("pmtilesdownload_hint"))
        self._hint_label.setWordWrap(True)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText(i18n.tr("pmtilesdownload_filter_placeholder"))
        self._filter_edit.textChanged.connect(self._apply_filter)

        self._region_list = QListWidget()
        self._region_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for region in KNOWN_REGIONS:
            item = QListWidgetItem(i18n.tr(region.label_key))
            item.setData(Qt.ItemDataRole.UserRole, region)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._region_list.addItem(item)

        select_all_btn = QPushButton(i18n.tr("pmtilesdownload_select_all_btn"))
        select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        select_none_btn = QPushButton(i18n.tr("pmtilesdownload_select_none_btn"))
        select_none_btn.clicked.connect(lambda: self._set_all_checked(False))
        select_row = QHBoxLayout()
        select_row.addWidget(select_all_btn)
        select_row.addWidget(select_none_btn)
        select_row.addStretch(1)

        self._folder_label = QLabel(i18n.tr("pmtilesdownload_folder_label", folder=str(pmtiles_dir())))
        self._folder_label.setWordWrap(True)
        self._folder_label.setStyleSheet("color: palette(mid);")

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)

        self._overall_label = QLabel()
        self._overall_label.setVisible(False)

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
        layout.addWidget(self._filter_edit)
        layout.addWidget(self._region_list, 1)
        layout.addLayout(select_row)
        layout.addWidget(self._folder_label)
        layout.addWidget(self._start_button)
        layout.addWidget(self._cancel_button)
        layout.addWidget(self._overall_label)
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._status_label)
        layout.addWidget(button_box)

        self._worker: Optional[PMTilesDownloadWorker] = None
        self._queue: List[RegionSpec] = []
        self._queue_total = 0
        self._cancel_requested = False

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self._region_list.count()):
            item = self._region_list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self._region_list.count()):
            item = self._region_list.item(i)
            if not item.isHidden():
                item.setCheckState(state)

    def _checked_regions(self) -> List[RegionSpec]:
        regions = []
        for i in range(self._region_list.count()):
            item = self._region_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                regions.append(item.data(Qt.ItemDataRole.UserRole))
        return regions

    def _on_start(self) -> None:
        regions = self._checked_regions()
        if not regions:
            QMessageBox.information(
                self, i18n.tr("pmtilesdownload_dialog_title"), i18n.tr("pmtilesdownload_no_selection")
            )
            return

        self._queue = regions
        self._queue_total = len(regions)
        self._cancel_requested = False

        self._region_list.setEnabled(False)
        self._filter_edit.setEnabled(False)
        self._start_button.setVisible(False)
        self._cancel_button.setVisible(True)
        self._cancel_button.setEnabled(True)
        self._close_button.setEnabled(False)
        self._overall_label.setVisible(self._queue_total > 1)
        self._progress_bar.setVisible(True)

        self._start_next_download()

    def _start_next_download(self) -> None:
        if self._cancel_requested or not self._queue:
            self._finish_queue()
            return

        region = self._queue.pop(0)
        done_count = self._queue_total - len(self._queue)
        self._overall_label.setText(
            i18n.tr("pmtilesdownload_overall_progress", index=done_count, total=self._queue_total, region=i18n.tr(region.label_key))
        )

        output_path = pmtiles_dir() / region.filename
        if output_path.exists():
            confirm = QMessageBox.question(
                self, i18n.tr("pmtilesdownload_dialog_title"),
                i18n.tr("pmtilesdownload_confirm_overwrite", filename=region.filename),
            )
            if confirm != QMessageBox.StandardButton.Yes:
                self._start_next_download()
                return

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
        self._worker = None
        self._start_next_download()

    def _on_failed(self, message: str) -> None:
        self._status_label.setText(i18n.tr("pmtilesdownload_status_failed", error=message))
        self._worker = None
        self._start_next_download()

    def _on_cancelled(self) -> None:
        self._status_label.setText(i18n.tr("pmtilesdownload_status_cancelled"))
        self._worker = None
        self._queue.clear()
        self._finish_queue()

    def _on_cancel(self) -> None:
        self._cancel_requested = True
        self._queue.clear()
        if self._worker is not None:
            self._cancel_button.setEnabled(False)
            self._status_label.setText(i18n.tr("pmtilesdownload_status_cancelling"))
            self._worker.cancel()

    def _finish_queue(self) -> None:
        self._region_list.setEnabled(True)
        self._filter_edit.setEnabled(True)
        self._start_button.setVisible(True)
        self._cancel_button.setVisible(False)
        self._cancel_button.setEnabled(True)
        self._close_button.setEnabled(True)
        self._overall_label.setVisible(False)
        self._progress_bar.setVisible(False)

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._cancel_requested = True
            self._queue.clear()
            self._worker.cancel()
            self._worker.wait(3000)
        super().closeEvent(event)
