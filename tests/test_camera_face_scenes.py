import unittest
from types import SimpleNamespace
import numpy as np
from kaleidoscope_camera import kaleidoscope_maps
from polygon_face_field import FaceField, mouth_openness


class CameraFaceScenesTests(unittest.TestCase):
    def test_kaleidoscope_reflection_and_motion(self):
        x, y = kaleidoscope_maps(160, 90, 0)
        self.assertEqual(x.shape, (90, 160))
        self.assertTrue(np.isfinite(x).all() and np.isfinite(y).all())
        np.testing.assert_allclose(x, x[::-1], atol=.001)
        np.testing.assert_allclose(y, y[::-1], atol=.001)
        later, _ = kaleidoscope_maps(160, 90, 20)
        self.assertFalse(np.array_equal(x, later))

    def test_mouth_ratio_scale_independent(self):
        lm = [SimpleNamespace(x=.5, y=.5) for _ in range(468)]
        lm[10].y, lm[152].y = .2, .8
        self.assertEqual(mouth_openness(lm), 0)
        lm[13].y, lm[14].y = .44, .56
        opened = mouth_openness(lm)
        self.assertGreater(opened, .9)
        for p in lm:
            p.x *= .5
            p.y *= .5
        self.assertAlmostEqual(mouth_openness(lm), opened)

    def test_face_wave_relaxes_after_exit(self):
        field = FaceField(1280, 720)
        for _ in range(90):
            tri, rgb = field.step((640, 360), 1, 1/30, 1)
        self.assertGreater(field.opening, .99)
        self.assertEqual(tri.shape, (2400, 3, 2))
        self.assertEqual(rgb.shape, (2400, 3))
        for _ in range(90):
            field.step(None, 0, 1/30, 4)
        self.assertLess(field.opening, .001)
