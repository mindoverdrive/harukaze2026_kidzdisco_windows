"""Run Mandala3's real drawing and loop with camera/window substitutes."""
import ast
from contextlib import ExitStack
import math
from pathlib import Path
import runpy
import sys
import traceback
from types import SimpleNamespace
import unittest
from unittest import mock

import scene_profile_runner


ROOT = Path(__file__).resolve().parents[1]


def hand(x, y, wrist=None):
    landmarks = [SimpleNamespace(x=x, y=y) for _ in range(21)]
    if wrist is not None:
        landmarks[0] = SimpleNamespace(x=wrist[0], y=wrist[1])
    return SimpleNamespace(landmark=landmarks)


class SceneHarness:
    def __init__(self, reads=None, observations=None, events=None, times=None):
        reads = reads if reads is not None else [(True, object())]
        self.pygame = mock.MagicMock()
        self.pygame.QUIT, self.pygame.KEYDOWN = 1, 2
        self.pygame.K_ESCAPE, self.pygame.K_q, self.pygame.K_SPACE = 3, 4, 5
        self.screen, self.canvas, self.cursor = (mock.Mock() for _ in range(3))
        self.screen.get_size.return_value = (640, 360)
        self.pygame.Surface.side_effect = [self.canvas, self.cursor]
        self.pygame.event.get.side_effect = events if events is not None else (
            [[] for _ in reads] + [[SimpleNamespace(type=self.pygame.QUIT)]]
        )
        self.cap = mock.Mock()
        self.cap.read.side_effect = reads
        self.hands = mock.Mock()
        successful_reads = sum(bool(ok) for ok, _ in reads)
        observations = observations if observations is not None else [None] * successful_reads
        process_results = []
        for observed in observations:
            labels = [] if not observed else ["Right" if index % 2 == 0 else "Left"
                                               for index in range(len(observed))]
            handedness = [SimpleNamespace(classification=[SimpleNamespace(label=label)])
                          for label in labels]
            process_results.append(SimpleNamespace(
                multi_hand_landmarks=observed, multi_handedness=handedness))
        self.hands.process.side_effect = process_results
        self.display = mock.Mock()
        self.display.setup_pygame_fullscreen.return_value = (self.screen, (640, 360))
        self.display.open_camera.return_value = self.cap
        self.display.prepare_camera_frame.return_value = (object(), object(), object())
        self.display.normalized_to_stage.side_effect = lambda x, y, layout: (round(x * 640), round(y * 360))
        self.first, self.reason = mock.Mock(), mock.Mock()
        self.trace, self.frame_cursor_counts = [], []
        self.cursor_count = 0

        def draw_circle(surface, *_args):
            if surface is self.cursor:
                self.cursor_count += 1

        def clear_cursor(*_args):
            self.cursor_count = 0

        def flip():
            self.trace.append("flip")
            self.frame_cursor_counts.append(self.cursor_count)

        self.pygame.draw.circle.side_effect = draw_circle
        self.cursor.fill.side_effect = clear_cursor
        self.pygame.display.flip.side_effect = flip
        self.pygame.time.get_ticks.return_value = 0
        self.first.side_effect = lambda *_args, **_kwargs: self.trace.append("first")
        self.atexit = mock.Mock()
        self.env = dict(
            ExitStack=ExitStack, atexit=self.atexit, math=math, sys=sys, pygame=self.pygame,
            display_utils=self.display, cv2=mock.MagicMock(),
            time=SimpleNamespace(monotonic=mock.Mock(side_effect=times if times is not None else [0])),
            mp=SimpleNamespace(solutions=SimpleNamespace(hands=SimpleNamespace(
                Hands=mock.Mock(return_value=self.hands)))),
            notify_first_frame=self.first, notify_exit_request=self.reason,
        )
        tree = ast.parse((ROOT / "finger_mandala_3.py").read_text(encoding="utf-8"))
        definitions = [node for node in tree.body if isinstance(node, (ast.Assign, ast.ClassDef, ast.FunctionDef))]
        exec(compile(ast.Module(body=definitions, type_ignores=[]), "finger_mandala_3.py", "exec"), self.env)

    def run(self):
        self.env["main"]()

    def artwork_calls(self, method):
        return [call for call in getattr(self.pygame.draw, method).call_args_list
                if call.args[0] is self.canvas]

    def assert_released(self, test):
        self.cap.release.assert_called_once()
        self.hands.close.assert_called_once()
        self.pygame.quit.assert_called_once()
        self.atexit.unregister.assert_called_once_with(self.atexit.register.call_args.args[0])
        # An atexit callback racing the ordinary close must not release twice.
        self.atexit.register.call_args.args[0]()
        self.cap.release.assert_called_once()
        self.hands.close.assert_called_once()
        self.pygame.quit.assert_called_once()


class Mandala3SceneTests(unittest.TestCase):
    def test_acer_entrypoint_runs_mandala3(self):
        with mock.patch.object(scene_profile_runner, "run_scene") as run_scene:
            runpy.run_path(str(ROOT / "finger_mandala_acer.py"), run_name="__main__")
        run_scene.assert_called_once_with("finger_mandala_3.py", profile="acer")

    def test_first_hand_appearance_draws_symmetric_points_and_notifies_after_display(self):
        scene = SceneHarness(observations=[[hand(.75, .5)]])
        scene.run()
        points = scene.artwork_calls("circle")
        self.assertEqual(len(points), 24)
        self.assertEqual(points[0].args[2], (480, 180))
        self.assertEqual(points[1].args[2], (160, 180))
        self.assertEqual(scene.artwork_calls("line"), [])
        self.assertEqual(scene.frame_cursor_counts, [3])
        self.assertEqual(scene.trace, ["flip", "first"])
        scene.first.assert_called_once_with(scene.cap, frame_processed=True)
        scene.assert_released(self)

    def test_continuous_strokes_keep_twelve_rotations_and_mirrors_for_both_hands(self):
        scene = SceneHarness(
            reads=[(True, object())] * 2,
            observations=[[hand(.75, .5), hand(.1, .1)], [hand(.8, .5), hand(.15, .1)]],
        )
        scene.run()
        lines = scene.artwork_calls("line")
        self.assertEqual(len(lines), 48)
        self.assertEqual(lines[0].args[2:4], ((480.0, 180.0), (512.0, 180.0)))
        self.assertEqual(lines[1].args[2:4], ((160.0, 180.0), (128.0, 180.0)))
        self.assertEqual(scene.display.normalized_to_stage.call_count, 8)
        scene.canvas.fill.assert_called_once_with((0, 0, 0, 0))
        scene.assert_released(self)

    def test_near_opposite_hands_share_participant_and_distant_person_has_other_color(self):
        tracker = SceneHarness().env["ParticipantTracker"]()
        detections = [
            {"tip": (110, 100), "anchor": (100, 150), "label": "Right"},
            {"tip": (185, 100), "anchor": (180, 150), "label": "Left"},
            {"tip": (560, 100), "anchor": (550, 150), "label": "Right"},
        ]
        first = tracker.update(detections, 640)
        self.assertEqual(first[0]["participant"], first[1]["participant"])
        self.assertNotEqual(first[0]["participant"], first[2]["participant"])
        self.assertTrue(all(item["previous"] is None for item in first))

        second = tracker.update(list(reversed([
            {"tip": (115, 103), "anchor": (105, 153), "label": "Right"},
            {"tip": (190, 103), "anchor": (185, 153), "label": "Left"},
            {"tip": (555, 103), "anchor": (545, 153), "label": "Right"},
        ])), 640)
        self.assertEqual([item["participant"] for item in second],
                         [item["participant"] for item in first])
        self.assertTrue(all(item["previous"] is not None for item in second))

    def test_one_persons_far_apart_left_and_right_hands_still_share_color(self):
        tracker = SceneHarness().env["ParticipantTracker"]()
        hands = tracker.update([
            {"tip": (250, 100), "anchor": (220, 160), "label": "Right"},
            {"tip": (1430, 100), "anchor": (1400, 160), "label": "Left"},
        ], 1920)
        self.assertEqual(len(hands), 2)
        self.assertEqual(hands[0]["participant"], hands[1]["participant"])

    def test_two_people_are_paired_by_nearest_opposite_hands(self):
        tracker = SceneHarness().env["ParticipantTracker"]()
        hands = tracker.update([
            {"tip": (110, 100), "anchor": (100, 160), "label": "Right"},
            {"tip": (310, 100), "anchor": (300, 160), "label": "Left"},
            {"tip": (1310, 100), "anchor": (1300, 160), "label": "Right"},
            {"tip": (1510, 100), "anchor": (1500, 160), "label": "Left"},
        ], 1920)
        self.assertEqual(hands[0]["participant"], hands[1]["participant"])
        self.assertEqual(hands[2]["participant"], hands[3]["participant"])
        self.assertNotEqual(hands[0]["participant"], hands[2]["participant"])

    def test_distant_single_hands_stay_separate_then_join_nearby_partner(self):
        tracker = SceneHarness().env["ParticipantTracker"]()
        first = tracker.update([
            {"tip": (110, 100), "anchor": (100, 160), "label": "Right"},
            {"tip": (1710, 100), "anchor": (1700, 160), "label": "Left"},
        ], 1920)
        self.assertNotEqual(first[0]["participant"], first[1]["participant"])

        second = tracker.update([
            {"tip": (115, 100), "anchor": (105, 160), "label": "Right"},
            {"tip": (315, 100), "anchor": (305, 160), "label": "Left"},
            {"tip": (1505, 100), "anchor": (1495, 160), "label": "Right"},
            {"tip": (1705, 100), "anchor": (1695, 160), "label": "Left"},
        ], 1920)
        by_x = {item["current"][0]: item["participant"] for item in second}
        self.assertEqual(by_x[115], by_x[315])
        self.assertEqual(by_x[1505], by_x[1705])
        self.assertNotEqual(by_x[115], by_x[1505])

    def test_opposite_hands_with_close_wrists_and_distant_tips_are_not_duplicates(self):
        tracker = SceneHarness().env["ParticipantTracker"]()
        hands = tracker.update([
            {"tip": (300, 100), "anchor": (500, 160), "label": "Right"},
            {"tip": (800, 100), "anchor": (540, 160), "label": "Left"},
        ], 1920)
        self.assertEqual(len(hands), 2)

    def test_departed_participant_slot_is_reserved_during_reentry_window(self):
        tracker = SceneHarness().env["ParticipantTracker"]()
        first = tracker.update([
            {"tip": (60, 100), "anchor": (50, 160), "label": "Right"},
            {"tip": (160, 100), "anchor": (150, 160), "label": "Left"},
        ], 1920)
        original = first[0]["participant"]
        tracker.update([], 1920)
        newcomer = tracker.update([
            {"tip": (710, 100), "anchor": (700, 160), "label": "Right"},
            {"tip": (790, 100), "anchor": (780, 160), "label": "Left"},
        ], 1920)
        self.assertNotEqual(newcomer[0]["participant"], original)

    def test_oldest_absent_participant_is_evicted_when_all_colors_are_reserved(self):
        tracker = SceneHarness().env["ParticipantTracker"]()
        tracker.update([
            {"tip": (60, 100), "anchor": (50, 160), "label": "Right"},
            {"tip": (160, 100), "anchor": (150, 160), "label": "Left"},
            {"tip": (710, 100), "anchor": (700, 160), "label": "Right"},
            {"tip": (810, 100), "anchor": (800, 160), "label": "Left"},
            {"tip": (1510, 100), "anchor": (1500, 160), "label": "Right"},
            {"tip": (1610, 100), "anchor": (1600, 160), "label": "Left"},
        ], 1920)
        tracker.update([
            {"tip": (65, 100), "anchor": (55, 160), "label": "Right"},
            {"tip": (165, 100), "anchor": (155, 160), "label": "Left"},
        ], 1920)

        current = tracker.update([
            {"tip": (70, 100), "anchor": (60, 160), "label": "Right"},
            {"tip": (170, 100), "anchor": (160, 160), "label": "Left"},
            {"tip": (910, 850), "anchor": (900, 900), "label": "Right"},
            {"tip": (1010, 850), "anchor": (1000, 900), "label": "Left"},
        ], 1920)
        by_x = {item["current"][0]: item["participant"] for item in current}
        self.assertEqual(by_x[70], by_x[170])
        self.assertEqual(by_x[910], by_x[1010])
        self.assertNotEqual(by_x[70], by_x[910])

        reentered = tracker.update([
            {"tip": (75, 100), "anchor": (65, 160), "label": "Right"},
            {"tip": (175, 100), "anchor": (165, 160), "label": "Left"},
            {"tip": (915, 850), "anchor": (905, 900), "label": "Right"},
            {"tip": (1015, 850), "anchor": (1005, 900), "label": "Left"},
            {"tip": (715, 100), "anchor": (705, 160), "label": "Right"},
            {"tip": (815, 100), "anchor": (805, 160), "label": "Left"},
        ], 1920)
        participants = {item["participant"] for item in reentered}
        self.assertEqual(len(reentered), 6)
        self.assertEqual(participants, {0, 1, 2})

    def test_duplicate_detection_is_ignored_and_gap_starts_without_bridge(self):
        tracker = SceneHarness().env["ParticipantTracker"]()
        first = tracker.update([
            {"tip": (100, 100), "anchor": (100, 150), "label": "Right"},
            {"tip": (105, 103), "anchor": (105, 153), "label": "Right"},
        ], 640)
        self.assertEqual(len(first), 1)
        participant = first[0]["participant"]
        tracker.update([], 640)
        returned = tracker.update([
            {"tip": (110, 105), "anchor": (110, 155), "label": "Right"},
        ], 640)
        self.assertEqual(returned[0]["participant"], participant)
        self.assertIsNone(returned[0]["previous"])

    def test_axis_angle_changes_symmetry_without_clearing_canvas(self):
        zero, turned = mock.Mock(), mock.Mock()
        # Use a real pygame draw mock so the exact endpoints can be compared.
        pygame_stub = mock.MagicMock()
        environment = SceneHarness().env
        original_pygame = environment["pygame"]
        environment["pygame"] = pygame_stub
        try:
            environment["draw_mandala"](zero, (10, 20), (30, 40), (320, 180), (255, 0, 0), 0.0)
            zero_end = pygame_stub.draw.line.call_args_list[0].args[3]
            pygame_stub.draw.line.reset_mock()
            environment["draw_mandala"](turned, (10, 20), (30, 40), (320, 180), (255, 0, 0), math.pi / 12)
            turned_end = pygame_stub.draw.line.call_args_list[0].args[3]
        finally:
            environment["pygame"] = original_pygame
        self.assertNotEqual(zero_end, turned_end)

    def test_departure_and_reentry_preserve_art_without_a_connecting_line(self):
        scene = SceneHarness(
            reads=[(True, object())] * 5,
            observations=[[hand(.6, .5)], [hand(.65, .5)], None, [hand(.1, .2)], [hand(.15, .2)]],
        )
        scene.run()
        self.assertEqual(len(scene.artwork_calls("circle")), 48)
        lines = scene.artwork_calls("line")
        self.assertEqual(len(lines), 48)
        self.assertEqual(lines[0].args[2:4], ((384.0, 180.0), (416.0, 180.0)))
        self.assertEqual(lines[24].args[2:4], ((64.0, 72.0), (96.0, 72.0)))
        self.assertEqual(scene.frame_cursor_counts, [3, 3, 0, 3, 3])
        scene.canvas.fill.assert_called_once_with((0, 0, 0, 0))
        scene.assert_released(self)

    def test_space_does_not_erase_art_or_interrupt_the_stroke(self):
        scene = SceneHarness(
            reads=[(True, object())] * 2,
            observations=[[hand(.6, .5)], [hand(.65, .5)]],
            events=[[], [SimpleNamespace(type=2, key=5)], [SimpleNamespace(type=1)]],
        )
        scene.run()
        scene.canvas.fill.assert_called_once_with((0, 0, 0, 0))
        self.assertEqual(len(scene.artwork_calls("line")), 24)
        scene.assert_released(self)

    def test_camera_gap_recovers_in_same_loop_and_starts_a_new_stroke(self):
        scene = SceneHarness(
            reads=[(True, object()), (False, None), (True, object())],
            observations=[[hand(.8, .5)], [hand(.1, .2)]], times=[0],
        )
        scene.run()
        self.assertEqual(scene.cap.read.call_count, 3)
        self.assertEqual(scene.trace, ["flip", "first", "flip", "first"])
        self.assertEqual(len(scene.artwork_calls("circle")), 48)
        self.assertEqual(scene.artwork_calls("line"), [])
        scene.canvas.fill.assert_called_once_with((0, 0, 0, 0))
        scene.reason.assert_called_once_with("pygame_quit")
        scene.assert_released(self)

    def test_persistent_camera_failure_times_out_without_first_frame(self):
        scene = SceneHarness(reads=[(False, None)] * 3, times=[0, .5, 1.01])
        scene.run()
        scene.first.assert_not_called()
        scene.pygame.display.flip.assert_not_called()
        scene.reason.assert_called_once_with("camera_read_failed_timeout")
        self.assertEqual(scene.pygame.time.Clock.return_value.tick.call_args_list,
                         [mock.call(60), mock.call(60)])
        scene.assert_released(self)

    def test_successful_frame_resets_the_camera_failure_deadline(self):
        scene = SceneHarness(
            reads=[(False, None), (True, object()), (False, None), (False, None), (True, object())],
            times=[0, 10, 10.5],
        )
        scene.run()
        self.assertEqual(scene.first.call_count, 2)
        scene.reason.assert_called_once_with("pygame_quit")
        scene.assert_released(self)

    def test_exit_events_remain_responsive_while_camera_is_unavailable(self):
        for event, reason in (
            (SimpleNamespace(type=1), "pygame_quit"),
            (SimpleNamespace(type=2, key=3), "key_escape"),
            (SimpleNamespace(type=2, key=4), "key_q"),
        ):
            with self.subTest(reason=reason):
                scene = SceneHarness(reads=[(False, None)], events=[[], [event]], times=[0])
                scene.run()
                self.assertEqual(scene.cap.read.call_count, 1)
                scene.first.assert_not_called()
                scene.reason.assert_called_once_with(reason)
                scene.assert_released(self)

    def test_failed_display_does_not_send_first_frame_and_releases_resources(self):
        for operation in ("blit", "flip"):
            with self.subTest(operation=operation):
                scene = SceneHarness()
                failed = scene.screen.blit if operation == "blit" else scene.pygame.display.flip
                failed.side_effect = RuntimeError("display failed")
                with self.assertRaisesRegex(RuntimeError, "display failed"):
                    scene.run()
                scene.first.assert_not_called()
                scene.assert_released(self)

    def test_processing_failure_is_preserved_without_first_frame(self):
        scene = SceneHarness()
        scene.hands.process.side_effect = RuntimeError("detection failed")
        with self.assertRaisesRegex(RuntimeError, "detection failed"):
            scene.run()
        scene.first.assert_not_called()
        scene.assert_released(self)

    def test_processing_and_cleanup_failures_keep_the_cause_and_attempt_every_release(self):
        scene = SceneHarness()
        body_failure = RuntimeError("original detection failed")
        camera_failure = OSError("camera release failed")
        hands_failure = ValueError("hands close failed")
        scene.hands.process.side_effect = body_failure
        scene.cap.release.side_effect = camera_failure
        scene.hands.close.side_effect = hands_failure
        cleanup_order = mock.Mock()
        cleanup_order.attach_mock(scene.cap.release, "camera_release")
        cleanup_order.attach_mock(scene.hands.close, "hands_close")
        cleanup_order.attach_mock(scene.pygame.quit, "pygame_quit")

        with self.assertRaises(ValueError) as caught:
            scene.run()

        scene.first.assert_not_called()
        scene.assert_released(self)
        self.assertEqual(cleanup_order.mock_calls,
                         [mock.call.camera_release(), mock.call.hands_close(), mock.call.pygame_quit()])
        self.assertIs(caught.exception, hands_failure)
        chain = []
        current = caught.exception
        while current is not None and all(current is not seen for seen in chain):
            chain.append(current)
            current = current.__context__
        self.assertIn(camera_failure, chain)
        self.assertIn(body_failure, chain)
        self.assertIn("main", [frame.name for frame in traceback.extract_tb(body_failure.__traceback__)])
        rendered = "".join(traceback.format_exception(caught.exception))
        self.assertIn("original detection failed", rendered)
        self.assertIn("camera release failed", rendered)
        self.assertIn("hands close failed", rendered)

    def test_single_cleanup_failure_on_normal_exit_attempts_every_release(self):
        for resource in ("camera", "hands"):
            with self.subTest(resource=resource):
                scene = SceneHarness()
                cleanup_failure = OSError(f"{resource} cleanup failed")
                failed = scene.cap.release if resource == "camera" else scene.hands.close
                failed.side_effect = cleanup_failure
                with self.assertRaises(OSError) as caught:
                    scene.run()
                self.assertIs(caught.exception, cleanup_failure)
                scene.reason.assert_called_once_with("pygame_quit")
                scene.first.assert_called_once_with(scene.cap, frame_processed=True)
                scene.assert_released(self)

    def test_camera_initialization_failure_releases_already_created_resources(self):
        for failure in ("exception", "none", "closed"):
            with self.subTest(failure=failure):
                scene = SceneHarness()
                if failure == "exception":
                    scene.display.open_camera.side_effect = RuntimeError("attach failed")
                elif failure == "none":
                    scene.display.open_camera.return_value = None
                else:
                    scene.cap.isOpened.return_value = False
                with self.assertRaises(RuntimeError):
                    scene.run()
                scene.hands.close.assert_called_once()
                scene.pygame.quit.assert_called_once()
                scene.first.assert_not_called()
                if failure == "closed":
                    scene.cap.release.assert_called_once()
                else:
                    scene.cap.release.assert_not_called()


if __name__ == "__main__":
    unittest.main()
