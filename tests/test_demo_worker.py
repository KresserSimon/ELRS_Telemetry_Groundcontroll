import math
import unittest

from telemetry.demo_worker import RADIUS_M, _heading_for_angle


def _numeric_bearing(angle: float, dt: float = 1e-5) -> float:
    """Ground truth: numerically differentiate the demo flight's actual
    position formula (offset_lat_m = RADIUS_M*sin(angle), offset_lon_m =
    RADIUS_M*cos(angle)) and convert the resulting velocity to a compass
    bearing, independent of _heading_for_angle()'s own derivation."""

    def position(a: float) -> tuple:
        return RADIUS_M * math.sin(a), RADIUS_M * math.cos(a)  # (north, east)

    n0, e0 = position(angle)
    n1, e1 = position(angle + dt)
    v_north, v_east = (n1 - n0) / dt, (e1 - e0) / dt
    return (math.degrees(math.atan2(v_east, v_north)) + 360) % 360


class DemoWorkerHeadingTest(unittest.TestCase):
    def test_heading_matches_numeric_derivative_of_the_flight_path(self):
        for deg in range(0, 360, 15):
            angle = math.radians(deg)
            expected = _numeric_bearing(angle)
            actual = _heading_for_angle(angle)
            # Angles wrap at 0/360 - compare via the shorter angular distance.
            diff = abs(actual - expected) % 360
            diff = min(diff, 360 - diff)
            self.assertLess(
                diff, 0.5,
                f"at angle={deg}deg: heading={actual:.1f} but the flight path's "
                f"actual direction of travel is {expected:.1f}",
            )

    def test_heading_rotates_the_same_direction_as_the_flight_path(self):
        # The loiter circle is traversed with `angle` increasing over time;
        # a regression that flips the rotational sense (as opposed to just
        # a phase offset) would still coincidentally match at some angles,
        # so check a full sweep tracks the same direction throughout.
        headings = [_heading_for_angle(math.radians(deg)) for deg in range(0, 360, 10)]
        for a, b in zip(headings, headings[1:]):
            delta = (b - a + 540) % 360 - 180  # signed shortest delta, (-180, 180]
            self.assertLess(delta, 0, f"heading should decrease (mod 360) as angle increases: {a} -> {b}")


if __name__ == "__main__":
    unittest.main()
