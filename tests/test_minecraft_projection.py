"""CPU camera-matrix regression; imports no scene, camera input, window or renderer."""
import ast
import math
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

# Camera matrices need no system-font discovery/cache during this isolated test.
os.environ.setdefault("PYGFX_DISABLE_SYSTEM_FONTS", "1")
import numpy as np
import pygfx as gfx
import pylinalg as la

ROOT = Path(os.environ.get("MATAHARI_PROJECTION_SOURCE",
                           str(Path(__file__).resolve().parents[1])))


def projection_method(width, height):
    tree = ast.parse((ROOT / "minecraft.py").read_text(encoding="utf-8-sig"))
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "MinecraftApp")
    method = next(n for n in cls.body
                  if isinstance(n, ast.FunctionDef) and n.name == "get_world_pos_from_screen")
    namespace = dict(np=np, math=math, la=la, WINDOW_WIDTH=width, WINDOW_HEIGHT=height)
    exec(compile(ast.Module(body=[method], type_ignores=[]), "minecraft-projection", "exec"),
         namespace)
    return namespace["get_world_pos_from_screen"]


class MinecraftProjectionTests(unittest.TestCase):
    def check_projection(self, width, height, rotated):
        camera = gfx.PerspectiveCamera(70, width / height)
        camera.set_view_size(width, height)
        camera.local.position = (7.0, 11.0, 50.0)
        if rotated:
            camera.local.rotation = la.quat_from_euler((0.2, -0.35, 0.1))
        app = SimpleNamespace(camera=camera)
        method = projection_method(width, height)
        for depth in (10.0, 40.0, 120.0):
            for point in ((0., 0.), (.1, .1), (.5, .5), (.9, .9), (1., 1.)):
                world = method(app, *point, depth)
                clip = camera.camera_matrix @ np.array([*world, 1.0])
                ndc = clip[:2] / clip[3]
                pixel = ((ndc[0] + 1) * width / 2, (1 - ndc[1]) * height / 2)
                with self.subTest(size=(width, height), rotated=rotated,
                                  depth=depth, point=point):
                    np.testing.assert_allclose(pixel, (point[0] * width, point[1] * height),
                                               atol=0.01)

    def test_landscape_projection_matches_visible_hand_before_grid_snap(self):
        for size in ((1920, 1080), (3840, 2160), (1360, 800)):
            self.check_projection(*size, rotated=False)

    def test_portrait_projection_matches_visible_hand_before_grid_snap(self):
        self.check_projection(1080, 1920, rotated=False)

    def test_rotating_view_keeps_the_same_screen_coordinate(self):
        for size in ((1920, 1080), (1080, 1920)):
            self.check_projection(*size, rotated=True)


if __name__ == "__main__":
    unittest.main()
