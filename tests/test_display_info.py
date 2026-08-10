import unittest

from core.display_info import DASHBOARD_SCALE_LARGE, DASHBOARD_SCALE_MEDIUM, DASHBOARD_SCALE_SMALL, auto_dashboard_scale


class AutoDashboardScaleTest(unittest.TestCase):
    def test_1080p_class_width_gets_the_small_scale(self):
        self.assertEqual(auto_dashboard_scale(1920), DASHBOARD_SCALE_SMALL)

    def test_narrow_laptop_width_gets_the_small_scale(self):
        self.assertEqual(auto_dashboard_scale(1366), DASHBOARD_SCALE_SMALL)

    def test_mid_range_width_gets_the_medium_scale(self):
        self.assertEqual(auto_dashboard_scale(2000), DASHBOARD_SCALE_MEDIUM)

    def test_2k_and_up_width_gets_the_large_scale(self):
        self.assertEqual(auto_dashboard_scale(2560), DASHBOARD_SCALE_LARGE)

    def test_4k_logical_width_gets_the_large_scale(self):
        self.assertEqual(auto_dashboard_scale(3840), DASHBOARD_SCALE_LARGE)

    def test_4k_at_200_percent_windows_scaling_has_the_same_logical_width_as_1080p(self):
        # The whole point of classifying by logical rather than physical
        # pixels: a 4K display running at 200% Windows scaling exposes
        # ~1920 logical px to Qt, same as a plain 1080p/100% display, and
        # must get the same (compact) default rather than the large one.
        logical_width_4k_at_200pct = 3840 // 2
        self.assertEqual(auto_dashboard_scale(logical_width_4k_at_200pct), DASHBOARD_SCALE_SMALL)


if __name__ == "__main__":
    unittest.main()
