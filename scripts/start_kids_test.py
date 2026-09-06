"""Run the first Acer/C922 kids-test candidate with a checked Python runtime."""
import argparse
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import runpy
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def check_runtime():
    failures = []
    versions = {}
    loaded_modules = {}
    for name, distribution in (("numpy", "numpy"), ("cv2", "opencv-contrib-python"),
                               ("pygame", "pygame"), ("mediapipe", "mediapipe"),
                               ("screeninfo", "screeninfo"), ("pygrabber.dshow_graph", "pygrabber")):
        try:
            module = importlib.import_module(name)
            loaded_modules[name] = {"version": str(getattr(module, "__version__", "unknown")),
                                    "path": str(getattr(module, "__file__", "unknown"))}
            if name == "pygame":
                loaded_modules[name]["sdl_version"] = list(module.get_sdl_version())
            if name == "mediapipe" and not hasattr(getattr(module, "solutions", None), "hands"):
                raise RuntimeError("this scene requires mediapipe.solutions.hands")
            try:
                versions[name] = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                versions[name] = str(getattr(module, "__version__", "unknown"))
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    return {"python": sys.executable, "python_version": sys.version.split()[0],
            "versions": versions, "loaded_modules": loaded_modules, "failures": failures,
            "physical_camera_tested": False, "visual_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check imports only; do not open camera/windows")
    parser.add_argument("--audience", action="store_true", help="Use Acer local control and the configured Xiaomi extended display")
    parser.add_argument("--scene", choices=("dots", "spheres"), default="dots",
                        help="Scene candidate; spheres requires --audience")
    parser.add_argument("--duration-minutes", type=float, help="Stop after this many minutes of the initial scene")
    parser.add_argument("--switch-every", type=float, help="Trial switch interval in seconds")
    parser.add_argument("--switch-count", type=int, help="Number of successful trial switches")
    parser.add_argument("--operator-host", default="127.0.0.1", help="Operator UI bind address; audience mode requires 127.0.0.1")
    parser.add_argument("--operator-port", type=int, default=8766)
    parser.add_argument("--no-ui", action="store_true", help="Disable the browser operator panel")
    args = parser.parse_args()
    if args.scene == "spheres" and not args.audience:
        parser.error("--scene spheres requires --audience")
    sys.path.insert(0, str(ROOT))
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    config_name = "rebirth_acer_xiaomi.json" if args.audience else "kids_test_acer.json"
    if args.scene == "spheres":
        config_name = "rebirth_spheres_acer_xiaomi.json"
    config_path = ROOT / "configs" / config_name
    displays = None
    display_failures = []
    if args.audience:
        if args.operator_host != "127.0.0.1":
            parser.error("--audience requires --operator-host 127.0.0.1")
        from stage_display import AUDIENCE_DPI_ENV, configure_audience_dpi, resolve_audience_displays

        os.environ.update(AUDIENCE_DPI_ENV)
        try:
            configure_audience_dpi()
            displays = resolve_audience_displays(json.loads(config_path.read_text(encoding="utf-8")))
        except Exception as exc:
            display_failures.append(f"audience display: {type(exc).__name__}: {exc}")
    report = check_runtime()
    if args.audience:
        report["displays"] = displays
        report["config"] = config_path.name
        report["failures"].extend(display_failures)
    report_dir = ROOT / "test_reports"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / (time.strftime("kids_preflight_%Y%m%d_%H%M%S") + ".json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Preflight report: {report_path}")
    if report["failures"]:
        print("Select the Python environment that already runs the scenes; see KIDS_TEST_START.md.")
        return 2
    if args.check:
        return 0
    os.chdir(ROOT)
    trial_dir = report_dir / (time.strftime("kids_trial_%Y%m%d_%H%M%S_") + str(time.time_ns() % 1_000_000_000))
    sys.argv = [str(ROOT / "manager.py"), "--config", str(config_path),
                "--report-dir", str(trial_dir)]
    if not args.no_ui:
        sys.argv.extend(["--operator-host", args.operator_host, "--operator-port", str(args.operator_port)])
    if args.duration_minutes is not None:
        sys.argv.extend(["--duration-seconds", str(args.duration_minutes * 60)])
    if args.switch_every is not None:
        sys.argv.extend(["--switch-interval-seconds", str(args.switch_every)])
    if args.switch_count is not None:
        sys.argv.extend(["--switch-count", str(args.switch_count)])
    runpy.run_path(str(ROOT / "manager.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
