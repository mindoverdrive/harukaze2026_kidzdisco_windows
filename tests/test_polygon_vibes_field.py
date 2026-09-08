import unittest
import numpy as np
from polygon_vibes_field import PolygonField


class PolygonFieldTests(unittest.TestCase):
    def test_color_crosses_shared_edges_then_fades(self):
        field = PolygonField(1920, 1080)
        origin = 1200
        field.ink[origin] = 1
        adjacent = set(field.neighbors[origin]) - {origin}
        field.spread_color([], 1 / 60)
        self.assertTrue(all(field.ink[i] > 0 for i in adjacent))
        untouched = set(range(len(field.faces))) - adjacent - {origin}
        self.assertTrue(all(field.ink[i] == 0 for i in untouched))
        for _ in range(300):
            field.spread_color([], .1)
        self.assertLess(float(field.ink.max()), .001)

    def test_color_pressure_bounded(self):
        field = PolygonField(1920, 1080)
        for _ in range(600):
            field.spread_color([(960, 540)] * 5, .1)
        self.assertGreater(float(field.ink.max()), .5)
        self.assertTrue(np.isfinite(field.ink).all())
        self.assertGreaterEqual(float(field.ink.min()), 0)
        self.assertLessEqual(float(field.ink.max()), 1)

    def test_local_press_and_release(self):
        field = PolygonField(1920, 1080)
        for _ in range(60):
            field.step([(960, 540)], 1 / 30, 0)
        self.assertGreater(float(field.lift.max()), 170)
        self.assertLess(float(field.lift[0]), .01)
        for _ in range(120):
            field.step([], 1 / 30, 4)
        self.assertLess(float(field.lift.max()), .001)

    def test_geometry_finite_and_bounded(self):
        field = PolygonField(1920, 1080)
        for i in range(300):
            triangles, colors = field.step([(960, 540)] * 5, .1, i)
        self.assertEqual(triangles.shape, (2400, 3, 2))
        self.assertEqual(colors.shape, (2400, 3))
        self.assertTrue(np.isfinite(field.lift).all())
        self.assertLessEqual(float(field.lift.max()), 270)

    def test_autonomous_motion(self):
        field = PolygonField(1920, 1080)
        a, colors_a = field.step([], .03, 0)
        b, colors_b = field.step([], .03, 10)
        self.assertFalse(np.array_equal(a, b))
        self.assertFalse(np.array_equal(colors_a, colors_b))
