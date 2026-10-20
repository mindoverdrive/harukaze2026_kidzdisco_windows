"""Pure reset-gesture contract tests; no Minecraft, camera, or renderer imports.

Synthetic landmarks exercise observation validity, not person identification.
The helper remains a single-player feature: handedness is not person identity.
Run with Python -B -m unittest discover -s <this directory> -v.
"""
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as Object
import unittest


_SPEC = importlib.util.spec_from_file_location(
    "_minecraft_reset_gesture_subject",
    Path(__file__).resolve().parents[1] / "minecraft_reset.py",
)
reset = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = reset
_SPEC.loader.exec_module(reset)


def sample(left="fist", right=None, **coordinates):
    return reset.ResetSample(
        left, left if right is None else right,
        coordinates.get("left_wrist", (0.30, 0.65)),
        coordinates.get("right_wrist", (0.70, 0.65)),
        coordinates.get("face_center", (0.50, 0.40)),
    )


def point(x, y):
    return Object(x=x, y=y)


def hand(shape="fist", wrist=(0.30, 0.65)):
    """Construct deterministic 21-point geometry away from shape thresholds."""
    x, y = wrist
    landmarks = [point(x, y) for _ in range(21)]
    landmarks[9] = point(x, y - 0.08)
    for offset, tip, pip in zip(
        (-0.06, -0.02, 0.02, 0.06), (8, 12, 16, 20), (6, 10, 14, 18)
    ):
        landmarks[pip] = point(x + offset, y - 0.12)
        landmarks[tip] = point(x + offset, y - (0.25 if shape == "palm" else 0.03))
    landmarks[3] = point(x - 0.06, y - 0.05)
    landmarks[4] = point(x - 0.10, y - 0.10) if shape == "palm" else point(x + 0.02, y - 0.05)
    landmarks[17] = point(x + 0.05, y - 0.06)
    if shape == "other":
        landmarks[8] = point(x - 0.06, y - 0.12)
    return Object(landmark=landmarks)


def label(name, score=0.99):
    return Object(classification=[Object(label=name, score=score)])


def observations(left="fist", right="fist"):
    hands = Object(
        multi_hand_landmarks=[hand(left), hand(right, (0.70, 0.65))],
        multi_handedness=[label("Left"), label("Right")],
    )
    faces = Object(multi_face_landmarks=[Object(landmark=[point(0.5, 0.4), point(0.5, 0.4)])])
    return hands, faces


class SequenceAssertions:
    def setUp(self):
        self.gesture = reset.TwoHandReset()

    def quiet(self, frames, gesture=None):
        detector = self.gesture if gesture is None else gesture
        for now, observation in frames:
            with self.subTest(now=now, observation=observation):
                self.assertFalse(detector.update(observation, now))

    def arm(self, start=0.0, gesture=None):
        self.quiet([(start + t, sample()) for t in (0.0, 0.10, 0.20, 0.30, 0.35)], gesture)


class TemporalGestureTests(SequenceAssertions, unittest.TestCase):
    def test_stable_fists_then_stable_palms_emits_once_at_exact_holds(self):
        self.arm()
        self.quiet([(0.40, sample("palm")), (0.519, sample("palm"))])
        self.assertTrue(self.gesture.update(sample("palm"), 0.52))
        self.quiet([(t, sample("palm")) for t in (0.62, 0.72, 0.82, 0.92, 1.02)])

    def test_starting_with_palms_never_arms(self):
        self.quiet([(i / 10, sample("palm")) for i in range(20)])

    def test_one_hand_fist_cannot_arm(self):
        for left, right in (("fist", "other"), ("other", "fist"), ("fist", "palm"), ("palm", "fist")):
            with self.subTest(left=left, right=right):
                detector = reset.TwoHandReset()
                self.quiet([(i / 10, sample(left, right)) for i in range(8)], detector)
                self.quiet([(0.8, sample("palm")), (0.92, sample("palm"))], detector)

    def test_fists_just_short_of_required_hold_do_not_arm(self):
        self.quiet([(t, sample()) for t in (0.0, 0.10, 0.20, 0.30, 0.349)])
        self.quiet([(0.40, sample("palm")), (0.52, sample("palm"))])

    def test_fist_shape_jitter_restarts_hold(self):
        self.quiet([(0.0, sample()), (0.1, sample()), (0.2, sample("other"))])
        self.quiet([(t, sample()) for t in (0.3, 0.4, 0.5, 0.6, 0.649)])
        self.quiet([(0.65, sample("palm")), (0.77, sample("palm"))])
        self.arm(0.9)
        self.quiet([(1.30, sample("palm"))])
        self.assertTrue(self.gesture.update(sample("palm"), 1.42))

    def test_staggered_fists_require_full_simultaneous_hold(self):
        self.quiet([(0.0, sample("fist", "other")), (0.1, sample("fist", "other"))])
        self.quiet([(t, sample()) for t in (0.2, 0.3, 0.4, 0.45)])
        self.quiet([(0.5, sample("palm")), (0.62, sample("palm"))])

    def test_staggered_opening_can_succeed_inside_window(self):
        self.arm()
        self.quiet([(0.4, sample("palm", "fist")), (0.5, sample("palm", "other")), (0.55, sample("palm"))])
        self.assertTrue(self.gesture.update(sample("palm"), 0.67))

    def test_staggered_palms_do_not_accumulate_individual_hold_times(self):
        self.arm()
        self.quiet([(0.4, sample("palm", "other")), (0.5, sample("other", "palm")), (0.6, sample("palm"))])
        self.quiet([(0.719, sample("palm"))])
        self.assertTrue(self.gesture.update(sample("palm"), 0.72))

    def test_palm_jitter_restarts_palm_hold(self):
        self.arm()
        self.quiet([(0.4, sample("palm")), (0.46, sample("palm", "other")), (0.5, sample("palm")), (0.619, sample("palm"))])
        self.assertTrue(self.gesture.update(sample("palm"), 0.62))

    def test_palms_just_short_of_required_hold_do_not_trigger(self):
        self.arm()
        self.quiet([(0.40, sample("palm")), (0.519, sample("palm")), (0.52, sample("other"))])

    def test_opening_window_includes_exact_deadline(self):
        self.arm()
        self.quiet([(t, sample("other")) for t in (0.4, 0.55, 0.7, 0.85)])
        self.quiet([(0.93, sample("palm"))])
        self.assertTrue(self.gesture.update(sample("palm"), 1.05))

    def test_palm_hold_finishing_after_opening_deadline_is_rejected(self):
        self.arm()
        self.quiet([(t, sample("other")) for t in (0.4, 0.55, 0.7, 0.85)])
        self.quiet([(0.93, sample("palm")), (1.05001, sample("palm")), (1.17, sample("palm"))])

    def test_opening_deadline_starts_when_first_hand_leaves_fist(self):
        self.arm()
        self.quiet([(t, sample("palm", "fist")) for t in (0.4, 0.55, 0.7, 0.85)])
        self.quiet([(0.94, sample("palm")), (1.06, sample("palm")), (1.18, sample("palm"))])

    def test_armed_fists_can_wait_before_opening_window_starts(self):
        self.arm()
        self.quiet([(i / 10, sample()) for i in range(4, 21)])
        self.quiet([(2.1, sample("palm"))])
        self.assertTrue(self.gesture.update(sample("palm"), 2.22))

    def test_return_to_fists_after_opening_requires_full_fresh_hold(self):
        self.arm()
        self.quiet([(0.4, sample("other")), (0.45, sample()), (0.55, sample()), (0.65, sample())])
        self.quiet([(0.7, sample("palm")), (0.82, sample("palm"))])

    def test_return_to_fists_can_rearm_after_fresh_full_hold(self):
        self.arm()
        self.quiet([(0.4, sample("other"))])
        self.arm(0.45)
        self.quiet([(0.85, sample("palm"))])
        self.assertTrue(self.gesture.update(sample("palm"), 0.97))

    def test_short_missing_observation_cancels_and_new_hold_can_rearm(self):
        self.arm()
        self.quiet([(0.36, None), (0.4, sample("palm")), (0.52, sample("palm"))])
        self.arm(0.6)
        self.quiet([(1.0, sample("palm"))])
        self.assertTrue(self.gesture.update(sample("palm"), 1.12))

    def test_missing_observation_during_palm_hold_cancels(self):
        self.arm()
        self.quiet([(0.4, sample("palm")), (0.46, None), (0.5, sample("palm")), (0.62, sample("palm"))])

    def test_gap_exactly_point_two_seconds_is_allowed(self):
        self.quiet([(0.0, sample()), (0.2, sample()), (0.35, sample()), (0.55, sample("palm"))])
        self.assertTrue(self.gesture.update(sample("palm"), 0.67))

    def test_long_gap_cancels_armed_state(self):
        self.arm()
        self.quiet([(0.55001, sample("palm")), (0.67001, sample("palm"))])

    def test_long_gap_restarts_fist_hold(self):
        self.quiet([(0.0, sample()), (0.1, sample()), (0.30001, sample()), (0.4, sample()), (0.5, sample())])
        self.quiet([(0.55, sample("palm")), (0.67, sample("palm"))])

    def test_reversed_clock_cancels_armed_state(self):
        self.arm()
        self.quiet([(0.34, sample("palm")), (0.46, sample("palm"))])

    def test_duplicate_timestamp_cancels_armed_state(self):
        self.arm()
        self.quiet([(0.35, sample("palm")), (0.47, sample("palm"))])

    def test_nonfinite_time_cancels_and_recovery_needs_fresh_hold(self):
        for invalid in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(invalid=invalid):
                detector = reset.TwoHandReset()
                self.arm(gesture=detector)
                self.quiet([(invalid, sample("palm")), (0.4, sample("palm")), (0.52, sample("palm"))], detector)
                self.arm(0.6, detector)
                self.quiet([(1.0, sample("palm"))], detector)
                self.assertTrue(detector.update(sample("palm"), 1.12))

    def test_second_trigger_requires_new_complete_fist_and_palm_sequence(self):
        self.arm()
        self.quiet([(0.4, sample("palm"))])
        self.assertTrue(self.gesture.update(sample("palm"), 0.52))
        self.quiet([(0.53, sample()), (0.54, sample("palm")), (0.66, sample("palm"))])
        self.arm(0.7)
        self.quiet([(1.1, sample("palm"))])
        self.assertTrue(self.gesture.update(sample("palm"), 1.22))

    def test_explicit_cancel_requires_new_hold(self):
        self.arm()
        self.gesture.cancel()
        self.quiet([(0.4, sample("palm")), (0.52, sample("palm"))])


class SpatialContinuityTests(SequenceAssertions, unittest.TestCase):
    def test_position_jump_cancels(self):
        for changes in (
            {"left_wrist": (0.431, 0.65)},
            {"right_wrist": (0.831, 0.65)},
            {"face_center": (0.581, 0.40)},
            {"left_wrist": (0.70, 0.65), "right_wrist": (0.30, 0.65)},
        ):
            with self.subTest(changes=changes):
                detector = reset.TwoHandReset()
                self.arm(gesture=detector)
                moved = sample("palm", **changes)
                self.quiet([(0.4, moved), (0.52, moved)], detector)

    def test_small_motion_remains_valid(self):
        self.arm()
        moved = sample("palm", left_wrist=(0.419, 0.65), right_wrist=(0.581, 0.65), face_center=(0.579, 0.40))
        self.quiet([(0.4, moved)])
        self.assertTrue(self.gesture.update(moved, 0.52))

    def test_horizontal_order_reversal_cancels_even_with_small_motion(self):
        # Separate the hands vertically so reversing x order needs only .02 motion.
        initial = sample(left_wrist=(0.49, 0.35), right_wrist=(0.51, 0.65))
        self.quiet([(t, initial) for t in (0.0, 0.1, 0.2, 0.3, 0.35)])
        crossed = sample("palm", left_wrist=(0.51, 0.35), right_wrist=(0.49, 0.65))
        self.quiet([(0.4, crossed), (0.52, crossed)])

    def test_nonfinite_direct_sample_coordinates_cancel(self):
        for attribute in ("left_wrist", "right_wrist", "face_center"):
            for invalid in (float("nan"), float("inf"), -float("inf")):
                for point_value in ((invalid, 0.5), (0.5, invalid)):
                    with self.subTest(attribute=attribute, point=point_value):
                        detector = reset.TwoHandReset()
                        self.arm(gesture=detector)
                        corrupt = replace(sample("palm"), **{attribute: point_value})
                        self.quiet([(0.4, corrupt), (0.52, corrupt)], detector)
                        self.quiet([(0.6, sample("palm")), (0.72, sample("palm"))], detector)

    def test_wrong_coordinate_dimensions_cancel(self):
        for attribute in ("left_wrist", "right_wrist", "face_center"):
            for point_value in ((), (0.5,), (0.5, 0.5, 0.5)):
                with self.subTest(attribute=attribute, point=point_value):
                    detector = reset.TwoHandReset()
                    self.arm(gesture=detector)
                    corrupt = replace(sample("palm"), **{attribute: point_value})
                    self.quiet([(0.4, corrupt), (0.52, sample("palm")), (0.64, sample("palm"))], detector)


class ObservationGateTests(unittest.TestCase):
    def test_complete_fists_palms_and_indeterminate_hands(self):
        for left, right in (("fist", "fist"), ("palm", "palm"), ("fist", "palm"), ("other", "other")):
            with self.subTest(left=left, right=right):
                self.assertEqual(reset.reset_sample(*observations(left, right)), sample(left, right))

    def test_detector_order_does_not_determine_left_and_right(self):
        hands, faces = observations("fist", "palm")
        hands.multi_hand_landmarks.reverse()
        hands.multi_handedness.reverse()
        self.assertEqual(reset.reset_sample(hands, faces), sample("fist", "palm"))

    def test_confidence_exactly_point_eight_is_accepted(self):
        hands, faces = observations()
        hands.multi_handedness = [label("Left", 0.8), label("Right", 0.8)]
        self.assertEqual(reset.reset_sample(hands, faces), sample())

    def test_low_nonfinite_and_malformed_confidence_is_rejected(self):
        for score in (0.79999, 0.0, -1.0, float("nan"), float("inf"), -float("inf"), None, "0.99"):
            for index in (0, 1):
                with self.subTest(score=score, index=index):
                    hands, faces = observations()
                    hands.multi_handedness[index].classification[0].score = score
                    self.assertIsNone(reset.reset_sample(hands, faces))

    def test_duplicate_or_unknown_handedness_is_rejected(self):
        for names in (("Left", "Left"), ("Right", "Right"), ("Unknown", "Right"), ("left", "Right"), (None, "Right")):
            with self.subTest(names=names):
                hands, faces = observations()
                hands.multi_handedness = [label(name) for name in names]
                self.assertIsNone(reset.reset_sample(hands, faces))

    def test_missing_and_extra_hands_labels_or_faces_are_rejected(self):
        for target, attribute in (("hands", "multi_hand_landmarks"), ("hands", "multi_handedness"), ("faces", "multi_face_landmarks")):
            for count in (0, 1, 3):
                if target == "faces" and count == 1:
                    continue
                with self.subTest(target=target, attribute=attribute, count=count):
                    hands, faces = observations()
                    owner = hands if target == "hands" else faces
                    original = getattr(owner, attribute)
                    setattr(owner, attribute, [original[i % len(original)] for i in range(count)])
                    self.assertIsNone(reset.reset_sample(hands, faces))
        hands, faces = observations()
        faces.multi_face_landmarks *= 2
        self.assertIsNone(reset.reset_sample(hands, faces))

    def test_none_collections_are_rejected(self):
        for attribute in ("multi_hand_landmarks", "multi_handedness", "multi_face_landmarks"):
            with self.subTest(attribute=attribute):
                hands, faces = observations()
                setattr(faces if attribute == "multi_face_landmarks" else hands, attribute, None)
                self.assertIsNone(reset.reset_sample(hands, faces))

    def test_missing_top_level_attributes_are_rejected(self):
        hands, faces = observations()
        for malformed_hands, malformed_faces in ((None, faces), (hands, None), (Object(), faces), (hands, Object())):
            with self.subTest(hands=malformed_hands, faces=malformed_faces):
                self.assertIsNone(reset.reset_sample(malformed_hands, malformed_faces))

    def test_missing_handedness_classification_is_rejected(self):
        for malformed in (Object(), Object(classification=[]), Object(classification=[Object()]), Object(classification=None)):
            with self.subTest(malformed=malformed):
                hands, faces = observations()
                hands.multi_handedness[0] = malformed
                self.assertIsNone(reset.reset_sample(hands, faces))

    def test_hand_requires_exactly_twenty_one_landmarks(self):
        for count in (0, 1, 20, 22):
            with self.subTest(count=count):
                hands, faces = observations()
                original = hands.multi_hand_landmarks[0].landmark
                hands.multi_hand_landmarks[0].landmark = [original[i % 21] for i in range(count)]
                self.assertIsNone(reset.reset_sample(hands, faces))

    def test_face_requires_center_landmark(self):
        for malformed in (Object(), Object(landmark=[]), Object(landmark=[point(0.5, 0.4)]), Object(landmark=None)):
            with self.subTest(malformed=malformed):
                hands, faces = observations()
                faces.multi_face_landmarks[0] = malformed
                self.assertIsNone(reset.reset_sample(hands, faces))

    def test_nonfinite_out_of_range_or_malformed_coordinates_are_rejected(self):
        for invalid in (float("nan"), float("inf"), -float("inf"), -0.10001, 1.10001, None, "bad"):
            for target in ("left_wrist", "right_wrist", "finger", "face"):
                for axis in ("x", "y"):
                    with self.subTest(invalid=invalid, target=target, axis=axis):
                        hands, faces = observations()
                        landmark = {
                            "left_wrist": hands.multi_hand_landmarks[0].landmark[0],
                            "right_wrist": hands.multi_hand_landmarks[1].landmark[0],
                            "finger": hands.multi_hand_landmarks[0].landmark[12],
                            "face": faces.multi_face_landmarks[0].landmark[1],
                        }[target]
                        setattr(landmark, axis, invalid)
                        self.assertIsNone(reset.reset_sample(hands, faces))

    def test_missing_coordinate_attributes_are_rejected(self):
        hands, faces = observations()
        hands.multi_hand_landmarks[0].landmark[8] = Object(y=0.5)
        self.assertIsNone(reset.reset_sample(hands, faces))

    def test_tiny_or_collapsed_hand_is_rejected(self):
        for size in (0.0, 0.0249):
            with self.subTest(size=size):
                hands, faces = observations()
                hands.multi_hand_landmarks[0].landmark[9] = point(0.3, 0.65 - size)
                self.assertIsNone(reset.reset_sample(hands, faces))

    def test_wrist_separation_too_small_is_rejected(self):
        hands, faces = observations()
        hands.multi_hand_landmarks[1] = hand(wrist=(0.41, 0.65))
        self.assertIsNone(reset.reset_sample(hands, faces))

    def test_wrist_too_far_from_face_is_rejected(self):
        hands, faces = observations()
        faces.multi_face_landmarks[0].landmark[1] = point(0.0, 0.0)
        self.assertIsNone(reset.reset_sample(hands, faces))

    def test_four_extended_fingers_with_closed_thumb_is_not_palm(self):
        hands, faces = observations("palm", "palm")
        hands.multi_hand_landmarks[0].landmark[4] = point(0.3, 0.6)
        self.assertEqual(reset.reset_sample(hands, faces).left, "other")

    def test_folded_fingers_with_extended_thumb_is_not_fist(self):
        hands, faces = observations()
        hands.multi_hand_landmarks[0].landmark[4] = point(0.20, 0.55)
        self.assertEqual(reset.reset_sample(hands, faces).left, "other")

    def test_both_thumbs_up_then_palms_do_not_trigger(self):
        detector = reset.TwoHandReset()
        hands, faces = observations()
        hands.multi_hand_landmarks[0].landmark[4] = point(0.20, 0.55)
        hands.multi_hand_landmarks[1].landmark[4] = point(0.60, 0.55)
        thumbs_up = reset.reset_sample(hands, faces)
        self.assertIsNotNone(thumbs_up)
        self.assertEqual((thumbs_up.left, thumbs_up.right), ("other", "other"))
        for now in (0.0, 0.1, 0.2, 0.3, 0.35):
            self.assertFalse(detector.update(thumbs_up, now))
        palms = reset.reset_sample(*observations("palm", "palm"))
        self.assertFalse(detector.update(palms, 0.4))
        self.assertFalse(detector.update(palms, 0.52))

    def test_one_curled_finger_is_not_full_palm(self):
        hands, faces = observations("palm", "palm")
        hands.multi_hand_landmarks[0].landmark[12] = point(0.28, 0.62)
        self.assertEqual(reset.reset_sample(hands, faces).left, "other")

    def test_valid_observations_drive_complete_gesture(self):
        detector = reset.TwoHandReset()
        fists = reset.reset_sample(*observations())
        palms = reset.reset_sample(*observations("palm", "palm"))
        self.assertIsNotNone(fists)
        self.assertIsNotNone(palms)
        for now in (0.0, 0.1, 0.2, 0.3, 0.35):
            self.assertFalse(detector.update(fists, now))
        self.assertFalse(detector.update(palms, 0.4))
        self.assertTrue(detector.update(palms, 0.52))

    def test_vertically_separated_hands_with_equal_x_can_trigger(self):
        detector = reset.TwoHandReset()
        decoded = {}
        for shape in ("fist", "palm"):
            hands, faces = observations(shape, shape)
            hands.multi_hand_landmarks = [hand(shape, (0.5, 0.35)), hand(shape, (0.5, 0.65))]
            decoded[shape] = reset.reset_sample(hands, faces)
            self.assertIsNotNone(decoded[shape])
            self.assertEqual((decoded[shape].left, decoded[shape].right), (shape, shape))
        for now in (0.0, 0.1, 0.2, 0.3, 0.35):
            self.assertFalse(detector.update(decoded["fist"], now))
        self.assertFalse(detector.update(decoded["palm"], 0.4))
        self.assertTrue(detector.update(decoded["palm"], 0.52))

    def test_invalid_observation_breaks_otherwise_valid_gesture(self):
        detector = reset.TwoHandReset()
        fists = reset.reset_sample(*observations())
        for now in (0.0, 0.1, 0.2, 0.3, 0.35):
            self.assertFalse(detector.update(fists, now))
        hands, faces = observations()
        hands.multi_handedness[1] = label("Left")
        self.assertFalse(detector.update(reset.reset_sample(hands, faces), 0.36))
        palms = reset.reset_sample(*observations("palm", "palm"))
        self.assertFalse(detector.update(palms, 0.4))
        self.assertFalse(detector.update(palms, 0.52))


if __name__ == "__main__":
    unittest.main()
