import unittest

from core.route import RouteManager, Waypoint


class RouteManagerStructuralEditsTest(unittest.TestCase):
    def setUp(self):
        self.rm = RouteManager()
        self.changed_count = 0
        self.rm.changed.connect(self._on_changed)

    def _on_changed(self):
        self.changed_count += 1

    def _seed(self, n):
        self.rm.set_all([Waypoint(lat=float(i), lon=float(i) * 2) for i in range(n)])
        self.changed_count = 0  # ignore the seeding emit for assertions below

    def test_remove_many_removes_by_index_regardless_of_order(self):
        self._seed(5)
        self.rm.remove_many([3, 1])
        lats = [wp.lat for wp in self.rm.waypoints()]
        self.assertEqual(lats, [0.0, 2.0, 4.0])
        self.assertEqual(self.changed_count, 1)

    def test_remove_many_ignores_out_of_range_indices(self):
        self._seed(3)
        self.rm.remove_many([10, -5])
        self.assertEqual(len(self.rm.waypoints()), 3)

    def test_update_position_changes_lat_lon_in_place(self):
        self._seed(2)
        self.rm.update_position(1, 9.0, 8.0)
        wp = self.rm.waypoints()[1]
        self.assertEqual((wp.lat, wp.lon), (9.0, 8.0))
        self.assertEqual(self.changed_count, 1)

    def test_update_position_out_of_range_is_a_no_op(self):
        self._seed(2)
        self.rm.update_position(5, 9.0, 8.0)
        self.assertEqual(self.changed_count, 0)

    def test_reorder_moves_waypoint_to_target_index(self):
        self._seed(4)  # lats 0,1,2,3
        self.rm.reorder(0, 2)
        lats = [wp.lat for wp in self.rm.waypoints()]
        self.assertEqual(lats, [1.0, 2.0, 0.0, 3.0])
        self.assertEqual(self.changed_count, 1)

    def test_reorder_same_index_is_a_no_op(self):
        self._seed(3)
        self.rm.reorder(1, 1)
        self.assertEqual(self.changed_count, 0)

    def test_reorder_out_of_range_is_a_no_op(self):
        self._seed(3)
        self.rm.reorder(0, 10)
        self.assertEqual(self.changed_count, 0)

    def test_insert_between_adds_midpoint_waypoint(self):
        self.rm.set_all([Waypoint(0.0, 0.0, alt=10.0), Waypoint(10.0, 20.0, alt=30.0)])
        self.changed_count = 0
        self.rm.insert_between(0)
        wps = self.rm.waypoints()
        self.assertEqual(len(wps), 3)
        self.assertEqual((wps[1].lat, wps[1].lon, wps[1].alt), (5.0, 10.0, 20.0))
        self.assertEqual(self.changed_count, 1)

    def test_insert_between_last_index_is_a_no_op(self):
        self._seed(3)
        self.rm.insert_between(2)  # no segment after the last waypoint
        self.assertEqual(len(self.rm.waypoints()), 3)
        self.assertEqual(self.changed_count, 0)

    def test_insert_between_handles_missing_altitude(self):
        self.rm.set_all([Waypoint(0.0, 0.0, alt=None), Waypoint(10.0, 10.0, alt=30.0)])
        self.rm.insert_between(0)
        self.assertIsNone(self.rm.waypoints()[1].alt)

    def test_reverse_flips_order(self):
        self._seed(3)
        self.rm.reverse()
        lats = [wp.lat for wp in self.rm.waypoints()]
        self.assertEqual(lats, [2.0, 1.0, 0.0])
        self.assertEqual(self.changed_count, 1)

    def test_reverse_single_waypoint_is_a_no_op(self):
        self._seed(1)
        self.rm.reverse()
        self.assertEqual(self.changed_count, 0)

    def test_set_altitude_many_applies_to_given_indices_only(self):
        self._seed(4)
        self.rm.set_altitude_many([0, 2], 55.0)
        alts = [wp.alt for wp in self.rm.waypoints()]
        self.assertEqual(alts, [55.0, None, 55.0, None])
        self.assertEqual(self.changed_count, 1)

    def test_set_speed_many_applies_to_given_indices_only(self):
        self._seed(3)
        self.rm.set_speed_many([1], 12.5)
        speeds = [wp.speed for wp in self.rm.waypoints()]
        self.assertEqual(speeds, [0.0, 12.5, 0.0])

    def test_set_altitude_many_empty_indices_is_a_no_op(self):
        self._seed(2)
        self.rm.set_altitude_many([], 10.0)
        self.assertEqual(self.changed_count, 0)


if __name__ == "__main__":
    unittest.main()
