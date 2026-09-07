import os
from types import SimpleNamespace
import unittest

import test_grid_launch


@unittest.skipUnless(os.name == "nt", "Windows audience profile")
class BodySceneLaunchTests(unittest.TestCase):
    run_launcher = test_grid_launch.GridLaunchTests.run_launcher

    def test_body_scenes_use_isolated_shared_camera_profiles(self):
        module = SimpleNamespace(__version__="fixture", __file__="fixture", solutions=SimpleNamespace(
            hands=object(), selfie_segmentation=object(), pose=object(), face_detection=object()))
        for scene, entry in (("jacket", "sci_fi_jacket_acer.py"), ("skeleton", "skeleton_glitch_acer.py")):
            with self.subTest(scene=scene):
                result = self.run_launcher(["--audience", "--scene", scene, "--duration-minutes", "30"],
                    extra_modules={"mediapipe": module})
                self.assertEqual(result["exit_code"], 0, result["report"])
                observed = result["observed"]
                self.assertTrue(observed["is_trial_profile"])
                self.assertEqual(observed["config"]["PRODUCTION_SCENES"], [entry])
                self.assertTrue(observed["config"]["SHARED_CAMERA_ENABLED"])
                self.assertFalse(observed["config"]["TRANSITION_ENABLED"])
                self.assertEqual(observed["config"]["PRELOAD_COUNT"], 0)
                self.assertIn("1800.0", observed["argv"])

    def test_missing_body_detector_stops_before_manager_or_camera(self):
        for scene in ("jacket", "skeleton"):
            with self.subTest(scene=scene):
                result = self.run_launcher(["--audience", "--scene", scene])
                self.assertEqual(result["exit_code"], 2)
                self.assertEqual(result["observed"], {})
                self.assertTrue(any("mediapipe.solutions" in item for item in result["report"]["failures"]))


if __name__ == "__main__":
    unittest.main()
