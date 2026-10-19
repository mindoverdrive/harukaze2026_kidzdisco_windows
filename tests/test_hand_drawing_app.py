"""Gesture drawing contracts with synthetic landmarks and no camera/window."""

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


FINGER_IDS = {"thumb": (4, 3), "index": (8, 6), "middle": (12, 10),
              "ring": (16, 14), "pinky": (20, 18)}
COUNT_FINGERS = ((), ("index",), ("index", "middle"),
                 ("index", "middle", "ring"), ("index", "middle", "ring", "pinky"),
                 ("thumb", "index", "middle", "ring", "pinky"))


def hand(raised=("index",), *, x=.45, y=.35, wrist_x=None, handedness="Right"):
    """Upright mirrored hands; raised finger tips are above their PIPs."""
    direction = -1 if handedness == "Left" else 1
    points = [SimpleNamespace(x=x, y=y + .18, z=0.) for _ in range(21)]
    points[0] = SimpleNamespace(x=x if wrist_x is None else wrist_x, y=y + .32, z=0.)
    for name, (tip, pip) in FINGER_IDS.items():
        offset = {"thumb": -.10, "index": 0., "middle": .04, "ring": .08, "pinky": .12}[name]
        offset *= direction
        points[pip] = SimpleNamespace(x=x + offset, y=y + .12, z=0.)
        points[tip] = SimpleNamespace(x=x + offset, y=y if name in raised else y + .2, z=0.)
    points[3].x = x - .08 * direction
    points[4].x = x - (.16 if "thumb" in raised else .03) * direction
    return SimpleNamespace(landmark=points)


def results(*label_hands):
    return SimpleNamespace(
        multi_hand_landmarks=[item[1] for item in label_hands],
        multi_handedness=[SimpleNamespace(classification=[SimpleNamespace(label=item[0], score=.99)])
                         for item in label_hands],
    )


class FingerColorTests(unittest.TestCase):
    def test_upright_mirrored_finger_states_count_zero_through_five(self):
        for side in ("Left", "Right"):
            for count, raised in enumerate(COUNT_FINGERS):
                with self.subTest(side=side, count=count):
                    states = drawing.finger_states(hand(raised, handedness=side), side)
                    self.assertEqual(tuple(states), tuple(name in raised for name in FINGER_IDS))
                    self.assertEqual(sum(states), count)

    def test_thumb_is_counted_from_mirrored_horizontal_pose_independently_of_y(self):
        for side in ("Left", "Right"):
            with self.subTest(side=side):
                sample = hand(("thumb",), handedness=side)
                sample.landmark[4].y = .8
                self.assertEqual(tuple(drawing.finger_states(sample, side)), (True, False, False, False, False))
                sample.landmark[4].x = sample.landmark[3].x + (-.1 if side == "Left" else .1)
                self.assertEqual(tuple(drawing.finger_states(sample, side)), (False, False, False, False, False))

    def test_unknown_handedness_excludes_thumb_without_disabling_other_fingers(self):
        self.assertEqual(tuple(drawing.finger_states(hand(COUNT_FINGERS[5]), "Unknown")),
                         (False, True, True, True, True))

    def test_finger_counts_are_invariant_when_either_hand_rotates_around_its_wrist(self):
        for side in ("Left", "Right"):
            for count, raised in enumerate(COUNT_FINGERS):
                original = hand(raised, handedness=side)
                wrist = original.landmark[0]
                for angle in (-math.pi / 2, math.pi / 2, math.pi):
                    with self.subTest(side=side, count=count, angle=angle):
                        rotated = []
                        for point in original.landmark:
                            dx, dy = point.x - wrist.x, point.y - wrist.y
                            rotated.append(SimpleNamespace(
                                x=wrist.x + dx * math.cos(angle) - dy * math.sin(angle),
                                y=wrist.y + dx * math.sin(angle) + dy * math.cos(angle), z=0.))
                        states = drawing.finger_states(SimpleNamespace(landmark=rotated), side)
                        self.assertEqual(tuple(states), tuple(name in raised for name in FINGER_IDS))
                        self.assertEqual(sum(states), count)

    def test_color_changes_only_after_a_continuous_180ms_count(self):
        color = drawing.StableFingerColor(stable_seconds=.18)
        self.assertEqual(color.update(1, 0.), 1)
        self.assertEqual(color.update(2, .01), 1)
        self.assertEqual(color.update(2, .189), 1)
        self.assertEqual(color.update(1, .19), 1)
        self.assertEqual(color.update(2, .20), 1)
        self.assertEqual(color.update(2, .379), 1)
        self.assertEqual(color.update(2, .381), 2)

    def test_reset_candidate_retains_color_but_restarts_the_stability_interval(self):
        color = drawing.StableFingerColor(stable_seconds=.18)
        color.update(3, 0.)
        self.assertEqual(color.update(3, .181), 3)
        self.assertEqual(color.update(4, .2), 3)
        color.reset_candidate()
        self.assertEqual(color.update(4, .5), 3)
        self.assertEqual(color.update(4, .679), 3)
        self.assertEqual(color.update(4, .681), 4)


class DrawingInputTests(unittest.TestCase):
    def setUp(self):
        self.layout = display_utils.get_uniform_layout(640, 480, 1280, 720)
        self.input = drawing.DrawingInput(1280, 720, stable_seconds=.18, rng=random.Random(7))

    def update(self, now, *, right=None, left=None):
        hands = []
        if right is not None:
            hands.append(("Right", right))
        if left is not None:
            hands.append(("Left", left))
        return self.input.update(results(*hands), self.layout, now)

    def eight(self, dx=0.):
        return [(side, hand(x=x + dx, y=y, handedness=side))
                for y in (.12, .53)
                for x, side in ((.18, "Left"), (.39, "Right"), (.60, "Left"), (.81, "Right"))]

    def test_pointer_and_stroke_use_one_mirror_and_the_camera_letterbox(self):
        first = hand(x=.25, y=.35)
        frame = self.update(0., right=first)
        expected = display_utils.normalized_to_stage(.25, .35, self.layout)
        self.assertEqual(expected, (400, 252))
        self.assertEqual(frame.active_points, (expected,))
        self.assertEqual(frame.hands, (first,))
        self.assertFalse(frame.strokes)
        moved = hand(x=.27, y=.36)
        frame = self.update(.05, right=moved)
        self.assertEqual(len(frame.strokes), 1)
        self.assertEqual((frame.strokes[0].start, frame.strokes[0].end),
                         (expected, display_utils.normalized_to_stage(.27, .36, self.layout)))

    def test_eight_left_and_right_hands_draw_with_separate_track_and_effect_identity(self):
        first = self.input.update(results(*self.eight()), self.layout, 0.)
        self.assertEqual(len(first.hands), 8)
        self.assertEqual(len(first.inputs), 8)
        self.assertEqual(len(first.active_points), 8)
        initial = {entry.track_id: entry for entry in first.inputs}
        self.assertEqual(len(initial), 8)
        self.assertFalse(first.strokes)
        second = self.input.update(results(*self.eight(.01)), self.layout, .05)
        self.assertEqual(len(second.strokes), 8)
        for stroke in second.strokes:
            self.assertIn(stroke.track_id, initial)
            self.assertEqual(stroke.start, initial[stroke.track_id].point)
            self.assertEqual(stroke.effect_id, initial[stroke.track_id].effect_id)
            self.assertNotEqual(stroke.start, stroke.end)
        self.assertEqual({entry.handedness for entry in second.inputs}, {"Left", "Right"})

    def test_detection_reordering_preserves_each_hands_stroke_and_effect(self):
        first = self.input.update(results(*self.eight()), self.layout, 0.)
        initial = {entry.track_id: entry for entry in first.inputs}
        reordered = self.input.update(results(*self.eight(.01)[::-1]), self.layout, .05)
        self.assertEqual(len(reordered.strokes), 8)
        self.assertEqual({entry.track_id for entry in reordered.inputs}, set(initial))
        for stroke in reordered.strokes:
            self.assertEqual(stroke.start, initial[stroke.track_id].point)
            self.assertEqual(stroke.effect_id, initial[stroke.track_id].effect_id)

    def test_fist_hand_loss_and_thumb_only_break_stroke_continuity(self):
        for interruption in (hand(()), None, hand(("thumb",))):
            with self.subTest(interruption=interruption):
                self.input = drawing.DrawingInput(1280, 720, rng=random.Random(7))
                self.update(0., right=hand(x=.3))
                self.assertEqual(len(self.update(.05, right=hand(x=.32)).strokes), 1)
                interrupted = self.update(.10, right=interruption)
                self.assertFalse(interrupted.strokes)
                self.assertEqual(interrupted.active_points, ())
                resumed = self.update(.15, right=hand(x=.34))
                self.assertFalse(resumed.strokes)
                self.assertEqual(len(self.update(.19, right=hand(x=.36)).strokes), 1)

    def test_one_hand_pausing_does_not_break_the_other_hands_stroke(self):
        self.update(0., right=hand(x=.25), left=hand(x=.70, handedness="Left"))
        first = self.update(.05, right=hand(x=.26), left=hand(x=.71, handedness="Left"))
        right_id = next(entry.track_id for entry in first.inputs if entry.handedness == "Right")
        paused = self.update(.10, right=hand(x=.27), left=hand((), x=.72, handedness="Left"))
        self.assertEqual([stroke.track_id for stroke in paused.strokes], [right_id])
        resumed = self.update(.15, right=hand(x=.28), left=hand(x=.73, handedness="Left"))
        self.assertEqual([stroke.track_id for stroke in resumed.strokes], [right_id])
        self.assertEqual(len(self.update(.19, right=hand(x=.29), left=hand(x=.74, handedness="Left")).strokes), 2)

    def test_long_gap_and_large_jump_do_not_bridge_disconnected_positions(self):
        self.update(0., right=hand(x=.25))
        self.assertFalse(self.update(.25, right=hand(x=.27)).strokes)
        self.assertEqual(len(self.update(.30, right=hand(x=.29)).strokes), 1)
        self.assertFalse(self.update(.35, right=hand(x=.80)).strokes)
        self.assertEqual(len(self.update(.40, right=hand(x=.82)).strokes), 1)

    def test_same_side_hands_both_draw_instead_of_overwriting_one_another(self):
        for side in ("Left", "Right"):
            with self.subTest(side=side):
                self.input = drawing.DrawingInput(1280, 720, rng=random.Random(7))
                first = [(side, hand(x=x, handedness=side)) for x in (.25, .7)]
                second = [(side, hand(x=x, handedness=side)) for x in (.27, .72)]
                self.input.update(results(*first), self.layout, 0.)
                frame = self.input.update(results(*second), self.layout, .05)
                self.assertEqual(len(frame.inputs), 2)
                self.assertEqual(len(frame.active_points), 2)
                self.assertEqual(len(frame.strokes), 2)
                self.assertEqual(len({stroke.track_id for stroke in frame.strokes}), 2)

    def test_unknown_or_missing_handedness_still_uses_index_without_counting_thumb(self):
        for detected in (results(("Unknown", hand(COUNT_FINGERS[5]))), SimpleNamespace(
                multi_hand_landmarks=[hand(COUNT_FINGERS[5])], multi_handedness=[])):
            with self.subTest(results=detected):
                self.input = drawing.DrawingInput(1280, 720, rng=random.Random(7))
                self.input.update(detected, self.layout, 0.)
                frame = self.input.update(detected, self.layout, .19)
                self.assertEqual(len(frame.hands), 1)
                self.assertEqual(len(frame.active_points), 1)
                self.assertEqual(frame.inputs[0].selected_count, 4)

    def test_color_flicker_does_not_change_strokes_until_stable(self):
        self.update(0., right=hand(COUNT_FINGERS[1]))
        original = self.update(.05, right=hand(COUNT_FINGERS[1], x=.46))
        for now, fingers in ((.1, COUNT_FINGERS[2]), (.15, COUNT_FINGERS[1]),
                             (.2, COUNT_FINGERS[2]), (.37, COUNT_FINGERS[2])):
            frame = self.update(now, right=hand(fingers, x=.47))
            self.assertEqual(frame.inputs[0].selected_count, 1)
            self.assertEqual(frame.strokes[0].color_bgr, original.strokes[0].color_bgr)
        selected = self.update(.39, right=hand(COUNT_FINGERS[2], x=.48))
        self.assertEqual(selected.inputs[0].selected_count, 2)
        self.assertFalse(selected.strokes)
        emitted = self.update(.41, right=hand(COUNT_FINGERS[2], x=.49))
        self.assertEqual(emitted.inputs[0].selected_count, 2)
        self.assertNotEqual(emitted.strokes[0].color_bgr, original.strokes[0].color_bgr)

    def test_skipped_emission_frames_keep_live_pointer_and_connect_to_last_emitted_point(self):
        first = self.update(0., right=hand(x=.3))
        skipped = self.update(1 / 60, right=hand(x=.31))
        self.assertFalse(skipped.strokes)
        self.assertEqual(skipped.active_points,
                         (display_utils.normalized_to_stage(.31, .35, self.layout),))
        emitted = self.update(2 / 60, right=hand(x=.32))
        self.assertEqual(len(emitted.strokes), 1)
        self.assertEqual(emitted.strokes[0].start, first.inputs[0].point)
        self.assertEqual(emitted.strokes[0].end,
                         display_utils.normalized_to_stage(.32, .35, self.layout))
        skipped_again = self.update(3 / 60, right=hand(x=.33))
        self.assertFalse(skipped_again.strokes)
        self.assertEqual(skipped_again.active_points,
                         (display_utils.normalized_to_stage(.33, .35, self.layout),))
        next_emission = self.update(4 / 60, right=hand(x=.34))
        self.assertEqual(len(next_emission.strokes), 1)
        self.assertEqual(next_emission.strokes[0].start, emitted.strokes[0].end)
        self.assertEqual(next_emission.strokes[0].end,
                         display_utils.normalized_to_stage(.34, .35, self.layout))

    def test_sustained_eight_hands_at_sixty_fps_reach_fade_with_bounded_history_and_rate(self):
        duration, fps = 8, 60
        history_limit = drawing.run_app.__kwdefaults__["max_segments"]
        self.assertEqual(history_limit, drawing.DEFAULT_MAX_SEGMENTS)
        ink = drawing.FadingInk(1280, 720, max_segments=history_limit)
        emission_times = {}
        maximum_history = 0
        for index in range(duration * fps + 1):
            now = index / fps
            # Parallel triangular paths stay separated and keep moving by more
            # than one pixel per emission, including at the turning points.
            phase = (index % (2 * fps)) / (2 * fps)
            dx = .08 * (1 - abs(2 * phase - 1)) - .04
            frame = self.input.update(results(*self.eight(dx)), self.layout, now)
            self.assertEqual(len(frame.inputs), 8)
            self.assertEqual(len(frame.active_points), 8)
            for stroke in frame.strokes:
                emission_times.setdefault(stroke.track_id, []).append(now)
                self.assertTrue(ink.add_segment(stroke.start, stroke.end, stroke.color_bgr, now,
                                                effect_id=stroke.effect_id, track_id=stroke.track_id))
            ink.advance(now)
            maximum_history = max(maximum_history, len(ink.segments))
            self.assertLessEqual(len(ink.segments), history_limit)

        self.assertEqual(len(emission_times), 8)
        for track_id, times in emission_times.items():
            with self.subTest(track_id=track_id):
                self.assertGreaterEqual(len(times), duration * drawing.MAX_STROKE_HZ - 1)
                self.assertLessEqual(len(times), duration * drawing.MAX_STROKE_HZ)
                self.assertTrue(all(b - a >= 1 / drawing.MAX_STROKE_HZ - 1e-9
                                    for a, b in zip(times, times[1:])))
        self.assertGreater(maximum_history, 8 * drawing.MAX_STROKE_HZ * ink.hold_seconds)
        oldest_age = duration - ink.segments[0].created_at
        self.assertGreater(oldest_age, ink.hold_seconds)
        self.assertLess(oldest_age, ink.lifetime)
        fading_ids = {segment.track_id for segment in ink.segments
                      if ink.hold_seconds < duration - segment.created_at < ink.lifetime}
        self.assertEqual(fading_ids, set(emission_times))
        # Exercise the actual fade renderer once, without opening a window.
        with mock.patch.object(ink, "_styled_line", wraps=ink._styled_line) as fade_line:
            image = ink.render(duration)
        self.assertTrue(np.any(image))
        self.assertGreater(fade_line.call_count, 0)
        self.assertTrue(all(0 < call.args[1] < 1 for call in fade_line.call_args_list))
        self.assertLessEqual(len(ink.segments), history_limit)

    def test_left_and_right_color_selection_is_independent(self):
        self.update(0., left=hand(COUNT_FINGERS[2], x=.25, handedness="Left"),
                    right=hand(COUNT_FINGERS[3], x=.7))
        pending = self.update(.10, left=hand(COUNT_FINGERS[2], x=.26, handedness="Left"),
                              right=hand(COUNT_FINGERS[3], x=.71))
        self.assertEqual([entry.selected_count for entry in pending.inputs], [1, 1])
        frame = self.update(.19, left=hand(COUNT_FINGERS[2], x=.27, handedness="Left"),
                            right=hand(COUNT_FINGERS[3], x=.72))
        counts = {entry.handedness: entry.selected_count for entry in frame.inputs}
        self.assertEqual(counts, {"Left": 2, "Right": 3})
        colors = {entry.track_id: drawing.FINGER_COLORS_BGR[entry.selected_count] for entry in frame.inputs}
        for stroke in frame.strokes:
            self.assertEqual(stroke.color_bgr, colors[stroke.track_id])

    def test_lost_hand_restarts_its_color_candidate_without_resetting_other_hand(self):
        self.update(0., left=hand(COUNT_FINGERS[2], x=.25, handedness="Left"),
                    right=hand(COUNT_FINGERS[3], x=.7))
        self.update(.10, right=hand(COUNT_FINGERS[3], x=.71))
        returned = self.update(.19, left=hand(COUNT_FINGERS[2], x=.25, handedness="Left"),
                               right=hand(COUNT_FINGERS[3], x=.72))
        self.assertEqual({entry.handedness: entry.selected_count for entry in returned.inputs},
                         {"Left": 1, "Right": 3})
        self.assertEqual(len(returned.strokes), 1)
        settled = self.update(.38, left=hand(COUNT_FINGERS[2], x=.26, handedness="Left"),
                              right=hand(COUNT_FINGERS[3], x=.73))
        self.assertEqual({entry.handedness: entry.selected_count for entry in settled.inputs},
                         {"Left": 2, "Right": 3})

    def test_reset_retains_selected_color_and_effect_without_connecting_old_strokes(self):
        self.update(0., right=hand(COUNT_FINGERS[3]))
        selected = self.update(.19, right=hand(COUNT_FINGERS[3], x=.46))
        self.assertEqual(selected.inputs[0].selected_count, 3)
        self.input.reset()
        resumed = self.update(.20, right=hand(COUNT_FINGERS[3], x=.47))
        self.assertEqual(resumed.inputs[0].selected_count, 3)
        self.assertEqual(resumed.inputs[0].track_id, selected.inputs[0].track_id)
        self.assertEqual(resumed.inputs[0].effect_id, selected.inputs[0].effect_id)
        self.assertFalse(resumed.strokes)


class WindowPlacementTests(unittest.TestCase):
    def setUp(self):
        patches = ExitStack()
        self.addCleanup(patches.close)
        self.named = patches.enter_context(mock.patch.object(drawing.cv2, "namedWindow"))
        self.resize = patches.enter_context(mock.patch.object(drawing.cv2, "resizeWindow"))
        self.move = patches.enter_context(mock.patch.object(drawing.cv2, "moveWindow"))
        self.property = patches.enter_context(mock.patch.object(drawing.cv2, "setWindowProperty"))

    def test_preview_is_centered_and_scaled_inside_primary_monitor_even_when_listed_second(self):
        primary = SimpleNamespace(x=-1280, y=200, width=1280, height=800, is_primary=True)
        audience = SimpleNamespace(x=0, y=0, width=1920, height=1080, is_primary=False)
        with mock.patch("screeninfo.get_monitors", return_value=[audience, primary]):
            drawing.setup_window(1920, 1080)
        self.named.assert_called_once_with(drawing.WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        self.resize.assert_called_once()
        self.move.assert_called_once()
        _, width, height = self.resize.call_args.args
        _, x, y = self.move.call_args.args
        self.assertLessEqual(width, primary.width * .85)
        self.assertLessEqual(height, primary.height * .80)
        self.assertAlmostEqual(width / height, 1920 / 1080, places=3)
        self.assertEqual(x + width // 2, primary.x + primary.width // 2)
        self.assertEqual(y + height // 2, primary.y + primary.height // 2)
        self.assertGreaterEqual(x, primary.x)
        self.assertGreaterEqual(y, primary.y)
        self.assertLessEqual(x + width, primary.x + primary.width)
        self.assertLessEqual(y + height, primary.y + primary.height)
        self.property.assert_not_called()

    def test_monitor_lookup_failure_or_empty_list_uses_requested_size_and_fallback_position(self):
        for failure in (RuntimeError("injected monitor lookup failure"), None):
            with self.subTest(failure=failure):
                self.named.reset_mock()
                self.resize.reset_mock()
                self.move.reset_mock()
                with mock.patch("screeninfo.get_monitors", side_effect=failure, return_value=[]):
                    drawing.setup_window(960, 540)
                self.named.assert_called_once_with(drawing.WINDOW_NAME,
                                                  cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
                self.resize.assert_called_once_with(drawing.WINDOW_NAME, 960, 540)
                self.move.assert_called_once_with(drawing.WINDOW_NAME, 40, 40)
                self.property.assert_not_called()


class DrawingLifecycleTests(unittest.TestCase):
    def setUp(self):
        patches = ExitStack()
        self.addCleanup(patches.close)
        self.frame = np.zeros((240, 320, 3), dtype=np.uint8)
        self.frame[:, :60] = (20, 60, 200)
        self.cap = mock.Mock(last_read_frame_id=None)
        self.cap.isOpened.return_value = True
        self.cap.read.return_value = (True, self.frame)
        self.detector = mock.Mock()
        self.detector.process.return_value = results(("Right", hand(x=.25)))
        self.factory = patches.enter_context(mock.patch.object(
            drawing.mp.solutions.hands, "Hands", return_value=self.detector))
        self.open_camera = patches.enter_context(mock.patch.object(
            drawing.display_utils, "open_camera", return_value=self.cap))
        self.setup_window = patches.enter_context(mock.patch.object(drawing, "setup_window"))
        self.imshow = patches.enter_context(mock.patch.object(drawing.cv2, "imshow"))
        self.destroy = patches.enter_context(mock.patch.object(drawing.cv2, "destroyWindow"))
        self.wait_key = patches.enter_context(mock.patch.object(drawing.cv2, "waitKey"))
        self.visible = patches.enter_context(mock.patch.object(drawing.cv2, "getWindowProperty", return_value=1.))
        self.ready = patches.enter_context(mock.patch.object(drawing, "notify_first_frame"))
        self.exit_request = patches.enter_context(mock.patch.object(drawing, "notify_exit_request"))
        self.overlay = patches.enter_context(mock.patch.object(drawing, "draw_hand_overlay"))
        self.now = 0.
        patches.enter_context(mock.patch.object(drawing.time, "monotonic", side_effect=lambda: self.now))
        self.keys(0, ord("q"))

    def keys(self, *values, step=.05):
        sequence = iter(values)

        def poll(_delay):
            self.now += step
            return next(sequence)

        self.wait_key.side_effect = poll

    def run_app(self):
        drawing.run_app(width=960, height=540)

    def assert_cleaned(self):
        self.cap.release.assert_called_once_with()
        self.detector.close.assert_called_once_with()
        self.destroy.assert_called_once()

    def test_successful_frame_uses_shared_camera_once_and_mirrors_only_for_inference(self):
        self.run_app()
        self.open_camera.assert_called_once_with()
        self.assertEqual(self.factory.call_args.kwargs["max_num_hands"], 8)
        self.cap.set.assert_not_called()
        self.cap.read.assert_called_once_with()
        self.detector.process.assert_called_once()
        np.testing.assert_array_equal(self.detector.process.call_args.args[0],
                                      cv2.cvtColor(cv2.flip(self.frame, 1), cv2.COLOR_BGR2RGB))
        self.assert_cleaned()

    def test_runtime_draws_all_eight_hands_with_independent_effect_and_track_metadata(self):
        poses = [(side, x, y) for y in (.12, .53)
                 for x, side in ((.18, "Left"), (.39, "Right"), (.60, "Left"), (.81, "Right"))]
        self.detector.process.side_effect = [
            results(*[(side, hand(x=x + offset, y=y, handedness=side)) for side, x, y in poses])
            for offset in (0., .01)
        ]
        self.keys(0, 0, ord("q"))
        with mock.patch.object(drawing.FadingInk, "add_segment", return_value=True) as add_segment:
            self.run_app()
        self.assertEqual(self.detector.process.call_count, 2)
        self.assertEqual(add_segment.call_count, 8)
        self.assertEqual(len({call.kwargs["track_id"] for call in add_segment.call_args_list}), 8)
        self.assertTrue(all(isinstance(call.kwargs["effect_id"], int) for call in add_segment.call_args_list))
        for overlay_call in self.overlay.call_args_list:
            self.assertEqual(len(overlay_call.args[1]), 8)
            self.assertEqual(len(overlay_call.kwargs["active_points"]), 8)
        self.open_camera.assert_called_once_with()
        self.assert_cleaned()

    def test_left_hand_movement_never_clears_existing_ink(self):
        self.detector.process.side_effect = [results(("Left", hand(x=x, handedness="Left")))
                                             for x in (.25, .45)]
        self.keys(0, 0, ord("q"))
        with mock.patch.object(drawing.FadingInk, "clear") as clear:
            self.run_app()
        clear.assert_not_called()
        self.assert_cleaned()

    def test_common_overlay_highlights_actual_index_point_in_letterboxed_stage(self):
        self.run_app()
        self.overlay.assert_called_once()
        args, kwargs = self.overlay.call_args
        layout = display_utils.get_uniform_layout(320, 240, 960, 540)
        self.assertEqual(args[0].shape, (540, 960, 3))
        self.assertEqual(kwargs["layout"], layout)
        self.assertEqual(kwargs.get("focus", ()), ())
        self.assertEqual(tuple(kwargs["active_points"]),
                         (display_utils.normalized_to_stage(.25, .35, layout),))

    def test_q_stops_before_camera_read_and_releases_resources(self):
        self.keys(ord("q"))
        self.run_app()
        self.cap.read.assert_not_called()
        self.detector.process.assert_not_called()
        self.ready.assert_not_called()
        self.exit_request.assert_called_once()
        self.assert_cleaned()

    def test_closed_window_stops_without_inference(self):
        self.visible.return_value = 0.
        self.keys(0)
        self.run_app()
        self.detector.process.assert_not_called()
        self.exit_request.assert_called_once()
        self.assert_cleaned()

    def test_failed_and_none_frames_continue_polling_and_recover(self):
        self.cap.read.side_effect = [(False, None), (True, None), (True, self.frame)]
        self.keys(0, 0, 0, ord("q"))
        self.run_app()
        self.assertEqual(self.cap.read.call_count, 3)
        self.assertEqual(self.wait_key.call_count, 4)
        self.detector.process.assert_called_once()
        successful = [call for call in self.ready.call_args_list if call.kwargs.get("frame_processed")]
        self.assertEqual(len(successful), 1)
        self.open_camera.assert_called_once_with()
        self.assert_cleaned()

    def test_missing_camera_closes_detector_without_fallback_or_window(self):
        self.open_camera.return_value = None
        with self.assertRaisesRegex(RuntimeError, "Camera unavailable"):
            self.run_app()
        self.open_camera.assert_called_once_with()
        self.detector.close.assert_called_once_with()
        self.setup_window.assert_not_called()
        self.detector.process.assert_not_called()

    def test_unopened_camera_and_detector_are_both_released(self):
        self.cap.isOpened.return_value = False
        with self.assertRaisesRegex(RuntimeError, "Camera unavailable"):
            self.run_app()
        self.open_camera.assert_called_once_with()
        self.cap.release.assert_called_once_with()
        self.detector.close.assert_called_once_with()
        self.setup_window.assert_not_called()

    def test_duplicate_shared_frames_do_not_run_inference_or_add_ink_again(self):
        frame_ids = iter((1, 2, 2, 2))

        def read():
            self.cap.last_read_frame_id = next(frame_ids)
            return True, self.frame

        self.cap.read.side_effect = read
        self.detector.process.side_effect = [results(("Right", hand(x=.3))),
                                             results(("Right", hand(x=.32)))]
        self.keys(0, 0, 0, 0, ord("q"))
        with mock.patch.object(drawing.FadingInk, "add_segment", return_value=True) as add_segment:
            self.run_app()
        self.assertEqual(self.detector.process.call_count, 2)
        self.assertEqual(add_segment.call_count, 1)
        self.assertEqual(self.imshow.call_count, 4)
        self.assertEqual([call.kwargs["frame_processed"] for call in self.ready.call_args_list],
                         [True, True, False, False])
        self.assert_cleaned()

    def test_stale_shared_frame_clears_feedback_and_recovery_cannot_bridge_old_ink(self):
        frame_ids = iter((1, 2, 2, 3, 4))

        def read():
            self.cap.last_read_frame_id = next(frame_ids)
            return True, self.frame

        self.cap.read.side_effect = read
        times = iter((.05, .10, .40, .45, .50, .55))
        keys = iter((0, 0, 0, 0, 0, ord("q")))

        def poll(_delay):
            self.now = next(times)
            return next(keys)

        self.wait_key.side_effect = poll
        self.detector.process.side_effect = [results(("Right", hand(x=x))) for x in (.3, .32, .34, .36)]
        with mock.patch.object(drawing.FadingInk, "add_segment", return_value=True) as add_segment:
            self.run_app()
        self.assertEqual(self.detector.process.call_count, 4)
        self.assertEqual(add_segment.call_count, 2)
        layout = display_utils.get_uniform_layout(320, 240, 960, 540)
        expected = [tuple(display_utils.normalized_to_stage(x, .35, layout) for x in pair)
                    for pair in ((.3, .32), (.34, .36))]
        self.assertEqual([call.args[:2] for call in add_segment.call_args_list], expected)
        stale = self.overlay.call_args_list[2]
        self.assertEqual(stale.args[1], ())
        self.assertEqual(stale.kwargs["active_points"], ())
        self.assertEqual([call.kwargs["frame_processed"] for call in self.ready.call_args_list],
                         [True, True, False, True, True])
        self.assert_cleaned()

    def test_camera_timeout_notifies_failure_and_releases_resources(self):
        self.cap.read.return_value = (False, None)
        self.keys(0, 0, 0, 0, 0, step=.4)
        with self.assertRaisesRegex(RuntimeError, "Camera stopped providing fresh frames"):
            self.run_app()
        self.detector.process.assert_not_called()
        self.exit_request.assert_called_once_with("camera_read_failed_timeout")
        self.assert_cleaned()

    def test_first_frame_is_reported_after_inference_and_display(self):
        order = mock.Mock()
        order.attach_mock(self.detector.process, "infer")
        order.attach_mock(self.imshow, "present")
        order.attach_mock(self.ready, "ready")
        self.run_app()
        names = [call[0] for call in order.mock_calls]
        self.assertLess(names.index("infer"), names.index("present"))
        self.assertLess(names.index("present"), names.index("ready"))
        self.assertTrue(self.ready.call_args.kwargs["frame_processed"])

    def test_inference_exception_releases_camera_detector_and_window(self):
        self.detector.process.side_effect = RuntimeError("injected inference failure")
        with self.assertRaisesRegex(RuntimeError, "injected inference"):
            self.run_app()
        self.ready.assert_not_called()
        self.assert_cleaned()


if __name__ == "__main__":
    unittest.main()
