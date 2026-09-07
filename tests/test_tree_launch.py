import os
from pathlib import Path
import runpy
import unittest
from unittest import mock

import scene_profile_runner
import test_grid_launch


ROOT = Path(__file__).resolve().parents[1]


class TreeLaunchTests(unittest.TestCase):
    run_launcher = test_grid_launch.GridLaunchTests.run_launcher

    def test_acer_entrypoint_runs_the_original_tree_scene(self):
        with mock.patch.object(scene_profile_runner, "run_scene") as run_scene:
            runpy.run_path(str(ROOT / "colorfull_tree_acer.py"), run_name="__main__")
        run_scene.assert_called_once_with("colorfull_tree.py", profile="acer")

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_tree_trial_is_isolated_and_uses_the_shared_camera(self):
        result = self.run_launcher(
            ["--audience", "--scene", "tree", "--duration-minutes", "2"],
            base_overrides={"CAMERA_EXPOSURE": -4, "CAMERA_ZOOM": 176},
        )
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        config = result["observed"]["config"]
        self.assertTrue(result["observed"]["is_trial_profile"])
        self.assertEqual(config["PRODUCTION_SCENES"], ["colorfull_tree_acer.py"])
        self.assertEqual((config["CAMERA_EXPOSURE"], config["CAMERA_ZOOM"]), (-4, 176))
        self.assertTrue(config["SHARED_CAMERA_ENABLED"])
        self.assertEqual(config["PRELOAD_COUNT"], 0)
        self.assertFalse(config["TRANSITION_ENABLED"])
        self.assertFalse(config["CLAP_MONITOR_ENABLED"])
        self.assertEqual(config["DISPLAY_TARGET"], "audience")
        self.assertEqual(config["DISPLAY_NAME"], r"\\.\DISPLAY5")
        self.assertNotIn("wgpu", result["imported_modules"])


if __name__ == "__main__":
    unittest.main()
