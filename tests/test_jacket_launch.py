from pathlib import Path
import runpy
import unittest
from unittest import mock

import scene_profile_runner


class JacketLaunchTests(unittest.TestCase):
    def test_acer_wrapper_uses_the_shared_production_runner(self):
        with mock.patch.object(scene_profile_runner, "run_scene") as run_scene:
            runpy.run_path(str(Path(__file__).resolve().parents[1] / "sci_fi_jacket_acer.py"), run_name="__main__")
        run_scene.assert_called_once_with("sci_fi_jacket.py", profile="acer")


if __name__ == "__main__":
    unittest.main()
