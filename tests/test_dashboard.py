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
from core.telemetry_state import TelemetryState
from ui.dashboard import DASHBOARD_SCALE_LARGE, DASHBOARD_SCALE_SMALL, Dashboard

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


if __name__ == "__main__":
    unittest.main()
