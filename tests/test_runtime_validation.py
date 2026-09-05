import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())
import manager


class RuntimeValidationTests(unittest.TestCase):
    def test_launch_log_failure_keeps_process_reference_when_cleanup_fails(self):
        diagnostics = mock.Mock()
        diagnostics.record.side_effect = PermissionError("log is not writable")
        scene_manager = manager.SceneManager(scenes=["fixture_acer.py"], diagnostics=diagnostics)
        process = mock.Mock()
        with (mock.patch.object(manager.subprocess, "Popen", return_value=process),
              mock.patch.object(manager, "WindowsSceneJob"),
              mock.patch.object(scene_manager, "_kill_process", return_value=False)):
            with self.assertRaises(PermissionError):
                scene_manager._spawn_process([sys.executable, "fixture_acer.py"], ".")
        self.assertIs(scene_manager.uncontained_process, process)
        self.assertIsNotNone(scene_manager.fatal_error)

    def test_misspelled_trial_option_is_not_silently_ignored(self):
        with (mock.patch.object(sys, "argv", ["manager.py", "--duratoin-seconds", "1800"]),
              mock.patch.object(manager, "SharedCameraRelay") as relay,
              mock.patch.object(sys, "stderr")):
            with self.assertRaises(SystemExit) as caught:
                manager.main()
        self.assertEqual(caught.exception.code, 2)
        relay.assert_not_called()

    def test_invalid_operational_config_is_rejected_before_allocation(self):
        for config in ([], {"CAMERA_WIDTH": -1}, {"CAMERA_FPS": 0},
                       {"CAMERA_EXPOSURE": float("nan")}, {"CAMERA_EXPOSURE": True},
                       {"CAMERA_EXPOSURE": -14},
                       {"SCENE_FIRST_FRAME_TIMEOUT": float("nan")},
                       {"SHARED_CAMERA_ENABLED": False}, {"CAMERA_BACKEND": "dshwo"}):
            with self.subTest(config=config), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.json"
                path.write_text(json.dumps(config), encoding="utf-8")
                with self.assertRaises(manager.ConfigurationError):
                    manager.load_config(path)

    def test_missing_source_and_wrong_profile_do_not_pass_entrypoint_validation(self):
        for source, profile in (("__missing_body__.py", "acer"), ("finger_colorfull_dots_2.py", "acerr")):
            with self.subTest(source=source, profile=profile), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "candidate_acer.py"
                path.write_text(f'from scene_profile_runner import run_scene\n'
                                f'run_scene("{source}", profile="{profile}")\n', encoding="utf-8")
                config = dict(manager.DEFAULT_CONFIG, SCENE_DIR=directory, PRODUCTION_SCENES=[path.name])
                with self.assertRaises(manager.ConfigurationError):
                    manager.resolve_production_scenes(config)

    def test_manager_geometry_is_not_overridden_by_acer_profile_default(self):
        config = dict(manager.DEFAULT_CONFIG, DISPLAY_X=1920, DISPLAY_Y=0, DISPLAY_WIDTH=1360, DISPLAY_HEIGHT=800)
        with mock.patch.object(manager, "CONFIG", config):
            scene_manager = manager.SceneManager(scenes=["fixture_acer.py"])
            self.assertEqual(scene_manager._scene_env()["KIDZDISCO_DISPLAY_TARGET"], "stage")

    def test_missing_mediapipe_sets_monitor_failure_status(self):
        monitor = manager.HeadClapMonitor(frame_source=mock.Mock())
        with mock.patch.dict(sys.modules, {"mediapipe": None}), mock.patch("builtins.print"):
            monitor._monitor_loop()
        self.assertEqual(monitor.status, "failed")


if __name__ == "__main__":
    unittest.main()
