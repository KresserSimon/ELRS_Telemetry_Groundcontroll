import math
import unittest

from core.geo import meters_per_degree as _meters_per_degree
from core.geo import to_local_xy as _to_local_xy
from core.grid_pattern import generate_grid_route

# ~48.10..48.10+dlat, 11.50..11.50+dlon spans roughly 500m x 330m at this latitude.
LAT0, LON0 = 48.10, 11.50
LAT1, LON1 = 48.1030, 11.5045
CENTER = (48.10, 11.50)


class GridRouteRectangleTest(unittest.TestCase):
    def _to_local(self, wp):
        lat0, lon0 = (LAT0 + LAT1) / 2, (LON0 + LON1) / 2
        m_lat, m_lon = _meters_per_degree(lat0)
        return _to_local_xy(wp.lat, wp.lon, lat0, lon0, m_lat, m_lon)

    def test_points_stay_within_the_requested_box(self):
        lat0, lon0 = (LAT0 + LAT1) / 2, (LON0 + LON1) / 2
        m_lat, m_lon = _meters_per_degree(lat0)
        x0, y0 = _to_local_xy(LAT0, LON0, lat0, lon0, m_lat, m_lon)
        x1, y1 = _to_local_xy(LAT1, LON1, lat0, lon0, m_lat, m_lon)
        x_min, x_max = min(x0, x1), max(x0, x1)
        y_min, y_max = min(y0, y1), max(y0, y1)

        waypoints = generate_grid_route(corners=((LAT0, LON0), (LAT1, LON1)), spacing_m=50, angle_deg=0, altitude_m=40)
        self.assertGreater(len(waypoints), 4)
        for wp in waypoints:
            x, y = self._to_local(wp)
            self.assertGreaterEqual(x, x_min - 1.0)
            self.assertLessEqual(x, x_max + 1.0)
            self.assertGreaterEqual(y, y_min - 1.0)
            self.assertLessEqual(y, y_max + 1.0)
            self.assertEqual(wp.alt, 40)
            self.assertEqual(wp.action, "WAYPOINT")

    def test_zigzag_alternates_direction(self):
        waypoints = generate_grid_route(corners=((LAT0, LON0), (LAT1, LON1)), spacing_m=100, angle_deg=0, altitude_m=10)
        # angle=0 -> lines run parallel to the y axis (north-south); every
        # consecutive pair of waypoints is one line, and successive lines
        # must start where the previous one ended (a proper lawnmower path,
        # not "fly to the far end and teleport back").
        ys = [self._to_local(wp)[1] for wp in waypoints]
        for i in range(1, len(ys) - 1, 2):
            # end of line i and start of line i+1 should be at the same y (turn in place)
            self.assertAlmostEqual(ys[i], ys[i + 1], delta=1.0)

    def test_rotated_scan_lines_produce_a_different_pattern(self):
        wps_0 = generate_grid_route(corners=((LAT0, LON0), (LAT1, LON1)), spacing_m=80, angle_deg=0, altitude_m=10)
        wps_90 = generate_grid_route(corners=((LAT0, LON0), (LAT1, LON1)), spacing_m=80, angle_deg=90, altitude_m=10)
        coords_0 = [(round(wp.lat, 6), round(wp.lon, 6)) for wp in wps_0]
        coords_90 = [(round(wp.lat, 6), round(wp.lon, 6)) for wp in wps_90]
        self.assertNotEqual(coords_0, coords_90)

    def test_degenerate_corners_rejected(self):
        with self.assertRaises(ValueError):
            generate_grid_route(corners=((LAT0, LON0), (LAT0, LON0)), spacing_m=50)

    def test_non_positive_spacing_rejected(self):
        with self.assertRaises(ValueError):
            generate_grid_route(corners=((LAT0, LON0), (LAT1, LON1)), spacing_m=0)


class GridRouteCircleTest(unittest.TestCase):
    def test_points_stay_within_the_requested_radius(self):
        radius_m = 200.0
        waypoints = generate_grid_route(center=CENTER, radius_m=radius_m, spacing_m=40, angle_deg=30, altitude_m=60)
        self.assertGreater(len(waypoints), 4)
        m_lat, m_lon = _meters_per_degree(CENTER[0])
        for wp in waypoints:
            x, y = _to_local_xy(wp.lat, wp.lon, CENTER[0], CENTER[1], m_lat, m_lon)
            dist = math.hypot(x, y)
            self.assertLessEqual(dist, radius_m + 1.0)

    def test_non_positive_radius_rejected(self):
        with self.assertRaises(ValueError):
            generate_grid_route(center=CENTER, radius_m=0, spacing_m=40)

    def test_neither_mode_supplied_rejected(self):
        with self.assertRaises(ValueError):
            generate_grid_route(spacing_m=40)


if __name__ == "__main__":
    unittest.main()
