import os
from types import SimpleNamespace
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import numpy as np
import pygame
import hand_focus_overlay as overlay


def synthetic_hand():
    coords = [(0.5, 0.8), (.43, .7), (.38, .6), (.32, .54), (.27, .48),
              (.44, .56), (.43, .43), (.42, .30), (.41, .18),
              (.50, .53), (.50, .37), (.50, .23), (.50, .10),
              (.56, .56), (.57, .42), (.58, .30), (.59, .20),
              (.62, .61), (.65, .51), (.68, .42), (.70, .34)]
    return SimpleNamespace(landmark=[SimpleNamespace(x=x, y=y, z=0.) for x, y in coords])


class HandFocusOverlayTests(unittest.TestCase):
    def test_worker_tuples_and_solutions_landmarks_use_identical_letterbox_coordinates(self):
        hand = synthetic_hand()
        frozen = tuple((p.x, p.y, p.z) for p in hand.landmark)
        layout = dict(offset_x=160, offset_y=0, scaled_width=960, scaled_height=720)
        points = overlay.stage_points(hand, (1280, 720), layout)
        self.assertEqual(points, overlay.stage_points(frozen, (1280, 720), layout))
        self.assertEqual(points[8], (round(160 + .41 * 959), round(.18 * 719)))

    def test_passive_bones_have_no_active_cyan_and_active_marker_survives_light_background(self):
        for background in ((2, 2, 4), (255, 255, 255)):
            with self.subTest(background=background):
                screen = pygame.Surface((1280, 720))
                screen.fill(background)
                hand = synthetic_hand()
                overlay.draw_pygame(screen, [hand])
                pixels = pygame.surfarray.array3d(screen)
                self.assertFalse(np.any(np.all(pixels == overlay.CYAN, axis=-1)))
                overlay.draw_pygame(screen, [hand], focus=(8,))
                x, y = overlay.stage_points(hand, screen.get_size())[8]
                self.assertEqual(tuple(screen.get_at((x + 7, y)))[:3], overlay.CYAN)
                self.assertEqual(tuple(screen.get_at((x + 16, y)))[:3], overlay.DARK)

    def test_explicit_active_point_and_palm_circle_match_game_inputs_in_both_renderers(self):
        hand = synthetic_hand()
        screen = pygame.Surface((1280, 720))
        screen.fill((0, 0, 0))
        frame = np.zeros((720, 1280, 3), np.uint8)
        kwargs = dict(active_points=((250, 200),), palm_focus=True,
                      palm_circles=((650, 500, 75),))
        overlay.draw_pygame(screen, [hand], **kwargs)
        overlay.draw_cv2(frame, [hand], **kwargs)
        for x, y in ((257, 200), (657, 500)):
            self.assertEqual(tuple(screen.get_at((x, y)))[:3], overlay.CYAN)
            # cv2 antialiasing blends a one-pixel ring; both must remain cyan dominant.
            blue, green, red = map(int, frame[y, x])
            self.assertGreater(min(blue, green), red + 100)
        # Rasterizers place the outside edge of a one-pixel ring one pixel apart.
        ring_rgb = pygame.surfarray.array3d(screen)[722:727, 499:502]
        self.assertTrue(np.any(np.all(ring_rgb == overlay.CYAN, axis=-1)))
        self.assertGreater(int(frame[500, 725, 1]), 150)

    def test_missing_frame_clears_cached_hands_and_forces_fresh_inference_on_recovery(self):
        import mediapipe as mp
        model = mock.Mock()
        hand = synthetic_hand()
        model.process.side_effect = [SimpleNamespace(multi_hand_landmarks=[hand]),
                                     SimpleNamespace(multi_hand_landmarks=None)]
        with mock.patch.object(mp.solutions.hands, "Hands", return_value=model):
            detector = overlay.PassiveHandDetector()
        frame = np.zeros((12, 16, 3), np.uint8)
        with mock.patch.object(overlay.time, "monotonic", side_effect=[1., 1.01, 1.02]):
            self.assertEqual(detector.detect(frame), (hand,))
            self.assertEqual(detector.detect(frame), (hand,))
            self.assertEqual(model.process.call_count, 1)
            self.assertEqual(detector.detect(None), ())
            self.assertEqual(detector.detect(frame), ())
        self.assertEqual(model.process.call_count, 2)
        detector.close()
        model.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
