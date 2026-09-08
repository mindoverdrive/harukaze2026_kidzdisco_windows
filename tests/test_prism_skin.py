import unittest
import numpy as np
from prism_skin_field import PrismSkin


class PrismSkinTests(unittest.TestCase):
    def test_press_is_local_and_release_relaxes(self):
        field = PrismSkin(80, 45)
        for _ in range(60):
            field.update([(.5, .5)], 1 / 30)
        self.assertGreater(field.pressure[22, 40], .9)
        self.assertLess(field.pressure[0, 0], .001)
        for _ in range(90):
            field.update([], 1 / 30)
        self.assertLess(float(field.pressure.max()), .001)

    def test_multiple_hands_bounded_over_long_simulation(self):
        field = PrismSkin(80, 45)
        for i in range(3600):
            field.update([(.2, .5), (.8, .5)] * 3, .1)
        self.assertTrue(np.isfinite(field.pressure).all())
        self.assertLessEqual(float(field.pressure.max()), float(np.float32(1.6)))
        self.assertGreater(field.pressure[22, 16], .5)
        self.assertGreater(field.pressure[22, 63], .5)
        self.assertLess(field.pressure[22, 40], .01)

    def test_autonomous_motion_and_render_shape(self):
        field = PrismSkin(80, 45)
        before, after = field.render(0), field.render(10)
        self.assertEqual(before.shape, (45, 80, 3))
        self.assertEqual(before.dtype, np.uint8)
        self.assertFalse(np.array_equal(before, after))

    def test_frame_rate_independent_press(self):
        a, b = PrismSkin(80, 45), PrismSkin(80, 45)
        for _ in range(30):
            a.update([(.5, .5)], 1 / 30)
        for _ in range(60):
            b.update([(.5, .5)], 1 / 60)
        np.testing.assert_allclose(a.pressure, b.pressure, atol=1e-6)
