"""Exercise the real field scene loops without opening cameras or windows."""

import ast
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def run_field_scene(filename, *, camera_failure):
    source = ROOT / filename
    tree = ast.parse(source.read_text(encoding="utf-8"))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name == "main")
    projection_tree = ast.parse((ROOT / "display_utils.py").read_text(encoding="utf-8"))
    projection = next(node for node in projection_tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == "normalized_to_stage")
    projection_namespace = {}
    exec(compile(ast.Module(body=[projection], type_ignores=[]), "display_utils.py", "exec"),
         projection_namespace)
    width, height = 320, 180
    layout = dict(offset_x=40, offset_y=0, scaled_width=240, scaled_height=180)
    detected = [SimpleNamespace(landmark=[SimpleNamespace(x=x, y=y, z=0.)
                                         for _ in range(21)])
                for x, y in ((0., .25), (1., .75))]
    ordered = []
    screen = mock.Mock()
    screen.get_size.return_value = (width, height)
    screen.blit.side_effect = lambda *_: ordered.append("blit")
    camera = mock.Mock()
    camera.isOpened.return_value = True
    camera.read.side_effect = [(True, object()), (not camera_failure, None if camera_failure else object())]
    hands = mock.MagicMock()
    hands.__enter__.return_value = hands
    hands.process.side_effect = [SimpleNamespace(multi_hand_landmarks=detected),
                                SimpleNamespace(multi_hand_landmarks=None)]
    make_hands = mock.Mock(return_value=hands)
    display = mock.Mock()
    display.open_camera.return_value = camera
    display.setup_pygame_fullscreen.return_value = (screen, (width, height))
    display.prepare_camera_frame.return_value = (object(), object(), layout)
    display.normalized_to_stage.side_effect = projection_namespace["normalized_to_stage"]
    pygame = mock.Mock(QUIT=1, KEYDOWN=2, K_ESCAPE=27)
    pygame.event.get.side_effect = [[], [], [SimpleNamespace(type=1)]]
    pygame.display.flip.side_effect = lambda: ordered.append("flip")
    field = mock.Mock()
    triangles, colors = mock.Mock(), mock.Mock()
    triangles.tolist.return_value = colors.tolist.return_value = []
    field.step.return_value = (triangles, colors)
    make_field = mock.Mock(return_value=field)
    overlay = mock.Mock(side_effect=lambda *_args, **_kwargs: ordered.append("overlay"))
    notify = mock.Mock()
    namespace = dict(
        ExitStack=ExitStack,
        time=SimpleNamespace(monotonic=mock.Mock(side_effect=[10., 10.1, 10.2])),
        cv2=mock.Mock(), pygame=pygame, display_utils=display,
        mp=SimpleNamespace(solutions=SimpleNamespace(hands=SimpleNamespace(Hands=make_hands))),
        PrismSkin=make_field, PolygonField=make_field,
        draw_hand_overlay=overlay, notify_first_frame=notify,
    )
    exec(compile(ast.Module(body=[main], type_ignores=[]), str(source), "exec"), namespace)
    namespace["main"]()
    return SimpleNamespace(**locals())


class HandFieldScenesTests(unittest.TestCase):
    def test_all_current_index_inputs_use_the_camera_layout_and_draw_after_art(self):
        for filename in ("prism_skin.py", "polygon_vibes_stage.py"):
            with self.subTest(scene=filename):
                scene = run_field_scene(filename, camera_failure=False)
                first = scene.overlay.call_args_list[0]
                self.assertIs(first.args[0], scene.screen)
                self.assertIs(first.args[1], scene.detected)
                self.assertIs(first.kwargs["layout"], scene.layout)
                self.assertEqual(first.kwargs["focus"], (8,))
                inputs = ((40, 45), (279, 134))
                if filename == "prism_skin.py":
                    self.assertEqual(scene.field.update.call_args_list[0].args[0],
                                     [(x / 319, y / 179) for x, y in inputs])
                else:
                    self.assertEqual(scene.field.step.call_args_list[0].args[0], list(inputs))
                for index, event in enumerate(scene.ordered):
                    if event == "overlay":
                        self.assertEqual(scene.ordered[index - 1], "blit")
                        self.assertEqual(scene.ordered[index + 1], "flip")
                scene.display.open_camera.assert_called_once_with()
                scene.make_hands.assert_called_once()
                self.assertEqual(scene.hands.process.call_count, 2)
                scene.camera.release.assert_called_once_with()
                scene.hands.__exit__.assert_called_once()

    def test_no_hand_result_and_camera_failure_clear_every_previous_hand(self):
        for filename in ("prism_skin.py", "polygon_vibes_stage.py"):
            for camera_failure in (False, True):
                with self.subTest(scene=filename, camera_failure=camera_failure):
                    scene = run_field_scene(filename, camera_failure=camera_failure)
                    self.assertEqual(scene.overlay.call_count, 2)
                    self.assertEqual(scene.overlay.call_args_list[1].args[1], ())
                    if camera_failure:
                        self.assertIsNone(scene.overlay.call_args_list[1].kwargs["layout"])
                    operation = scene.field.update if filename == "prism_skin.py" else scene.field.step
                    self.assertEqual(operation.call_args_list[1].args[0], [])
                    self.assertEqual(scene.hands.process.call_count, 1 if camera_failure else 2)
                    self.assertEqual(scene.notify.call_args_list[-1].kwargs["frame_processed"],
                                     not camera_failure)


if __name__ == "__main__":
    unittest.main()
