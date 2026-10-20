"""Six-hand Otedama contracts with synthetic landmarks and real SDL rendering.

Camera access and MediaPipe inference are replaced at their native boundaries.
Pygame, OpenCV, NumPy, the collision code, and the shared overlay remain real.
No physical camera or visible window is opened and sys.modules is not changed.
"""

from contextlib import ExitStack
import math
import os
from types import SimpleNamespace
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import cv2
import numpy as np
import pygame

from hand_focus_overlay import CYAN
import modern_otedama


CENTERS = ((160, 260), (640, 260), (1120, 260),
           (160, 540), (640, 540), (1120, 540))
LABELS = ("Left", "Left", "Left", "Right", "Right", "Right")


def hand_at(x, y):
    """Small separated hands with wrist/MCP midpoint exactly at the input."""
    offsets = ((0, .03), (-.015, .02), (-.025, .01), (-.035, 0), (-.045, -.01),
               (-.018, -.015), (-.018, -.035), (-.018, -.05), (-.018, -.065),
               (0, -.03), (0, -.045), (0, -.065), (0, -.08),
               (.018, -.015), (.02, -.035), (.022, -.05), (.024, -.065),
               (.03, 0), (.035, -.015), (.04, -.03), (.045, -.045))
    return SimpleNamespace(landmark=[
        SimpleNamespace(x=x / modern_otedama.WINDOW_WIDTH + dx,
                        y=y / modern_otedama.WINDOW_HEIGHT + dy, z=0.)
        for dx, dy in offsets
    ])


def result_for(hands, labels=LABELS):
    return SimpleNamespace(
        multi_hand_landmarks=list(hands),
        multi_handedness=[SimpleNamespace(classification=[SimpleNamespace(label=label, score=.99)])
                         for label in labels[:len(hands)]],
    )


class OtedamaMultiHandTests(unittest.TestCase):
    def setUp(self):
        patches = ExitStack()
        self.addCleanup(patches.close)
        self.cap = mock.Mock(last_read_frame_id=None)
        self.cap.isOpened.return_value = True
        self.frame = np.zeros((180, 320, 3), dtype=np.uint8)
        self.cap.read.return_value = (True, self.frame)
        self.detector = mock.Mock()
        self.detector.process.return_value = result_for([])
        size = (modern_otedama.WINDOW_WIDTH, modern_otedama.WINDOW_HEIGHT)
        self.open_camera = patches.enter_context(mock.patch.object(
            modern_otedama.display_utils, "open_camera", return_value=self.cap))
        patches.enter_context(mock.patch.object(
            modern_otedama.display_utils, "setup_pygame_scaled_fullscreen",
            return_value=(pygame.Surface(size), pygame.Surface(size), None)))
        patches.enter_context(mock.patch.object(modern_otedama.display_utils, "present_pygame_scaled"))
        patches.enter_context(mock.patch.object(modern_otedama, "notify_first_frame"))
        self.factory = patches.enter_context(mock.patch.object(
            modern_otedama.mp.solutions.hands, "Hands", return_value=self.detector))
        self.game = modern_otedama.ModernOtedamaGame()
        self.addCleanup(self.game.cleanup)
        self.hands = [hand_at(x, y) for x, y in CENTERS]

    def detect(self, hands):
        self.detector.process.return_value = result_for(hands)
        self.game.process_hands(self.frame)

    def ball_above(self, collider):
        x, y = collider["pos"]
        ball = modern_otedama.Otedama(x, y)
        ball.y -= collider["radius"] + ball.radius - 4
        ball.vx, ball.vy = 0., 6.
        return ball

    def test_detector_capacity_is_six_and_camera_is_attached_only_once(self):
        self.assertEqual(modern_otedama.MAX_HANDS, 6)
        self.assertEqual(self.factory.call_args.kwargs["max_num_hands"], 6)
        self.factory.assert_called_once()
        self.detect(self.hands)
        self.game.update(1 / 60)
        self.open_camera.assert_called_once_with()
        self.cap.set.assert_not_called()
        self.cap.read.assert_called_once_with()

    def test_zero_through_six_hands_all_have_colliders_and_visible_palm_markers(self):
        for count in (*range(7), 0):
            with self.subTest(count=count):
                self.detect(self.hands[:count])
                self.assertEqual(len(self.game.hand_colliders), count)
                self.assertEqual([id(hand["landmarks"]) for hand in self.game.hand_colliders],
                                 [id(hand) for hand in self.hands[:count]])
                self.game.draw()
                for index, hand in enumerate(self.hands):
                    x = int((hand.landmark[0].x + hand.landmark[9].x) / 2 * modern_otedama.WINDOW_WIDTH)
                    y = int((hand.landmark[0].y + hand.landmark[9].y) / 2 * modern_otedama.WINDOW_HEIGHT)
                    color = tuple(self.game.screen.get_at((x + 7, y)))[:3]
                    self.assertEqual(color, CYAN if index < count else modern_otedama.COLOR_BG_DARK,
                                     f"hand {index + 1} at detection count {count}")

    def test_each_of_six_separated_hands_bounces_a_ball_independently(self):
        self.detect(self.hands)
        for index, collider in enumerate(self.game.hand_colliders):
            with self.subTest(hand=index + 1), mock.patch.object(modern_otedama.random, "uniform", return_value=0.):
                ball = self.ball_above(collider)
                previous_particles = len(self.game.particles)
                self.assertTrue(self.game.check_hand_collision(ball))
                self.assertLess(ball.vy, 0)
                self.assertEqual(len(self.game.particles), previous_particles + 20)
                self.assertLessEqual(math.hypot(ball.vx, ball.vy), modern_otedama.MAX_SPEED)

    def test_zero_through_six_hands_need_no_start_button(self):
        for count in range(7):
            with self.subTest(hands=count):
                self.detector.process.return_value = result_for(self.hands[:count])
                self.game.refill_balls()
                self.game.update(1 / 60)
                self.assertFalse(hasattr(self.game, 'start_button'))
                self.assertEqual(len(self.game.hand_colliders), count)
                self.assertEqual(len(self.game.balls), 1)
        self.open_camera.assert_called_once_with()

    def test_three_repeated_left_and_right_labels_do_not_overwrite_hands(self):
        self.detect(self.hands)
        labels = [entry.classification[0].label
                  for entry in self.detector.process.return_value.multi_handedness]
        self.assertEqual(labels, list(LABELS))
        self.assertEqual(len(self.game.hand_colliders), 6)
        self.assertEqual(len({hand["pos"] for hand in self.game.hand_colliders}), 6)
        self.assertEqual({id(hand["landmarks"]) for hand in self.game.hand_colliders},
                         {id(hand) for hand in self.hands})

    def test_reordering_nonoverlapping_hands_does_not_create_velocity_artifacts(self):
        self.detect(self.hands)
        target = self.game.hand_colliders[5].copy()
        outcomes = []
        orders = (self.hands, self.hands[::-1], self.hands[2:] + self.hands[:2])
        for order in orders:
            self.detect(order)
            with mock.patch.object(modern_otedama.random, "uniform", return_value=0.):
                ball = self.ball_above(target)
                self.assertTrue(self.game.check_hand_collision(ball))
                outcomes.append((ball.x, ball.y, ball.vx, ball.vy))
        for outcome in outcomes[1:]:
            np.testing.assert_allclose(outcome, outcomes[0], rtol=0, atol=1e-9)

    def test_hand_loss_and_reentry_remove_old_colliders_and_old_markers(self):
        self.detect(self.hands)
        old_colliders = [hand.copy() for hand in self.game.hand_colliders]
        self.game.draw()
        moved_hands = [hand_at(x + 90, y) for x, y in CENTERS]
        for hands in ([], moved_hands):
            with self.subTest(phase="lost" if not hands else "reentered"):
                self.detect(hands)
                self.assertEqual(len(self.game.hand_colliders), len(hands))
                self.game.draw()
                for collider in old_colliders:
                    ball = self.ball_above(collider)
                    before = ball.x, ball.y, ball.vx, ball.vy
                    self.assertFalse(self.game.check_hand_collision(ball))
                    self.assertEqual((ball.x, ball.y, ball.vx, ball.vy), before)
                    x, y = collider["pos"]
                    self.assertEqual(tuple(self.game.screen.get_at((x + 7, y)))[:3],
                                     modern_otedama.COLOR_BG_DARK)
        for collider in self.game.hand_colliders:
            ball = self.ball_above(collider)
            self.assertTrue(self.game.check_hand_collision(ball))
            self.assertLess(ball.vy, 0)
            x, y = collider["pos"]
            self.assertEqual(tuple(self.game.screen.get_at((x + 7, y)))[:3], CYAN)

    def test_six_overlapping_hands_keep_motion_finite_and_score_once_per_ball_frame(self):
        self.detector.process.return_value = result_for([
            hand_at(640 + offset, 500) for offset in (-18, -12, -6, 6, 12, 18)
        ])
        self.game.refill_balls()
        self.game._start_frame_pending = False
        ball = self.game.balls[0]
        ball.x, ball.y, ball.vx, ball.vy = 640., 450., 0., 6.
        with mock.patch.object(modern_otedama.random, "uniform", return_value=0.):
            self.game.update(1 / 60)
        self.assertEqual(len(self.game.hand_colliders), 6)
        self.assertTrue(all(math.isfinite(value) for value in (ball.x, ball.y, ball.vx, ball.vy)))
        self.assertLessEqual(math.hypot(ball.vx, ball.vy), modern_otedama.MAX_SPEED)
        self.assertGreaterEqual(len(self.game.particles), 20)
        self.assertEqual(self.game.combo, 2)
        self.assertEqual(self.game.score, 200)


if __name__ == "__main__":
    unittest.main()
