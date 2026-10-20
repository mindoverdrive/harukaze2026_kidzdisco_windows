"""Real shape geometry/rendering with synthetic hands; no camera or GUI access."""
from contextlib import ExitStack
import math
import random
from types import SimpleNamespace
import unittest
from unittest import mock

import cv2
import numpy as np

import display_utils
import hand_drawing_app as drawing
from hand_drawing_effects import FadingInk
import hand_shapes_app as shapes


def hand(count=5, *, x=.5, y=.5, side="Right", scale=1., angle=0.):
    points = [(0., .10), (-.035, .07), (-.055, .04), (-.075, .02),
              (-.12 if count == 5 else -.04, .015),
              (-.04, .0), (-.04, -.045), (-.04, -.075), (-.04, -.11),
              (0., 0.), (0., -.05), (0., -.085), (0., -.125),
              (.04, .005), (.04, -.04), (.04, -.07), (.04, -.105),
              (.075, .02), (.08, -.015), (.085, -.045), (.09, -.075)]
    for number, tip in enumerate((8, 12, 16, 20), 1):
        if count < number:
            px, _ = points[tip]
            points[tip] = (px, .05)
            points[tip - 1] = (px, .025)
    c, s = math.cos(angle), math.sin(angle)
    direction = -1 if side == "Left" else 1
    return SimpleNamespace(landmark=[SimpleNamespace(
        x=x + scale * (direction * px * c - py * s),
        y=y + scale * (direction * px * s + py * c), z=0.) for px, py in points])


def result(*hands, sides=None):
    sides = sides or ["Right"] * len(hands)
    return SimpleNamespace(multi_hand_landmarks=list(hands), multi_handedness=[
        SimpleNamespace(classification=[SimpleNamespace(label=side, score=.99)]) for side in sides])


def add_strokes(ink, frame, now):
    for stroke in frame.strokes:
        ink.add_segment(stroke.start, stroke.end, stroke.color_bgr, now,
                        effect_id=stroke.effect_id, track_id=stroke.track_id)


class ShapeGeometryTests(unittest.TestCase):
    def setUp(self):
        self.layout = display_utils.get_uniform_layout(1000, 1000, 1000, 1000)

    def test_five_distinct_shapes_enclose_all_landmarks_at_every_rotation(self):
        self.assertEqual([len(shapes.CANONICAL_SHAPES[i]) for i in range(1, 6)], [40, 40, 3, 4, 10])
        self.assertNotEqual(shapes.CANONICAL_SHAPES[1], shapes.CANONICAL_SHAPES[2])
        for count in range(1, 6):
            for side in ("Left", "Right"):
                for angle in (0., math.pi / 2, math.pi, -math.pi / 2):
                    with self.subTest(count=count, side=side, angle=angle):
                        sample = hand(count, side=side, angle=angle)
                        pose, outline, tick, palm = shapes.shape_geometry(sample, self.layout, count)
                        contour = np.asarray(outline, np.float32)
                        for p in sample.landmark:
                            point = display_utils.normalized_to_stage(p.x, p.y, self.layout)
                            self.assertGreaterEqual(cv2.pointPolygonTest(contour, point, True), -.01)
                        self.assertEqual(bool(tick), count == 1)
                        self.assertTrue(all(math.isfinite(value) for point in outline for value in point))

    def test_geometry_translates_scales_and_ring_tick_follows_palm_rotation(self):
        first = shapes.shape_geometry(hand(1), self.layout, 1)
        moved = shapes.shape_geometry(hand(1, x=.6, y=.55, scale=1.5), self.layout, 1)
        self.assertAlmostEqual(moved[0].scale / first[0].scale, 1.5, delta=.015)
        self.assertAlmostEqual(moved[3][0] - first[3][0], 100., delta=1.)
        rotated = shapes.shape_geometry(hand(1, angle=math.pi / 2), self.layout, 1)
        before = np.asarray(first[2][1]) - first[0].center
        after = np.asarray(rotated[2][1]) - rotated[0].center
        np.testing.assert_allclose(after, (-before[1], before[0]), atol=1.5)

    def test_letterbox_palm_and_shape_follow_the_same_pixel_mapping(self):
        layout = display_utils.get_uniform_layout(640, 480, 960, 540)
        sample = hand(4, x=.2, angle=.6)
        _pose, outline, _tick, palm = shapes.shape_geometry(sample, layout, 4)
        wrist, middle = [display_utils.normalized_to_stage(sample.landmark[i].x,
                        sample.landmark[i].y, layout) for i in (0, 9)]
        self.assertEqual(palm, tuple((a+b)/2 for a, b in zip(wrist, middle)))
        self.assertGreater(layout["offset_x"], 0)
        for p in sample.landmark:
            self.assertGreaterEqual(cv2.pointPolygonTest(np.asarray(outline, np.float32),
                                    display_utils.normalized_to_stage(p.x, p.y, layout), True), -.01)

    def test_pose_smoothing_uses_elapsed_time_and_still_covers_current_hand(self):
        initial = shapes.shape_geometry(hand(5), self.layout, 5)[0]
        changed = hand(5, x=.55, angle=.35)
        final = []
        for fps in (20, 60, 120):
            pose = initial
            for _ in range(round(fps * .5)):
                pose, outline, _tick, _palm = shapes.shape_geometry(changed, self.layout, 5, pose, 1/fps)
                for p in changed.landmark:
                    self.assertGreaterEqual(cv2.pointPolygonTest(np.asarray(outline, np.float32),
                        display_utils.normalized_to_stage(p.x, p.y, self.layout), True), -.01)
            final.append(pose)
        for pose in final[1:]:
            np.testing.assert_allclose(pose.center, final[0].center, atol=1e-9)
            self.assertAlmostEqual(pose.angle, final[0].angle, places=10)


class ShapeInputTests(unittest.TestCase):
    def setUp(self):
        self.layout = display_utils.get_uniform_layout(960, 540, 960, 540)

    def controller(self, stable=0.):
        return shapes.ShapeInput(960, 540, stable, random.Random(7))

    def test_counts_zero_to_five_select_the_expected_independent_shape(self):
        for side in ("Left", "Right"):
            for count in range(6):
                for angle in (0., math.pi/2, math.pi):
                    with self.subTest(side=side, count=count, angle=angle):
                        controller = self.controller()
                        frame = controller.update(result(hand(count, side=side, angle=angle), sides=[side]),
                                                  self.layout, 0.)
                        self.assertEqual(len(frame.shapes), int(count > 0))
                        if count:
                            self.assertEqual(frame.shapes[0].selected_count, count)
                            self.assertEqual(frame.active_points, (frame.shapes[0].palm,))

    def test_shape_and_fist_changes_require_stable_counts_and_retire_only_once(self):
        controller = self.controller(.18)
        for now in (0., .1):
            self.assertFalse(controller.update(result(hand(3)), self.layout, now).shapes)
        initial = controller.update(result(hand(3)), self.layout, .181)
        self.assertEqual(initial.shapes[0].selected_count, 3)
        for now in (.2, .3):
            frame = controller.update(result(hand(4)), self.layout, now)
            self.assertEqual(frame.shapes[0].selected_count, 3)
            self.assertFalse(frame.strokes)
        changed = controller.update(result(hand(4)), self.layout, .381)
        self.assertEqual(changed.shapes[0].selected_count, 4)
        self.assertFalse(changed.strokes, 'A morph replaces the old shape without a second fading outline')
        self.assertEqual((changed.shapes[0].effect_id, changed.shapes[0].track_id),
                         (initial.shapes[0].effect_id, initial.shapes[0].track_id))
        for now in (.4, .5):
            self.assertTrue(controller.update(result(hand(0)), self.layout, now).shapes)
        fist = controller.update(result(hand(0)), self.layout, .581)
        self.assertFalse(fist.shapes)
        self.assertFalse(fist.active_points)
        self.assertEqual(len(fist.strokes), 4)
        self.assertFalse(controller.update(result(hand(0)), self.layout, .65).strokes)

    def test_moving_a_hand_never_accumulates_old_outlines(self):
        controller = self.controller()
        for step in range(200):
            sample = hand(1, x=.45 + .05 * math.sin(step/20), angle=.2 * math.sin(step/30))
            frame = controller.update(result(sample), self.layout, step/60)
            self.assertEqual(len(frame.shapes), 1)
            self.assertFalse(frame.strokes)
        self.assertEqual(len(controller.current), 1)

    def test_missing_hand_and_reset_retire_once_then_reentry_keeps_style(self):
        controller = self.controller()
        initial = controller.update(result(hand(1)), self.layout, 0.).shapes[0]
        controller.reset()
        self.assertEqual(len(controller.current), 1)
        absent = controller.update(None, self.layout, .1)
        self.assertEqual(len(absent.strokes), 41)
        self.assertFalse(absent.hands)
        self.assertFalse(absent.shapes)
        for now in (.2, .3, .4):
            controller.reset()
            self.assertFalse(controller.update(None, self.layout, now).strokes)
        returned = controller.update(result(hand(4)), self.layout, .5)
        self.assertFalse(returned.strokes)
        self.assertEqual((returned.shapes[0].track_id, returned.shapes[0].effect_id),
                         (initial.track_id, initial.effect_id))
        self.assertEqual(returned.shapes[0].selected_count, 4)

    def test_eight_hands_reorder_keep_unique_styles_and_change_independently(self):
        controller = self.controller()
        poses = [hand(i % 5 + 1, x=.12 + (i % 4)*.25, y=.30 + (i // 4)*.4, scale=.45)
                 for i in range(8)]
        first = controller.update(result(*poses), self.layout, 0.)
        expected = {shape.track_id: (shape.effect_id, shape.selected_count) for shape in first.shapes}
        self.assertEqual(len(first.shapes), 8)
        self.assertEqual({shape.effect_id for shape in first.shapes}, set(range(8)))
        second = controller.update(result(*reversed(poses)), self.layout, .05)
        self.assertEqual({shape.track_id: (shape.effect_id, shape.selected_count) for shape in second.shapes}, expected)
        self.assertFalse(second.strokes)
        poses[0] = hand(5, x=.12, y=.30, scale=.45)
        changed = controller.update(result(*poses), self.layout, .1)
        self.assertFalse(changed.strokes)
        changed_keys = {shape.track_id for shape in changed.shapes
                        if shape.selected_count != expected[shape.track_id][1]}
        self.assertEqual(len(changed_keys), 1)
        for shape in changed.shapes:
            if shape.track_id not in changed_keys:
                self.assertEqual((shape.effect_id, shape.selected_count), expected[shape.track_id])

    def test_retirement_and_history_remain_bounded_during_repeated_reentry(self):
        controller = self.controller()
        ink = FadingInk(320, 240, hold_seconds=0, fade_seconds=3, max_segments=1920)
        poses = [hand(1, x=.12 + (i % 4)*.25, y=.30 + (i // 4)*.4, scale=.45) for i in range(8)]
        layout = display_utils.get_uniform_layout(960, 540, 320, 240)
        for tick in range(40):
            now = tick * .05
            frame = controller.update(result(*poses) if tick % 2 == 0 else None, layout, now)
            self.assertLessEqual(len(frame.shapes), 8)
            self.assertLessEqual(len(frame.strokes), 8 * 41)
            add_strokes(ink, frame, now)
            self.assertLessEqual(len(ink.segments), 1920)
        ink.advance(now + 3.)
        self.assertFalse(ink.segments)
        controller.update(None, layout, now + 3.)
        self.assertFalse(controller.counts)
        self.assertFalse(controller.poses)
        self.assertFalse(controller.current)

    def test_invalid_observations_and_clock_reset_do_not_leave_live_shapes(self):
        controller = self.controller()
        controller.update(result(hand(3)), self.layout, 10.)
        invalid = hand(3)
        invalid.landmark[8].x = float("nan")
        frame = controller.update(result(invalid), self.layout, 10.1)
        self.assertFalse(frame.shapes)
        self.assertEqual(len(frame.strokes), 3)
        self.assertFalse(controller.update(None, None, 0.).strokes)
        with self.assertRaises(ValueError):
            controller.update(None, self.layout, float("nan"))

    def test_offscreen_retirement_matches_visible_outline_without_false_border_edges(self):
        for count in (1, 4):
            for x, y in ((.045, .5), (.91, .5), (.5, .125), (.5, .90)):
                with self.subTest(count=count, position=(x, y)):
                    controller = self.controller()
                    frame = controller.update(result(hand(count, x=x, y=y)), self.layout, 0.)
                    live = np.zeros((540, 960), np.uint8)
                    for start, end in frame.shapes[0].edges:
                        cv2.line(live, tuple(map(round, start)), tuple(map(round, end)), 255, 1, cv2.LINE_8)
                    retired = controller.update(None, self.layout, .1)
                    faded = np.zeros_like(live)
                    for stroke in retired.strokes:
                        self.assertTrue(all(0 <= point[0] < 960 and 0 <= point[1] < 540
                                            for point in (stroke.start, stroke.end)))
                        cv2.line(faded, stroke.start, stroke.end, 255, 1, cv2.LINE_8)
                    np.testing.assert_array_equal(faded, live)
                    if count == 4 and x == .045:
                        self.assertEqual(len(retired.strokes), 3)
                        self.assertFalse(any(s.start[0] == s.end[0] == 0 for s in retired.strokes))


class ShapeRenderingTests(unittest.TestCase):
    def test_real_renderer_shows_translucent_shape_common_palm_focus_and_full_expiry(self):
        width, height = 640, 480
        layout = display_utils.get_uniform_layout(width, height, width, height)
        controller = shapes.ShapeInput(width, height, 0., random.Random(1))
        ink = FadingInk(width, height, 0., 3., 1920)
        stage = np.full((height, width, 3), 80, np.uint8)
        frame = controller.update(result(hand(4)), layout, 0.)
        image = shapes.render_frame(stage, ink, frame, layout, 0.)
        self.assertEqual(image.shape, stage.shape)
        self.assertEqual(image.dtype, np.uint8)
        self.assertTrue(np.all(stage == 80), "Renderer must not mutate the camera frame")
        x, y = map(round, frame.active_points[0])
        self.assertTrue(np.array_equal(image[y, x], (23, 17, 12)))
        absent = controller.update(None, layout, .1)
        add_strokes(ink, absent, .1)
        start = shapes.render_frame(stage, ink, absent, layout, .1)
        later = shapes.render_frame(stage, ink, absent, layout, 1.5)
        self.assertFalse(np.array_equal(start, later))
        expired = shapes.render_frame(stage, ink, absent, layout, 3.11)
        blank = shapes.render_frame(stage, FadingInk(width, height, 0., 3.), absent, layout, 3.11)
        np.testing.assert_array_equal(expired, blank)
        self.assertFalse(ink.segments)

    def test_renderer_accepts_shared_runners_empty_startup_frame(self):
        stage = np.zeros((240, 320, 3), np.uint8)
        frame = drawing.DrawingFrame((), (), (), ())
        image = shapes.render_frame(stage, FadingInk(320, 240, 0., 3.), frame, None, 0.)
        self.assertEqual(image.shape, stage.shape)

    def test_cli_injects_shape_controller_into_shared_lifecycle_with_immediate_fade(self):
        with mock.patch.object(shapes, "run_app") as run:
            shapes.main([])
        args = run.call_args.kwargs
        self.assertIsInstance(args["controller"], shapes.ShapeInput)
        self.assertIs(args["renderer"], shapes.render_frame)
        self.assertEqual(args["window_name"], shapes.WINDOW_NAME)
        self.assertEqual((args["hold_seconds"], args["fade_seconds"], args["max_segments"]), (0., 3., 1920))

    def test_shared_runner_camera_loss_delivers_retirement_and_cleans_up(self):
        controller = shapes.ShapeInput(320, 240, 0., random.Random(3))
        camera = mock.Mock()
        camera.isOpened.return_value = True
        camera.last_read_frame_id = None
        raw = np.zeros((240, 320, 3), np.uint8)
        camera.read.side_effect = [(True, raw), (False, None)]
        model = mock.Mock()
        model.process.return_value = result(hand(3))
        captured = []

        def render(stage, ink, feedback, layout, now):
            captured.append((len(getattr(feedback, "shapes", ())), len(feedback.strokes), len(ink.segments)))
            return shapes.render_frame(stage, ink, feedback, layout, now)

        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(drawing.mp.solutions.hands, "Hands", return_value=model))
            stack.enter_context(mock.patch.object(drawing.display_utils, "open_camera", return_value=camera))
            stack.enter_context(mock.patch.object(drawing, "setup_window"))
            close = stack.enter_context(mock.patch.object(drawing, "close_window"))
            stack.enter_context(mock.patch.object(drawing.cv2, "waitKey", side_effect=[-1, -1, ord('q')]))
            stack.enter_context(mock.patch.object(drawing.cv2, "getWindowProperty", return_value=1))
            stack.enter_context(mock.patch.object(drawing.cv2, "imshow"))
            stack.enter_context(mock.patch.object(drawing.time, "monotonic", side_effect=[0., .1]))
            stack.enter_context(mock.patch.object(drawing, "notify_first_frame"))
            stack.enter_context(mock.patch.object(drawing, "notify_exit_request"))
            drawing.run_app(width=320, height=240, hold_seconds=0, fade_seconds=3, max_segments=1920,
                            controller=controller, renderer=render, window_name=shapes.WINDOW_NAME)
        self.assertEqual(captured, [(1, 0, 0), (0, 3, 3)])
        model.process.assert_called_once()
        model.close.assert_called_once_with()
        camera.release.assert_called_once_with()
        close.assert_called_once_with(shapes.WINDOW_NAME)


if __name__ == "__main__":
    unittest.main()
