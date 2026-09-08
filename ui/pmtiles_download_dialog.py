"""Dialog to download one or more regions' vector-map tiles (see
core/pmtiles_extract.py) into pmtiles_dir() - a one-shot download, not a
live/auto-updating subscription (see docs/feature_plan.md's "PMTiles-Region
herunterladen" for the P5 follow-up note on that).

Multiple regions can be checked at once; they are downloaded sequentially
(one PMTilesDownloadWorker at a time, queued) rather than in parallel, to
stay well within Protomaps' fair-use expectations for the free daily build.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
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
            item = QListWidgetItem(self._item_text(region))
            item.setData(Qt.ItemDataRole.UserRole, region)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._region_list.addItem(item)

        select_all_btn = QPushButton(i18n.tr("pmtilesdownload_select_all_btn"))
        select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        select_none_btn = QPushButton(i18n.tr("pmtilesdownload_select_none_btn"))
        select_none_btn.clicked.connect(lambda: self._set_all_checked(False))
        open_folder_btn = QPushButton(i18n.tr("pmtilesdownload_open_folder_btn"))
        open_folder_btn.clicked.connect(self._open_folder)
        import_btn = QPushButton(i18n.tr("pmtilesdownload_import_btn"))
        import_btn.clicked.connect(self._import_pmtiles)
        select_row = QHBoxLayout()
        select_row.addWidget(select_all_btn)
        select_row.addWidget(select_none_btn)
        select_row.addStretch(1)
        select_row.addWidget(open_folder_btn)
        select_row.addWidget(import_btn)

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
        self._current_region: Optional[RegionSpec] = None

    def _open_folder(self) -> None:
        folder = pmtiles_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _import_pmtiles(self) -> None:
        """Copy an already-downloaded .pmtiles file (e.g. transferred from
        another machine or a USB stick) into pmtiles_dir(), matching it to a
        known region by filename - falling back to asking the user which
        country it is if the filename doesn't match any known region."""
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.tr("pmtilesdownload_import_dialog_title"), str(pmtiles_dir()),
            "PMTiles (*.pmtiles)",
        )
        if not path:
            return

        source = Path(path)
        region = next(
            (r for r in KNOWN_REGIONS if r.filename.lower() == source.name.lower()), None
        )
        if region is None:
            region = self._ask_import_target_region()
            if region is None:
                return

        destination = pmtiles_dir() / region.filename
        if destination.exists() and destination.resolve() != source.resolve():
            confirm = QMessageBox.question(
                self, i18n.tr("pmtilesdownload_dialog_title"),
                i18n.tr("pmtilesdownload_confirm_overwrite", filename=region.filename),
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.resolve() != source.resolve():
                shutil.copyfile(source, destination)
        except OSError as exc:
            self._status_label.setText(i18n.tr("pmtilesdownload_status_failed", error=str(exc)))
            return

        self._refresh_item_text(region)
        self._status_label.setText(i18n.tr("pmtilesdownload_status_done", path=str(destination)))

    def _ask_import_target_region(self) -> Optional[RegionSpec]:
        names = [i18n.tr(region.label_key) for region in KNOWN_REGIONS]
        choice, ok = QInputDialog.getItem(
            self, i18n.tr("pmtilesdownload_import_pick_region_title"),
            i18n.tr("pmtilesdownload_import_pick_region_label"), names, 0, False,
        )
        if not ok:
            return None
        index = names.index(choice)
        return KNOWN_REGIONS[index]

    def _downloaded_timestamp(self, region: RegionSpec) -> Optional[str]:
        path = pmtiles_dir() / region.filename
        if not path.is_file():
            return None
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return mtime.strftime("%d.%m.%Y %H:%M")

    def _item_text(self, region: RegionSpec) -> str:
        name = i18n.tr(region.label_key)
        downloaded_at = self._downloaded_timestamp(region)
        if downloaded_at is None:
            return name
        return f"{name}  —  {i18n.tr('pmtilesdownload_item_downloaded_suffix', date=downloaded_at)}"

    def _refresh_item_text(self, region: RegionSpec) -> None:
        for i in range(self._region_list.count()):
            item = self._region_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) is region:
                item.setText(self._item_text(region))
                return

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
        self._current_region = region
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
        if self._current_region is not None:
            self._refresh_item_text(self._current_region)
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
