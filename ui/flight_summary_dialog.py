"""Displays a computed FlightSummary (core/flight_summary.py) - reachable
both by loading any flight-log CSV directly and from the replay transport
overlay for whatever's currently loaded there.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core import i18n
from core.flight_summary import FlightSummary, format_summary_text

_NA = "n/v"


class FlightSummaryDialog(QDialog):
    def __init__(self, summary: FlightSummary, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("flightsummary_dialog_title"))
        self._summary = summary

        form = QFormLayout()
        form.addRow(i18n.tr("flightsummary_duration_label"), QLabel(self._format_duration(summary.duration_s)))
        form.addRow(i18n.tr("flightsummary_samples_label"), QLabel(str(summary.sample_count)))
        form.addRow(i18n.tr("flightsummary_max_altitude_label"), QLabel(self._fmt(summary.max_altitude_m, " m")))
        form.addRow(i18n.tr("flightsummary_max_distance_label"), QLabel(self._fmt(summary.max_distance_m, " m")))
        form.addRow(i18n.tr("flightsummary_min_lq_label"), QLabel(self._fmt(summary.min_link_quality, " %")))
        form.addRow(i18n.tr("flightsummary_capacity_label"), QLabel(self._fmt(summary.capacity_used_mah, " mAh")))
        avg_kmh = summary.avg_speed_ms * 3.6 if summary.avg_speed_ms is not None else None
        max_kmh = summary.max_speed_ms * 3.6 if summary.max_speed_ms is not None else None
        form.addRow(i18n.tr("flightsummary_avg_speed_label"), QLabel(self._fmt(avg_kmh, " km/h")))
        form.addRow(i18n.tr("flightsummary_max_speed_label"), QLabel(self._fmt(max_kmh, " km/h")))

        export_btn = QPushButton(i18n.tr("flightsummary_export_btn"))
        export_btn.clicked.connect(self._export)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)
        button_box.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(export_btn)
        layout.addWidget(button_box)

    @staticmethod
    def _fmt(value, suffix: str) -> str:
        return _NA if value is None else f"{value:.0f}{suffix}"

    @staticmethod
    def _format_duration(seconds: float) -> str:
        minutes, secs = divmod(int(seconds), 60)
        return f"{minutes:02d}:{secs:02d}"

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, i18n.tr("flightsummary_export_btn"), "flight_summary.txt", i18n.tr("flightsummary_txt_filter")
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(format_summary_text(self._summary))
        except OSError as exc:
            QMessageBox.critical(self, i18n.tr("msgbox_export_failed_title"), str(exc))
