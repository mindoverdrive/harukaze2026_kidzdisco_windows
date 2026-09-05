import signal
import sys
import unittest
from unittest import mock

sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())

import manager
import shared_camera


class CleanupTests(unittest.TestCase):
    def test_scene_manager_cleanup_continues_after_one_step_fails(self):
        scene_manager = manager.SceneManager.__new__(manager.SceneManager)
        transition_process = object()
        scene_manager.transition_process = transition_process
        scene_manager._discard_preloaded = mock.Mock(side_effect=RuntimeError("preload cleanup failed"))
        scene_manager.kill_current = mock.Mock()
        scene_manager._kill_process = mock.Mock()

        with mock.patch("builtins.print"):
            scene_manager.cleanup()

        scene_manager.kill_current.assert_called_once_with()
        scene_manager._kill_process.assert_called_once_with(
            transition_process,
            "sakura_transition",
        )

    def test_camera_start_failure_closes_allocated_relay(self):
        relay = shared_camera.SharedCameraRelay.__new__(shared_camera.SharedCameraRelay)
        relay.cap = None
        relay._create_capture = mock.Mock(return_value=None)
        relay.close = mock.Mock()
        relay.camera_index = 0

        with self.assertRaises(RuntimeError):
            relay.start()

        relay.close.assert_called_once_with()

    def test_manager_closes_relay_when_camera_start_raises(self):
        relay = mock.Mock()
        relay.start.side_effect = RuntimeError("camera failed")
        config = dict(manager.DEFAULT_CONFIG)
        config["PRODUCTION_SCENES"] = ["fixture_acer.py"]

        with (
            mock.patch.object(manager, "CONFIG", config),
            mock.patch.object(manager, "resolve_production_scenes", return_value=["fixture_acer.py"]),
            mock.patch.object(manager, "SharedCameraRelay", return_value=relay),
            mock.patch.object(sys, "argv", ["manager.py"]),
            mock.patch("builtins.print"),
        ):
            result = manager.main()

        self.assertEqual(result, 1)
        relay.close.assert_called_once_with()

    def test_manager_reports_incomplete_shutdown_with_nonzero_exit(self):
        relay = mock.Mock()
        relay.export_env.return_value = {}
        relay.close.return_value = False
        scene_manager = mock.Mock()
        scene_manager.is_scene_running.return_value = True
        scene_manager.cleanup.return_value = True
        scene_manager.fatal_error = None
        config = dict(manager.DEFAULT_CONFIG)
        config["CLAP_MONITOR_ENABLED"] = False

        with (
            mock.patch.object(manager, "CONFIG", config),
            mock.patch.object(manager, "resolve_production_scenes", return_value=["fixture_acer.py"]),
            mock.patch.object(manager, "SharedCameraRelay", return_value=relay),
            mock.patch.object(manager, "SceneManager", return_value=scene_manager),
            mock.patch.object(manager.cv2, "waitKey", return_value=ord("q")),
            mock.patch.object(sys, "argv", ["manager.py"]),
            mock.patch("builtins.print"),
        ):
            result = manager.main()

        self.assertEqual(result, 1)
        scene_manager.cleanup.assert_called_once_with()
        relay.close.assert_called_once_with()

    def test_scene_stop_requests_graceful_interrupt_before_terminate(self):
        process = mock.Mock()
        process.poll.side_effect = [None, 0]
        scene_manager = manager.SceneManager.__new__(manager.SceneManager)

        with (
            mock.patch.object(manager.os, "name", "nt"),
            mock.patch.dict(manager.CONFIG, {"SCENE_GRACEFUL_TIMEOUT": 0.1}),
            mock.patch("builtins.print"),
        ):
            scene_manager._kill_process(process, "fixture_acer.py")

        process.send_signal.assert_called_once_with(signal.CTRL_BREAK_EVENT)
        process.terminate.assert_not_called()

    def test_monitor_stop_reports_thread_that_did_not_exit(self):
        monitor = manager.HeadClapMonitor(frame_source=mock.Mock())
        monitor.thread = mock.Mock()
        monitor.thread.is_alive.return_value = True

        with mock.patch("builtins.print"):
            result = monitor.stop()

        self.assertIs(result, False)
        monitor.thread.join.assert_called_once_with(timeout=3)

    def test_switch_keeps_current_process_when_it_cannot_be_stopped(self):
        scene_manager = manager.SceneManager(scenes=["next_acer.py"])
        current_process = mock.Mock()
        current_process.poll.return_value = None
        preloaded_process = mock.Mock()
        scene_manager.running_process = current_process
        scene_manager.running_scene_path = "current_acer.py"
        scene_manager.current_scene_name = "current_acer.py"
        scene_manager.scene_index = 0
        scene_manager.all_scenes = ["next_acer.py"]
        scene_manager.preload_enabled = True
        scene_manager.preloaded_process = preloaded_process
        scene_manager.preloaded_scene_path = "next_acer.py"
        scene_manager.preloaded_scene_name = "next_acer.py"
        scene_manager.preloaded_control = mock.Mock()
        scene_manager.preloaded_control.poll.return_value = "FIRST_FRAME"
        scene_manager.transition_process = None
        scene_manager._ensure_preloaded_scene = mock.Mock()
        scene_manager._start_transition_overlay = mock.Mock(return_value=None)
        scene_manager._kill_process = mock.Mock(side_effect=[False, True])
        scene_manager.launch_scene = mock.Mock()

        with (
            mock.patch.dict(
                manager.CONFIG,
                {
                    "TRANSITION_ENABLED": False,
                },
            ),
            mock.patch("builtins.print"),
        ):
            result = scene_manager.switch_scene()

        self.assertFalse(result)
        self.assertIs(scene_manager.running_process, current_process)
        self.assertEqual(scene_manager.running_scene_path, "current_acer.py")
        self.assertIsNone(scene_manager.preloaded_process)
        scene_manager.launch_scene.assert_not_called()

    def test_cleanup_retains_transition_handle_when_force_stop_fails(self):
        scene_manager = manager.SceneManager.__new__(manager.SceneManager)
        transition_process = object()
        scene_manager.transition_process = transition_process
        scene_manager._discard_preloaded = mock.Mock(return_value=True)
        scene_manager.kill_current = mock.Mock(return_value=True)
        scene_manager._kill_process = mock.Mock(return_value=False)

        with mock.patch("builtins.print"):
            result = scene_manager.cleanup()

        self.assertFalse(result)
        self.assertIs(scene_manager.transition_process, transition_process)


if __name__ == "__main__":
    unittest.main()
