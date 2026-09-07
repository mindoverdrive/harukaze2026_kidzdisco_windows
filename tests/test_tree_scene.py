import ast
from contextlib import ExitStack
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
scene = ModuleType("colorfull_tree_test_target")
scene.__dict__.update(
    ExitStack=ExitStack,
    argparse=mock.MagicMock(),
    atexit=mock.MagicMock(),
    cv2=mock.MagicMock(),
    display_utils=mock.MagicMock(),
    json=mock.MagicMock(),
    math=math,
    mp=mock.MagicMock(),
    notify_exit_request=mock.Mock(),
    notify_first_frame=mock.Mock(),
    pygame=mock.MagicMock(),
    socket=mock.MagicMock(),
    sys=sys,
    time=mock.MagicMock(),
)
tree = ast.parse((ROOT / "colorfull_tree.py").read_text(encoding="utf-8"))
definitions = [node for node in tree.body if isinstance(node, (ast.Assign, ast.FunctionDef))]
exec(compile(ast.Module(body=definitions, type_ignores=[]), "colorfull_tree.py", "exec"), scene.__dict__)


def neutral_hand(x=0.5):
    landmarks = [SimpleNamespace(x=x, y=0.7) for _ in range(21)]
    landmarks[0] = SimpleNamespace(x=x, y=0.8)
    landmarks[9] = SimpleNamespace(x=x + 0.1, y=0.6)
    landmarks[5] = SimpleNamespace(x=x + 0.03, y=0.5)
    landmarks[4] = SimpleNamespace(x=x + 0.06, y=0.55)
    for tip, pip in zip((8, 12, 16, 20), (6, 10, 14, 18)):
        landmarks[tip] = SimpleNamespace(x=x, y=0.3)
        landmarks[pip] = SimpleNamespace(x=x, y=0.5)
    return SimpleNamespace(landmark=landmarks)


class SceneHarness:
    def __init__(self, *, reads=None, events=None, times=None):
        self.trace = []
        self.screen = mock.MagicMock()
        self.screen.get_size.return_value = (30, 30)
        self.camera_surface = mock.sentinel.camera_surface
        self.screen.blit.side_effect = lambda surface, *_args: (
            self.trace.append("camera") if surface is self.camera_surface else None
        )
        self.clock = mock.MagicMock()
        self.clock.get_time.return_value = 16
        self.cap = mock.MagicMock()
        self.cap.isOpened.return_value = True
        self.cap.read.side_effect = reads or [(True, object())]
        self.hands = mock.MagicMock()
        self.hands.process.return_value = SimpleNamespace(multi_hand_landmarks=None)
        self.atexit = mock.MagicMock()
        self.first = mock.Mock(side_effect=lambda *_args, **kwargs: (
            self.trace.append("first") if kwargs.get("frame_processed") else None
        ))
        self.reason = mock.Mock()
        self.font = mock.MagicMock()

        self.pygame = SimpleNamespace(
            QUIT=1, KEYDOWN=2, K_ESCAPE=3, K_q=4,
            init=mock.Mock(), quit=mock.Mock(), Color=mock.Mock(return_value=mock.MagicMock()),
            draw=SimpleNamespace(line=mock.Mock(), circle=mock.Mock()),
            image=SimpleNamespace(frombuffer=mock.Mock(return_value=self.camera_surface)),
            display=SimpleNamespace(flip=mock.Mock(side_effect=lambda: self.trace.append("flip"))),
            event=SimpleNamespace(get=mock.Mock(side_effect=events or [[], [SimpleNamespace(type=1)]])),
            time=SimpleNamespace(Clock=mock.Mock(return_value=self.clock), get_ticks=mock.Mock(return_value=0)),
            font=SimpleNamespace(SysFont=mock.Mock(return_value=self.font)),
        )
        self.stage_frame = mock.MagicMock()
        self.stage_frame.tobytes.return_value = b"rgb"
        self.display = SimpleNamespace(
            setup_pygame_fullscreen=mock.Mock(return_value=(self.screen, (30, 30))),
            open_camera=mock.Mock(return_value=self.cap),
            prepare_camera_frame=mock.Mock(return_value=(object(), self.stage_frame, {
                "offset_x": 0, "offset_y": 0, "scaled_width": 30, "scaled_height": 30,
            })),
            normalized_to_stage=mock.Mock(side_effect=lambda x, y, _layout: (round(x * 29), round(y * 29))),
        )
        self.stage_rgb = mock.MagicMock()
        self.stage_rgb.tobytes.return_value = b"rgb"
        self.cv2 = SimpleNamespace(
            COLOR_BGR2RGB=1,
            cvtColor=mock.Mock(side_effect=lambda value, _code: (
                self.stage_rgb if value is self.stage_frame else object()
            )),
        )
        self.mp = SimpleNamespace(solutions=SimpleNamespace(hands=SimpleNamespace(
            Hands=mock.Mock(return_value=self.hands),
        )))
        self.time = SimpleNamespace(monotonic=mock.Mock(side_effect=times or [0]))

    def run(self, *, finger_params=None):
        shallow = {count: (0.7, 0.75, 1) for count in range(6)}
        if finger_params is None:
            finger_params = shallow
        with (
            mock.patch.object(scene, "pygame", self.pygame),
            mock.patch.object(scene, "display_utils", self.display),
            mock.patch.object(scene, "cv2", self.cv2),
            mock.patch.object(scene, "mp", self.mp),
            mock.patch.object(scene, "time", self.time),
            mock.patch.object(scene, "atexit", self.atexit),
            mock.patch.object(scene, "notify_first_frame", self.first),
            mock.patch.object(scene, "notify_exit_request", self.reason),
            mock.patch.object(scene, "FINGER_PARAMS", finger_params),
        ):
            scene.main()


class TreeSceneTests(unittest.TestCase):
    def test_finger_count_keeps_the_existing_zero_to_five_range(self):
        self.assertEqual(scene.count_raised_fingers(neutral_hand()), 5)
        folded = neutral_hand()
        folded.landmark[4].x = folded.landmark[5].x
        for tip, pip in zip((8, 12, 16, 20), (6, 10, 14, 18)):
            folded.landmark[tip].y = folded.landmark[pip].y + 0.1
        self.assertEqual(scene.count_raised_fingers(folded), 0)

    def test_hand_targets_and_their_mirror_use_the_same_stage_layout(self):
        layout = {"offset_x": 100, "offset_y": 0, "scaled_width": 400, "scaled_height": 300}
        hand = neutral_hand()
        with mock.patch.object(
            scene.display_utils,
            "normalized_to_stage",
            side_effect=lambda x, y, _layout: (100 + round(x * 399), round(y * 299)),
        ):
            raised = scene.get_raised_fingers_dict(hand, 800, 600, layout)
        self.assertIn(0, raised)
        self.assertIn(1, raised)
        x = raised[1][0]
        self.assertEqual(scene._mirrored_stage_x(x, 800, layout), 599 - x)

    def test_one_hand_side_selection_is_stable_near_the_center(self):
        self.assertEqual(scene.choose_single_hand_base_path(None, 0.49), "L")
        self.assertEqual(scene.choose_single_hand_base_path("L", 0.59), "L")
        self.assertEqual(scene.choose_single_hand_base_path("L", 0.61), "R")
        self.assertEqual(scene.choose_single_hand_base_path("R", 0.41), "R")
        self.assertEqual(scene.choose_single_hand_base_path("R", 0.39), "L")

    def test_recursive_branch_count_and_target_marker_are_preserved(self):
        pygame_stub = SimpleNamespace(
            Color=mock.Mock(return_value=mock.MagicMock()),
            draw=SimpleNamespace(line=mock.Mock(), circle=mock.Mock()),
        )
        screen = mock.Mock()
        with mock.patch.object(scene, "pygame", pygame_stub):
            scene.draw_tree(
                screen, 100, 200, math.pi / 2, 3, 50, 0, math.pi / 4, 0.75,
                "", {"R": (120, 100)}, "R",
            )
        self.assertEqual(pygame_stub.draw.line.call_count, 7)
        pygame_stub.draw.circle.assert_called_once_with(screen, (255, 255, 255), (120, 100), 8, 0)

    def test_successful_draw_notifies_after_present_and_cleans_up(self):
        harness = SceneHarness()
        harness.run()
        self.assertEqual(harness.trace, ["camera", "flip", "first"])
        harness.screen.blit.assert_any_call(harness.camera_surface, (0, 0))
        harness.first.assert_called_once_with(harness.cap, frame_processed=True)
        harness.reason.assert_called_once_with("pygame_quit")
        harness.cap.release.assert_called_once()
        harness.hands.close.assert_called_once()
        harness.pygame.quit.assert_called_once()

    def test_one_hand_controls_density_and_mirrored_branch_targets(self):
        harness = SceneHarness()
        harness.hands.process.return_value = SimpleNamespace(
            multi_hand_landmarks=[neutral_hand(0.25)]
        )
        actual_params = dict(scene.FINGER_PARAMS)
        with (
            mock.patch.object(scene, "draw_tree") as draw_tree,
            mock.patch.object(scene, "lerp", side_effect=lambda _current, target, _speed, _dt: target),
        ):
            harness.run(finger_params=actual_params)

        self.assertEqual(draw_tree.call_count, 2)
        upper, lower = draw_tree.call_args_list
        self.assertEqual((upper.args[1], upper.args[2]), (15, 15))
        self.assertEqual((lower.args[1], lower.args[2]), (15, 15))
        self.assertEqual((upper.args[4], lower.args[4]), (11, 11))
        self.assertEqual((upper.args[9], lower.args[9]), ("L", "R"))
        targets = upper.args[10]
        self.assertIs(targets, lower.args[10])
        self.assertEqual((upper.args[11], lower.args[11]), ("L", "L"))
        self.assertEqual(set(targets), {"L", "R", "LL", "RR", "LR", "RL"})
        self.assertEqual(targets["R"][0], 29 - targets["L"][0])
        self.assertEqual(targets["RR"][0], 29 - targets["LL"][0])
        self.assertEqual(targets["RL"][0], 29 - targets["LR"][0])

    def test_two_hands_draw_separate_compact_fractals(self):
        harness = SceneHarness()
        harness.hands.process.return_value = SimpleNamespace(
            multi_hand_landmarks=[neutral_hand(0.75), neutral_hand(0.25)]
        )
        actual_params = dict(scene.FINGER_PARAMS)
        with (
            mock.patch.object(scene, "draw_tree") as draw_tree,
            mock.patch.object(scene, "lerp", side_effect=lambda _current, target, _speed, _dt: target),
        ):
            harness.run(finger_params=actual_params)

        self.assertEqual(draw_tree.call_count, 4)
        first_up, first_down, second_up, second_down = draw_tree.call_args_list
        self.assertEqual((first_up.args[4], first_down.args[4]), (10, 10))
        self.assertEqual((second_up.args[4], second_down.args[4]), (10, 10))
        self.assertEqual((first_up.args[9], first_down.args[9]), ("L", "R"))
        self.assertEqual((second_up.args[9], second_down.args[9]), ("L", "R"))
        self.assertEqual(first_up.args[10], {})
        self.assertEqual(second_up.args[10], {})
        self.assertNotEqual(first_up.args[1:3], second_up.args[1:3])
        self.assertEqual(first_up.args[6], 0)
        self.assertEqual(second_up.args[6], 120)
        harness.font.render.assert_not_called()

    def test_short_camera_gap_keeps_drawing_but_does_not_claim_a_first_frame(self):
        harness = SceneHarness(
            reads=[(False, None), (True, object())],
            events=[[], [], [SimpleNamespace(type=1)]],
            times=[0],
        )
        harness.run()
        self.assertEqual(harness.trace, ["flip", "camera", "flip", "first"])
        harness.first.assert_has_calls([
            mock.call(harness.cap, frame_processed=False),
            mock.call(harness.cap, frame_processed=True),
        ])
        harness.reason.assert_called_once_with("pygame_quit")

    def test_persistent_camera_failure_times_out_and_releases(self):
        harness = SceneHarness(
            reads=[(False, None), (False, None), (False, None)],
            events=[[], [], []],
            times=[0.0, 0.5, 1.01],
        )
        harness.run()
        self.assertEqual(harness.pygame.display.flip.call_count, 2)
        harness.first.assert_has_calls([
            mock.call(harness.cap, frame_processed=False),
            mock.call(harness.cap, frame_processed=False),
        ])
        harness.reason.assert_called_once_with("camera_read_failed_timeout")
        harness.cap.release.assert_called_once()
        harness.hands.close.assert_called_once()

    def test_true_read_with_no_frame_is_not_reported_as_processed(self):
        harness = SceneHarness(
            reads=[(True, None), (True, object())],
            events=[[], [], [SimpleNamespace(type=1)]],
            times=[0],
        )
        harness.run()
        self.assertEqual(harness.trace, ["flip", "camera", "flip", "first"])
        harness.first.assert_has_calls([
            mock.call(harness.cap, frame_processed=False),
            mock.call(harness.cap, frame_processed=True),
        ])


if __name__ == "__main__":
    unittest.main()
