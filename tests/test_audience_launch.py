import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from scripts import start_kids_test
import stage_display


class AudienceLaunchTests(unittest.TestCase):
    def run_launcher(self, arguments):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            (root / "configs/rebirth_acer_xiaomi.json").write_text("{}", encoding="utf-8")
            order = []
            observed = {}

            def import_check():
                order.append("imports")
                self.assertEqual(os.environ["SDL_WINDOWS_DPI_SCALING"], "0")
                return {"failures": [], "physical_camera_tested": False, "visual_tested": False}

            def manager_entry(*_args, **_kwargs):
                observed["argv"] = list(sys.argv)

            with (
                mock.patch.object(start_kids_test, "ROOT", root),
                mock.patch.object(sys, "argv", ["start_kids_test.py", "--audience", *arguments]),
                mock.patch.object(sys, "path", list(sys.path)),
                mock.patch.dict(os.environ, {"SDL_WINDOWS_DPI_SCALING": "1"}),
                mock.patch.object(start_kids_test.os, "chdir"),
                mock.patch.object(stage_display, "configure_audience_dpi", side_effect=lambda: order.append("dpi")),
                mock.patch.object(stage_display, "resolve_audience_displays", side_effect=lambda _: order.append("display") or {"audience": "fixture"}),
                mock.patch.object(start_kids_test, "check_runtime", side_effect=import_check),
                mock.patch.object(start_kids_test.runpy, "run_path", side_effect=manager_entry),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(start_kids_test.main(), 0)
            report = json.loads(next((root / "test_reports").glob("kids_preflight_*.json")).read_text(encoding="utf-8"))
        return order, observed, report

    def test_preflight_sets_dpi_before_graphics_imports_and_never_runs_manager(self):
        order, observed, report = self.run_launcher(["--check"])
        self.assertEqual(order, ["dpi", "display", "imports"])
        self.assertNotIn("argv", observed)
        self.assertFalse(report["physical_camera_tested"])
        self.assertFalse(report["visual_tested"])

    def test_launch_uses_audience_config_and_loopback_operator(self):
        _, observed, _ = self.run_launcher(["--duration-minutes", "2"])
        argv = observed["argv"]
        self.assertEqual(Path(argv[argv.index("--config") + 1]).name, "rebirth_acer_xiaomi.json")
        self.assertEqual(argv[argv.index("--operator-host") + 1], "127.0.0.1")
        self.assertEqual(argv[argv.index("--duration-seconds") + 1], "120.0")


if __name__ == "__main__":
    unittest.main()
