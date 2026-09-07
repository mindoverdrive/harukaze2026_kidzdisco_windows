import os
from pathlib import Path
import runpy
import unittest
from unittest import mock

import scene_profile_runner
import test_grid_launch


ROOT = Path(__file__).resolve().parents[1]


class WaveDotsLaunchTests(unittest.TestCase):
    run_launcher = test_grid_launch.GridLaunchTests.run_launcher

    def test_acer_entrypoint_runs_the_original_wave_scene(self):
        with mock.patch.object(scene_profile_runner, "run_scene") as run_scene:
            runpy.run_path(str(ROOT / "colorfull_wave_dots_acer.py"), run_name="__main__")
        run_scene.assert_called_once_with("colorfull_wave_dots.py", profile="acer")

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_trial_launch_uses_an_isolated_shared_camera_profile(self):
        result = self.run_launcher(
            ["--audience", "--scene", "wave-dots", "--duration-minutes", "2"],
            base_overrides={"CAMERA_EXPOSURE": -4, "CAMERA_ZOOM": 176},
        )
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        observed = result["observed"]
        self.assertTrue(observed["is_trial_profile"])
        config = observed["config"]
        self.assertEqual(config["PRODUCTION_SCENES"], ["colorfull_wave_dots_acer.py"])
        self.assertEqual((config["CAMERA_EXPOSURE"], config["CAMERA_ZOOM"]), (-4, 176))
        self.assertTrue(config["SHARED_CAMERA_ENABLED"])
        self.assertEqual(config["PRELOAD_COUNT"], 0)
        self.assertFalse(config["TRANSITION_ENABLED"])
        self.assertFalse(config["CLAP_MONITOR_ENABLED"])
        self.assertEqual(config["DISPLAY_TARGET"], "audience")
        self.assertEqual(config["DISPLAY_NAME"], r"\\.\DISPLAY5")
        self.assertNotIn("wgpu", result["imported_modules"])

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_preflight_does_not_open_the_camera_or_replace_saved_profiles(self):
        result = self.run_launcher(["--audience", "--scene", "wave-dots", "--check"])
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        self.assertEqual(result["observed"], {})
        self.assertEqual(result["report"]["failures"], [])
        self.assertFalse(result["report"]["physical_camera_tested"])
        profile = result["profiles"][result["report"]["config"]]
        self.assertEqual(profile["PRODUCTION_SCENES"], ["colorfull_wave_dots_acer.py"])


if __name__ == "__main__":
    unittest.main()
