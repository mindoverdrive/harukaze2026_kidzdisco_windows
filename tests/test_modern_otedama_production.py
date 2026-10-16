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
