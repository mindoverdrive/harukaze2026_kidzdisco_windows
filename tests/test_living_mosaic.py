import unittest
import numpy as np
from living_mosaic_field import LivingMosaic


class LivingMosaicTests(unittest.TestCase):
    def test_motion_local_and_decays(self):
        m=LivingMosaic(160,90)
        still=np.zeros((90,160,3),np.uint8)
        moving=still.copy()
        moving[35:55,70:90]=255
        m.update_motion(still,1/30)
        m.update_motion(moving,1/30)
        self.assertGreater(float(m.activity[45,80]),.3)
        self.assertEqual(float(m.activity[0,0]),0)
        for _ in range(120):
            m.update_motion(moving,1/30)
        self.assertLess(float(m.activity.max()),.01)

    def test_uniform_input_inverts_without_gaps(self):
        m=LivingMosaic(160,90)
        frame=np.full((90,160,3),(20,70,180),np.uint8)
        out=m.render(frame,0,1/30)
        np.testing.assert_array_equal(out,np.full_like(frame,(235,185,75)))

    def test_coarse_faces_larger_and_geometry_changes(self):
        m=LivingMosaic(160,90)
        fine,coarse=m.labels(8,0),m.labels(48,0)
        self.assertGreater(len(np.unique(fine)),len(np.unique(coarse))*15)
        self.assertFalse(np.array_equal(fine,m.labels(8,10)))
