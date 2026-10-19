"""Actual color guidance on CPU images; no camera or GUI is opened."""
import random
import unittest

import numpy as np

from hand_drawing_app import HandInput
from hand_drawing_feedback import draw_color_guidance, layout_badges, legend_rect, _scale
from hand_drawing_gestures import FINGER_COLORS_BGR
from transition_overlay import navigation_regions


def overlaps(a, b):
    return (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
            and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


def eight(size, crowded=False):
    width, height = size
    return tuple(HandInput(i + 1, i, 'Left' if i % 2 else 'Right',
                           None, i % 5 + 1,
                           (round(width * (.5 if crowded else .15 + (i % 4) * .23)),
                            round(height * (.50 if crowded else .38 + (i // 4) * .34))))
                 for i in range(8))


class HandDrawingFeedbackTests(unittest.TestCase):
    def test_eight_labels_fit_even_for_crowded_wrists_and_small_preview(self):
        for size in ((320, 240), (960, 540), (1280, 720), (1920, 1080)):
            for crowded in (False, True):
                with self.subTest(size=size, crowded=crowded):
                    placed = layout_badges(size, eight(size, crowded))
                    self.assertEqual(len(placed), 8)
                    rects = [rect for _, rect in placed]
                    excluded = [*navigation_regions(*size).values(), legend_rect(size)]
                    for index, rect in enumerate(rects):
                        x, y, width, height = rect
                        self.assertGreaterEqual(min(x, y), 0)
                        self.assertLessEqual(x + width, size[0])
                        self.assertLessEqual(y + height, size[1])
                        self.assertFalse(any(overlaps(rect, area) for area in excluded + rects[:index]))

    def test_detector_order_does_not_change_track_to_badge_correspondence(self):
        samples = list(eight((1280, 720), crowded=True))
        expected = layout_badges((1280, 720), samples)
        random.Random(53).shuffle(samples)
        self.assertEqual(layout_badges((1280, 720), samples), expected)

    def test_each_hand_chip_uses_its_own_stabilized_count_including_same_side_hands(self):
        size, samples = (1280, 720), eight((1280, 720))
        before = tuple(samples)
        image = np.zeros((size[1], size[0], 3), np.uint8)
        draw_color_guidance(image, samples)
        scale = _scale(size)
        for hand, (x, y, _, bh) in layout_badges(size, samples):
            pixel = tuple(image[y + bh // 2, x + round(15 * scale)])
            self.assertEqual(pixel, FINGER_COLORS_BGR[hand.selected_count])
        self.assertEqual(samples, before)

    def test_corner_key_uses_the_existing_one_to_five_palette_exactly(self):
        size = (1280, 720)
        image = np.zeros((size[1], size[0], 3), np.uint8)
        draw_color_guidance(image, ())
        x, y, _, _ = legend_rect(size)
        for index, color in enumerate(FINGER_COLORS_BGR.values()):
            self.assertEqual(tuple(image[y + 47, x + 12 + index * 70 + 45]), color)

    def test_navigation_and_active_input_markers_are_not_painted_over(self):
        size = (1280, 720)
        image = np.full((size[1], size[0], 3), 73, np.uint8)
        before = image.copy()
        points = ((640, 350), (280, 290))
        hands = list(eight(size, crowded=True))
        hands[0] = HandInput(1, 0, 'Left', None, 2, (70, 70))
        draw_color_guidance(image, hands, points)
        for x, y, width, height in navigation_regions(*size).values():
            np.testing.assert_array_equal(image[y:y + height, x:x + width],
                                          before[y:y + height, x:x + width])
        for x, y in points:
            np.testing.assert_array_equal(image[y - 18:y + 18, x - 18:x + 18],
                                          before[y - 18:y + 18, x - 18:x + 18])

    def test_missing_hands_leave_only_the_key_without_old_badges(self):
        image = np.zeros((720, 1280, 3), np.uint8)
        draw_color_guidance(image, ())
        self.assertFalse(np.any(image[:600]))
        self.assertTrue(np.any(image[600:]))


if __name__ == '__main__':
    unittest.main()
