"""Live-traffic (ADS-B) settings: provider/base URL, poll radius/interval,
and the altitude filter (AGL by default, switchable to MSL - see
core/traffic_config.py's module docstring for why AGL is the default).

Enable/disable lives in this dialog (unlike geofence's menu-only toggle,
ui/geofence_settings_dialog.py) because there's meaningfully more to
configure before first use (provider, radius) - a bare menu checkbox alone
wouldn't get a first-time user to a working setup.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from core import i18n
from core.traffic_config import ALTITUDE_MODE_AGL, ALTITUDE_MODE_MSL, TrafficConfig
from core.traffic_import import DEFAULT_BASE_URLS, PROVIDER_AIRPLANES_LIVE, PROVIDER_OPENSKY


class TrafficSettingsDialog(QDialog):
    def __init__(self, config: TrafficConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("traffic_dialog_title"))
        self.resize(420, 320)

        self._enabled_check = QCheckBox(i18n.tr("traffic_enabled_label"))
        self._enabled_check.setChecked(config["enabled"])

        self._provider_combo = QComboBox()
        self._provider_combo.addItem("airplanes.live", PROVIDER_AIRPLANES_LIVE)
        self._provider_combo.addItem("OpenSky Network", PROVIDER_OPENSKY)
        index = self._provider_combo.findData(config["provider"])
        self._provider_combo.setCurrentIndex(index if index >= 0 else 0)
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)

        self._base_url_edit = QLineEdit(config["base_url"])

        self._radius_spin = QDoubleSpinBox()
        self._radius_spin.setRange(1.0, 500.0)
        self._radius_spin.setSingleStep(5.0)
        self._radius_spin.setSuffix(" km")
        self._radius_spin.setValue(config["radius_km"])

        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setRange(5.0, 300.0)
        self._interval_spin.setSingleStep(5.0)
        self._interval_spin.setSuffix(" s")
        self._interval_spin.setValue(config["poll_interval_s"])

        self._altitude_mode_combo = QComboBox()
        self._altitude_mode_combo.addItem(i18n.tr("traffic_altitude_mode_agl"), ALTITUDE_MODE_AGL)
        self._altitude_mode_combo.addItem(i18n.tr("traffic_altitude_mode_msl"), ALTITUDE_MODE_MSL)
        mode_index = self._altitude_mode_combo.findData(config["altitude_mode"])
        self._altitude_mode_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)

        self._max_altitude_spin = QDoubleSpinBox()
        self._max_altitude_spin.setRange(10.0, 15000.0)
        self._max_altitude_spin.setSingleStep(100.0)
        self._max_altitude_spin.setSuffix(" m")
        self._max_altitude_spin.setValue(config["max_altitude_m"])

        hint = QLabel(i18n.tr("traffic_max_altitude_hint"))
        hint.setWordWrap(True)

        form = QFormLayout()
        form.addRow(self._enabled_check)
        form.addRow(i18n.tr("traffic_provider_label"), self._provider_combo)
        form.addRow(i18n.tr("traffic_base_url_label"), self._base_url_edit)
        form.addRow(i18n.tr("traffic_radius_label"), self._radius_spin)
        form.addRow(i18n.tr("traffic_interval_label"), self._interval_spin)
        form.addRow(i18n.tr("traffic_altitude_mode_label"), self._altitude_mode_combo)
        form.addRow(i18n.tr("traffic_max_altitude_label"), self._max_altitude_spin)
        form.addRow(hint)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(button_box)

    def _on_provider_changed(self, _index: int) -> None:
        # Only overwrite the URL field with the new provider's default while
        # it still holds *some* provider's unmodified default - a user who
        # already typed a custom mirror/proxy URL never gets it silently
        # clobbered by switching providers in the same dialog session.
        if self._base_url_edit.text().strip() in DEFAULT_BASE_URLS.values():
            self._base_url_edit.setText(DEFAULT_BASE_URLS[self._provider_combo.currentData()])

    def result_config(self) -> TrafficConfig:
        return {
            "enabled": self._enabled_check.isChecked(),
            "provider": self._provider_combo.currentData(),
            "base_url": self._base_url_edit.text().strip() or DEFAULT_BASE_URLS[self._provider_combo.currentData()],
            "radius_km": self._radius_spin.value(),
            "poll_interval_s": self._interval_spin.value(),
            "altitude_mode": self._altitude_mode_combo.currentData(),
            "max_altitude_m": self._max_altitude_spin.value(),
        }
