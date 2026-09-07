import os
import unittest

import test_grid_launch


class FractalLaunchTests(unittest.TestCase):
    run_launcher = test_grid_launch.GridLaunchTests.run_launcher

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_fractal_launch_uses_saved_controls_in_an_isolated_one_scene_profile(self):
        result = self.run_launcher(
            ["--audience", "--scene", "fractal", "--duration-minutes", "2"],
            base_overrides={"CAMERA_EXPOSURE": -4, "CAMERA_ZOOM": 176},
        )
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        observed = result["observed"]
        self.assertEqual(observed["entrypoint"], "manager.py")
        self.assertTrue(observed["is_trial_profile"])
        config = observed["config"]
        self.assertEqual(config["PRODUCTION_SCENES"], ["fractal_moving_acer.py"])
        self.assertEqual((config["CAMERA_EXPOSURE"], config["CAMERA_ZOOM"]), (-4, 176))
        self.assertTrue(config["SHARED_CAMERA_ENABLED"])
        self.assertEqual(config["PRELOAD_COUNT"], 0)
        self.assertFalse(config["TRANSITION_ENABLED"])
        self.assertFalse(config["CLAP_MONITOR_ENABLED"])
        self.assertEqual(config["DISPLAY_TARGET"], "audience")
        self.assertEqual(config["DISPLAY_NAME"], r"\\.\DISPLAY5")
        argv = observed["argv"]
        self.assertEqual(argv[argv.index("--duration-seconds") + 1], "120.0")
        self.assertEqual(argv[argv.index("--operator-host") + 1], "127.0.0.1")

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_preflight_selects_fractal_without_starting_manager_or_opening_devices(self):
        result = self.run_launcher(["--audience", "--scene", "fractal", "--check"])
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        self.assertEqual(result["observed"], {})
        report = result["report"]
        self.assertEqual(report["failures"], [])
        self.assertFalse(report["physical_camera_tested"])
        self.assertFalse(report["visual_tested"])
        self.assertEqual(result["profiles"][report["config"]]["PRODUCTION_SCENES"],
                         ["fractal_moving_acer.py"])
        self.assertNotIn("wgpu", result["imported_modules"])

    def test_missing_audience_or_nonlocal_operator_is_rejected_before_imports(self):
        cases = (
            (["--scene", "fractal"], "--scene fractal requires --audience"),
            (["--audience", "--scene", "fractal", "--operator-host", "0.0.0.0"],
             "--audience requires --operator-host 127.0.0.1"),
        )
        for arguments, expected_error in cases:
            with self.subTest(arguments=arguments):
                result = self.run_launcher(arguments)
                self.assertEqual(result["exit_code"], 2)
                self.assertIn(expected_error, result["stderr"])
                self.assertEqual(result["observed"], {})
                self.assertEqual(result["profiles"], {})
                self.assertIsNone(result["report"])
                self.assertEqual(result["import_count"], 0)

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_missing_display_prevents_manager_launch(self):
        result = self.run_launcher(["--audience", "--scene", "fractal"], audience_present=False)
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["observed"], {})
        self.assertTrue(any("DISPLAY5" in failure for failure in result["report"]["failures"]))

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_missing_camera_or_hand_tracking_dependency_prevents_manager_launch(self):
        for dependency in ("cv2", "mediapipe"):
            with self.subTest(dependency=dependency):
                result = self.run_launcher(["--audience", "--scene", "fractal"],
                                           missing_modules=(dependency,))
                self.assertEqual(result["exit_code"], 2)
                self.assertEqual(result["observed"], {})
                self.assertTrue(any(dependency in failure for failure in result["report"]["failures"]))


if __name__ == "__main__":
    unittest.main()
