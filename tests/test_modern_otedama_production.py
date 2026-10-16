import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pygame

import manager
import modern_otedama


ROOT = Path(__file__).resolve().parents[1]


class ModernOtedamaProductionTests(unittest.TestCase):
    def test_speed_rises_gradually_and_stops_at_a_child_friendly_cap(self):
        speed = modern_otedama.gameplay_speed_multiplier
        self.assertEqual(speed(0), 1.0)
        self.assertAlmostEqual(speed(30), 1 + 1 / 6)
        self.assertAlmostEqual(speed(60), 1 + 1 / 3)
        self.assertEqual(speed(90), 1.5)
        self.assertEqual(speed(300), 1.5)

    def test_only_active_play_time_counts_and_replay_resets_speed(self):
        game = modern_otedama.ModernOtedamaGame.__new__(modern_otedama.ModernOtedamaGame)
        game.state = modern_otedama.STATE_TITLE
        game.play_elapsed_seconds = 0.0
        game._start_frame_pending = False
        self.assertEqual(game.advance_play_time(20), 0)
        game.reset_game()
        self.assertEqual(game.advance_play_time(1 / 60), 0)
        self.assertEqual(game.play_elapsed_seconds, 0)
        self.assertEqual(game.advance_play_time(1 / 60), 1 / 60)
        game.state = modern_otedama.STATE_GAMEOVER
        self.assertEqual(game.advance_play_time(20), 0)
        self.assertAlmostEqual(game.play_elapsed_seconds, 1 / 60)
        game.state = modern_otedama.STATE_PLAYING
        self.assertEqual(game.advance_play_time(20), 0)
        self.assertAlmostEqual(game.play_elapsed_seconds, 1 / 60)
        game.reset_game()
        self.assertEqual(modern_otedama.gameplay_speed_multiplier(game.play_elapsed_seconds), 1)

    def test_speed_progression_uses_seconds_at_different_frame_rates(self):
        factors = []
        for fps in (5, 10, 30, 60, 120):
            game = modern_otedama.ModernOtedamaGame.__new__(modern_otedama.ModernOtedamaGame)
            game.state = modern_otedama.STATE_PLAYING
            game.play_elapsed_seconds = 0.0
            game._start_frame_pending = False
            for _ in range(fps * 60):
                game.advance_play_time(1 / fps)
            factors.append(modern_otedama.gameplay_speed_multiplier(game.play_elapsed_seconds))
        for factor in factors:
            self.assertAlmostEqual(factor, 1 + 1 / 3, places=7)

    def test_all_substeps_check_collisions_after_first_hit_and_zero_time_does_not(self):
        game = modern_otedama.ModernOtedamaGame.__new__(modern_otedama.ModernOtedamaGame)
        game.check_hand_collision = mock.Mock(return_value=True)
        ball = modern_otedama.Otedama(640, 300)
        self.assertFalse(game.advance_ball(ball, 0, 1.5))
        game.check_hand_collision.assert_not_called()
        self.assertTrue(game.advance_ball(ball, 0.1, 1.5))
        self.assertEqual(game.check_hand_collision.call_count, 9)

    def test_camera_loss_clears_hands_and_freezes_play_until_fresh_interval(self):
        cap = mock.Mock()
        cap.isOpened.return_value = True
        cap.read.side_effect = [(False, None)] + [
            (True, np.zeros((18, 32, 3), dtype=np.uint8))] * 2
        hands = mock.Mock()
        hands.process.return_value = SimpleNamespace(multi_hand_landmarks=None)
        with (
            mock.patch.object(modern_otedama.display_utils, "open_camera", return_value=cap),
            mock.patch.object(modern_otedama.display_utils, "setup_pygame_scaled_fullscreen",
                              return_value=(pygame.Surface((1280, 720)), pygame.Surface((1280, 720)), None)),
            mock.patch.object(modern_otedama.mp.solutions.hands, "Hands", return_value=hands),
        ):
            game = modern_otedama.ModernOtedamaGame()
            try:
                game.reset_game()
                game._start_frame_pending = False
                game.hand_colliders = [{'pos': (640, 0), 'radius': 80}]
                game.update(1 / 60)
                self.assertEqual(game.hand_colliders, [])
                self.assertEqual(game.play_elapsed_seconds, 0)
                self.assertEqual(game.score, 0)
                self.assertEqual(game.balls[0].y, 0)
                game.update(0.2)
                self.assertEqual(game.play_elapsed_seconds, 0)
                self.assertEqual(game.balls[0].y, 0)
                game.update(1 / 60)
                self.assertAlmostEqual(game.play_elapsed_seconds, 1 / 60)
            finally:
                game.cleanup()

    def test_substeps_keep_ball_motion_and_hand_checks_consistent_across_frame_rates(self):
        positions = []
        checks = []
        for fps in (30, 60):
            ball = modern_otedama.Otedama(640, 100)
            ball.vx, ball.vy = 4.0, -6.0
            game = modern_otedama.ModernOtedamaGame.__new__(modern_otedama.ModernOtedamaGame)
            game.check_hand_collision = mock.Mock(return_value=False)
            for _ in range(fps // 2):
                game.advance_ball(ball, 1 / fps, 1.5)
            positions.append((ball.x, ball.y))
            checks.append(game.check_hand_collision.call_count)
        self.assertAlmostEqual(positions[0][0], positions[1][0], delta=2)
        self.assertAlmostEqual(positions[0][1], positions[1][1], delta=4)
        self.assertGreaterEqual(checks[0], 30)
        self.assertGreaterEqual(checks[1], 30)

    def test_production_playlist_registers_one_valid_otedama_entrypoint(self):
        config = manager.load_config(ROOT / "configs/rebirth_operator_acer_xiaomi.json")
        scenes = manager.resolve_production_scenes(config)
        names = [Path(scene).name for scene in scenes]
        self.assertEqual(names.count("modern_otedama_acer.py"), 1)
        self.assertEqual(len(names), 18)
        self.assertEqual(names[-1], "modern_otedama_acer.py")

    def test_missing_shared_camera_fails_without_retry_or_resource_leak(self):
        hands = mock.Mock()
        with (
            mock.patch.object(modern_otedama.display_utils, "open_camera", return_value=None) as open_camera,
            mock.patch.object(modern_otedama.display_utils, "setup_pygame_scaled_fullscreen",
                              return_value=(pygame.Surface((1280, 720)), pygame.Surface((1280, 720)), None)),
            mock.patch.object(modern_otedama.mp.solutions.hands, "Hands", return_value=hands),
        ):
            with self.assertRaisesRegex(RuntimeError, "shared camera"):
                modern_otedama.ModernOtedamaGame()

        open_camera.assert_called_once_with()
        hands.close.assert_called_once_with()

    def test_shared_camera_frame_is_presented_before_startup_ack_and_cleanup(self):
        cap = mock.Mock()
        cap.isOpened.return_value = True
        cap.read.return_value = (True, np.zeros((18, 32, 3), dtype=np.uint8))
        hands = mock.Mock()
        hands.process.return_value = SimpleNamespace(multi_hand_landmarks=None)
        events = []

        def presented(*_args):
            events.append("present")

        def acknowledged(camera, *, frame_processed):
            self.assertIs(camera, cap)
            self.assertTrue(frame_processed)
            events.append("first_frame")

        with (
            mock.patch.object(modern_otedama.display_utils, "open_camera", return_value=cap) as open_camera,
            mock.patch.object(modern_otedama.display_utils, "setup_pygame_scaled_fullscreen",
                              return_value=(pygame.Surface((1280, 720)), pygame.Surface((1280, 720)), None)),
            mock.patch.object(modern_otedama.display_utils, "present_pygame_scaled", side_effect=presented),
            mock.patch.object(modern_otedama.mp.solutions.hands, "Hands", return_value=hands),
            mock.patch.object(modern_otedama, "notify_first_frame", side_effect=acknowledged),
        ):
            game = modern_otedama.ModernOtedamaGame()
            with mock.patch.object(game, "handle_input", side_effect=[True, False]):
                game.run()

        open_camera.assert_called_once_with()
        self.assertEqual(events, ["present", "first_frame"])
        hands.close.assert_called_once_with()
        cap.release.assert_called_once_with()

    def test_escape_exits_without_reading_camera_and_releases_resources(self):
        cap = mock.Mock()
        cap.isOpened.return_value = True
        hands = mock.Mock()
        with (
            mock.patch.object(modern_otedama.display_utils, "open_camera", return_value=cap),
            mock.patch.object(modern_otedama.display_utils, "setup_pygame_scaled_fullscreen",
                              return_value=(pygame.Surface((1280, 720)), pygame.Surface((1280, 720)), None)),
            mock.patch.object(modern_otedama.mp.solutions.hands, "Hands", return_value=hands),
            mock.patch.object(modern_otedama.pygame.event, "get", return_value=[
                SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_ESCAPE)]),
            mock.patch.object(modern_otedama, "notify_exit_request") as exit_request,
        ):
            modern_otedama.ModernOtedamaGame().run()

        exit_request.assert_called_once_with("key_escape")
        cap.read.assert_not_called()
        hands.close.assert_called_once_with()
        cap.release.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
