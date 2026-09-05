"""Exercise actual scene initialization with native libraries replaced by fakes."""
import ast
from contextlib import ExitStack
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def namespace():
    screen = mock.Mock()
    screen.get_size.return_value = (640, 360)
    display = mock.Mock()
    display.setup_pygame_fullscreen.return_value = (screen, (640, 360))
    return dict(__name__="resource_test", atexit=mock.Mock(), ExitStack=ExitStack,
                pygame=mock.Mock(), mp=mock.Mock(), cv2=mock.Mock(), display_utils=display,
                math=math, WINDOW_WIDTH=640, WINDOW_HEIGHT=360, RenderCanvas=mock.Mock(),
                gfx=mock.Mock())


def run_exit_callbacks(ns):
    for call in reversed(ns["atexit"].register.call_args_list):
        call.args[0]()


class SceneResourceTests(unittest.TestCase):
    def test_one_release_failure_does_not_skip_the_other_scene_resources(self):
        ns = namespace()
        tree = ast.parse((ROOT / "finger_colorfull_dots_2.py").read_text(encoding="utf-8"))
        tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
        cap = ns["display_utils"].open_camera.return_value
        cap.isOpened.return_value = False
        cap.release.side_effect = RuntimeError("injected release failure")
        with self.assertRaisesRegex(RuntimeError, "could not be attached"):
            exec(compile(tree, "finger_colorfull_dots_2.py", "exec"), ns)
        with self.assertRaisesRegex(RuntimeError, "injected release failure"):
            run_exit_callbacks(ns)
        ns["mp"].solutions.hands.Hands.return_value.close.assert_called_once()
        ns["pygame"].quit.assert_called_once()

    def test_module_initialization_failure_releases_already_created_hands(self):
        for filename in ("finger_colorfull_dots_2.py", "finger_mandala_2.py", "finger_grid_interaction_2.py"):
            with self.subTest(filename=filename):
                ns = namespace()
                tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
                tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
                ns["display_utils"].open_camera.side_effect = RuntimeError("injected camera attach failure")
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    exec(compile(tree, filename, "exec"), ns)
                run_exit_callbacks(ns)
                ns["mp"].solutions.hands.Hands.return_value.close.assert_called_once()
                ns["pygame"].quit.assert_called_once()

    def test_function_initialization_failure_releases_camera_and_window(self):
        for filename in ("fractal_moving_2.py", "spider_cursor_2.py"):
            with self.subTest(filename=filename):
                ns = namespace()
                tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
                node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
                exec(compile(ast.Module(body=[node], type_ignores=[]), filename, "exec"), ns)
                ns["mp"].solutions.hands.Hands.side_effect = RuntimeError("injected detector failure")
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    ns["main"]()
                run_exit_callbacks(ns)
                ns["display_utils"].open_camera.return_value.release.assert_called_once()
                ns["pygame"].quit.assert_called_once()

    def test_gpu_constructor_failure_closes_canvas_before_app_assignment(self):
        for filename, cls_name in (("particle_storm_2.py", "ParticleStormApp"),
                                   ("saturn_particles_2.py", "SaturnParticlesApp")):
            with self.subTest(filename=filename):
                ns = namespace()
                tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
                node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == cls_name)
                exec(compile(ast.Module(body=[node], type_ignores=[]), filename, "exec"), ns)
                ns["gfx"].renderers.WgpuRenderer.side_effect = RuntimeError("injected GPU initialization failure")
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    ns[cls_name]()
                run_exit_callbacks(ns)
                ns["RenderCanvas"].return_value.close.assert_called_once()

    def test_first_scene_clears_departed_hands_and_does_not_display_stale_camera(self):
        ns = namespace()
        tree = ast.parse((ROOT / "finger_colorfull_dots_2.py").read_text(encoding="utf-8"))
        tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
        cap = ns["display_utils"].open_camera.return_value
        cap.read.side_effect = [(True, object()), (True, object()), (False, None)]
        ns["display_utils"].prepare_camera_frame.return_value = (object(), object(), object())
        ns["display_utils"].normalized_to_stage.return_value = (100, 200)
        hand = SimpleNamespace(landmark=[SimpleNamespace(x=0.5, y=0.5)] * 21)
        ns["mp"].solutions.hands.Hands.return_value.process.side_effect = [
            SimpleNamespace(multi_hand_landmarks=[hand]), SimpleNamespace(multi_hand_landmarks=None)]
        ns["pygame"].event.get.side_effect = [[], [], [SimpleNamespace(type=ns["pygame"].QUIT)]]
        ns["pygame"].time.get_ticks.side_effect = [0, 16, 32, 48]
        ns["notify_first_frame"] = mock.Mock()
        try:
            exec(compile(tree, "finger_colorfull_dots_2.py", "exec"), ns)
            markers = [call for call in ns["pygame"].draw.circle.call_args_list
                       if call.args[1] == (255, 255, 255)]
            self.assertEqual(len(markers), 1)
            self.assertEqual(ns["cursors"], [])
            self.assertIsNone(ns["camera_surface"])
        finally:
            run_exit_callbacks(ns)


if __name__ == "__main__":
    unittest.main()
