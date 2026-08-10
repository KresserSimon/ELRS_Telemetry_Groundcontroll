"""QThread wrapper around core/pmtiles_extract.py's extract_region() - runs
the (potentially minutes-long) HTTP range-request download off the GUI
thread. Not a TelemetryWorker subclass (this is a one-shot task, not a
continuous telemetry stream) but follows the same progress/finished-signal
+ cooperative-cancellation-flag shape already established by that class.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.pmtiles_extract import ExtractCancelled, PMTilesExtractError, RegionSpec, extract_region


class PMTilesDownloadWorker(QThread):
    progress = pyqtSignal(int, int)  # (done, total)
    finished_ok = pyqtSignal(str)  # output path
    failed = pyqtSignal(str)  # human-readable error message
    cancelled = pyqtSignal()

    def __init__(self, region: RegionSpec, output_path: Path, maxzoom: int, parent=None) -> None:
        super().__init__(parent)
        self._region = region
        self._output_path = output_path
        self._maxzoom = maxzoom
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            extract_region(
                self._region,
                self._output_path,
                maxzoom=self._maxzoom,
                progress_callback=lambda done, total: self.progress.emit(done, total),
                is_cancelled=lambda: self._cancel_requested,
            )
        except ExtractCancelled:
            self.cancelled.emit()
        except PMTilesExtractError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - any unexpected failure must surface, not vanish
            self.failed.emit(f"Unerwarteter Fehler: {exc}")
        else:
            self.finished_ok.emit(str(self._output_path))
