"""Lets the user assign a custom EdgeTX sound (assets/en/*.wav) to each
warning type instead of the spoken TTS phrase - see core/sound_alerts.py
for the catalog/persistence and alerts/tts_alert.py's TTSWorker for the
actual playback point. Changes apply immediately (persisted on every
selection), same pattern as ui/telemetry_variable_editor_dialog.py - there
is nothing to roll back on Cancel, so the dialog only has a Close button.
"""
from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core import i18n
from core.sound_alerts import WARNING_TYPES, get_sound_path, list_available_sounds, load_overrides, set_sound

_COL_WARNING, _COL_SOUND, _COL_PLAY = range(3)


class SoundAlertSettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("warnsound_dialog_title"))
        self.resize(560, 360)

        self._hint_label = QLabel(i18n.tr("warnsound_hint"))
        self._hint_label.setWordWrap(True)

        self._sounds = list_available_sounds()
        overrides = load_overrides()

        self._table = QTableWidget(len(WARNING_TYPES), 3)
        self._table.setHorizontalHeaderLabels([
            i18n.tr("warnsound_col_warning"),
            i18n.tr("warnsound_col_sound"),
            "",
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(_COL_WARNING, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(_COL_SOUND, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(_COL_PLAY, QHeaderView.ResizeMode.ResizeToContents)

        for row, warning_type in enumerate(WARNING_TYPES):
            label_item = QTableWidgetItem(i18n.tr(warning_type.label_key))
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, _COL_WARNING, label_item)

            combo = QComboBox()
            combo.setEditable(True)
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.addItem(i18n.tr("warnsound_tts_default"), None)
            selected_index = 0
            for sound in self._sounds:
                combo.addItem(sound.display_name, sound.relative_path)
                if overrides.get(warning_type.key) == sound.relative_path:
                    selected_index = combo.count() - 1
            combo.setCurrentIndex(selected_index)
            completer = QCompleter([combo.itemText(i) for i in range(combo.count())], combo)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            combo.setCompleter(completer)
            combo.currentIndexChanged.connect(
                lambda _idx, key=warning_type.key, box=combo: self._on_sound_changed(key, box)
            )
            self._table.setCellWidget(row, _COL_SOUND, combo)

            play_button = QPushButton(i18n.tr("warnsound_play_btn"))
            play_button.setToolTip(i18n.tr("warnsound_play_tooltip"))
            play_button.clicked.connect(lambda _checked, key=warning_type.key: self._play_preview(key))
            self._table.setCellWidget(row, _COL_PLAY, play_button)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self._hint_label)
        layout.addWidget(self._table, 1)
        layout.addWidget(button_box)

    def _on_sound_changed(self, key: str, combo: QComboBox) -> None:
        relative_path = combo.currentData()
        set_sound(key, relative_path)

    def _play_preview(self, key: str) -> None:
        if sys.platform != "win32":
            return
        path = get_sound_path(key)
        if path is None:
            return
        try:
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass
