"""Exercise the real sphere motion helpers using only Python's standard library."""

import math
import unittest

from spheres_visuals import (
    LAYER_COUNT,
    TipSmoother,
    fibonacci_points,
    rotation_matrix,
    sphere_axis,
    sphere_rotation,
)


def transform(matrix, point):
    return tuple(sum(value * coordinate for value, coordinate in zip(row, point))
                 for row in matrix)


def norm(point):
    return math.sqrt(sum(value * value for value in point))


def equal_area_counts(points, bands=8, sectors=8):
    """Equal y intervals and azimuth intervals partition a unit sphere by area."""
    counts = [0] * (bands * sectors)
    for x, y, z in points:
        band = min(bands - 1, max(0, int((y + 1.0) * 0.5 * bands)))
        azimuth = math.atan2(z, x) % math.tau
        sector = min(sectors - 1, int(azimuth / math.tau * sectors))
        counts[band * sectors + sector] += 1
    return counts


class FibonacciPointsTests(unittest.TestCase):
    def test_points_are_distinct_finite_and_on_the_unit_sphere(self):
        for count in (2, 17, 1200):
            with self.subTest(count=count):
                points = fibonacci_points(count)
                self.assertEqual(len(points), count)
                self.assertEqual(len(set(points)), count)
                for point in points:
                    self.assertTrue(all(math.isfinite(value) for value in point))
                    self.assertAlmostEqual(norm(point), 1.0, places=12)

    def test_default_cloud_covers_the_sphere_without_a_preferred_direction(self):
        points = fibonacci_points()
        for coordinate in range(3):
            values = [point[coordinate] for point in points]
            self.assertLess(abs(sum(values) / len(points)), 0.005)
            # Every axis sees approximately a quarter of the sphere in each cap.
            for sign in (-1, 1):
                cap_fraction = sum(sign * value > 0.5 for value in values) / len(points)
                self.assertAlmostEqual(cap_fraction, 0.25, delta=0.02)
        expected = len(points) / 64
        for count in equal_area_counts(points):
            self.assertLessEqual(abs(count - expected), expected * 0.4)

    def test_configured_layers_supply_9600_points_without_sparse_regions(self):
        base = fibonacci_points()
        for seconds in (0.0, 50.0, 123.4):
            with self.subTest(seconds=seconds):
                points = [transform(sphere_rotation(seconds, layer), point)
                          for layer in range(LAYER_COUNT) for point in base]
                self.assertEqual(len(points), 9600)
                # Check spatial coverage of the complete point cloud, not just its count.
                expected = 9600 / 64
                for count in equal_area_counts(points):
                    self.assertLessEqual(abs(count - expected), expected * 0.25)

    def test_invalid_sample_counts_are_rejected(self):
        for count in (0, 1, -2, True, 2.5, "1200"):
            with self.subTest(count=count), self.assertRaises(ValueError):
                fibonacci_points(count)


class SphereMotionTests(unittest.TestCase):
    def assert_vector_close(self, actual, expected):
        for value, wanted in zip(actual, expected):
            self.assertAlmostEqual(value, wanted, places=10)

    def test_axes_stay_diagonal_in_the_picture_and_tilt_into_depth(self):
        for layer in range(LAYER_COUNT):
            for seconds in (0.0, 25.0, 50.0, 300.0, 3600.0, 43200.0):
                with self.subTest(layer=layer, seconds=seconds):
                    axis = sphere_axis(seconds, layer)
                    self.assertAlmostEqual(norm(axis), 1.0, places=12)
                    angle = math.degrees(math.atan2(axis[1], axis[0]))
                    self.assertGreaterEqual(angle, 30.0)
                    self.assertLessEqual(angle, 60.0)
                    # A screen-plane axis or a front-facing spin loses the oblique volume.
                    self.assertGreater(axis[2], 0.15)
                    self.assertLess(axis[2], 0.6)

    def test_rotation_leaves_its_axis_fixed(self):
        axes = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
                tuple(value / math.sqrt(14) for value in (1.0, -2.0, 3.0))]
        for axis in axes:
            for angle in (0.0, math.pi / 2, -math.pi / 3, math.tau, 13.0):
                with self.subTest(axis=axis, angle=angle):
                    self.assert_vector_close(transform(rotation_matrix(axis, angle), axis), axis)

    def test_rotation_preserves_lengths_and_angles_between_points(self):
        axis = tuple(value / math.sqrt(6) for value in (1.0, 1.0, 2.0))
        first, second = (17.0, -3.5, 2.0), (-4.0, 0.25, 9.0)
        original_dot = sum(a * b for a, b in zip(first, second))
        for angle in (-2.0, 0.0, 0.7, math.pi, 20.0):
            with self.subTest(angle=angle):
                matrix = rotation_matrix(axis, angle)
                moved_first, moved_second = transform(matrix, first), transform(matrix, second)
                self.assertAlmostEqual(norm(moved_first), norm(first), places=10)
                self.assertAlmostEqual(norm(moved_second), norm(second), places=10)
                self.assertAlmostEqual(sum(a * b for a, b in zip(moved_first, moved_second)),
                                       original_dot, places=10)

    def test_quarter_turn_moves_a_point_in_the_requested_direction(self):
        self.assert_vector_close(
            transform(rotation_matrix((0.0, 0.0, 1.0), math.pi / 2), (1.0, 0.0, 0.0)),
            (0.0, 1.0, 0.0),
        )
        self.assert_vector_close(
            transform(rotation_matrix((1.0, 0.0, 0.0), -math.pi / 2), (0.0, 1.0, 0.0)),
            (0.0, 0.0, -1.0),
        )

    def test_motion_is_continuous_across_zero_and_fifty_second_boundaries(self):
        probes = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        for layer in range(LAYER_COUNT):
            for boundary in (0.0, 50.0, 100.0):
                with self.subTest(layer=layer, boundary=boundary):
                    matrices = [sphere_rotation(boundary + offset, layer)
                                for offset in (-0.001, 0.0, 0.001)]
                    for point in probes:
                        moved = [transform(matrix, point) for matrix in matrices]
                        # At a 540 px radius, this permits less than one pixel of motion.
                        self.assertLess(math.dist(moved[0], moved[1]), 1 / 540)
                        self.assertLess(math.dist(moved[1], moved[2]), 1 / 540)

    def test_equal_elapsed_time_has_equal_orientation_at_30_and_60_fps(self):
        for layer in range(LAYER_COUNT):
            # Exercise every call in both schedules, including the old 50 s wrap point.
            schedule_30 = [sphere_rotation(frame / 30, layer) for frame in range(52 * 30 + 1)]
            schedule_60 = [sphere_rotation(frame / 60, layer) for frame in range(52 * 60 + 1)]
            with self.subTest(layer=layer):
                for frame, matrix in enumerate(schedule_30):
                    for row, expected in zip(matrix, schedule_60[frame * 2]):
                        self.assert_vector_close(row, expected)
                # A constant matrix must not pass merely because both frame rates agree.
                self.assertGreater(math.dist(transform(schedule_30[0], (1.0, 0.0, 0.0)),
                                             transform(schedule_30[300], (1.0, 0.0, 0.0))), 0.1)
                # Dropped frames and a later redraw must not advance the orientation.
                for frame in (1560, 1500, 1, 900, 0):
                    for row, expected in zip(sphere_rotation(frame / 30, layer), schedule_30[frame]):
                        self.assert_vector_close(row, expected)


class TipSmootherTests(unittest.TestCase):
    def test_new_points_start_at_the_detected_position_even_without_elapsed_time(self):
        targets = ((1450.0, 820.0), (360.0, 250.0))
        for dt in (0.0, 1 / 60, 1 / 30):
            with self.subTest(dt=dt):
                self.assertEqual(TipSmoother().update(targets, dt), targets)

    def test_zero_hands_clears_immediately_and_reappearance_has_no_old_trail(self):
        smoother = TipSmoother()
        smoother.update(((1600.0, 800.0), (1300.0, 700.0)), 1 / 60)
        self.assertEqual(smoother.update((), 0.0), ())
        self.assertEqual(smoother.points, ())
        self.assertEqual(smoother.update(((300.0, 200.0),), 0.0), ((300.0, 200.0),))

    def test_existing_point_approaches_its_target_without_overshoot(self):
        smoother = TipSmoother()
        previous = (300.0, 400.0)
        target = (350.0, 370.0)
        smoother.update((previous,), 0.0)
        for _ in range(10):
            point, = smoother.update((target,), 1 / 60)
            self.assertGreater(math.dist(point, target), 0.0)
            self.assertLess(math.dist(point, target), math.dist(previous, target))
            for value, old, wanted in zip(point, previous, target):
                self.assertGreaterEqual(value, min(old, wanted))
                self.assertLessEqual(value, max(old, wanted))
            previous = point

    def test_reversed_detector_order_keeps_each_tip_near_its_own_hand(self):
        smoother = TipSmoother()
        left, right = (300.0, 400.0), (1600.0, 600.0)
        smoother.update((left, right), 0.0)
        moved_right, moved_left = smoother.update(((1590.0, 590.0), (310.0, 410.0)), 1 / 60)
        self.assertLess(math.dist(moved_right, right), 15.0)
        self.assertLess(math.dist(moved_left, left), 15.0)
        self.assertGreater(moved_left[0], left[0])
        self.assertLess(moved_right[0], right[0])

    def test_one_departed_hand_is_dropped_without_reassigning_the_survivor(self):
        smoother = TipSmoother()
        smoother.update(((200.0, 300.0), (1500.0, 500.0)), 0.0)
        points = smoother.update(((1510.0, 505.0),), 1 / 60)
        self.assertEqual(len(points), 1)
        self.assertGreater(points[0][0], 1500.0)
        self.assertLess(points[0][0], 1510.0)

    def test_new_hand_does_not_steal_the_nearby_surviving_hand_when_order_changes(self):
        smoother = TipSmoother()
        smoother.update(((1500.0, 500.0),), 0.0)
        new_hand, continuing_hand = smoother.update(((200.0, 300.0), (1510.0, 505.0)), 1 / 60)
        self.assertEqual(new_hand, (200.0, 300.0))
        self.assertGreater(continuing_hand[0], 1500.0)
        self.assertLess(continuing_hand[0], 1510.0)
        self.assertGreater(continuing_hand[1], 500.0)
        self.assertLess(continuing_hand[1], 505.0)


if __name__ == "__main__":
    unittest.main()
