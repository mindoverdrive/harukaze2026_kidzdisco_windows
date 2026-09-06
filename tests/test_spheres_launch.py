import contextlib
import ctypes
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts import start_kids_test


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SpheresLaunchTests(unittest.TestCase):
    def run_launcher(self, arguments):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            for name in (
                "kids_test_acer.json",
                "rebirth_acer_xiaomi.json",
                "rebirth_spheres_acer_xiaomi.json",
            ):
                source = PROJECT_ROOT / "configs" / name
                if source.exists():
                    shutil.copyfile(source, root / "configs" / name)

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
            modules["screeninfo"].get_monitors = lambda: [
                SimpleNamespace(name=r"\\.\DISPLAY1", x=0, y=0, width=1920, height=1080, is_primary=True),
                SimpleNamespace(name=r"\\.\DISPLAY5", x=1920, y=0, width=1920, height=1080, is_primary=False),
            ]
            user32 = mock.MagicMock()
            user32.SetProcessDpiAwarenessContext.return_value = True
            user32.GetAwarenessFromDpiAwarenessContext.return_value = 2
            observed = {}
            stdout = io.StringIO()
            stderr = io.StringIO()

            def manager_entry(path, *, run_name):
                observed.update(path=path, run_name=run_name, argv=list(sys.argv))

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
                    mock.patch("importlib.import_module", side_effect=lambda name: modules[name]) as imports,
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
            selected_name = report.get("config") if report else None
            if selected_name is None and observed:
                argv = observed["argv"]
                selected_name = Path(argv[argv.index("--config") + 1]).name
            selected_config = (
                json.loads((root / "configs" / selected_name).read_text(encoding="utf-8"))
                if selected_name else None
            )
            capture.assert_not_called()
            window.assert_not_called()
            return {
                "exit_code": exit_code,
                "observed": observed,
                "report": report,
                "selected_config": selected_config,
                "import_count": imports.call_count,
                "stdout": stdout.getvalue(),
                "stderr": stderr.getvalue(),
            }

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_spheres_preflight_selects_only_spheres_without_starting_manager_or_camera(self):
        result = self.run_launcher(["--audience", "--scene", "spheres", "--check"])
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        self.assertEqual(result["report"]["config"], "rebirth_spheres_acer_xiaomi.json")
        self.assertEqual(result["selected_config"]["PRODUCTION_SCENES"], ["colorfull_dots_spheres_acer.py"])
        self.assertFalse(result["report"]["physical_camera_tested"])
        self.assertFalse(result["report"]["visual_tested"])
        self.assertEqual(result["observed"], {})
        original = json.loads((PROJECT_ROOT / "configs/rebirth_acer_xiaomi.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {key: value for key, value in result["selected_config"].items() if key != "PRODUCTION_SCENES"},
            {key: value for key, value in original.items() if key != "PRODUCTION_SCENES"},
        )

    def test_spheres_without_audience_is_rejected_before_preflight_or_manager(self):
        result = self.run_launcher(["--scene", "spheres", "--check"])
        self.assertEqual(result["exit_code"], 2)
        self.assertIn("--scene spheres requires --audience", result["stderr"])
        self.assertIsNone(result["report"])
        self.assertEqual(result["import_count"], 0)
        self.assertEqual(result["observed"], {})

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_spheres_launch_passes_selected_config_and_trial_controls_to_manager(self):
        result = self.run_launcher([
            "--audience", "--scene", "spheres", "--duration-minutes", "2",
            "--switch-every", "20", "--switch-count", "3",
        ])
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        observed = result["observed"]
        self.assertEqual(Path(observed["path"]).name, "manager.py")
        self.assertEqual(observed["run_name"], "__main__")
        argv = observed["argv"]
        self.assertEqual(Path(argv[argv.index("--config") + 1]).name, "rebirth_spheres_acer_xiaomi.json")
        self.assertEqual(result["selected_config"]["PRODUCTION_SCENES"], ["colorfull_dots_spheres_acer.py"])
        for option, value in (
            ("--operator-host", "127.0.0.1"), ("--operator-port", "8766"),
            ("--duration-seconds", "120.0"), ("--switch-interval-seconds", "20.0"),
            ("--switch-count", "3"),
        ):
            self.assertEqual(argv[argv.index(option) + 1], value)
        self.assertEqual(Path(argv[argv.index("--report-dir") + 1]).parent.name, "test_reports")
        self.assertNotIn("--scene", argv)

    @unittest.skipUnless(os.name == "nt", "Acer audience display validation requires Windows")
    def test_omitted_or_explicit_dots_preserves_existing_entrypoints(self):
        for arguments, name in (
            ([], "kids_test_acer.json"),
            (["--scene", "dots"], "kids_test_acer.json"),
            (["--audience"], "rebirth_acer_xiaomi.json"),
            (["--audience", "--scene", "dots"], "rebirth_acer_xiaomi.json"),
        ):
            with self.subTest(arguments=arguments):
                result = self.run_launcher(arguments)
                self.assertEqual(result["exit_code"], 0, result["stderr"])
                argv = result["observed"]["argv"]
                self.assertEqual(Path(argv[argv.index("--config") + 1]).name, name)
                self.assertEqual(result["selected_config"]["PRODUCTION_SCENES"], ["finger_colorfull_dots_acer.py"])

    def test_unknown_scene_is_rejected_before_preflight_or_manager(self):
        result = self.run_launcher(["--audience", "--scene", "unlisted.py", "--check"])
        self.assertEqual(result["exit_code"], 2)
        self.assertIn("invalid choice", result["stderr"])
        self.assertIsNone(result["report"])
        self.assertEqual(result["import_count"], 0)
        self.assertEqual(result["observed"], {})


if __name__ == "__main__":
    unittest.main()
