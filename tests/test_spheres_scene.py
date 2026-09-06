"""Run the actual scene loop with native display/camera/rendering boundaries faked."""

import ast
from contextlib import ExitStack
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from spheres_camera import CameraSnapshot
from spheres_visuals import TipSmoother


ROOT = Path(__file__).resolve().parents[1]
SCREEN_SIZE = (16, 9)


def snapshot(frame_id=1, tips=((4, 3),)):
    return CameraSnapshot(
        timestamp=100.0,
        rgb_bytes=bytes((frame_id, 20, 30)) * (SCREEN_SIZE[0] * SCREEN_SIZE[1]),
        size=SCREEN_SIZE,
        tips=tips,
        last_read_frame_id=frame_id,
        shm_name="fake-manager-shared-camera",
    )


class FakeScene:
    def __init__(self, snapshots, events=None):
        self.calls = []
        self.screen = mock.Mock()
        self.screen.get_size.return_value = SCREEN_SIZE
        self.screen.fill.side_effect = self.record("fill")
        self.screen.blit.side_effect = self.record("camera_blit")
        self.camera_surface = mock.Mock()
        self.frombuffer = mock.Mock(side_effect=self.record("camera_surface", self.camera_surface))
        self.flip = mock.Mock(side_effect=self.record("flip"))
        self.tick = mock.Mock(side_effect=self.record("tick"))
        self.pygame = SimpleNamespace(
            QUIT=1, KEYDOWN=2, K_ESCAPE=27, K_q=113,
            init=mock.Mock(side_effect=self.record("pygame_init")),
            quit=mock.Mock(side_effect=self.record("pygame_quit")),
            display=SimpleNamespace(flip=self.flip, set_caption=mock.Mock()),
            image=SimpleNamespace(frombuffer=self.frombuffer),
            time=SimpleNamespace(Clock=mock.Mock(return_value=SimpleNamespace(tick=self.tick))),
            event=SimpleNamespace(get=mock.Mock(side_effect=(
                events if events is not None else [[] for _ in snapshots] + [[SimpleNamespace(type=1)]]))),
        )
        self.display = SimpleNamespace(setup_pygame_fullscreen=mock.Mock(
            return_value=(self.screen, (1360, 800))))
        self.feed = mock.Mock()
        self.feed.start.side_effect = self.record("feed_start")
        self.feed.close.side_effect = self.record("feed_close")
        self.feed.latest.side_effect = list(snapshots)
        self.make_feed = mock.Mock(return_value=self.feed)
        self.renderer = mock.Mock(field=SimpleNamespace(particle_count=9600))
        self.renderer.draw.side_effect = self.record("draw", 9600)
        self.make_renderer = mock.Mock(return_value=self.renderer)
        self.notify_frame = mock.Mock(side_effect=self.record("notify_frame"))
        self.notify_exit = mock.Mock(side_effect=self.record("notify_exit"))
        timestamps = iter([100.0] + [100.0 + (i + 1) / 60 for i in range(len(snapshots))])
        namespace = dict(
            ExitStack=ExitStack, json=json,
            time=SimpleNamespace(monotonic=lambda: next(timestamps)),
            SpheresCameraFeed=self.make_feed, SphereRenderer=self.make_renderer,
            TipSmoother=TipSmoother,
            notify_first_frame=self.notify_frame, notify_exit_request=self.notify_exit,
        )
        source = ROOT / "colorfull_dots_spheres.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        exec(compile(ast.Module(body=[main], type_ignores=[]), str(source), "exec"), namespace)
        self.main = namespace["main"]

    def record(self, name, result=None, failure=None):
        def call(*_args, **_kwargs):
            self.calls.append(name)
            if failure is not None:
                raise failure
            return result
        return call

    def run(self):
        # Unexpected native imports fail instead of reaching a camera, window, or GPU.
        with mock.patch.dict(sys.modules, {
            "pygame": self.pygame, "display_utils": self.display,
            "cv2": None, "mediapipe": None, "numpy": None, "wgpu": None, "glfw": None,
        }):
            self.main()


class SpheresSceneTests(unittest.TestCase):
    def assert_all_resources_closed(self, scene):
        scene.feed.close.assert_called_once_with()
        scene.pygame.quit.assert_called_once_with()
        self.assertLess(scene.calls.index("feed_close"), scene.calls.index("pygame_quit"))

    def test_animation_keeps_drawing_without_a_camera_snapshot_and_never_acknowledges_it(self):
        scene = FakeScene([None, None, None])
        scene.run()
        self.assertEqual(scene.renderer.draw.call_count, 3)
        self.assertEqual(scene.flip.call_count, 3)
        self.assertEqual(scene.tick.call_count, 3)
        for call in scene.renderer.draw.call_args_list:
            self.assertEqual(call.args[2], ())
        self.assertGreater(scene.renderer.draw.call_args_list[-1].args[1],
                           scene.renderer.draw.call_args_list[0].args[1])
        scene.frombuffer.assert_not_called()
        scene.screen.blit.assert_not_called()
        scene.notify_frame.assert_not_called()
        scene.make_feed.assert_called_once_with(*SCREEN_SIZE)
        self.assert_all_resources_closed(scene)

    def test_real_snapshot_is_acknowledged_only_after_its_background_draw_and_flip(self):
        frame = snapshot()
        scene = FakeScene([None, frame, frame])
        scene.run()
        scene.frombuffer.assert_called_once_with(frame.rgb_bytes, frame.size, "RGB")
        scene.notify_frame.assert_called_once_with(frame, frame_processed=True)
        self.assertIs(scene.notify_frame.call_args.args[0], frame)
        self.assertEqual(scene.renderer.draw.call_args_list[1].args[2], frame.tips)
        relevant = [call for call in scene.calls
                    if call in {"camera_blit", "draw", "flip", "notify_frame"}]
        self.assertEqual(relevant, [
            "draw", "flip",
            "camera_blit", "draw", "flip", "notify_frame",
            "camera_blit", "draw", "flip",
        ])
        self.assert_all_resources_closed(scene)

    def test_lost_snapshot_removes_camera_and_tips_then_a_new_snapshot_can_be_presented(self):
        first, recovered = snapshot(), snapshot(2, ((12, 6),))
        scene = FakeScene([first, None, recovered])
        scene.run()
        self.assertEqual(scene.screen.blit.call_count, 2)
        self.assertEqual(scene.renderer.draw.call_args_list[1].args[2], ())
        self.assertEqual(scene.renderer.draw.call_args_list[2].args[2], recovered.tips)
        self.assertEqual(scene.notify_frame.call_args_list,
                         [mock.call(first, frame_processed=True), mock.call(recovered, frame_processed=True)])
        self.assert_all_resources_closed(scene)

    def test_quit_before_the_first_draw_never_reads_or_acknowledges_a_snapshot(self):
        scene = FakeScene([snapshot()], events=[[SimpleNamespace(type=1)]])
        scene.run()
        scene.feed.latest.assert_not_called()
        scene.renderer.draw.assert_not_called()
        scene.flip.assert_not_called()
        scene.notify_frame.assert_not_called()
        scene.tick.assert_not_called()
        scene.notify_exit.assert_called_once_with("pygame_quit")
        self.assert_all_resources_closed(scene)

    def test_exit_events_stop_before_the_next_camera_frame_is_presented(self):
        first, next_frame = snapshot(), snapshot(2)
        exits = ((SimpleNamespace(type=1), "pygame_quit"),
                 (SimpleNamespace(type=2, key=27), "key_escape"),
                 (SimpleNamespace(type=2, key=113), "key_q"))
        for event, reason in exits:
            with self.subTest(reason=reason):
                scene = FakeScene([first, next_frame], events=[[], [event]])
                scene.run()
                scene.feed.latest.assert_called_once_with()
                scene.renderer.draw.assert_called_once()
                scene.flip.assert_called_once_with()
                scene.notify_frame.assert_called_once_with(first, frame_processed=True)
                scene.notify_exit.assert_called_once_with(reason)
                self.assert_all_resources_closed(scene)

    def test_display_initialization_errors_quit_pygame_without_constructing_a_feed(self):
        for boundary in ("pygame_init", "window", "screen_size", "caption"):
            with self.subTest(boundary=boundary):
                scene = FakeScene([snapshot()])
                failure = RuntimeError("injected display failure: " + boundary)
                operation = {
                    "pygame_init": scene.pygame.init,
                    "window": scene.display.setup_pygame_fullscreen,
                    "screen_size": scene.screen.get_size,
                    "caption": scene.pygame.display.set_caption,
                }[boundary]
                operation.side_effect = failure
                with self.assertRaises(RuntimeError) as caught:
                    scene.run()
                self.assertIs(caught.exception, failure)
                scene.make_feed.assert_not_called()
                scene.feed.close.assert_not_called()
                scene.notify_frame.assert_not_called()
                scene.pygame.quit.assert_called_once_with()

    def test_acquired_feed_and_pygame_are_closed_after_startup_or_frame_failure(self):
        for boundary in ("feed_start", "renderer", "snapshot", "image", "draw", "flip"):
            with self.subTest(boundary=boundary):
                scene = FakeScene([snapshot()])
                failure = RuntimeError("injected frame failure: " + boundary)
                operation = {
                    "feed_start": scene.feed.start,
                    "renderer": scene.make_renderer,
                    "snapshot": scene.feed.latest,
                    "image": scene.frombuffer,
                    "draw": scene.renderer.draw,
                    "flip": scene.flip,
                }[boundary]
                operation.side_effect = failure
                with self.assertRaises(RuntimeError) as caught:
                    scene.run()
                self.assertIs(caught.exception, failure)
                scene.notify_frame.assert_not_called()
                self.assert_all_resources_closed(scene)

    def test_feed_close_failure_does_not_skip_pygame_quit(self):
        scene = FakeScene([None])
        failure = RuntimeError("injected feed close failure")
        scene.feed.close.side_effect = scene.record("feed_close", failure=failure)
        with self.assertRaises(RuntimeError) as caught:
            scene.run()
        self.assertIs(caught.exception, failure)
        self.assert_all_resources_closed(scene)

    def test_draw_and_cleanup_failures_still_attempt_every_acquired_cleanup(self):
        scene = FakeScene([snapshot()])
        original = RuntimeError("injected draw failure")
        scene.renderer.draw.side_effect = original
        scene.feed.close.side_effect = scene.record("feed_close", failure=RuntimeError("feed close failed"))
        scene.pygame.quit.side_effect = scene.record("pygame_quit", failure=RuntimeError("pygame quit failed"))
        with self.assertRaises(RuntimeError) as caught:
            scene.run()
        self.assertIs(caught.exception, original)
        notes = " ".join(original.__notes__)
        self.assertIn("feed close failed", notes)
        self.assertIn("pygame quit failed", notes)
        scene.notify_frame.assert_not_called()
        self.assert_all_resources_closed(scene)


if __name__ == "__main__":
    unittest.main()
