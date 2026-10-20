"""Check Storm camera/marker/navigation alignment without native resources.

The accepted artistic 3D force mapping is retained; its legacy inverse formula
below is not a claim that Storm uses a pixel-exact pygfx viewport unprojection.
"""
import ast
from importlib.machinery import PathFinder
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(os.environ.get("MATAHARI_STORM_SOURCE",
                           str(Path(__file__).resolve().parents[1])))
STAGES = ((1920, 1080), (1360, 800), (1080, 1920), (3840, 2160))


def camera_case(source_size=(1280, 720), stage_size=(1920, 1080)):
    import math
    from types import SimpleNamespace
    from unittest import mock
    import cv2
    import numpy as np
    sys.path.insert(0, str(ROOT))
    import display_utils
    from hand_focus_overlay import stage_points

    tree = ast.parse((ROOT / "particle_storm_2.py").read_text(encoding="utf-8-sig"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ParticleStormApp")
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    setup = [n for n in init.body if
             (isinstance(n, ast.Assign) and any(ast.unparse(t) in {
                 "self.camera_input_size", "(input_width, input_height)"} for t in n.targets)) or
             (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and
              ast.unparse(n.value.func) == "self.cap.set")]
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_landmark_to_world"]
    source_w, source_h = source_size
    width, height = stage_size
    frame = np.full((source_h, source_w, 3), 127, dtype=np.uint8)
    frame[:, :max(8, source_w // 20)] = [20, 40, 80]
    frame[:, -max(8, source_w // 20):] = [80, 160, 240]
    source = SimpleNamespace(
        read=lambda: (True, frame), isOpened=lambda: True,
        get=lambda prop: {cv2.CAP_PROP_FRAME_WIDTH: source_w,
                          cv2.CAP_PROP_FRAME_HEIGHT: source_h}.get(prop, 0),
        set=mock.Mock(side_effect=AssertionError("Proxy resize must not configure physical capture")),
    )
    proxy = display_utils.CameraResizingProxy(source)
    app = SimpleNamespace(cap=proxy, camera=SimpleNamespace(local=SimpleNamespace(z=1200)))
    ns = dict(self=app, cv2=cv2, np=np, math=math, display_utils=display_utils,
              WINDOW_WIDTH=width, WINDOW_HEIGHT=height, CAMERA_FOV=70.0)
    exec(compile(ast.Module(body=[*setup, *methods], type_ignores=[]), "storm-camera-setup", "exec"), ns)
    ok, resized = proxy.read()
    assert ok
    source.set.assert_not_called()
    with mock.patch.object(display_utils._camera_presentation, "opacity", return_value=1.0):
        camera, stage, layout = display_utils.prepare_camera_frame(resized, width, height)
        _, navigation_stage, navigation_layout = display_utils.prepare_camera_frame(frame, width, height)
    expected_input = (640, round(640 * source_h / source_w))
    assert app.camera_input_size == expected_input, (source_size, stage_size, app.camera_input_size)
    assert camera.shape == (expected_input[1], expected_input[0], 3), camera.shape
    assert stage.shape == navigation_stage.shape == (height, width, 3)
    # The scaled source shape differs, but the visible rectangle must be identical.
    rectangle_keys = ("stage_width", "stage_height", "scaled_width", "scaled_height", "offset_x", "offset_y")
    assert {k: layout[k] for k in rectangle_keys} == {
        k: navigation_layout[k] for k in rectangle_keys}, (layout, navigation_layout)
    x0, y0 = layout["offset_x"], layout["offset_y"]
    x1 = x0 + layout["scaled_width"]
    y1 = y0 + layout["scaled_height"]
    # Both source edges survive the reduction and exactly one mirror.
    for shown in (stage, navigation_stage):
        np.testing.assert_array_equal(shown[y0:y1, x0], np.tile([80, 160, 240], (y1 - y0, 1)))
        np.testing.assert_array_equal(shown[y0:y1, x1 - 1], np.tile([20, 40, 80], (y1 - y0, 1)))
        for pad in (shown[:y0], shown[y1:], shown[y0:y1, :x0], shown[y0:y1, x1:]):
            assert not pad.any()
    for x, y in ((0, 0), (1, 0), (0, 1), (1, 1), (0.1, 0.1), (0.5, 0.5), (0.9, 0.9)):
        expected = display_utils.normalized_to_stage(x, y, navigation_layout)
        hand = [SimpleNamespace(x=x, y=y, z=0.0) for _ in range(21)]
        assert stage_points(hand, stage_size, layout)[8] == expected
        for z in (-0.5, 0, 0.5):
            world, screen = ns["_landmark_to_world"](app, SimpleNamespace(x=x, y=y, z=z), layout)
            assert screen == expected, (screen, expected)
            # Preserve the previously accepted force-field coordinates.
            half_h = math.tan(math.radians(70) / 2) * (1200 - world[2])
            legacy_projected = ((world[0] / (half_h * width / height) + 1) * width / 2,
                                (1 - world[1] / half_h) * height / 2)
            np.testing.assert_allclose(legacy_projected, expected, atol=0.001)
    return dict(source=source_size, stage=stage_size, resized=expected_input,
                rectangle={key: layout[key] for key in rectangle_keys})


@unittest.skipUnless(PathFinder.find_spec("numpy") is not None and PathFinder.find_spec("cv2") is not None,
                     "Requires real NumPy and OpenCV in the graphics runtime")
class ParticleStormCameraExtentTests(unittest.TestCase):
    def check_group(self, group):
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-X", "utf8", str(Path(__file__).resolve()), "--case", group],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["cases_passed"], {"production": 1, "display": 3, "input": 16}[group])

    def test_current_1280x720_to_640x360_full_camera_edges_are_preserved(self):
        self.check_group("production")

    def test_non169_portrait_and_4k_output_match_navigation_letterbox(self):
        self.check_group("display")

    def test_other_input_aspects_match_navigation_and_do_not_touch_physical_capture(self):
        self.check_group("input")


if __name__ == "__main__":
    if "--case" in sys.argv:
        group = sys.argv[sys.argv.index("--case") + 1]
        cases = {
            "production": [((1280, 720), STAGES[0])],
            "display": [((1280, 720), stage) for stage in STAGES[1:]],
            "input": [(source, stage) for source in ((640, 480), (1280, 960), (640, 360), (1920, 1080))
                      for stage in STAGES],
        }[group]
        reports = [camera_case(*case) for case in cases]
        print(json.dumps(dict(cases_passed=len(reports), cases=reports)))
    else:
        unittest.main()
