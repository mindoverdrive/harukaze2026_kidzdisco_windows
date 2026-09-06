import contextlib
import ctypes
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts import start_kids_test


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class GridLaunchTests(unittest.TestCase):
    """Exercise CLI selection and the configuration received by Manager."""

    def run_launcher(self, arguments, *, base_overrides=None, audience_present=True, prior_profile=None,
                     extra_modules=None, missing_modules=(), model_bytes=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            originals = {}
            for source in (PROJECT_ROOT / "configs").glob("*.json"):
                originals[source.name] = source.read_bytes()
                if source.name == "rebirth_acer_xiaomi.json" and base_overrides:
                    config = json.loads(originals[source.name])
                    config.update(base_overrides)
                    originals[source.name] = json.dumps(config).encode("utf-8")
                (root / "configs" / source.name).write_bytes(originals[source.name])
            production_original = (PROJECT_ROOT / "config.json").read_bytes()
            (root / "config.json").write_bytes(production_original)
            if prior_profile is not None:
                (root / "test_reports").mkdir()
                (root / "test_reports/kids_grid_profile_previous.json").write_text(
                    json.dumps(prior_profile), encoding="utf-8")
            if model_bytes is not None:
                (root / "models").mkdir()
                (root / "models/hand_landmarker.task").write_bytes(model_bytes)

            capture = mock.Mock(side_effect=AssertionError("camera must remain unopened"))
            window = mock.Mock(side_effect=AssertionError("window must remain unopened"))
            modules = {
                name: SimpleNamespace(__version__="fixture", __file__="fixture")
                for name in ("numpy", "cv2", "pygame", "mediapipe", "screeninfo", "pygrabber.dshow_graph")
            }
            modules["cv2"].VideoCapture = capture
            modules["pygame"].display = SimpleNamespace(set_mode=window)
            modules["pygame"].get_sdl_version = lambda: (2, 32, 10)
            modules["mediapipe"].solutions = SimpleNamespace(hands=object())
            modules.update(extra_modules or {})
            monitors = [
                SimpleNamespace(name=r"\\.\DISPLAY1", x=0, y=0, width=1920, height=1080, is_primary=True),
                SimpleNamespace(name=r"\\.\DISPLAY5", x=1920, y=0, width=1920, height=1080, is_primary=False),
            ]
            modules["screeninfo"].get_monitors = lambda: monitors if audience_present else monitors[:1]
            user32 = mock.MagicMock()
            user32.SetProcessDpiAwarenessContext.return_value = True
            user32.GetAwarenessFromDpiAwarenessContext.return_value = 2
            observed = {}
            stdout, stderr = io.StringIO(), io.StringIO()

            def import_module(name):
                if name in missing_modules:
                    raise ModuleNotFoundError(f"injected missing {name}")
                return modules[name]

            def manager_entry(path, *, run_name):
                argv = list(sys.argv)
                config_path = Path(argv[argv.index("--config") + 1])
                observed.update(
                    entrypoint=Path(path).name, run_name=run_name, argv=argv,
                    config=json.loads(config_path.read_text(encoding="utf-8")),
                    is_trial_profile=config_path.is_relative_to(root / "test_reports"),
                    rendercanvas_backend=os.environ.get("RENDERCANVAS_BACKEND"),
                )

            original_directory = Path.cwd()
            try:
                with (
                    mock.patch.object(start_kids_test, "ROOT", root),
                    mock.patch.object(sys, "argv", ["start_kids_test.py", *arguments]),
                    mock.patch.object(sys, "path", list(sys.path)),
                    mock.patch.dict(os.environ),
                    mock.patch.dict(sys.modules, {"screeninfo": modules["screeninfo"]}),
                    mock.patch.object(ctypes, "WinDLL", return_value=user32, create=True),
                    mock.patch("importlib.metadata.version", return_value="fixture"),
                    mock.patch("runpy.run_path", side_effect=manager_entry),
                    mock.patch("importlib.import_module", side_effect=import_module) as imports,
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                ):
                    try:
                        exit_code = start_kids_test.main()
                    except SystemExit as exc:
                        exit_code = exc.code
            finally:
                os.chdir(original_directory)

            reports = list((root / "test_reports").glob("kids_preflight_*.json"))
            report = json.loads(reports[0].read_text(encoding="utf-8")) if reports else None
            profiles = {
                path.name: json.loads(path.read_text(encoding="utf-8"))
                for path in (root / "test_reports").rglob("*.json")
                if not path.name.startswith("kids_preflight_")
            }
            self.assertEqual(
                {path.name: path.read_bytes() for path in (root / "configs").glob("*.json")},
                originals,
                "A trial must not replace the saved dots/spheres configurations",
            )
            self.assertEqual((root / "config.json").read_bytes(), production_original)
            capture.assert_not_called()
            window.assert_not_called()
            return dict(exit_code=exit_code, observed=observed, report=report,
                        profiles=profiles, import_count=imports.call_count,
                        imported_modules=[call.args[0] for call in imports.call_args_list],
                        stdout=stdout.getvalue(), stderr=stderr.getvalue())

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_grid_launch_uses_isolated_one_scene_audience_profile(self):
        result = self.run_launcher(["--audience", "--scene", "grid", "--duration-minutes", "2"])
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        observed = result["observed"]
        self.assertEqual((observed["entrypoint"], observed["run_name"]), ("manager.py", "__main__"))
        self.assertTrue(observed["is_trial_profile"])
        config = observed["config"]
        self.assertEqual(config["PRODUCTION_SCENES"], ["finger_grid_interaction_acer.py"])
        self.assertEqual(config["PRELOAD_COUNT"], 0)
        self.assertFalse(config["TRANSITION_ENABLED"])
        self.assertFalse(config["CLAP_MONITOR_ENABLED"])
        self.assertTrue(config["SHARED_CAMERA_ENABLED"])
        self.assertEqual(config["DISPLAY_TARGET"], "audience")
        self.assertEqual(config["DISPLAY_NAME"], r"\\.\DISPLAY5")
        self.assertEqual(config["CONTROL_DISPLAY_NAME"], r"\\.\DISPLAY1")
        self.assertEqual(config["CAMERA_NAME_HINTS"], ["c922"])
        self.assertTrue(config["CAMERA_REQUIRE_NAME_MATCH"])
        self.assertFalse(config["CAMERA_ALLOW_FALLBACK"])
        argv = observed["argv"]
        self.assertEqual(argv[argv.index("--operator-host") + 1], "127.0.0.1")
        self.assertEqual(argv[argv.index("--duration-seconds") + 1], "120.0")

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_grid_preflight_records_selected_profile_without_starting_manager(self):
        result = self.run_launcher(["--audience", "--scene", "grid", "--check"])
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        self.assertEqual(result["observed"], {})
        report = result["report"]
        self.assertEqual(report["failures"], [])
        self.assertFalse(report["physical_camera_tested"])
        self.assertFalse(report["visual_tested"])
        self.assertEqual(report["displays"]["audience"]["name"], r"\\.\DISPLAY5")
        self.assertEqual(result["profiles"][report["config"]]["PRODUCTION_SCENES"],
                         ["finger_grid_interaction_acer.py"])

    def test_grid_without_audience_is_rejected_before_imports_or_profile_creation(self):
        result = self.run_launcher(["--scene", "grid", "--check"])
        self.assertEqual(result["exit_code"], 2)
        self.assertIn("--scene grid requires --audience", result["stderr"])
        self.assertEqual(result["observed"], {})
        self.assertIsNone(result["report"])
        self.assertEqual(result["profiles"], {})
        self.assertEqual(result["import_count"], 0)

    def test_grid_rejects_nonlocal_operator_before_imports_or_profile_creation(self):
        result = self.run_launcher(["--audience", "--scene", "grid", "--operator-host", "0.0.0.0"])
        self.assertEqual(result["exit_code"], 2)
        self.assertIn("--audience requires --operator-host 127.0.0.1", result["stderr"])
        self.assertEqual(result["observed"], {})
        self.assertIsNone(result["report"])
        self.assertEqual(result["profiles"], {})
        self.assertEqual(result["import_count"], 0)

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_grid_missing_audience_display_cannot_reach_manager(self):
        result = self.run_launcher(["--audience", "--scene", "grid"], audience_present=False)
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["observed"], {})
        self.assertTrue(any("DISPLAY5" in failure for failure in result["report"]["failures"]))
        self.assertFalse(result["report"]["physical_camera_tested"])

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_trial_inherits_saved_camera_controls_but_enforces_one_shared_scene(self):
        result = self.run_launcher(["--audience", "--scene", "grid"], base_overrides={
            "CAMERA_EXPOSURE": -4, "CAMERA_ZOOM": 176,
            "PRODUCTION_SCENES": ["finger_colorfull_dots_acer.py", "colorfull_dots_spheres_acer.py"],
            "PRELOAD_COUNT": 2, "TRANSITION_ENABLED": True, "CLAP_MONITOR_ENABLED": True,
            "SHARED_CAMERA_ENABLED": False, "DISPLAY_TARGET": "primary",
        })
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        config = result["observed"]["config"]
        self.assertEqual((config["CAMERA_EXPOSURE"], config["CAMERA_ZOOM"]), (-4, 176))
        self.assertEqual(config["PRODUCTION_SCENES"], ["finger_grid_interaction_acer.py"])
        self.assertEqual(config["PRELOAD_COUNT"], 0)
        self.assertFalse(config["TRANSITION_ENABLED"])
        self.assertFalse(config["CLAP_MONITOR_ENABLED"])
        self.assertTrue(config["SHARED_CAMERA_ENABLED"])
        self.assertEqual(config["DISPLAY_TARGET"], "audience")

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_a_later_grid_launch_does_not_reuse_or_replace_an_old_trial_profile(self):
        previous = {"PRODUCTION_SCENES": ["finger_mandala_acer.py"], "CAMERA_EXPOSURE": -9}
        result = self.run_launcher(["--audience", "--scene", "grid"],
                                   base_overrides={"CAMERA_EXPOSURE": -4}, prior_profile=previous)
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        self.assertNotEqual(result["report"]["config"], "kids_grid_profile_previous.json")
        self.assertEqual(result["profiles"]["kids_grid_profile_previous.json"], previous)
        self.assertEqual(result["observed"]["config"]["PRODUCTION_SCENES"],
                         ["finger_grid_interaction_acer.py"])
        self.assertEqual(result["observed"]["config"]["CAMERA_EXPOSURE"], -4)


if __name__ == "__main__":
    unittest.main()
