import os
from types import SimpleNamespace
import unittest
from unittest import mock

import test_grid_launch


class ParticleStormLaunchTests(unittest.TestCase):
    run_launcher = test_grid_launch.GridLaunchTests.run_launcher

    def run_particle(self, extra_arguments=(), *, missing_modules=(), model_bytes=b"x" * 4096,
                     customize=None, scene="particle-storm"):
        native_call = mock.Mock(side_effect=AssertionError("preflight must not allocate native resources"))
        canvas = mock.Mock(side_effect=native_call)
        canvas.__module__ = "rendercanvas.glfw"
        modules = {
            "mediapipe": SimpleNamespace(solutions=SimpleNamespace(hands=object()),
                                         Image=native_call, ImageFormat=SimpleNamespace(SRGB=object())),
            "wgpu": SimpleNamespace(gpu=SimpleNamespace(request_adapter_sync=native_call)),
            "pygfx": SimpleNamespace(renderers=SimpleNamespace(WgpuRenderer=native_call),
                                     PointsMaterial=native_call, Texture=native_call, Geometry=native_call),
            "rendercanvas.auto": SimpleNamespace(RenderCanvas=canvas,
                                                 loop=SimpleNamespace(run=native_call, stop=native_call)),
            "glfw": SimpleNamespace(set_window_pos=native_call, set_window_size=native_call,
                                    set_window_attrib=native_call),
            "pylinalg": SimpleNamespace(),
            "mediapipe.tasks.python": SimpleNamespace(BaseOptions=native_call),
            "mediapipe.tasks.python.vision": SimpleNamespace(
                HandLandmarkerOptions=native_call,
                HandLandmarker=SimpleNamespace(create_from_options=native_call),
                RunningMode=SimpleNamespace(VIDEO=object())),
        }
        for module in modules.values():
            module.__version__ = "fixture"
            module.__file__ = "fixture"
        if customize is not None:
            customize(modules)
        result = self.run_launcher(["--audience", "--scene", scene, *extra_arguments],
                                   extra_modules=modules, missing_modules=missing_modules,
                                   model_bytes=model_bytes)
        native_call.assert_not_called()
        canvas.assert_not_called()
        return result

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_particle_storm_checks_dependencies_and_passes_one_scene_profile_to_manager(self):
        result = self.run_particle(["--duration-minutes", "2"])
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        observed = result["observed"]
        self.assertEqual((observed["entrypoint"], observed["run_name"]), ("manager.py", "__main__"))
        self.assertTrue(observed["is_trial_profile"])
        config = observed["config"]
        self.assertEqual(config["PRODUCTION_SCENES"], ["particle_storm_acer.py"])
        self.assertTrue(config["SHARED_CAMERA_ENABLED"])
        self.assertEqual(config["DISPLAY_TARGET"], "audience")
        self.assertEqual(config["DISPLAY_NAME"], r"\\.\DISPLAY5")
        self.assertEqual(config["CONTROL_DISPLAY_NAME"], r"\\.\DISPLAY1")
        self.assertEqual(config["CAMERA_NAME_HINTS"], ["c922"])
        self.assertTrue(config["CAMERA_REQUIRE_NAME_MATCH"])
        self.assertFalse(config["CAMERA_ALLOW_FALLBACK"])
        self.assertEqual(config["PRELOAD_COUNT"], 0)
        self.assertFalse(config["TRANSITION_ENABLED"])
        self.assertFalse(config["CLAP_MONITOR_ENABLED"])
        self.assertEqual(observed["rendercanvas_backend"], "glfw")
        for module in ("wgpu", "pygfx", "rendercanvas.auto", "glfw", "pylinalg",
                       "mediapipe.tasks.python", "mediapipe.tasks.python.vision"):
            self.assertIn(module, result["report"]["loaded_modules"])

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_missing_or_truncated_hand_model_fails_before_manager(self):
        for contents in (None, b"truncated model"):
            with self.subTest(model=contents):
                result = self.run_particle(model_bytes=contents)
                self.assertEqual(result["exit_code"], 2)
                self.assertEqual(result["observed"], {})
                self.assertTrue(any("hand_landmarker.task" in failure
                                    for failure in result["report"]["failures"]))

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_installed_packages_without_required_scene_apis_cannot_reach_manager(self):
        for module_name, attribute in (
            ("mediapipe", "Image"), ("pygfx", "PointsMaterial"),
            ("rendercanvas.auto", "RenderCanvas"),
            ("mediapipe.tasks.python", "BaseOptions"),
            ("mediapipe.tasks.python.vision", "HandLandmarker"),
        ):
            with self.subTest(module=module_name, attribute=attribute):
                result = self.run_particle(customize=lambda modules: delattr(modules[module_name], attribute))
                self.assertEqual(result["exit_code"], 2)
                self.assertEqual(result["observed"], {})
                self.assertTrue(any(module_name in failure and attribute in failure
                                    for failure in result["report"]["failures"]))

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_non_glfw_canvas_cannot_bypass_audience_window_placement(self):
        result = self.run_particle(customize=lambda modules: setattr(
            modules["rendercanvas.auto"].RenderCanvas, "__module__", "rendercanvas.offscreen"))
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["observed"], {})
        self.assertTrue(any("GLFW" in failure for failure in result["report"]["failures"]))

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_each_missing_particle_dependency_fails_before_manager(self):
        for module in ("wgpu", "pygfx", "rendercanvas.auto", "glfw", "pylinalg",
                       "mediapipe.tasks.python", "mediapipe.tasks.python.vision"):
            with self.subTest(module=module):
                result = self.run_particle(missing_modules=(module,))
                self.assertEqual(result["exit_code"], 2)
                self.assertEqual(result["observed"], {})
                self.assertTrue(any(module in failure for failure in result["report"]["failures"]))

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_particle_preflight_leaves_gpu_model_and_camera_execution_unproven(self):
        result = self.run_particle(["--check"])
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        self.assertEqual(result["observed"], {})
        report = result["report"]
        self.assertEqual(report["failures"], [])
        self.assertFalse(report["physical_camera_tested"])
        self.assertFalse(report["visual_tested"])
        self.assertFalse(report["gpu_device_tested"])
        self.assertFalse(report["model_asset"]["load_tested"])
        self.assertEqual(result["profiles"][report["config"]]["PRODUCTION_SCENES"],
                         ["particle_storm_acer.py"])

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_existing_scenes_do_not_acquire_particle_dependencies(self):
        dependencies = ("wgpu", "pygfx", "rendercanvas.auto", "glfw", "pylinalg",
                        "mediapipe.tasks.python", "mediapipe.tasks.python.vision")
        for scene in ("dots", "spheres", "grid"):
            with self.subTest(scene=scene):
                result = self.run_particle(scene=scene, missing_modules=dependencies, model_bytes=None)
                self.assertEqual(result["exit_code"], 0, result["stderr"])
                self.assertTrue(set(dependencies).isdisjoint(result["imported_modules"]))

    def test_particle_requires_audience_and_local_operator_before_preflight(self):
        for arguments in (
            ["--scene", "particle-storm", "--check"],
            ["--audience", "--scene", "particle-storm", "--operator-host", "0.0.0.0"],
        ):
            with self.subTest(arguments=arguments):
                result = self.run_launcher(arguments)
                self.assertEqual(result["exit_code"], 2)
                self.assertEqual(result["import_count"], 0)
                self.assertIsNone(result["report"])
                self.assertEqual(result["observed"], {})


if __name__ == "__main__":
    unittest.main()
