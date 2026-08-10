import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PyQt6.QtWidgets import QApplication

from core.model_profiles import ModelProfile
from ui.model_editor_dialog import ModelEditorDialog

_app = QApplication.instance() or QApplication([])


class ModelEditorDialogTest(unittest.TestCase):
    def test_loads_lipo_profile_correctly(self):
        profile = ModelProfile(name="Racer", battery_chemistry="lipo", battery_cells=4, vehicle_type="quad")
        dialog = ModelEditorDialog(profile)
        self.assertTrue(dialog._lipo_radio.isChecked())
        self.assertFalse(dialog._liion_radio.isChecked())
        self.assertEqual(dialog._cells_combo.currentData(), 4)
        self.assertTrue(dialog._vehicle_radios["quad"].isChecked())

    def test_loads_liion_wing_profile_correctly(self):
        profile = ModelProfile(name="Glider", battery_chemistry="liion", battery_cells=6, vehicle_type="wing")
        dialog = ModelEditorDialog(profile)
        self.assertTrue(dialog._liion_radio.isChecked())
        self.assertEqual(dialog._cells_combo.currentData(), 6)
        self.assertTrue(dialog._vehicle_radios["wing"].isChecked())

    def test_out_of_range_cell_count_clamps_into_1_to_8s(self):
        # A pre-existing profile saved before the 1-8S UI cap (or a
        # hand-edited config) shouldn't crash the dialog.
        profile = ModelProfile(name="BigPack", battery_cells=12)
        dialog = ModelEditorDialog(profile)
        self.assertEqual(dialog._cells_combo.currentData(), 8)

    def test_result_profile_round_trips_all_fields(self):
        profile = ModelProfile(
            name="Test", battery_chemistry="liion", battery_cells=6,
            battery_low_v=3.3, battery_critical_v=3.0, battery_capacity_mah=2200,
            vehicle_type="plane", geofence_enabled=True, geofence_radius_m=300.0,
            geofence_max_alt_m=200.0, energy_rth_speed_assumption_ms=8.0,
        )
        dialog = ModelEditorDialog(profile)
        result = dialog.result_profile()
        self.assertEqual(result.battery_chemistry, "liion")
        self.assertEqual(result.battery_cells, 6)
        self.assertAlmostEqual(result.battery_low_v, 3.3)
        self.assertAlmostEqual(result.battery_critical_v, 3.0)
        self.assertEqual(result.battery_capacity_mah, 2200)
        self.assertEqual(result.vehicle_type, "plane")
        self.assertTrue(result.geofence_enabled)
        self.assertAlmostEqual(result.geofence_radius_m, 300.0)
        self.assertAlmostEqual(result.geofence_max_alt_m, 200.0)
        self.assertAlmostEqual(result.energy_rth_speed_assumption_ms, 8.0)

    def test_changing_chemistry_applies_default_voltage_thresholds(self):
        profile = ModelProfile(name="Test", battery_chemistry="lipo")
        dialog = ModelEditorDialog(profile)
        dialog._liion_radio.setChecked(True)
        result = dialog.result_profile()
        self.assertLess(result.battery_low_v, 3.6)  # Li-Ion defaults are lower than LiPo's

    def test_result_profile_uses_edited_name(self):
        profile = ModelProfile(name="Old Name")
        dialog = ModelEditorDialog(profile)
        dialog._name_edit.setText("New Name")
        self.assertEqual(dialog.result_profile().name, "New Name")


if __name__ == "__main__":
    unittest.main()
