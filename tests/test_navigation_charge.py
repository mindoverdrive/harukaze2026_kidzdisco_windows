import math
import unittest
from navigation_charge import capsule_point


class CapsuleChargeTests(unittest.TestCase):
    def test_closed_clockwise_perimeter(self):
        rect=(10,20,384,132)
        self.assertLess(math.dist(capsule_point(rect,0),capsule_point(rect,1)),1e-8)
        self.assertGreater(capsule_point(rect,.25)[0],capsule_point(rect,0)[0])
        self.assertLess(capsule_point(rect,.75)[0],capsule_point(rect,0)[0])
        self.assertAlmostEqual(capsule_point(rect,.5)[1],151)

    def test_steps_stay_on_capsule_and_advance_uniformly(self):
        rect=(0,0,384,132)
        points=[capsule_point(rect,i/256) for i in range(257)]
        steps=[math.dist(a,b) for a,b in zip(points,points[1:])]
        self.assertLess(max(steps)-min(steps),.02)
        for x,y in points:
            self.assertTrue(-1e-6<=x<=383+1e-6 and -1e-6<=y<=131+1e-6)
