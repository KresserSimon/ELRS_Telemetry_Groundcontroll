"""Dialog to save/load/delete named model profiles (core/model_profiles.py)
- a QListWidget of saved names plus save-current/load/delete actions,
persisting to disk itself so the profile list survives dialog re-opens.
"""
from __future__ import annotations

from typing import Callable, Dict

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core import i18n
from core.model_profiles import ModelProfile, load_profiles, save_profiles


class ModelProfileDialog(QDialog):
    profile_loaded = pyqtSignal(ModelProfile)

    def __init__(self, build_current_profile: Callable[[str], ModelProfile], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("modelprofile_dialog_title"))
        self._build_current_profile = build_current_profile
        self._profiles: Dict[str, ModelProfile] = load_profiles()

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(i18n.tr("modelprofile_name_placeholder"))
        save_btn = QPushButton(i18n.tr("modelprofile_save_btn"))
        save_btn.clicked.connect(self._on_save)
        save_row = QHBoxLayout()
        save_row.addWidget(self._name_edit, 1)
        save_row.addWidget(save_btn)

        self._list = QListWidget()
        self._list.addItems(sorted(self._profiles.keys()))
        self._list.currentTextChanged.connect(self._on_selection_changed)

        self._load_btn = QPushButton(i18n.tr("modelprofile_load_btn"))
        self._load_btn.clicked.connect(self._on_load)
        self._delete_btn = QPushButton(i18n.tr("modelprofile_delete_btn"))
        self._delete_btn.clicked.connect(self._on_delete)
        action_row = QHBoxLayout()
        action_row.addWidget(self._load_btn)
        action_row.addWidget(self._delete_btn)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)
        button_box.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(save_row)
        layout.addWidget(self._list)
        layout.addLayout(action_row)
        layout.addWidget(button_box)

        self._update_button_states()

    def _on_selection_changed(self, name: str) -> None:
        if name:
            self._name_edit.setText(name)
        self._update_button_states()

    def _update_button_states(self) -> None:
        has_selection = self._list.currentItem() is not None
        self._load_btn.setEnabled(has_selection)
        self._delete_btn.setEnabled(has_selection)

    def _selected_name(self) -> str:
        item = self._list.currentItem()
        return item.text() if item is not None else ""

    def _on_save(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            return
        self._profiles[name] = self._build_current_profile(name)
        save_profiles(self._profiles)
        if not self._list.findItems(name, Qt.MatchFlag.MatchExactly):
            self._list.addItem(name)
        self._list.sortItems()

    def _on_load(self) -> None:
        name = self._selected_name()
        if not name or name not in self._profiles:
            return
        self.profile_loaded.emit(self._profiles[name])

    def _on_delete(self) -> None:
        name = self._selected_name()
        if not name or name not in self._profiles:
            return
        confirm = QMessageBox.question(
            self, i18n.tr("modelprofile_dialog_title"), i18n.tr("modelprofile_confirm_delete", name=name)
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        del self._profiles[name]
        save_profiles(self._profiles)
        item = self._list.currentItem()
        if item is not None:
            self._list.takeItem(self._list.row(item))
        self._update_button_states()
