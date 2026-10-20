"""Detected finger combinations reach the visible hand badges, without a camera."""
from itertools import product
import random
import unittest
from unittest.mock import patch

import numpy as np

import display_utils
import hand_drawing_app as drawing
import hand_drawing_feedback as guidance
import hand_shapes_app as shapes
from hand_drawing_effects import FadingInk
from hand_drawing_gestures import FINGER_COLORS_BGR
from test_hand_drawing_app import FINGER_IDS, hand, results


SIZE = (960, 540)
LAYOUT = display_utils.get_uniform_layout(*SIZE, *SIZE)
FINGERS = tuple(FINGER_IDS)


def sample(mask, side='Right', **position):
    return hand(tuple(name for name, raised in zip(FINGERS, mask) if raised),
                handedness=side, **position)


def controller(mode, stable_seconds=0.):
    cls = drawing.DrawingInput if mode == 'drawing' else shapes.ShapeInput
    return cls(*SIZE, stable_seconds=stable_seconds, rng=random.Random(19))


def items(mode, frame):
    return frame.inputs if mode == 'drawing' else frame.shapes


class DetectedFingerFeedbackTests(unittest.TestCase):
    def test_all_finger_combinations_reach_the_correct_hand_in_both_scenes(self):
        for mode in ('drawing', 'shapes'):
            for side in ('Right', 'Left'):
                for mask in product((False, True), repeat=5):
                    with self.subTest(mode=mode, side=side, mask=mask):
                        frame = controller(mode).update(results((side, sample(mask, side))), LAYOUT, 0.)
                        output = items(mode, frame)
                        if mode == 'shapes' and not any(mask):
                            self.assertFalse(output)
                            continue
                        self.assertEqual(len(output), 1)
                        self.assertEqual(output[0].finger_mask, mask)
                        self.assertEqual(output[0].handedness, side)
                        self.assertEqual(output[0].selected_count, sum(mask) or 1)

    def test_live_mask_changes_before_the_stabilized_color_and_shape_count(self):
        first = (False, True, False, False, False)
        changed = (True, False, False, False, True)
        same_count = (False, False, True, True, False)
        for mode in ('drawing', 'shapes'):
            with self.subTest(mode=mode):
                control = controller(mode, .18)
                for now in (0., .1, .19):
                    initial = control.update(results(('Right', sample(first))), LAYOUT, now)
                initial_item = items(mode, initial)[0]
                for now in (.2, .3):
                    pending = control.update(results(('Right', sample(changed))), LAYOUT, now)
                    item = items(mode, pending)[0]
                    self.assertEqual(item.finger_mask, changed)
                    self.assertEqual(item.selected_count, 1)
                    self.assertEqual(item.track_id, initial_item.track_id)
                    if mode == 'shapes':
                        self.assertEqual(item.color_bgr, FINGER_COLORS_BGR[1])
                settled = control.update(results(('Right', sample(changed))), LAYOUT, .381)
                self.assertEqual(items(mode, settled)[0].selected_count, 2)
                replaced = control.update(results(('Right', sample(same_count))), LAYOUT, .4)
                self.assertEqual(items(mode, replaced)[0].finger_mask, same_count)
                self.assertEqual(items(mode, replaced)[0].selected_count, 2)
                self.assertEqual(items(mode, replaced)[0].track_id, initial_item.track_id)

    def test_fist_is_reported_immediately_while_previous_selection_is_held(self):
        raised = (False, True, False, False, False)
        fist = (False,) * 5
        for mode in ('drawing', 'shapes'):
            with self.subTest(mode=mode):
                control = controller(mode, .18)
                for now in (0., .1, .19):
                    control.update(results(('Left', sample(raised, 'Left'))), LAYOUT, now)
                pending = control.update(results(('Left', sample(fist, 'Left'))), LAYOUT, .2)
                self.assertEqual(items(mode, pending)[0].finger_mask, fist)
                self.assertEqual(items(mode, pending)[0].selected_count, 1)

    def test_eight_tracks_keep_their_masks_when_same_side_detections_reorder(self):
        masks = ((True, False, False, False, False),
                 (False, True, False, False, False),
                 (False, False, True, False, False),
                 (False, False, False, True, False),
                 (False, False, False, False, True),
                 (True, True, False, False, False),
                 (False, True, False, False, True),
                 (True, False, True, True, False))
        observations = [('Right', sample(mask, x=.11 + index % 4 * .24,
                                         y=.03 + index // 4 * .38))
                        for index, mask in enumerate(masks)]
        for mode in ('drawing', 'shapes'):
            with self.subTest(mode=mode):
                control = controller(mode)
                initial = control.update(results(*observations), LAYOUT, 0.)
                expected = {item.track_id: item.finger_mask for item in items(mode, initial)}
                self.assertEqual(len(expected), 8)
                reordered = control.update(results(*reversed(observations)), LAYOUT, .05)
                self.assertEqual({item.track_id: item.finger_mask for item in items(mode, reordered)}, expected)

    def test_both_renderers_pass_each_tracked_mask_to_guidance(self):
        masks = ((True, False, False, False, True), (False, True, True, False, False))
        observations = results(('Left', sample(masks[0], 'Left', x=.25)),
                               ('Right', sample(masks[1], 'Right', x=.7)))
        for mode, app in (('drawing', drawing), ('shapes', shapes)):
            with self.subTest(mode=mode):
                frame = controller(mode).update(observations, LAYOUT, 0.)
                expected = {item.track_id: item.finger_mask for item in items(mode, frame)}
                stage = np.zeros((SIZE[1], SIZE[0], 3), np.uint8)
                ink = FadingInk(*SIZE, 0., 3.)
                with patch.object(app, 'draw_color_guidance', wraps=guidance.draw_color_guidance) as render:
                    app.render_frame(stage, ink, frame, LAYOUT, 0.)
                actual = render.call_args.args[1]
                self.assertEqual({item.track_id: item.finger_mask for item in actual}, expected)


class FingerIconTests(unittest.TestCase):
    def icon(self, mask, side='Right'):
        image = np.zeros((100, 130, 3), np.uint8)
        guidance._hand_icon(image, (20, 10), mask, 2., FINGER_COLORS_BGR[2], side)
        return image

    def test_all_32_combinations_have_distinct_icons_even_when_the_count_matches(self):
        for side in ('Right', 'Left'):
            with self.subTest(side=side):
                icons = [self.icon(mask, side).tobytes() for mask in product((False, True), repeat=5)]
                self.assertEqual(len(set(icons)), 32)

    def test_left_hand_places_the_raised_thumb_on_the_opposite_side(self):
        mask = (True, False, False, False, False)
        means = {}
        for side in ('Right', 'Left'):
            image = self.icon(mask, side)
            ys, xs = np.nonzero(np.all(image == FINGER_COLORS_BGR[2], axis=2))
            self.assertGreater(len(xs), 0)
            means[side] = float(xs.mean())
        self.assertLess(means['Right'], means['Left'])

    def test_missing_or_incomplete_masks_draw_no_invented_hand(self):
        for mask in ((), (True,), (False,) * 4, (True,) * 6):
            with self.subTest(mask=mask):
                self.assertFalse(np.any(self.icon(mask)))

    def test_legacy_hand_input_defaults_to_no_finger_mask(self):
        item = drawing.HandInput(1, 0, 'Right', None, 4, (300, 300))
        self.assertEqual(item.finger_mask, ())


if __name__ == '__main__':
    unittest.main()
