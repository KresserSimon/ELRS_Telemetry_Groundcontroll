"""Direct editor for a single ModelProfile's parameters (battery, vehicle
type, geofence, energy-budget speed assumption) - see
docs/feature_plan.md's "Erweiterter Modell-Editor". Operates purely on a
ModelProfile object, never on MainWindow's live state - editing a profile
that isn't currently active never touches the running app; applying it to
the active profile (if it is) is the caller's job, same as loading any
other profile.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
)

from alerts.tts_alert import CHEMISTRY_DEFAULTS
from core import i18n
from core.model_profiles import ModelProfile

CELL_COUNTS = list(range(1, 9))  # 1S..8S - see docs/feature_plan.md's risk
# note: a real >8S pack would need widening this, deliberately capped for now.
VEHICLE_TYPES = (("vehicle_quad", "quad"), ("vehicle_wing", "wing"), ("vehicle_plane", "plane"))


class ModelEditorDialog(QDialog):
    def __init__(self, profile: ModelProfile, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("modeleditor_dialog_title"))

        self._name_edit = QLineEdit(profile.name)
        name_form = QFormLayout()
        name_form.addRow(i18n.tr("modeleditor_name_label"), self._name_edit)

        # ------------------------------------------------------------ battery
        self._chemistry_group = QButtonGroup(self)
        self._lipo_radio = QRadioButton(i18n.tr("battery_chemistry_lipo"))
        self._liion_radio = QRadioButton(i18n.tr("battery_chemistry_liion"))
        self._chemistry_group.addButton(self._lipo_radio)
        self._chemistry_group.addButton(self._liion_radio)
        chem_row = QHBoxLayout()
        chem_row.addWidget(self._lipo_radio)
        chem_row.addWidget(self._liion_radio)

        self._cells_combo = QComboBox()
        for n in CELL_COUNTS:
            self._cells_combo.addItem(f"{n}S", n)

        self._capacity_spin = QDoubleSpinBox()
        self._capacity_spin.setRange(50, 50000)
        self._capacity_spin.setSingleStep(50)
        self._capacity_spin.setDecimals(0)
        self._capacity_spin.setSuffix(" mAh")

        self._low_spin = QDoubleSpinBox()
        self._low_spin.setRange(0.5, 5.0)
        self._low_spin.setSingleStep(0.05)
        self._low_spin.setSuffix(" V")
        self._critical_spin = QDoubleSpinBox()
        self._critical_spin.setRange(0.5, 5.0)
        self._critical_spin.setSingleStep(0.05)
        self._critical_spin.setSuffix(" V")

        battery_box = QGroupBox(i18n.tr("modeleditor_battery_box"))
        battery_layout = QVBoxLayout(battery_box)
        battery_layout.addLayout(chem_row)
        battery_form = QFormLayout()
        battery_form.addRow(i18n.tr("modeleditor_cells_label"), self._cells_combo)
        battery_form.addRow(i18n.tr("battery_capacity_label"), self._capacity_spin)
        battery_form.addRow(i18n.tr("battery_low_label"), self._low_spin)
        battery_form.addRow(i18n.tr("battery_critical_label"), self._critical_spin)
        battery_layout.addLayout(battery_form)

        # -------------------------------------------------------- vehicle
        self._vehicle_group = QButtonGroup(self)
        self._vehicle_radios = {}
        vehicle_box = QGroupBox(i18n.tr("modeleditor_vehicle_box"))
        vehicle_row = QHBoxLayout(vehicle_box)
        for key, vtype in VEHICLE_TYPES:
            radio = QRadioButton(i18n.tr(key))
            self._vehicle_group.addButton(radio)
            vehicle_row.addWidget(radio)
            self._vehicle_radios[vtype] = radio

        # ------------------------------------------------------- geofence
        self._geofence_check = QCheckBox(i18n.tr("modeleditor_geofence_enabled_label"))
        self._geofence_radius_spin = QDoubleSpinBox()
        self._geofence_radius_spin.setRange(10.0, 50000.0)
        self._geofence_radius_spin.setSingleStep(10.0)
        self._geofence_radius_spin.setSuffix(" m")
        self._geofence_max_alt_spin = QDoubleSpinBox()
        self._geofence_max_alt_spin.setRange(1.0, 10000.0)
        self._geofence_max_alt_spin.setSingleStep(10.0)
        self._geofence_max_alt_spin.setSuffix(" m")

        geofence_box = QGroupBox(i18n.tr("geofence_dialog_title"))
        geofence_layout = QVBoxLayout(geofence_box)
        geofence_layout.addWidget(self._geofence_check)
        geofence_form = QFormLayout()
        geofence_form.addRow(i18n.tr("geofence_radius_label"), self._geofence_radius_spin)
        geofence_form.addRow(i18n.tr("geofence_max_alt_label"), self._geofence_max_alt_spin)
        geofence_layout.addLayout(geofence_form)

        # ---------------------------------------------------- energy budget
        self._speed_spin = QDoubleSpinBox()
        self._speed_spin.setRange(0.5, 50.0)
        self._speed_spin.setSingleStep(0.5)
        self._speed_spin.setSuffix(" m/s")

        energy_box = QGroupBox(i18n.tr("energy_dialog_title"))
        energy_form = QFormLayout(energy_box)
        energy_form.addRow(i18n.tr("energy_speed_assumption_label"), self._speed_spin)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(name_form)
        layout.addWidget(battery_box)
        layout.addWidget(vehicle_box)
        layout.addWidget(geofence_box)
        layout.addWidget(energy_box)
        layout.addWidget(button_box)

        self._load(profile)
        self._chemistry_group.buttonToggled.connect(self._apply_chemistry_defaults)

    def _load(self, profile: ModelProfile) -> None:
        self._lipo_radio.setChecked(profile.battery_chemistry != "liion")
        self._liion_radio.setChecked(profile.battery_chemistry == "liion")
        idx = self._cells_combo.findData(max(1, min(8, profile.battery_cells)))
        self._cells_combo.setCurrentIndex(idx if idx >= 0 else 3)
        self._capacity_spin.setValue(profile.battery_capacity_mah)
        self._low_spin.setValue(profile.battery_low_v)
        self._critical_spin.setValue(profile.battery_critical_v)

        radio = self._vehicle_radios.get(profile.vehicle_type, self._vehicle_radios["quad"])
        radio.setChecked(True)

        self._geofence_check.setChecked(profile.geofence_enabled)
        self._geofence_radius_spin.setValue(profile.geofence_radius_m)
        self._geofence_max_alt_spin.setValue(profile.geofence_max_alt_m)

        self._speed_spin.setValue(profile.energy_rth_speed_assumption_ms)

    def _apply_chemistry_defaults(self, button, checked) -> None:
        if not checked:
            return
        chemistry = "liion" if button is self._liion_radio else "lipo"
        low, critical = CHEMISTRY_DEFAULTS[chemistry]
        self._low_spin.setValue(low)
        self._critical_spin.setValue(critical)

    def result_profile(self) -> ModelProfile:
        """The edited profile - callers should merge in fields this dialog
        doesn't touch (dashboard layout etc.) from the original profile
        rather than assume this is a complete replacement."""
        vehicle_type = "quad"
        for vtype, radio in self._vehicle_radios.items():
            if radio.isChecked():
                vehicle_type = vtype
                break
        return ModelProfile(
            name=self._name_edit.text().strip(),
            battery_chemistry="liion" if self._liion_radio.isChecked() else "lipo",
            battery_cells=self._cells_combo.currentData(),
            battery_low_v=self._low_spin.value(),
            battery_critical_v=self._critical_spin.value(),
            battery_capacity_mah=int(self._capacity_spin.value()),
            vehicle_type=vehicle_type,
            geofence_enabled=self._geofence_check.isChecked(),
            geofence_radius_m=self._geofence_radius_spin.value(),
            geofence_max_alt_m=self._geofence_max_alt_spin.value(),
            energy_rth_speed_assumption_ms=self._speed_spin.value(),
        )
