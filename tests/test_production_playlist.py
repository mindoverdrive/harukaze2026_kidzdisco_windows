import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())

import manager


class ProductionPlaylistTests(unittest.TestCase):
    def test_missing_or_empty_json_playlist_fails_before_camera_or_scene_allocation(self):
        for user_config in ({}, {"CAMERA_FPS": 30}, {"PRODUCTION_SCENES": None},
                            {"PRODUCTION_SCENES": []}):
            with self.subTest(config=user_config), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.json"
                path.write_text(json.dumps(user_config), encoding="utf-8")
                with (
                    mock.patch.object(manager, "CONFIG", dict(manager.CONFIG)),
                    mock.patch.object(sys, "argv", ["manager.py", "--config", str(path)]),
                    mock.patch.object(manager, "SharedCameraRelay", side_effect=AssertionError("camera allocation")) as relay,
                    mock.patch.object(manager, "SceneManager", side_effect=AssertionError("scene allocation")) as scenes,
                    mock.patch("builtins.print"),
                    mock.patch.object(sys, "stderr"),
                ):
                    result = manager.main()
                self.assertEqual(result, 2)
                relay.assert_not_called()
                scenes.assert_not_called()

    def test_json_playlist_preserves_only_the_explicit_scene_order(self):
        requested = ["spider_cursor_acer.py", "finger_colorfull_dots_acer.py"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"PRODUCTION_SCENES": requested}), encoding="utf-8")
            resolved = manager.resolve_production_scenes(manager.load_config(path))
        self.assertEqual([Path(scene).name for scene in resolved], requested)

    def test_manager_uses_only_explicit_production_entrypoints(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            approved = root / "approved_scene_acer.py"
            approved.write_text('from scene_profile_runner import run_scene\n'
                                'run_scene("finger_colorfull_dots_2.py", profile="acer")\n', encoding="utf-8")
            (root / "unapproved_scene_acer.py").write_text("# not selected\n", encoding="utf-8")
            (root / "helper.py").write_text("# not a scene\n", encoding="utf-8")

            config = dict(manager.DEFAULT_CONFIG)
            config.update(
                {
                    "SCENE_DIR": str(root),
                    "PRODUCTION_SCENES": [approved.name],
                }
            )

            with mock.patch.object(manager, "CONFIG", config):
                scene_manager = manager.SceneManager(camera_env={})

            self.assertEqual(scene_manager.all_scenes, [str(approved.resolve())])

    def test_invalid_production_entrypoints_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "valid_acer.py").write_text('run_scene("finger_colorfull_dots_2.py", profile="acer")\n', encoding="utf-8")

            invalid_playlists = [
                [],
                ["valid_acer.py", "valid_acer.py"],
                ["helper.py"],
                ["../outside_acer.py"],
                ["missing_acer.py"],
            ]
            for playlist in invalid_playlists:
                with self.subTest(playlist=playlist):
                    config = dict(manager.DEFAULT_CONFIG)
                    config.update(
                        {
                            "SCENE_DIR": str(root),
                            "PRODUCTION_SCENES": playlist,
                        }
                    )
                    with self.assertRaises(manager.ConfigurationError):
                        manager.resolve_production_scenes(config)

    def test_invalid_playlist_fails_before_camera_is_opened(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = dict(manager.DEFAULT_CONFIG)
            config.update(
                {
                    "SCENE_DIR": temp_dir,
                    "PRODUCTION_SCENES": ["missing_acer.py"],
                }
            )
            with (
                mock.patch.object(manager, "CONFIG", config),
                mock.patch.object(manager, "SharedCameraRelay") as relay_type,
                mock.patch.object(sys, "argv", ["manager.py"]),
            ):
                result = manager.main()

            self.assertEqual(result, 2)
            relay_type.assert_not_called()


if __name__ == "__main__":
    unittest.main()
