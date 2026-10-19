"""Exercise ink lifetime, bounded work and the actual OpenCV dissolve pixels."""

from collections import deque
from dataclasses import FrozenInstanceError
import math
import unittest
from unittest import mock

import cv2
import numpy as np

from hand_drawing_effects import EFFECT_NAMES, FadingInk, MAX_WISP_SEGMENTS, WISPS_PER_SEGMENT


class FadingInkTests(unittest.TestCase):
    def test_hold_then_expire_at_exact_combined_lifetime(self):
        ink = FadingInk(320, 200)
        self.assertTrue(ink.add_segment((40, 100), (270, 100), (0, 180, 255), 10.))
        first = ink.render(10.).copy()
        np.testing.assert_array_equal(ink.render(13.5), first)
        ink.advance(16.49)
        self.assertEqual(len(ink.segments), 1)
        self.assertFalse(ink.render(16.5).any())
        self.assertFalse(ink.segments)

    def test_zero_length_and_subpixel_stationary_samples_do_not_accumulate(self):
        ink = FadingInk(100, 80)
        for index in range(500):
            self.assertFalse(ink.add_segment((20, 30), (20, 30), (0, 255, 255), index / 60))
            self.assertFalse(ink.add_segment((20, 30), (20.1, 30.1), (0, 255, 255), index / 60))
        self.assertFalse(ink.segments)
        self.assertTrue(ink.add_segment((20, 30), (21, 30), (0, 255, 255), 9.))

    def test_segment_cap_discards_oldest_and_no_per_frame_growth_occurs(self):
        ink = FadingInk(320, 200, max_segments=7)
        self.assertIsInstance(ink.segments, deque)
        for index in range(200):
            ink.add_segment((20, 50), (30, 50), (0, 255, 255), index / 100)
        self.assertEqual(len(ink.segments), 7)
        self.assertEqual(ink.segments.maxlen, 7)
        self.assertAlmostEqual(ink.segments[0].created_at, 1.93)
        ids = tuple(id(segment) for segment in ink.segments)
        for _ in range(20):
            ink.render(5.5)
        self.assertEqual(tuple(id(segment) for segment in ink.segments), ids)

    def test_clear_blanks_reused_output_and_starts_a_clean_session(self):
        ink = FadingInk(100, 80)
        ink.add_segment((10, 20), (80, 60), (20, 200, 255), 1.)
        output = ink.render(1.)
        self.assertTrue(output.any())
        ink.clear()
        self.assertFalse(output.any())
        self.assertFalse(ink.segments)
        self.assertIs(ink.render(2.), output)
        self.assertFalse(output.any())
        self.assertTrue(ink.add_segment((10, 20), (80, 60), (20, 200, 255), 2.))

    def test_dissolve_produces_lighter_drifting_pixels_and_fades_to_zero(self):
        ink = FadingInk(320, 200)
        ink.add_segment((40, 100), (270, 100), (0, 180, 255), 0.)
        held = ink.render(3.5).copy()
        dissolving = ink.render(5.).copy()
        late = ink.render(6.3).copy()
        self.assertLess(int(dissolving.sum()), int(held.sum()))
        self.assertLess(int(late.sum()), int(dissolving.sum()))
        # Original ink has no blue; the whiter wisps introduce blue pixels
        # away from the line. Uniform opacity fading could not pass this test.
        self.assertFalse(held[:, :, 0].any())
        self.assertGreater(np.count_nonzero(dissolving[:92, :, 0]), 5)
        # Gaps between fragments are visibly dimmer than neighboring ink.
        self.assertLess(int(dissolving[100, 116, 2]), int(dissolving[100, 80, 2]))
        self.assertFalse(ink.render(6.5).any())

    def test_same_age_matches_across_frame_rates_and_repeated_renders(self):
        slow, fast = FadingInk(240, 160), FadingInk(240, 160)
        for ink in (slow, fast):
            ink.add_segment((20, 80), (220, 80), (255, 80, 120), 0.)
        for frame in range(150):
            fast.render(frame / 30.)
        np.testing.assert_array_equal(slow.render(5.), fast.render(5.))
        expected = fast.render(5.).copy()
        np.testing.assert_array_equal(fast.render(5.), expected)

    def test_nonfinite_inputs_are_rejected_and_coordinates_colors_are_clamped(self):
        ink = FadingInk(100, 80)
        for bad in (float("nan"), float("inf"), float("-inf"), None):
            self.assertFalse(ink.add_segment((bad, 20), (80, 60), (0, 255, 255), 1.))
            self.assertFalse(ink.add_segment((10, 20), (80, 60), (bad, 255, 255), 1.))
            self.assertFalse(ink.add_segment((10, 20), (80, 60), (0, 255, 255), bad))
        self.assertTrue(ink.add_segment((-1e300, -10), (1e300, 1e300), (-30, 400, 40), 1.))
        segment = ink.segments[0]
        self.assertEqual((segment.start, segment.end), ((0, 0), (99, 79)))
        self.assertEqual(segment.color_bgr, (0, 255, 40))
        self.assertEqual(ink.render(1.).shape, (80, 100, 3))

    def test_advance_rejects_bad_time_and_old_sample_cannot_refresh_ink(self):
        ink = FadingInk(100, 80)
        ink.add_segment((10, 20), (80, 60), (0, 255, 255), 10.)
        self.assertFalse(ink.add_segment((10, 20), (80, 60), (0, 255, 255), 9.))
        with self.assertRaises(ValueError):
            ink.advance(float("nan"))
        with self.assertRaises(ValueError):
            ink.render(float("inf"))
        ink.advance(100.)
        self.assertFalse(ink.segments)
        self.assertFalse(ink.add_segment((10, 20), (80, 60), (0, 255, 255), 9.))

    def test_clock_rollback_does_not_rewind_the_fade(self):
        ink = FadingInk(100, 80)
        ink.add_segment((10, 20), (80, 60), (0, 255, 255), 0.)
        faded = ink.render(5.).copy()
        np.testing.assert_array_equal(ink.render(4.), faded)
        self.assertFalse(ink.render(6.5).any())
        self.assertFalse(ink.render(0.).any())

    def test_particle_work_is_bounded_without_allocating_particle_history(self):
        ink = FadingInk(320, 200, max_segments=720)
        for index in range(720):
            y = 40 + index % 100
            ink.add_segment((20, y), (290, y), (30, 210, 255), 0.)
        with mock.patch("hand_drawing_effects.cv2.circle", wraps=cv2.circle) as circle:
            ink.render(5.)
        self.assertGreater(circle.call_count, 0)
        self.assertLessEqual(circle.call_count, MAX_WISP_SEGMENTS * WISPS_PER_SEGMENT)
        self.assertEqual(len(ink.segments), 720)

    def test_constructor_rejects_invalid_dimensions_cap_or_lifetime(self):
        for kwargs in (dict(width=0), dict(height=-1), dict(width=10.5), dict(max_segments=0),
                       dict(hold_seconds=-1), dict(fade_seconds=0), dict(fade_seconds=float("inf"))):
            args = dict(width=100, height=80)
            args.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                FadingInk(**args)

    def test_effect_names_and_immutable_metadata_preserve_default_call(self):
        self.assertEqual(EFFECT_NAMES, ("Particles", "Smoke", "Drops", "Rise", "Swirl", "Wave", "Shards", "Wipe"))
        ink = FadingInk(320, 200)
        ink.add_segment((20, 80), (80, 80), (0, 180, 255), 0.)
        self.assertEqual((ink.segments[0].effect_id, ink.segments[0].track_id), (0, 0))
        ink.add_segment((90, 80), (150, 80), (0, 180, 255), 0., effect_id=5, track_id=12)
        segment = ink.segments[-1]
        self.assertEqual((segment.effect_id, segment.track_id), (5, 12))
        with self.assertRaises(FrozenInstanceError):
            segment.effect_id = 1
        ink.add_segment((160, 80), (220, 80), (0, 180, 255), 0., effect_id=2, track_id=12)
        self.assertEqual(segment.effect_id, 5)

    def test_invalid_effect_and_track_ids_do_not_mutate_history(self):
        ink = FadingInk(100, 80)
        for effect in (-1, 8, .5, 2., "1", None, True, float("nan"), float("inf")):
            with self.subTest(effect_id=effect):
                self.assertFalse(ink.add_segment((10, 10), (50, 40), (0, 255, 255), 0., effect_id=effect))
        for track in (-1, .5, 2., "1", None, True, float("nan"), float("inf")):
            with self.subTest(track_id=track):
                self.assertFalse(ink.add_segment((10, 10), (50, 40), (0, 255, 255), 0., track_id=track))
        self.assertFalse(ink.segments)

    def test_all_eight_dissolves_have_distinct_motion_and_same_exact_expiry(self):
        frames = []
        for effect_id in range(8):
            ink = FadingInk(320, 200)
            points = [(x, round(100 + 28 * math.sin(x / 35))) for x in range(30, 291, 10)]
            for a, b in zip(points, points[1:]):
                ink.add_segment(a, b, (0, 180, 255), 0., effect_id=effect_id, track_id=effect_id)
            held = ink.render(3.5).copy()
            middle = ink.render(5.).copy()
            self.assertTrue(middle.any(), EFFECT_NAMES[effect_id])
            self.assertLess(int(middle.sum()), int(held.sum()), EFFECT_NAMES[effect_id])
            frames.append(middle)
            self.assertFalse(ink.render(6.5).any(), EFFECT_NAMES[effect_id])
            self.assertFalse(ink.segments)
        for index, frame in enumerate(frames):
            for other_index, other in enumerate(frames[:index]):
                difference = np.count_nonzero(np.any(frame != other, axis=-1))
                self.assertGreater(difference, 100, (EFFECT_NAMES[index], EFFECT_NAMES[other_index]))

    def test_all_effects_are_frame_rate_independent_and_use_one_output_buffer(self):
        for effect in range(8):
            with self.subTest(effect_id=effect):
                slow, fast = FadingInk(120, 90), FadingInk(120, 90)
                for ink in (slow, fast):
                    ink.add_segment((20, 45), (100, 45), (180, 210, 40), 0., effect_id=effect)
                output = fast.render(0.)
                for frame in range(45):
                    self.assertIs(fast.render(frame / 10), output)
                np.testing.assert_array_equal(slow.render(5.), fast.render(5.))

    def test_round_robin_hands_share_one_history_and_fair_global_emission_budget(self):
        ink = FadingInk(320, 200, max_segments=1920)
        for serial in range(2300):
            y = 50 + serial % 80
            ink.add_segment((25, y), (285, y), (0, 220, 255), 0.,
                            effect_id=serial % 7, track_id=serial % 8)
        self.assertEqual(len(ink.segments), 1920)
        buffer_ids = (id(ink._ink), id(ink._output), id(ink._glow), id(ink._small), id(ink._blur))
        with mock.patch.object(ink, "_wisps", wraps=ink._wisps) as wisps:
            ink.render(5.)
        self.assertLessEqual(wisps.call_count, MAX_WISP_SEGMENTS)
        per_hand = {}
        for call in wisps.call_args_list:
            track = call.args[0].track_id
            per_hand[track] = per_hand.get(track, 0) + 1
        self.assertEqual(set(per_hand), set(range(8)))
        self.assertLessEqual(max(per_hand.values()) - min(per_hand.values()), 1)
        self.assertEqual(buffer_ids, (id(ink._ink), id(ink._output), id(ink._glow), id(ink._small), id(ink._blur)))
        self.assertEqual(len(ink.segments), 1920)
        ink.clear()
        self.assertFalse(ink.render(5.1).any())

    def test_swirl_stays_with_each_hands_own_artwork(self):
        ink = FadingInk(640, 320)
        ink.add_segment((50, 80), (110, 80), (0, 220, 255), 0., effect_id=4, track_id=0)
        ink.add_segment((500, 220), (560, 220), (0, 220, 255), 0., effect_id=4, track_id=1)
        image = ink.render(5.)
        self.assertTrue(image[:, :170].any())
        self.assertTrue(image[:, 450:].any())
        # A global-stage orbit would throw the lines into each other's space.
        self.assertFalse(image[:, 190:440].any())

    def test_wipe_has_a_steady_pale_front_and_erases_behind_it(self):
        ink = FadingInk(320, 200)
        ink.add_segment((30, 100), (290, 100), (0, 180, 255), 0., effect_id=7)
        image = ink.render(5.)
        self.assertFalse(image[:, :130].any())
        self.assertGreater(int(image[100, 161, 0]), 40)
        self.assertEqual(int(image[100, 240, 0]), 0)
        self.assertGreater(int(image[100, 240, 2]), 100)


if __name__ == "__main__":
    unittest.main()
