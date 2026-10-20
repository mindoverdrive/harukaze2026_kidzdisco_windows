"""Actual color guidance on CPU images; no camera or GUI is opened."""
import random
import unittest

import numpy as np

from hand_drawing_app import HandInput
from hand_drawing_feedback import draw_color_guidance, layout_badges
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
                            round(height * (.50 if crowded else .38 + (i // 4) * .34))),
                           (i % 5 == 4, *(finger <= i % 5 + 1 for finger in range(1, 5))))
                 for i in range(8))


class HandDrawingFeedbackTests(unittest.TestCase):
    def test_eight_labels_fit_even_for_crowded_wrists_and_small_preview(self):
        for size in ((320, 240), (960, 540), (1280, 720), (1920, 1080)):
            for crowded in (False, True):
                with self.subTest(size=size, crowded=crowded):
                    placed = layout_badges(size, eight(size, crowded))
                    self.assertEqual(len(placed), 8)
                    rects = [rect for _, rect in placed]
                    excluded = [*navigation_regions(*size).values()]
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
        for hand, (x, y, bw, bh) in layout_badges(size, samples):
            pixels=image[y:y+bh,x:x+bw]
            for count,color in FINGER_COLORS_BGR.items():
                visible=np.count_nonzero(np.all(pixels==color,axis=2))
                self.assertGreater(visible,20) if count==hand.selected_count else self.assertEqual(visible,0)
        self.assertEqual(samples, before)

    def test_bottom_space_is_available_for_a_hand_badge(self):
        for size in ((320, 240), (1280, 720), (1920, 1080)):
            width, height = size
            sample = HandInput(1, 0, 'Right', None, 1, (width // 2, height - 30),
                               (False, True, False, False, False))
            with self.subTest(size=size):
                placed = layout_badges(size, (sample,))
                self.assertEqual(len(placed), 1)
                _, (x, y, bw, bh) = placed[0]
                self.assertGreater(y + bh, height - 25)
                self.assertLessEqual(x + bw, width)
                self.assertLessEqual(y + bh, height)

    def test_shape_badges_retain_their_actual_color_and_remove_technical_ids(self):
        from unittest.mock import patch
        import cv2
        from hand_shapes_app import CANONICAL_SHAPES
        size=(1280,720);samples=eight(size)
        image=np.zeros((720,1280,3),np.uint8)
        with patch('hand_drawing_feedback.cv2.putText',wraps=cv2.putText) as draw_text:
            draw_color_guidance(image,samples,shape_outlines=CANONICAL_SHAPES)
        self.assertFalse(any(str(call.args[1]).startswith('H') for call in draw_text.call_args_list))
        for hand,(x,y,w,h) in layout_badges(size,samples):
            self.assertGreater(np.count_nonzero(np.all(image[y:y+h,x:x+w]==FINGER_COLORS_BGR[hand.selected_count],axis=2)),10)

    def test_bottom_input_marker_remains_visible_with_nearby_badges_in_both_modes(self):
        from hand_shapes_app import CANONICAL_SHAPES
        for mode in (None,CANONICAL_SHAPES):
            image=np.full((720,1280,3),73,np.uint8)
            point=(640,670)
            sample=HandInput(1,0,'Right',point,2,point,(True,False,False,False,True))
            draw_color_guidance(image,(sample,),(point,),shape_outlines=mode)
            px,py=point
            self.assertTrue(np.all(image[py-20:py+20,px-20:px+20]==73))

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

    def test_missing_hands_leave_the_entire_image_unchanged_without_a_guide(self):
        from hand_shapes_app import CANONICAL_SHAPES
        for mode in (None, CANONICAL_SHAPES):
            with self.subTest(shape_mode=mode is not None):
                image = np.random.default_rng(18).integers(0, 256, (720, 1280, 3), dtype=np.uint8)
                before = image.copy()
                draw_color_guidance(image, (), shape_outlines=mode)
                np.testing.assert_array_equal(image, before)


if __name__ == '__main__':
    unittest.main()
