import unittest
import test_grid_launch


class SpiderLaunchTests(unittest.TestCase):
    run_launcher = test_grid_launch.GridLaunchTests.run_launcher

    def test_spider_uses_isolated_shared_camera_profile(self):
        result = self.run_launcher(["--audience", "--scene", "spider", "--duration-minutes", "30"])
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        config = result["observed"]["config"]
        self.assertEqual(config["PRODUCTION_SCENES"], ["spider_cursor_acer.py"])
        self.assertTrue(config["SHARED_CAMERA_ENABLED"])
        self.assertEqual(config["PRELOAD_COUNT"], 0)
        self.assertFalse(config["TRANSITION_ENABLED"])
        self.assertFalse(config["CLAP_MONITOR_ENABLED"])
        self.assertEqual(config["DISPLAY_TARGET"], "audience")

    def test_spider_preflight_does_not_launch_manager(self):
        result = self.run_launcher(["--audience", "--scene", "spider", "--check"])
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        self.assertEqual(result["observed"], {})
        self.assertFalse(result["report"]["physical_camera_tested"])

    def test_spider_missing_camera_dependency_prevents_launch(self):
        result = self.run_launcher(["--audience", "--scene", "spider"], missing_modules=("cv2",))
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["observed"], {})
