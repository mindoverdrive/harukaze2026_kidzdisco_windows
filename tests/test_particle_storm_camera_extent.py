"""Check Storm's capture setup and projection without opening native resources."""
import ast
from importlib.machinery import PathFinder
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def camera_case():
    import math
    from types import SimpleNamespace
    import cv2
    import numpy as np
    sys.path.insert(0, str(ROOT))
    import display_utils

    tree = ast.parse((ROOT / "particle_storm_2.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ParticleStormApp")
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    setup = [n for n in init.body if
             (isinstance(n, ast.Assign) and any(ast.unparse(t) == "self.camera_input_size" for t in n.targets)) or
             (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and
              ast.unparse(n.value.func) == "self.cap.set")]
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_landmark_to_world"]
    frame = np.full((720, 1280, 3), 127, dtype=np.uint8)
    frame[:, :64] = [20, 40, 80]
    frame[:, -64:] = [80, 160, 240]
    proxy = display_utils.CameraResizingProxy(SimpleNamespace(read=lambda: (True, frame)))
    app = SimpleNamespace(cap=proxy, camera=SimpleNamespace(local=SimpleNamespace(z=1200)))
    ns = dict(self=app, cv2=cv2, np=np, math=math, display_utils=display_utils,
              WINDOW_WIDTH=1920, WINDOW_HEIGHT=1080, CAMERA_FOV=70.0)
    exec(compile(ast.Module(body=[*setup, *methods], type_ignores=[]), "storm-camera-setup", "exec"), ns)
    ok, resized = proxy.read()
    assert ok
    camera, stage, layout = display_utils.prepare_camera_frame(resized, 1920, 1080)
    assert camera.shape == (360, 640, 3), camera.shape
    assert (layout["offset_x"], layout["offset_y"]) == (0, 0), layout
    assert (layout["scaled_width"], layout["scaled_height"]) == (1920, 1080)
    # Both source edges survive the resizing and existing single mirror.
    np.testing.assert_array_equal(stage[:, 0], np.tile([80, 160, 240], (1080, 1)))
    np.testing.assert_array_equal(stage[:, -1], np.tile([20, 40, 80], (1080, 1)))
    for x, y in ((0, 0), (1, 0), (0, 1), (1, 1), (0.5, 0.5)):
        expected = (round(x * 1919), round(y * 1079))
        for z in (-0.5, 0, 0.5):
            world, screen = ns["_landmark_to_world"](app, SimpleNamespace(x=x, y=y, z=z), layout)
            assert screen == expected, (screen, expected)
            half_h = math.tan(math.radians(70) / 2) * (1200 - world[2])
            projected = ((world[0] / (half_h * 1920 / 1080) + 1) * 960,
                         (1 - world[1] / half_h) * 540)
            np.testing.assert_allclose(projected, expected, atol=0.001)


@unittest.skipUnless(PathFinder.find_spec("numpy") is not None and PathFinder.find_spec("cv2") is not None,
                     "Requires real NumPy and OpenCV in the graphics runtime")
class ParticleStormCameraExtentTests(unittest.TestCase):
    def test_full_camera_edges_and_landmarks_reach_the_audience_edges(self):
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(Path(__file__).resolve()), "--case"],
                                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    if "--case" in sys.argv:
        camera_case()
    else:
        unittest.main()
