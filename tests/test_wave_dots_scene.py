import ast
from contextlib import ExitStack
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from types import ModuleType
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
scene = ModuleType("colorfull_wave_dots_test_target")
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
tree = ast.parse((ROOT / "colorfull_wave_dots.py").read_text(encoding="utf-8"))
definitions = [node for node in tree.body if isinstance(node, (ast.Assign, ast.FunctionDef))]
exec(compile(ast.Module(body=definitions, type_ignores=[]), "colorfull_wave_dots.py", "exec"), scene.__dict__)


def hand(*, thumb=(0.1, 0.2), index=(0.8, 0.4)):
    landmarks = [SimpleNamespace(x=0.5, y=0.5) for _ in range(21)]
    landmarks[4] = SimpleNamespace(x=thumb[0], y=thumb[1])
    landmarks[8] = SimpleNamespace(x=index[0], y=index[1])
    return SimpleNamespace(landmark=landmarks)


class SceneHarness:
    def __init__(self, *, reads=None, events=None, times=None):
        self.trace = []
        self.screen = mock.MagicMock()
        self.screen.get_size.return_value = (30, 30)
        self.screen.blit.side_effect = lambda *_args: self.trace.append("camera")
        self.clock = mock.MagicMock()
        self.cap = mock.MagicMock()
        self.cap.isOpened.return_value = True
        self.cap.read.side_effect = reads or [(True, object())]
        self.hands = mock.MagicMock()
        self.hands.process.return_value = SimpleNamespace(multi_hand_landmarks=None)
        self.atexit = mock.MagicMock()
        self.first = mock.Mock(side_effect=lambda *_args, **_kwargs: self.trace.append("first"))
        self.reason = mock.Mock()

        color = mock.MagicMock()
        self.pygame = SimpleNamespace(
            QUIT=1,
            KEYDOWN=2,
            K_ESCAPE=3,
            K_q=4,
            init=mock.Mock(),
            quit=mock.Mock(),
            Color=mock.Mock(return_value=color),
            draw=SimpleNamespace(rect=mock.Mock(), circle=mock.Mock(), line=mock.Mock()),
            image=SimpleNamespace(frombuffer=mock.Mock(return_value=mock.sentinel.camera_surface)),
            display=SimpleNamespace(
                flip=mock.Mock(side_effect=lambda: self.trace.append("flip")),
            ),
            event=SimpleNamespace(get=mock.Mock(side_effect=events or [[], [SimpleNamespace(type=1)]])),
            time=SimpleNamespace(Clock=mock.Mock(return_value=self.clock)),
        )
        self.display = SimpleNamespace(
            setup_pygame_fullscreen=mock.Mock(return_value=(self.screen, (30, 30))),
            open_camera=mock.Mock(return_value=self.cap),
            prepare_camera_frame=mock.Mock(return_value=(object(), object(), {"layout": True})),
            normalized_to_stage=mock.Mock(side_effect=lambda x, y, _layout: (round(x * 30), round(y * 30))),
        )
        self.stage_rgb = mock.Mock()
        self.stage_rgb.tobytes.return_value = b"stage rgb"
        self.cv2 = SimpleNamespace(
            COLOR_BGR2RGB=1,
            cvtColor=mock.Mock(side_effect=[object(), self.stage_rgb]),
        )
        self.mp = SimpleNamespace(solutions=SimpleNamespace(hands=SimpleNamespace(
            Hands=mock.Mock(return_value=self.hands),
        )))
        self.time = SimpleNamespace(monotonic=mock.Mock(side_effect=times or [0]))

    def run(self):
        with (
            mock.patch.object(scene, "pygame", self.pygame),
            mock.patch.object(scene, "display_utils", self.display),
            mock.patch.object(scene, "cv2", self.cv2),
            mock.patch.object(scene, "mp", self.mp),
            mock.patch.object(scene, "time", self.time),
            mock.patch.object(scene, "atexit", self.atexit),
            mock.patch.object(scene, "notify_first_frame", self.first),
            mock.patch.object(scene, "notify_exit_request", self.reason),
        ):
            scene.main()


class WaveDotsSceneTests(unittest.TestCase):
    def test_grid_density_and_original_particle_force_are_preserved(self):
        particles = scene.create_particles(30, 30)
        self.assertEqual(len(particles), 4)
        particle = particles[0]
        scene.update_particle(particle, [{"x": 50, "y": 0, "down": False}])
        self.assertAlmostEqual(particle["x"], -9.2)
        self.assertAlmostEqual(particle["vx"], -9.2)
        self.assertEqual(particle["pinch_effect"], 0.0)

        pinched = scene.create_particles(15, 15)[0]
        scene.update_particle(pinched, [{"x": 50, "y": 0, "down": True}])
        self.assertAlmostEqual(pinched["x"], -46.0)
        self.assertAlmostEqual(pinched["pinch_effect"], 0.95)

    def test_all_five_fingertips_share_the_hand_pinch_and_stage_mapping(self):
        layout = {"offset_x": 3, "offset_y": 4, "scaled_width": 100, "scaled_height": 50}
        with mock.patch.object(
            scene.display_utils,
            "normalized_to_stage",
            side_effect=lambda x, y, _layout: (round(x * 100), round(y * 50)),
        ) as project:
            active = scene.collect_active_fingertips(
                SimpleNamespace(multi_hand_landmarks=[hand(thumb=(0.10, 0.20), index=(0.12, 0.22))]),
                1920,
                1080,
                layout,
            )
        self.assertEqual(len(active), 5)
        self.assertTrue(all(item["down"] for item in active))
        self.assertEqual(project.call_count, 5)
        self.assertEqual(active[1]["x"], 12)
        self.assertEqual(active[1]["y"], 11)

    def test_successful_draw_notifies_after_present_and_releases_resources(self):
        harness = SceneHarness()
        harness.run()
        self.assertEqual(harness.trace, ["camera", "flip", "first"])
        harness.pygame.image.frombuffer.assert_called_once_with(
            harness.stage_rgb.tobytes.return_value, (30, 30), "RGB"
        )
        harness.screen.blit.assert_called_once_with(mock.sentinel.camera_surface, (0, 0))
        harness.first.assert_called_once_with(harness.cap, frame_processed=True)
        harness.reason.assert_called_once_with("pygame_quit")
        harness.cap.release.assert_called_once()
        harness.hands.close.assert_called_once()
        harness.pygame.quit.assert_called_once()
        harness.atexit.unregister.assert_called_once_with(harness.atexit.register.call_args.args[0])

    def test_camera_failure_has_a_bounded_retry_without_false_first_frame(self):
        harness = SceneHarness(
            reads=[(False, None), (False, None), (False, None)],
            events=[[], [], []],
            times=[0.0, 0.5, 1.01],
        )
        harness.run()
        harness.first.assert_not_called()
        harness.pygame.display.flip.assert_not_called()
        harness.reason.assert_called_once_with("camera_read_failed_timeout")
        harness.cap.release.assert_called_once()
        harness.hands.close.assert_called_once()

    def test_initialization_failure_releases_already_created_resources(self):
        harness = SceneHarness()
        harness.cap.isOpened.return_value = False
        with self.assertRaisesRegex(RuntimeError, "shared camera"):
            harness.run()
        harness.cap.release.assert_called_once()
        harness.hands.close.assert_called_once()
        harness.pygame.quit.assert_called_once()
        harness.first.assert_not_called()

    def test_processing_or_present_failure_never_claims_a_first_frame(self):
        for operation in ("process", "flip"):
            with self.subTest(operation=operation):
                harness = SceneHarness()
                failure = RuntimeError(f"{operation} failed")
                if operation == "process":
                    harness.hands.process.side_effect = failure
                else:
                    harness.pygame.display.flip.side_effect = failure
                with self.assertRaisesRegex(RuntimeError, f"{operation} failed"):
                    harness.run()
                harness.first.assert_not_called()
                harness.cap.release.assert_called_once()
                harness.hands.close.assert_called_once()
                harness.pygame.quit.assert_called_once()

    def test_escape_exits_without_an_extra_camera_read(self):
        harness = SceneHarness(events=[[SimpleNamespace(type=2, key=3)]])
        harness.run()
        harness.cap.read.assert_not_called()
        harness.first.assert_not_called()
        harness.reason.assert_called_once_with("key_escape")


if __name__ == "__main__":
    unittest.main()
