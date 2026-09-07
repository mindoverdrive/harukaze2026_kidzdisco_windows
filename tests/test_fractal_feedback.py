"""Exercise the scene's actual functions and loop without a camera or SDL window."""
import ast
from contextlib import ExitStack
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "fractal_moving_2.py"


def load_scene_functions(namespace):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    selected = [node for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                and node.name in {"Pointer", "draw_pointer_feedback", "main"}]
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


class FractalFeedbackTests(unittest.TestCase):
    def test_marker_uses_actual_fingertip_instead_of_eased_artwork_position(self):
        pygame = mock.Mock()
        scene = load_scene_functions({"pygame": pygame})
        for kind in range(4):
            with self.subTest(kind=kind):
                pointer = scene["Pointer"](25, 35, kind)
                pointer.has_target = True
                pointer.target_x, pointer.target_y = 180.4, 91.7
                pygame.draw.circle.reset_mock()
                scene["draw_pointer_feedback"](mock.sentinel.screen, pointer, 0.02)
                calls = pygame.draw.circle.call_args_list
                self.assertEqual(len(calls), 2)
                self.assertTrue(all(call.args[2] == (180, 92) for call in calls))
                self.assertTrue(any(call.args[1] == (255, 255, 255) for call in calls))
                self.assertEqual((pointer.current_x, pointer.current_y), (25, 35))

    def test_lost_hand_has_no_marker_or_ripple(self):
        pygame = mock.Mock()
        scene = load_scene_functions({"pygame": pygame})
        pointer = scene["Pointer"](25, 35, 0)
        pointer.feedback_age = 0.0
        scene["draw_pointer_feedback"](mock.sentinel.screen, pointer, 0.1)
        pygame.draw.circle.assert_not_called()

    def test_entry_ripple_expands_and_fades_then_leaves_only_the_fingertip(self):
        pygame = mock.Mock()
        scene = load_scene_functions({"pygame": pygame})
        pointer = scene["Pointer"](25, 35, 1)
        pointer.has_target = True
        pointer.feedback_age = 0.0
        samples = []
        for _ in range(8):
            pygame.draw.circle.reset_mock()
            scene["draw_pointer_feedback"](mock.sentinel.screen, pointer, 0.1)
            samples.append(pygame.draw.circle.call_args_list)
        self.assertEqual(len(samples[0]), 3)
        self.assertGreater(samples[2][-1].args[3], samples[0][-1].args[3])
        self.assertLess(sum(samples[2][-1].args[1]), sum(samples[0][-1].args[1]))
        self.assertEqual([len(calls) for calls in samples[-3:]], [2, 2, 2])
        self.assertTrue(all(calls[1].args[1] == (255, 255, 255) for calls in samples))

    def run_loop(self, *, frames=(True,), detections=None, exit_kind="quit", flip_error=False):
        timeline = []
        frame_index = -1

        def record(kind, *values):
            timeline.append((frame_index, kind, *values))

        def read_frame():
            nonlocal frame_index
            frame_index += 1
            return frames[frame_index], mock.sentinel.camera_frame

        screen = mock.Mock()
        screen.get_size.return_value = (640, 360)
        screen.blit.side_effect = lambda surface, position: record("blit", surface)
        screen.fill.side_effect = lambda color: record("clear", color)
        pygame = mock.Mock(QUIT=1, KEYDOWN=2, VIDEORESIZE=3, K_ESCAPE=27, K_q=113)
        event = SimpleNamespace(type=pygame.QUIT)
        if exit_kind != "quit":
            event = SimpleNamespace(type=pygame.KEYDOWN,
                                    key=pygame.K_ESCAPE if exit_kind == "escape" else pygame.K_q)
        pygame.event.get.side_effect = [[] for _ in frames] + [[event]]
        # The trail surface needs fill(), but cannot create an actual SDL surface.
        trails = mock.Mock()
        pygame.Surface.return_value = trails
        pygame.image.frombuffer.return_value = mock.sentinel.camera_surface
        pygame.time.Clock.return_value.get_time.return_value = 16
        pygame.draw.circle.side_effect = lambda *args: record("circle", *args)

        def flip():
            record("flip")
            if flip_error:
                raise RuntimeError("injected display failure")

        pygame.display.flip.side_effect = flip
        cap = mock.Mock()
        cap.isOpened.return_value = True
        cap.read.side_effect = read_frame
        hands = mock.Mock()
        points_by_frame = detections if detections is not None else [[(0.2, 0.4)] for _ in frames]

        def detect(_frame):
            points = points_by_frame[frame_index]
            return SimpleNamespace(multi_hand_landmarks=[
                SimpleNamespace(landmark={8: SimpleNamespace(x=x, y=y)}) for x, y in points
            ])

        hands.process.side_effect = detect
        mp = mock.Mock()
        mp.solutions.hands.Hands.return_value = hands
        mp.solutions.hands.HandLandmark.INDEX_FINGER_TIP = 8
        display = mock.Mock()
        display.setup_pygame_fullscreen.return_value = (screen, (640, 360))
        display.open_camera.return_value = cap
        display.prepare_camera_frame.return_value = (object(), object(), object())
        display.normalized_to_stage.side_effect = lambda x, y, layout: (x * 640, y * 360)
        cv2 = mock.Mock()
        cv2.cvtColor.return_value.tobytes.return_value = b"fixture"
        notify = mock.Mock(side_effect=lambda cap, **kwargs: record("first_frame", kwargs["frame_processed"]))
        notify_exit = mock.Mock()
        atexit = mock.Mock()
        scene = load_scene_functions(dict(
            pygame=pygame, display_utils=display, cv2=cv2, mp=mp, math=math,
            ExitStack=ExitStack, atexit=atexit, sys=mock.Mock(),
            notify_first_frame=notify, notify_exit_request=notify_exit,
            draw_fractal=mock.Mock(side_effect=lambda *args: record("art", args[1], args[2])),
        ))
        scene["sys"].exit.side_effect = SystemExit(0)
        try:
            with self.assertRaises(RuntimeError if flip_error else SystemExit) as raised:
                scene["main"]()
            if not flip_error:
                self.assertEqual(raised.exception.code, 0)
                cap.release.assert_called_once_with()
                hands.close.assert_called_once_with()
                pygame.quit.assert_called_once_with()
        finally:
            # Execute the registered close callback as process exit would, including errors.
            for call in atexit.register.call_args_list:
                call.args[0]()
        cap.release.assert_called_once_with()
        hands.close.assert_called_once_with()
        pygame.quit.assert_called_once_with()
        return dict(timeline=timeline, cap=cap, hands=hands, pygame=pygame,
                    notify=notify, notify_exit=notify_exit, trails=trails)

    def test_first_frame_is_notified_after_camera_artwork_feedback_and_display_flip(self):
        result = self.run_loop()
        events = result["timeline"]
        camera_index = next(i for i, event in enumerate(events)
                            if event[1:] == ("blit", mock.sentinel.camera_surface))
        art_index = next(i for i, event in enumerate(events) if event[1] == "art")
        trail_index = next(i for i, event in enumerate(events)
                           if event[1:] == ("blit", result["trails"]))
        feedback_index = next(i for i, event in enumerate(events) if event[1] == "circle")
        flip_index = next(i for i, event in enumerate(events) if event[1] == "flip")
        notified_index = next(i for i, event in enumerate(events) if event[1] == "first_frame")
        self.assertLess(camera_index, art_index)
        self.assertLess(art_index, trail_index)
        self.assertLess(trail_index, feedback_index)
        self.assertLess(feedback_index, flip_index)
        self.assertLess(flip_index, notified_index)
        result["notify"].assert_called_once_with(result["cap"], frame_processed=True)

    def test_render_failure_cannot_report_first_frame(self):
        result = self.run_loop(flip_error=True)
        result["notify"].assert_not_called()

    def test_read_failure_removes_stale_camera_image_and_pointer_feedback(self):
        result = self.run_loop(frames=(True, False))
        failed_frame = [event for event in result["timeline"] if event[0] == 1]
        self.assertIn((1, "clear", (0, 0, 0)), failed_frame)
        self.assertNotIn((1, "blit", mock.sentinel.camera_surface), failed_frame)
        self.assertFalse(any(event[1] in {"circle", "art"} for event in failed_frame))
        result["hands"].process.assert_called_once()
        self.assertEqual([call.kwargs["frame_processed"] for call in result["notify"].call_args_list],
                         [True, False])

    def test_marker_stays_on_fingertip_while_fractal_eases_toward_it(self):
        result = self.run_loop(frames=(True, True), detections=[[(0.2, 0.4)], [(0.35, 0.4)]])
        second_frame = [event for event in result["timeline"] if event[0] == 1]
        white_core = next(event for event in second_frame
                          if event[1] == "circle" and event[3] == (255, 255, 255))
        art = next(event for event in second_frame if event[1] == "art")
        self.assertEqual(white_core[4], (224, 144))
        self.assertGreater(art[2], 128)
        self.assertLess(art[2], 224)

    def test_lost_and_reacquired_hand_hides_feedback_then_restarts_entry_ripple(self):
        result = self.run_loop(frames=(True, True, True),
                               detections=[[(0.2, 0.4)], [], [(0.2, 0.4)]])
        circles = [[event for event in result["timeline"] if event[0] == index and event[1] == "circle"]
                   for index in range(3)]
        self.assertEqual([len(events) for events in circles], [3, 0, 3])
        self.assertEqual(circles[0][-1][3:], circles[2][-1][3:])

    def test_each_exit_event_reports_reason_and_stops_before_another_camera_read(self):
        for exit_kind, reason in (("quit", "pygame_quit"), ("escape", "escape_key"), ("q", "q_key")):
            with self.subTest(exit_kind=exit_kind):
                result = self.run_loop(frames=(), exit_kind=exit_kind)
                result["notify_exit"].assert_called_once_with(reason)
                result["cap"].read.assert_not_called()
                result["pygame"].display.flip.assert_not_called()
                result["notify"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
