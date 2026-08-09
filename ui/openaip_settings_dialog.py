"""OpenAIP integration settings: API key, base URL (overridable in case
OpenAIP's real schema or a mirror needs a different endpoint - see
core/openaip_import.py's module docstring for why this isn't hardcoded),
and which airspace types to keep when downloading.
"""
from __future__ import annotations

from typing import Dict, List

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QVBoxLayout,
)

from core import i18n
from core.openaip_import import DEFAULT_BASE_URL, KNOWN_TYPE_LABELS


class OpenAipSettingsDialog(QDialog):
    def __init__(self, api_key: str, base_url: str, preferred_types: List[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("openaip_dialog_title"))
        self.resize(400, 420)

        self._api_key_edit = QLineEdit(api_key)
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._base_url_edit = QLineEdit(base_url or DEFAULT_BASE_URL)

        form = QFormLayout()
        form.addRow(i18n.tr("openaip_api_key_label"), self._api_key_edit)
        form.addRow(i18n.tr("openaip_base_url_label"), self._base_url_edit)

        types_box = QGroupBox(i18n.tr("openaip_types_label"))
        types_layout = QVBoxLayout(types_box)
        self._type_checkboxes: Dict[str, QCheckBox] = {}
        preferred_upper = {t.upper() for t in preferred_types}
        for code, label in KNOWN_TYPE_LABELS.items():
            if code in ("R", "P", "Q"):
                continue  # RESTRICTED/PROHIBITED/DANGER already cover these single-letter aliases
            cb = QCheckBox(label)
            cb.setChecked(not preferred_types or code in preferred_upper)
            self._type_checkboxes[code] = cb
            types_layout.addWidget(cb)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(types_box)
        layout.addWidget(button_box)

    def api_key(self) -> str:
        return self._api_key_edit.text().strip()

    def base_url(self) -> str:
        return self._base_url_edit.text().strip() or DEFAULT_BASE_URL

    def preferred_types(self) -> List[str]:
        selected = [code for code, cb in self._type_checkboxes.items() if cb.isChecked()]
        # All-checked means "no filter" (see openaip_import._should_include),
        # saved as empty so a newly added type isn't excluded by default.
        if len(selected) == len(self._type_checkboxes):
            return []
        return selected
