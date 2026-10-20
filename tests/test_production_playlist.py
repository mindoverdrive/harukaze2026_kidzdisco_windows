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
    def test_matahari_playlist_excludes_jacket_and_keeps_the_other_scene_order(self):
        root = Path(__file__).resolve().parents[1]
        config = manager.load_config(root / "configs/rebirth_operator_acer_xiaomi.json")
        expected = [
            "fractal_moving_acer.py", "finger_mandala_acer.py",
            "colorfull_wave_dots_acer.py", "colorfull_tree_acer.py",
            "skeleton_glitch_acer.py", "particle_storm_acer.py",
            "colorfull_dots_spheres_acer.py", "finger_colorfull_dots_acer.py",
            "spider_cursor_acer.py", "finger_grid_interaction_acer.py",
            "saturn_particles_acer.py", "prism_skin_acer.py",
            "polygon_vibes_acer.py", "kaleidoscope_camera_acer.py",
            "polygon_face_acer.py", "living_mosaic_acer.py",
            "modern_otedama_acer.py", "earth_acer.py",
            "hand_drawing_acer.py", "hand_shapes_acer.py",
        ]
        self.assertEqual(config["PRODUCTION_SCENES"], expected)
        self.assertEqual([Path(p).name for p in manager.resolve_production_scenes(config)], expected)
        for source in ("sci_fi_jacket_acer.py", "sci_fi_jacket.py", "jacket_effect.py"):
            self.assertTrue((root / source).is_file(), source)

    def test_actual_matahari_playlist_is_shared_by_automatic_next_and_back(self):
        root = Path(__file__).resolve().parents[1]
        config = manager.load_config(root / "configs/rebirth_operator_acer_xiaomi.json")
        with mock.patch.object(manager, "CONFIG", config), mock.patch("builtins.print"):
            sm = manager.SceneManager()
        with (
            mock.patch.object(sm, "_start_transition_overlay"),
            mock.patch.object(sm, "_ensure_preloaded_scene", return_value=True),
            mock.patch.object(sm, "tick"),
        ):
            for index, current in enumerate(sm.all_scenes):
                sm.running_scene_path = current
                sm.scene_index = index + 1
                # Timed rotation invokes switch_scene(), which delegates NEXT.
                for automatic in (True, False):
                    sm.switch_pending = False
                    self.assertTrue(sm.switch_scene() if automatic else sm.request_scene("next"))
                    target = sm.all_scenes[sm.requested_scene_index]
                    self.assertEqual(target, sm.all_scenes[(index + 1) % len(sm.all_scenes)])
                    self.assertNotIn("sci_fi_jacket", target)
                sm.switch_pending = False
                self.assertTrue(sm.request_scene("back"))
                target = sm.all_scenes[sm.requested_scene_index]
                self.assertEqual(target, sm.all_scenes[(index - 1) % len(sm.all_scenes)])
                self.assertNotIn("sci_fi_jacket", target)
            sm.switch_pending = False
            with self.assertRaises(manager.ConfigurationError):
                sm.request_scene("select", "sci_fi_jacket_acer.py")

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
