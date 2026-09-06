import os
import unittest

import test_particle_storm_launch


class SaturnLaunchTests(unittest.TestCase):
    run_launcher = test_particle_storm_launch.ParticleStormLaunchTests.run_launcher
    run_particle = test_particle_storm_launch.ParticleStormLaunchTests.run_particle

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_saturn_launch_retains_shared_camera_and_single_audience_scene(self):
        result = self.run_particle(["--duration-minutes", "30"], scene="saturn")
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        observed = result["observed"]
        self.assertEqual(observed["config"]["PRODUCTION_SCENES"], ["saturn_particles_acer.py"])
        self.assertTrue(observed["config"]["SHARED_CAMERA_ENABLED"])
        self.assertEqual(observed["config"]["DISPLAY_NAME"], r"\\.\DISPLAY5")
        self.assertEqual(observed["config"]["PRELOAD_COUNT"], 0)
        self.assertFalse(observed["config"]["TRANSITION_ENABLED"])
        self.assertFalse(observed["config"]["CLAP_MONITOR_ENABLED"])
        self.assertEqual(observed["rendercanvas_backend"], "glfw")
        self.assertEqual(observed["argv"][observed["argv"].index("--duration-seconds") + 1], "1800.0")

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_saturn_preflight_does_not_start_manager_or_allocate_native_resources(self):
        result = self.run_particle(["--check"], scene="saturn")
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        self.assertEqual(result["observed"], {})
        self.assertFalse(result["report"]["gpu_device_tested"])
        self.assertFalse(result["report"]["model_asset"]["load_tested"])
        self.assertEqual(result["profiles"][result["report"]["config"]]["PRODUCTION_SCENES"],
                         ["saturn_particles_acer.py"])

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_saturn_missing_dependencies_or_model_cannot_reach_manager(self):
        for missing in ("wgpu", "pygfx", "rendercanvas.auto", "pylinalg",
                        "mediapipe.tasks.python.vision", "model"):
            with self.subTest(missing=missing):
                kwargs = {"model_bytes": None} if missing == "model" else {"missing_modules": (missing,)}
                result = self.run_particle(scene="saturn", **kwargs)
                self.assertEqual(result["exit_code"], 2)
                self.assertEqual(result["observed"], {})

    def test_saturn_requires_audience_and_local_operator(self):
        for arguments in (["--scene", "saturn"],
                          ["--audience", "--scene", "saturn", "--operator-host", "0.0.0.0"]):
            with self.subTest(arguments=arguments):
                result = self.run_launcher(arguments)
                self.assertEqual(result["exit_code"], 2)
                self.assertEqual(result["import_count"], 0)


if __name__ == "__main__":
    unittest.main()
