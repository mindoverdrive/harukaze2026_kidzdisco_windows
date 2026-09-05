import sys
import time
from pathlib import Path
import unittest
from unittest import mock

sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())
import manager
from scene_control import SceneControlError


class SceneSwitchTests(unittest.TestCase):
    def prepared_manager(self):
        with mock.patch("builtins.print"):
            sm = manager.SceneManager(scenes=["next_acer.py"])
        old = mock.Mock()
        old.poll.return_value = None
        sm.running_process = old
        sm.current_scene_name = "old_acer.py"
        sm.running_scene_path = "old_acer.py"
        sm.preloaded_process = mock.Mock()
        sm.preloaded_process.poll.return_value = None
        sm.preloaded_control = mock.Mock()
        sm.preloaded_scene_name = "next_acer.py"
        sm.preloaded_scene_path = "next_acer.py"
        sm.switch_pending = True
        sm._kill_process = mock.Mock(return_value=True)
        return sm, old

    def test_first_frame_timeout_discards_only_candidate(self):
        sm, old = self.prepared_manager()
        candidate = sm.preloaded_process
        sm.preloaded_control.poll.side_effect = SceneControlError("FIRST_FRAME timeout")
        with mock.patch("builtins.print"):
            sm.tick()
        self.assertIs(sm.running_process, old)
        self.assertIsNone(sm.preloaded_process)
        self.assertIsNone(sm.fatal_error)
        self.assertFalse(sm.switch_pending)
        sm._kill_process.assert_called_once_with(candidate, "next_acer.py")

    def test_first_frame_from_another_camera_does_not_stop_current_scene(self):
        sm, old = self.prepared_manager()
        sm.camera_env = {"HARUKAZE_CAMERA_SHM": "expected"}
        sm.preloaded_control.poll.return_value = "FIRST_FRAME"
        sm.preloaded_control.first_frame = {"shm_name": "wrong"}
        with mock.patch("builtins.print"):
            sm.tick()
        self.assertIs(sm.running_process, old)
        self.assertIn("different shared camera", sm.last_switch_error)

    def test_first_frame_promotes_candidate_and_closes_control(self):
        sm, old = self.prepared_manager()
        candidate = sm.preloaded_process
        control = sm.preloaded_control
        control.poll.return_value = "FIRST_FRAME"
        sm.preload_enabled = False
        with mock.patch.dict(manager.CONFIG, {"TRANSITION_ENABLED": False}), mock.patch("builtins.print"):
            sm.tick()
        sm._kill_process.assert_called_once_with(old, "old_acer.py")
        self.assertIs(sm.running_process, candidate)
        self.assertFalse(sm.switch_pending)
        self.assertEqual(sm.scene_index, 1)
        control.close.assert_called_once_with()

    def test_real_manager_can_repeat_fixture_scene_switches(self):
        scene_path = str(Path(__file__).parent / "fixtures" / "handshake_scene_acer.py")
        with (
            mock.patch.dict(manager.CONFIG, {"TRANSITION_ENABLED": False, "SCENE_READY_TIMEOUT": 3}),
            mock.patch("builtins.print"),
        ):
            sm = manager.SceneManager(camera_env={"HARUKAZE_CAMERA_SHM": "fixture_camera"}, scenes=[scene_path])
            try:
                previous = None
                for _ in range(5):
                    self.assertTrue(sm.switch_scene())
                    deadline = time.monotonic() + 4
                    while sm.switch_pending and time.monotonic() < deadline:
                        sm.tick()
                        time.sleep(0.005)
                    self.assertIsNone(sm.last_switch_error)
                    self.assertFalse(sm.switch_pending)
                    self.assertTrue(sm.is_scene_running())
                    if previous is not None:
                        self.assertIsNotNone(previous.poll())
                    previous = sm.running_process
            finally:
                self.assertTrue(sm.cleanup())
            self.assertIsNone(sm.running_process)
            self.assertIsNone(sm.preloaded_process)

    def test_start_ack_does_not_stop_old_scene_before_first_frame(self):
        with mock.patch("builtins.print"):
            sm = manager.SceneManager(scenes=["next_acer.py"])
        old = mock.Mock()
        old.poll.return_value = None
        candidate = mock.Mock()
        candidate.poll.return_value = None
        sm.running_process = old
        sm.current_scene_name = "old_acer.py"
        sm.running_scene_path = "old_acer.py"
        sm.preloaded_process = candidate
        sm.preloaded_scene_name = "next_acer.py"
        sm.preloaded_scene_path = "next_acer.py"
        sm.preloaded_control = mock.Mock(state="START_ACK")
        sm.preloaded_control.poll.return_value = "START_ACK"
        sm._ensure_preloaded_scene = mock.Mock()
        sm._kill_process = mock.Mock(return_value=True)
        with (
            mock.patch.dict(manager.CONFIG, {"TRANSITION_ENABLED": False, "SCENE_PRELOAD_START_GRACE": 0, "SCENE_SWITCH_DELAY": 0}),
            mock.patch("builtins.print"),
        ):
            sm.switch_scene()
        self.assertIs(sm.running_process, old)
        sm._kill_process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
