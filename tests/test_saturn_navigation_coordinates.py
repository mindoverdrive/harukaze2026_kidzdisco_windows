import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
import cv2
import numpy as np
import display_utils


class SaturnNavigationCoordinatesTests(unittest.TestCase):
    def test_scene_camera_settings_preserve_overlay_coordinates(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'saturn_particles_2.py').read_text(encoding='utf-8-sig'))
        init = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '__init__')
        frame = np.zeros((720, 1280, 3), np.uint8)
        source = SimpleNamespace(read=lambda: (True, frame), set=lambda *args: True)
        instance = SimpleNamespace(cap=display_utils.CameraResizingProxy(source))
        for node in init.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and ast.unparse(node.value.func) == 'self.cap.set':
                exec(compile(ast.Module(body=[node], type_ignores=[]), '<camera settings>', 'exec'), {'self':instance,'cv2':cv2})
        _, scene_frame = instance.cap.read()
        scene_layout = display_utils.get_uniform_layout(scene_frame.shape[1], scene_frame.shape[0],1920,1080)
        overlay_layout = display_utils.get_uniform_layout(1280,720,1920,1080)
        for x,y in ((.05,.1),(.5,.5),(.95,.1)):
            self.assertEqual(display_utils.normalized_to_stage(x,y,scene_layout),
                             display_utils.normalized_to_stage(x,y,overlay_layout))
