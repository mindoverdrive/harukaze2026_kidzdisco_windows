"""Synthetic landmark animation, resource and tracking boundaries; no device access."""
import math
import random
import unittest
from unittest import mock

import cv2
import numpy as np
import display_utils
import hand_shapes_app as shapes
from hand_drawing_effects import FadingInk
from test_hand_shapes_app import hand, result, add_strokes


class ShapeMotionTests(unittest.TestCase):
    def setUp(self):
        self.layout = display_utils.get_uniform_layout(960, 540, 960, 540)
        self.controller = shapes.ShapeInput(960, 540, 0., random.Random(19))

    def test_all_twenty_directed_changes_cover_hand_and_finish(self):
        for first in range(1, 6):
            for target in range(1, 6):
                if target == first:
                    continue
                with self.subTest(first=first, target=target):
                    ctrl = shapes.ShapeInput(960, 540, 0., random.Random(19))
                    ctrl.update(result(hand(first)), self.layout, 0.)
                    for step in range(15):
                        now = .1 + step / 30
                        sample = hand(target)
                        shape = ctrl.update(result(sample), self.layout, now).shapes[0]
                        self.assertEqual(shape.selected_count, target)
                        polygon = np.asarray(shape.points, np.float32)
                        for point in sample.landmark:
                            self.assertGreaterEqual(cv2.pointPolygonTest(polygon,
                                display_utils.normalized_to_stage(point.x, point.y, self.layout), True), -.02)
                    self.assertFalse(ctrl.morphs)
                    self.assertEqual(len(shape.points), len(shapes.CANONICAL_SHAPES[target]))

    def test_morph_is_absolute_time_based_and_bounded(self):
        morph = shapes.ShapeMorph(shapes.RADIAL_SHAPES[1], 5, 10.)
        frames = []
        for fps in (15, 30, 60, 120):
            ctrl = shapes.ShapeInput(960, 540, 0., random.Random(1))
            ctrl.update(result(hand(1)), self.layout, 0.)
            ctrl.update(result(hand(5)), self.layout, .1)
            for step in range(1, math.ceil(fps * .16)):
                ctrl.update(result(hand(5)), self.layout, .1 + step / fps)
            frames.append(ctrl.update(result(hand(5)), self.layout, .26).shapes[0].points)
        for points in frames[1:]:
            np.testing.assert_allclose(points, frames[0], atol=1e-8)
        np.testing.assert_allclose(morph.outline(10 + shapes.MORPH_SECONDS), shapes.RADIAL_SHAPES[5], atol=1e-12)
        self.assertEqual(len(morph.outline(10.1)), shapes.MORPH_POINTS)
        self.assertTrue(all(math.isfinite(v) and abs(v)<1.6 for point in morph.outline(10.1) for v in point))

    def test_unstable_count_does_not_trigger_morph(self):
        ctrl = shapes.ShapeInput(960, 540, .18, random.Random(3))
        for step in range(20):
            frame = ctrl.update(result(hand(2)), self.layout, step/30)
        self.assertEqual(frame.shapes[0].selected_count, 2)
        for step in range(20, 45):
            frame = ctrl.update(result(hand(3 if step%2 else 5)), self.layout, step/30)
            self.assertEqual(frame.shapes[0].selected_count, 2)
            self.assertFalse(ctrl.morphs)

    def test_rapid_retarget_starts_from_current_outline(self):
        self.controller.update(result(hand(1)), self.layout, 0.)
        self.controller.update(result(hand(5)), self.layout, .1)
        key = next(iter(self.controller.morphs))
        expected = self.controller.morphs[key].outline(.16)
        self.controller.update(result(hand(3)), self.layout, .16)
        self.assertEqual(self.controller.morphs[key].source, expected)
        self.assertEqual(len(self.controller.morphs), 1)

    def test_eight_hands_cross_occlude_and_reappear_without_reallocation(self):
        rng = random.Random(6)
        ctrl = shapes.ShapeInput(960, 540, 0., rng)
        with mock.patch.object(rng, 'choice', wraps=rng.choice) as choose:
            initial_ids = None
            for step in range(100):
                t = step / 30
                # Four opposed pairs cross; order and weak side labels alternate.
                samples = [hand((step//8+i)%5+1, x=.15+.7*((i%4)/3*(1-step/99)+(1-(i%4)/3)*step/99),
                                y=.32+.36*(i//4), scale=.32, side='Left' if i%2 else 'Right') for i in range(8)]
                sides = ['Left' if i%2 else 'Right' for i in range(8)]
                if 42 <= step < 48:
                    samples, sides = samples[2:], sides[2:]
                if step%2:
                    samples.reverse(); sides.reverse()
                frame = ctrl.update(result(*samples, sides=sides), self.layout, t)
                if initial_ids is None:
                    initial_ids = set(ctrl.tracker.tracks)
                self.assertEqual(set(ctrl.tracker.tracks), initial_ids)
                self.assertLessEqual(len(ctrl.morphs), 8)
                self.assertLessEqual(sum(len(s.points) for s in frame.shapes), 8*shapes.MORPH_POINTS)
            self.assertEqual(choose.call_count, 8)
            self.assertEqual({s.effect_id for s in frame.shapes}, set(range(8)))

    def test_short_loss_keeps_assignment_and_does_not_restart_morph(self):
        first = self.controller.update(result(hand(1)), self.layout, 0.).shapes[0]
        self.controller.update(result(hand(5)), self.layout, .1)
        self.controller.update(None, self.layout, .15)
        returned = self.controller.update(result(hand(5)), self.layout, .2).shapes[0]
        self.assertEqual((returned.track_id, returned.effect_id), (first.track_id, first.effect_id))
        self.assertEqual(self.controller.morphs[first.track_id].started_at, .1)

    def test_resolution_change_resets_pixel_pose_but_keeps_track_and_effect(self):
        first = self.controller.update(result(hand(3)), self.layout, 0.).shapes[0]
        for step, size in enumerate(((1280,720),(1920,1080),(640,480)), 1):
            layout = display_utils.get_uniform_layout(960, 540, *size)
            frame = self.controller.update(result(hand(3)), layout, step*.1)
            current = frame.shapes[0]
            self.assertEqual((current.track_id,current.effect_id), (first.track_id,first.effect_id))
            self.assertEqual((self.controller.width,self.controller.height), size)
            self.assertFalse(frame.strokes)
            point = current.palm
            self.assertTrue(0 < point[0] < size[0] and 0 < point[1] < size[1])

    def test_long_switching_keeps_history_and_animation_bounded_then_cleans_up(self):
        ink=FadingInk(320,240,0,3,max_segments=64)
        layout=display_utils.get_uniform_layout(960,540,320,240)
        peak=0
        for step in range(600):
            frame=self.controller.update(None if step%4==3 else result(hand(step//3%5+1)),layout,step/30)
            add_strokes(ink,frame,step/30)
            ink.advance(step/30)
            peak=max(peak,len(ink.segments))
            self.assertLessEqual(len(ink.segments),64)
            self.assertLessEqual(len(self.controller.morphs),8)
        self.assertEqual(peak,64)
        self.controller.close()
        self.controller.close()
        self.assertFalse(self.controller.tracker.tracks)
        self.assertFalse(self.controller.morphs or self.controller.current or self.controller.poses or self.controller.counts)

    def test_main_releases_controller_when_runner_raises(self):
        ctrl=self.controller
        with mock.patch.object(shapes,'ShapeInput',return_value=ctrl), mock.patch.object(shapes,'run_app',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                shapes.main([])
        self.assertFalse(ctrl.tracker.tracks)


if __name__ == '__main__':
    unittest.main()
