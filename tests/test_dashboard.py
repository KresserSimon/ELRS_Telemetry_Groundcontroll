import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

# Qt6 requires QtWebEngineWidgets to be imported before a QApplication is
# constructed, anywhere in the process - other test modules (e.g.
# ui.map_widget, imported by test_map_widget.py) pull it in too, and
# unittest discover's alphabetical ordering doesn't guarantee one of those
# runs before this file. Importing it here directly makes this file
# correct on its own regardless of suite-wide import order.
from PyQt6 import QtWebEngineWidgets  # noqa: F401
from PyQt6.QtWidgets import QApplication

import ui.dashboard as dashboard_module
from core.telemetry_catalog import DiscoveredVariable
from core.telemetry_state import TelemetryState
from ui.dashboard import (
    DASHBOARD_AUTO_MAX_SCALE,
    DASHBOARD_AUTO_MIN_SCALE,
    DASHBOARD_SCALE_LARGE,
    DASHBOARD_SCALE_SMALL,
    Dashboard,
)

_app = QApplication.instance() or QApplication([])


class StaleVisibleFieldsFallbackTest(unittest.TestCase):
    """A saved dashboard_fields.json that shares zero keys with today's
    actual fields (an old install's file carried over, or field keys
    renamed/removed since) must not silently hide every single field -
    every group box would still render (title + icon) with a visibly
    empty body otherwise, which looks like a rendering bug rather than a
    stale-config problem."""

    def setUp(self):
        self._real_load_visible_fields = dashboard_module.load_visible_fields
        self._real_load_dashboard_layout = dashboard_module.load_dashboard_layout
        # Isolate from this machine's real ~/.elrs_ground_station config -
        # only load_visible_fields() is under test, the layout loader just
        # needs a harmless, valid default so Dashboard() constructs normally.
        dashboard_module.load_dashboard_layout = lambda: None

    def tearDown(self):
        dashboard_module.load_visible_fields = self._real_load_visible_fields
        dashboard_module.load_dashboard_layout = self._real_load_dashboard_layout

    def test_completely_stale_saved_set_falls_back_to_all_fields(self):
        dashboard_module.load_visible_fields = lambda: {"this_key_no_longer_exists", "neither_does_this"}
        dashboard = Dashboard()
        self.assertEqual(dashboard.visible_fields(), dashboard.all_field_keys())

    def test_partially_matching_saved_set_is_kept_as_is(self):
        # A real, intentional user selection (even a small subset) must be
        # respected - only a *completely* non-matching set is treated as
        # stale, not "the user only wanted a few fields visible".
        real_key = next(iter(Dashboard().all_field_keys()))
        dashboard_module.load_visible_fields = lambda: {real_key, "this_key_no_longer_exists"}
        dashboard = Dashboard()
        self.assertEqual(dashboard.visible_fields() & dashboard.all_field_keys(), {real_key})

    def test_missing_config_still_falls_back_to_all_fields(self):
        dashboard_module.load_visible_fields = lambda: None
        dashboard = Dashboard()
        self.assertEqual(dashboard.visible_fields(), dashboard.all_field_keys())


class AvgCellVoltageTest(unittest.TestCase):
    """avg_cell is deliberately distinct from min_cell: min_cell reads a
    real per-cell measurement when the hardware provides one (a safety
    figure), avg_cell is just total pack voltage / configured cell count,
    so it's available even with no per-cell telemetry at all - only ever
    an approximation."""

    def setUp(self):
        self.dashboard = Dashboard()

    def test_divides_pack_voltage_by_cell_count(self):
        self.dashboard.update_state(TelemetryState(battery_voltage=16.8), cells=4)
        self.assertEqual(self.dashboard.avg_cell.value.text(), "4.20")

    def test_shows_na_without_a_cell_count(self):
        self.dashboard.update_state(TelemetryState(battery_voltage=16.8), cells=None)
        self.assertEqual(self.dashboard.avg_cell.value.text(), "--")

    def test_shows_na_without_pack_voltage(self):
        self.dashboard.update_state(TelemetryState(battery_voltage=None), cells=4)
        self.assertEqual(self.dashboard.avg_cell.value.text(), "--")

    def test_shows_na_with_zero_cells(self):
        self.dashboard.update_state(TelemetryState(battery_voltage=16.8), cells=0)
        self.assertEqual(self.dashboard.avg_cell.value.text(), "--")

    def test_independent_of_real_per_cell_data(self):
        # Even with real cell_voltages present (min_cell's source), avg_cell
        # still comes from pack voltage / configured count, not from those.
        state = TelemetryState(battery_voltage=16.0, cell_voltages=[3.5, 4.5, 4.0, 4.0])
        self.dashboard.update_state(state, cells=4)
        self.assertEqual(self.dashboard.min_cell.value.text(), "3.50")
        self.assertEqual(self.dashboard.avg_cell.value.text(), "4.00")


class SetScaleTest(unittest.TestCase):
    """Built after a real report: the dashboard was tuned on a 4K/200%
    dev display and looked visibly cramped on a 1920x1080/100% laptop -
    set_scale() must actually change rendered sizes, not just accept the
    parameter."""

    def setUp(self):
        self.dashboard = Dashboard()

    def test_scale_is_reported_back(self):
        self.dashboard.set_scale(DASHBOARD_SCALE_SMALL)
        self.assertEqual(self.dashboard.scale(), DASHBOARD_SCALE_SMALL)

    def test_larger_scale_increases_field_value_font_size(self):
        field = self.dashboard.gps_lat
        self.dashboard.set_scale(DASHBOARD_SCALE_SMALL)
        small_style = field.value.styleSheet()
        self.dashboard.set_scale(DASHBOARD_SCALE_LARGE)
        large_style = field.value.styleSheet()
        self.assertNotEqual(small_style, large_style)

    def test_larger_scale_increases_icon_label_size(self):
        self.dashboard.set_scale(DASHBOARD_SCALE_SMALL)
        small_size = self.dashboard.link_icon_label.width()
        self.dashboard.set_scale(DASHBOARD_SCALE_LARGE)
        large_size = self.dashboard.link_icon_label.width()
        self.assertGreater(large_size, small_size)

    def test_static_group_icon_is_also_rescaled(self):
        # gps_icon is passed as icon_pixmap= (the static path), unlike
        # link_icon_label which is passed as icon_label= (the dynamic path)
        # - both must respond to set_scale().
        box = self.dashboard._boxes_by_key["dash_gps"]
        icon_label = self.dashboard._icon_by_box[box]
        self.dashboard.set_scale(DASHBOARD_SCALE_SMALL)
        small_size = icon_label.width()
        self.dashboard.set_scale(DASHBOARD_SCALE_LARGE)
        large_size = icon_label.width()
        self.assertGreater(large_size, small_size)

    def test_dynamic_icon_stays_scaled_after_a_telemetry_update(self):
        # A live update_state() call after set_scale() must not silently
        # reset the battery/link/connection icons back to the base size.
        self.dashboard.set_scale(DASHBOARD_SCALE_LARGE)
        expected_size = self.dashboard.link_icon_label.width()
        self.dashboard.update_state(TelemetryState(link_quality=80))
        self.assertEqual(self.dashboard.link_icon_label.width(), expected_size)

    def test_color_override_survives_a_scale_change(self):
        field = self.dashboard.energy_reserve
        field.set_color("#e74c3c")
        self.dashboard.set_scale(DASHBOARD_SCALE_LARGE)
        self.assertIn("#e74c3c", field.value.styleSheet())


class FitScaleToSizeTest(unittest.TestCase):
    """Auto-fit (the "Automatisch" Dashboard-Groesse entry, see
    MainWindow._fit_dashboard_scale()) must actually make the content fit
    the given size, not just clamp to the preset bounds regardless of
    input."""

    def setUp(self):
        self.dashboard = Dashboard()

    def test_returned_scale_is_within_bounds(self):
        scale = self.dashboard.fit_scale_to_size(2000, 2000)
        self.assertGreaterEqual(scale, DASHBOARD_AUTO_MIN_SCALE)
        self.assertLessEqual(scale, DASHBOARD_AUTO_MAX_SCALE)

    def test_content_fits_within_the_given_size_at_the_chosen_scale(self):
        # A single top/bottom-docked row of every group box (this
        # dashboard's construction-time default) is wide enough that no
        # scale in the auto range makes it fit a narrow target - that's
        # expected (see test_impossibly_small_size_falls_back_to_the_minimum_scale),
        # not what's under test here. A side-docked, multi-row layout (the
        # realistic "narrow side panel" case this feature targets) is
        # compact enough to actually fit a moderate, generous target size.
        self.dashboard.set_vertical(True)
        self.dashboard.apply_layout(self.dashboard.group_order(), 4)
        self.dashboard.set_scale(1.0)
        natural = self.dashboard.sizeHint()
        width, height = natural.width() + 50, natural.height() + 50

        scale = self.dashboard.fit_scale_to_size(width, height)
        self.assertEqual(self.dashboard.scale(), scale)
        hint = self.dashboard.sizeHint()
        self.assertLessEqual(hint.width(), width)
        self.assertLessEqual(hint.height(), height)

    def test_smaller_available_space_never_yields_a_larger_scale(self):
        big = self.dashboard.fit_scale_to_size(2000, 2000)
        small = self.dashboard.fit_scale_to_size(400, 250)
        self.assertLessEqual(small, big)

    def test_impossibly_small_size_falls_back_to_the_minimum_scale(self):
        scale = self.dashboard.fit_scale_to_size(1, 1)
        self.assertEqual(scale, DASHBOARD_AUTO_MIN_SCALE)

    def test_nonpositive_size_is_a_no_op(self):
        self.dashboard.set_scale(DASHBOARD_SCALE_LARGE)
        result = self.dashboard.fit_scale_to_size(0, 500)
        self.assertEqual(result, DASHBOARD_SCALE_LARGE)
        self.assertEqual(self.dashboard.scale(), DASHBOARD_SCALE_LARGE)


class ExtraFieldsTest(unittest.TestCase):
    """Pinned telemetry-catalog variables (core/telemetry_catalog.py)
    becoming their own dashboard fields at runtime - docs/feature_plan.md's
    Telemetrie-Variablen-Editor, Punkt 4."""

    def setUp(self):
        self.dashboard = Dashboard()

    def _variable(self, key, value=1.0, display_name=""):
        return DiscoveredVariable(key=key, last_value=value, first_seen=0.0, display_name=display_name)

    def test_pinning_adds_a_visible_field_with_the_expected_id(self):
        self.dashboard.set_extra_fields([self._variable("esc_temp_c", 45.0)])
        self.assertIn("extra:esc_temp_c", self.dashboard.all_field_keys())
        self.assertIn("extra:esc_temp_c", self.dashboard.visible_fields())

    def test_pinning_creates_the_custom_group(self):
        self.dashboard.set_extra_fields([self._variable("esc_temp_c")])
        self.assertIn("dash_extra", self.dashboard._boxes_by_key)
        self.assertIn("dash_extra", self.dashboard.group_order())

    def test_unpinning_removes_the_field(self):
        self.dashboard.set_extra_fields([self._variable("esc_temp_c")])
        self.dashboard.set_extra_fields([])
        self.assertNotIn("extra:esc_temp_c", self.dashboard.all_field_keys())

    def test_relabeling_updates_the_caption_without_removing_the_field(self):
        self.dashboard.set_extra_fields([self._variable("esc_temp_c", display_name="ESC")])
        field = self.dashboard._extra_fields_by_telemetry_key["esc_temp_c"]
        self.assertEqual(field.caption_text(), "ESC")
        self.dashboard.set_extra_fields([self._variable("esc_temp_c", display_name="ESC Temp")])
        self.assertIs(self.dashboard._extra_fields_by_telemetry_key["esc_temp_c"], field)
        self.assertEqual(field.caption_text(), "ESC Temp")

    def test_update_extra_values_sets_the_displayed_text(self):
        self.dashboard.set_extra_fields([self._variable("esc_temp_c")])
        self.dashboard.update_extra_values({"esc_temp_c": 47.5})
        field = self.dashboard._extra_fields_by_telemetry_key["esc_temp_c"]
        self.assertEqual(field.value.text(), "47.5")

    def test_update_extra_values_shows_na_for_a_missing_key(self):
        self.dashboard.set_extra_fields([self._variable("esc_temp_c")])
        self.dashboard.update_extra_values({})
        field = self.dashboard._extra_fields_by_telemetry_key["esc_temp_c"]
        self.assertEqual(field.value.text(), "--")

    def test_multiple_pinned_variables_all_get_fields(self):
        self.dashboard.set_extra_fields([self._variable("esc_temp_c"), self._variable("vtx_temp_c")])
        self.assertEqual(
            set(self.dashboard._extra_fields_by_telemetry_key.keys()), {"esc_temp_c", "vtx_temp_c"}
        )


if __name__ == "__main__":
    unittest.main()
