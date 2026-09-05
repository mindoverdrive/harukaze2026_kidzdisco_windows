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
    for name, distribution in (("numpy", "numpy"), ("cv2", "opencv-contrib-python"),
                               ("pygame", "pygame"), ("mediapipe", "mediapipe"),
                               ("screeninfo", "screeninfo"), ("pygrabber.dshow_graph", "pygrabber")):
        try:
            module = importlib.import_module(name)
            if name == "mediapipe" and not hasattr(getattr(module, "solutions", None), "hands"):
                raise RuntimeError("this scene requires mediapipe.solutions.hands")
            try:
                versions[name] = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                versions[name] = str(getattr(module, "__version__", "unknown"))
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    return {"python": sys.executable, "python_version": sys.version.split()[0],
            "versions": versions, "failures": failures,
            "physical_camera_tested": False, "visual_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check imports only; do not open camera/windows")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    report = check_runtime()
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
    sys.argv = [str(ROOT / "manager.py"), "--config", str(ROOT / "configs" / "kids_test_acer.json")]
    runpy.run_path(str(ROOT / "manager.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
