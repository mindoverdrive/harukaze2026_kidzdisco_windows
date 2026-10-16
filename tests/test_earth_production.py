"""Earth scene lifecycle and input contracts without camera, window, or GPU.

The production class is compiled from its source with native boundaries injected
into a private namespace. These fakes never enter sys.modules or affect normal
scene execution.
"""

import ast
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import cv2
import numpy as np

import display_utils


ROOT = Path(__file__).resolve().parents[1]


def hand_at(x=.4, y=.5, span=.2):
    hand = [SimpleNamespace(x=x, y=y, z=0.) for _ in range(21)]
    hand[0] = SimpleNamespace(x=x, y=y + span / 2, z=0.)
    hand[9] = SimpleNamespace(x=x, y=y - span / 2, z=0.)
    return hand


def detection(hands=(), labels=()):
    return SimpleNamespace(
        hand_landmarks=list(hands),
        handedness=[[SimpleNamespace(category_name=label)] for label in labels],
    )


class EarthProductionTests(unittest.TestCase):
    def setUp(self):
        self.canvas = mock.Mock()
        self.cap = mock.Mock(last_read_frame_id=1)
        self.cap.isOpened.return_value = True
        self.frame = np.zeros((180, 320, 3), dtype=np.uint8)
        self.frame[:, :80, 0] = 255
        self.cap.read.return_value = (True, self.frame)
        self.detector = mock.Mock()
        self.detector.detect_for_video.return_value = detection()
        self.display = mock.Mock(wraps=display_utils)
        self.display.open_camera.return_value = self.cap
        self.display.setup_rendercanvas_fullscreen = mock.Mock()
        self.display.resolve_model_path.return_value = "synthetic-test-model.task"
        self.display.is_valid_model_asset.return_value = True
        self.vision = mock.Mock()
        self.vision.HandLandmarker.create_from_options.return_value = self.detector
        self.ns = dict(
            __file__=str(ROOT / "earth.py"), __name__="earth_under_test",
            ExitStack=ExitStack, math=math, os=os, cv2=cv2, np=np,
            time=mock.Mock(monotonic=lambda: 10.),
            display_utils=self.display, RenderCanvas=mock.Mock(return_value=self.canvas),
            loop=mock.Mock(), gfx=mock.MagicMock(), mp=mock.Mock(),
            mp_tasks=mock.Mock(), vision=self.vision, la=mock.Mock(),
            WINDOW_WIDTH=1280, WINDOW_HEIGHT=720, EARTH_RADIUS=300, GALAXY_RADIUS=4000,
            notify_first_frame=mock.Mock(), notify_exit_request=mock.Mock(),
            draw_hand_overlay=mock.Mock(),
        )
        tree = ast.parse((ROOT / "earth.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "EarthViewer3D")
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(ROOT / "earth.py"), "exec"), self.ns)
        self.App = self.ns["EarthViewer3D"]

    def new_app(self, *, world_failure=False):
        def create_hud(app):
            app.hud_tex = mock.Mock(data=np.zeros((240, 320, 4), dtype=np.uint8), size=(320, 240, 1))

        def create_galaxy(app):
            app.galaxy_mesh = mock.Mock()

        def create_earth(app):
            if world_failure:
                raise RuntimeError("injected world creation failure")
            app.earth_mesh = mock.Mock()

        with (
            mock.patch.object(self.App, "create_hud", create_hud),
            mock.patch.object(self.App, "create_galaxy", create_galaxy),
            mock.patch.object(self.App, "create_earth", create_earth),
        ):
            app = self.App()
        self.addCleanup(app.cleanup)
        return app

    def test_one_shared_camera_attachment_without_fallback_or_reconfiguration(self):
        app = self.new_app()
        self.display.open_camera.assert_called_once_with()
        self.cap.set.assert_not_called()
        self.assertIs(app.cap, self.cap)
        self.canvas.add_event_handler.assert_called()

    def test_production_playlist_registers_nineteen_unique_scenes_and_one_earth_wrapper(self):
        config = json.loads((ROOT / "configs" / "rebirth_operator_acer_xiaomi.json").read_text(encoding="utf-8"))
        scenes = config["PRODUCTION_SCENES"]
        self.assertEqual(len(scenes), 19)
        self.assertEqual(len(set(scenes)), 19)
        self.assertEqual(scenes.count("earth_acer.py"), 1)
        self.assertEqual(scenes[-1], "earth_acer.py")
        targets = []
        for scene in scenes:
            wrapper = ast.parse((ROOT / scene).read_text(encoding="utf-8"))
            calls = [node for node in ast.walk(wrapper) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name) and node.func.id == "run_scene"]
            self.assertEqual(len(calls), 1, scene)
            targets.append(ast.literal_eval(calls[0].args[0]))
            if scene == "earth_acer.py":
                runner = mock.Mock()
                call_module = ast.Module(body=[ast.Expr(value=calls[0])], type_ignores=[])
                exec(compile(ast.fix_missing_locations(call_module), scene, "exec"), {"run_scene": runner})
                runner.assert_called_once_with("earth.py", profile="acer")
        self.assertEqual(targets.count("earth.py"), 1)

    def test_cleanup_is_idempotent_and_releases_every_acquired_resource(self):
        app = self.new_app()
        app.cleanup()
        app.cleanup()
        self.cap.release.assert_called_once_with()
        self.detector.close.assert_called_once_with()
        self.canvas.close.assert_called_once_with()

    def test_renderer_construction_failure_closes_the_acquired_canvas(self):
        self.ns["gfx"].renderers.WgpuRenderer.side_effect = RuntimeError("injected renderer failure")
        with self.assertRaisesRegex(RuntimeError, "injected renderer"):
            self.new_app()
        self.canvas.close.assert_called_once_with()
        self.display.open_camera.assert_not_called()

    def test_missing_model_fails_before_camera_and_closes_canvas(self):
        self.display.is_valid_model_asset.return_value = False
        with self.assertRaisesRegex(RuntimeError, "model missing or invalid"):
            self.new_app()
        self.canvas.close.assert_called_once_with()
        self.vision.HandLandmarker.create_from_options.assert_not_called()
        self.display.open_camera.assert_not_called()

    def test_detector_construction_failure_closes_canvas(self):
        self.vision.HandLandmarker.create_from_options.side_effect = RuntimeError("injected detector failure")
        with self.assertRaisesRegex(RuntimeError, "injected detector"):
            self.new_app()
        self.canvas.close.assert_called_once_with()
        self.display.open_camera.assert_not_called()

    def test_rejected_camera_is_released_without_fallback_and_other_resources_close(self):
        self.cap.isOpened.return_value = False
        with self.assertRaisesRegex(RuntimeError, "shared camera could not be attached"):
            self.new_app()
        self.display.open_camera.assert_called_once_with()
        self.cap.release.assert_called_once_with()
        self.detector.close.assert_called_once_with()
        self.canvas.close.assert_called_once_with()

    def test_world_creation_failure_releases_camera_detector_and_canvas(self):
        with self.assertRaisesRegex(RuntimeError, "injected world creation"):
            self.new_app(world_failure=True)
        self.cap.release.assert_called_once_with()
        self.detector.close.assert_called_once_with()
        self.canvas.close.assert_called_once_with()

    def test_cleanup_error_does_not_prevent_other_resources_closing(self):
        app = self.new_app()
        self.detector.close.side_effect = RuntimeError("injected close failure")
        with self.assertRaisesRegex(RuntimeError, "injected close"):
            app.cleanup()
        self.cap.release.assert_called_once_with()
        self.canvas.close.assert_called_once_with()
        app.cleanup()

    def test_run_cleans_up_if_loop_fails(self):
        app = self.new_app()
        self.ns["loop"].run.side_effect = RuntimeError("injected event loop failure")
        with self.assertRaisesRegex(RuntimeError, "injected event loop"):
            app.run()
        self.cap.release.assert_called_once_with()
        self.detector.close.assert_called_once_with()
        self.canvas.close.assert_called_once_with()

    def test_run_cleans_up_if_initial_draw_registration_fails(self):
        app = self.new_app()
        self.canvas.request_draw.side_effect = RuntimeError("injected request_draw failure")
        with self.assertRaisesRegex(RuntimeError, "injected request_draw"):
            app.run()
        self.cap.release.assert_called_once_with()
        self.detector.close.assert_called_once_with()
        self.canvas.close.assert_called_once_with()

    def test_run_propagates_callback_error_even_when_framework_swallows_it(self):
        app = self.new_app()
        failure = RuntimeError("injected callback render failure")
        app.renderer.render.side_effect = failure
        swallowed = []

        def run_like_rendercanvas():
            try:
                app.animate()
            except Exception as error:
                swallowed.append(error)

        self.ns["loop"].run.side_effect = run_like_rendercanvas
        with self.assertRaises(RuntimeError) as raised:
            app.run()
        self.assertIs(raised.exception, failure)
        self.assertEqual(swallowed, [failure])
        self.ns["notify_first_frame"].assert_not_called()
        self.ns["loop"].stop.assert_called_once_with()
        self.cap.release.assert_called_once_with()
        self.detector.close.assert_called_once_with()
        self.canvas.close.assert_called_once_with()

    def test_successful_restart_acquires_fresh_resources_and_resets_input_state(self):
        first = self.new_app()
        self.detector.detect_for_video.return_value = detection([hand_at()], ["Left"])
        self.assertTrue(first.update_camera(10.))
        first.run()
        self.cap.release.assert_called_once_with()
        self.detector.close.assert_called_once_with()
        self.canvas.close.assert_called_once_with()

        new_cap = mock.Mock(last_read_frame_id=2)
        new_cap.isOpened.return_value = True
        new_cap.read.return_value = (True, self.frame)
        new_detector = mock.Mock()
        new_detector.detect_for_video.return_value = detection()
        new_canvas = mock.Mock()
        self.display.open_camera.return_value = new_cap
        self.vision.HandLandmarker.create_from_options.return_value = new_detector
        self.ns["RenderCanvas"].return_value = new_canvas
        restarted = self.new_app()
        self.assertFalse(restarted.detected_hands)
        self.assertFalse(restarted.active_hand_indices)
        self.assertEqual(restarted.last_timestamp, 0)
        self.assertIsNone(restarted._frame_error)
        self.assertIsNot(first._resources, restarted._resources)
        self.assertTrue(restarted.update_camera(11.))
        new_cap.read.assert_called_once_with()
        new_detector.detect_for_video.assert_called_once()
        restarted.run()
        new_cap.release.assert_called_once_with()
        new_detector.close.assert_called_once_with()
        new_canvas.close.assert_called_once_with()
        self.assertEqual(self.display.open_camera.call_count, 2)
        self.cap.release.assert_called_once_with()
        self.detector.close.assert_called_once_with()
        self.canvas.close.assert_called_once_with()

    def test_exit_keys_and_window_close_notify_and_stop(self):
        for event in ({"event_type": "key_down", "key": "q"},
                      {"event_type": "key_down", "key": "Q"},
                      {"event_type": "key_down", "key": "Escape"},
                      {"event_type": "close"}):
            with self.subTest(event=event):
                app = self.new_app()
                self.ns["notify_exit_request"].reset_mock()
                self.ns["loop"].stop.reset_mock()
                app.on_event(event)
                self.ns["notify_exit_request"].assert_called_once()
                self.ns["loop"].stop.assert_called_once_with()

    def test_unrelated_key_does_not_request_exit(self):
        app = self.new_app()
        app.on_event({"event_type": "key_down", "key": "a"})
        self.ns["notify_exit_request"].assert_not_called()
        self.ns["loop"].stop.assert_not_called()

    def test_left_and_right_preserve_palm_control_equations(self):
        app = self.new_app()
        left, right = hand_at(.25, .7, .2), hand_at(.8, .3, .1)
        # Irrelevant fingertips must not affect the palm-based inputs.
        left[8].x, left[8].y = .99, .01
        self.detector.detect_for_video.return_value = detection([left, right], ["Left", "Right"])
        actual = app.process_input(self.frame, 123)
        expected = (True, -.2 * 1.5 * math.pi, .25 * 1.5 * math.pi,
                    1500 - (.2 - .05) / .25 * 1100,
                    True, .2 * math.pi, -.3 * math.pi)
        self.assertEqual(len(actual), 7)
        for got, want in zip(actual, expected):
            self.assertAlmostEqual(got, want)
        self.assertEqual(tuple(app.active_hand_indices), (0, 1))
        self.assertEqual(tuple(app.detected_hands), (left, right))

    def test_unknown_or_missing_handedness_is_passive_and_hand_loss_clears(self):
        app = self.new_app()
        for labels in (["Unknown"], [], [""]):
            with self.subTest(labels=labels):
                self.detector.detect_for_video.return_value = detection([hand_at()], labels)
                output = app.process_input(self.frame, 123)
                self.assertEqual(output, (False, 0., 0., 0., False, 0., 0.))
                self.assertFalse(app.active_hand_indices)
                self.assertEqual(len(app.detected_hands), 1)
        self.detector.detect_for_video.return_value = detection()
        app.process_input(self.frame, 124)
        self.assertFalse(app.active_hand_indices)
        self.assertFalse(app.detected_hands)

    def test_left_zoom_is_clamped_to_original_range(self):
        app = self.new_app()
        for span, expected in ((.01, 1500), (.5, 400)):
            self.detector.detect_for_video.return_value = detection([hand_at(span=span)], ["Left"])
            self.assertAlmostEqual(app.process_input(self.frame, 123)[3], expected)

    def test_duplicate_labels_highlight_only_the_hand_that_controls_the_result(self):
        app = self.new_app()
        first, last = hand_at(.2), hand_at(.8)
        self.detector.detect_for_video.return_value = detection([first, last], ["Left", "Left"])
        result = app.process_input(self.frame, 123)
        self.assertAlmostEqual(result[2], -.3 * 1.5 * math.pi)
        self.assertEqual(tuple(app.active_hand_indices), (1,))

    def test_camera_mirrors_once_and_hud_uses_the_same_letterbox_layout(self):
        app = self.new_app()
        recognized, unknown = hand_at(.25), hand_at(.75)
        self.detector.detect_for_video.return_value = detection([recognized, unknown], ["Left", "Unknown"])
        self.assertTrue(app.update_camera(10.))
        # VIDEO inference consumes the mirrored camera, before HUD artwork.
        inference_rgb = self.ns["mp"].Image.call_args.kwargs["data"]
        np.testing.assert_array_equal(inference_rgb, cv2.cvtColor(cv2.flip(self.frame, 1), cv2.COLOR_BGR2RGB))
        self.assertEqual(self.display.prepare_camera_frame.call_count, 1)
        calls = self.ns["draw_hand_overlay"].call_args_list
        self.assertEqual(len(calls), 2)
        for call, expected_hand, is_active in zip(calls, (recognized, unknown), (True, False)):
            self.assertEqual(call.args[1], (expected_hand,))
            self.assertEqual(call.kwargs["focus"], ())
            self.assertIs(call.kwargs["palm_focus"], is_active)
            self.assertEqual(call.kwargs["layout"]["offset_y"], 30)
            self.assertEqual(call.args[0].shape, (240, 320, 3))
        np.testing.assert_array_equal(app.hud_tex.data[:30, :, :3], 0)
        self.assertTrue(np.all(app.hud_tex.data[:, :, 3] == 255))
        self.cap.read.assert_called_once_with()
        self.detector.detect_for_video.assert_called_once()

    def test_video_timestamps_increase_even_inside_one_millisecond_or_after_clock_reversal(self):
        app = self.new_app()
        for frame_id, now in enumerate((10., 10., 9.5), 1):
            self.cap.last_read_frame_id = frame_id
            self.assertTrue(app.update_camera(now))
        timestamps = [call.args[1] for call in self.detector.detect_for_video.call_args_list]
        self.assertEqual(timestamps, [10000, 10001, 10002])

    def test_failed_or_none_camera_frames_clear_feedback_and_schedule_recovery(self):
        app = self.new_app()
        for failure in ((False, None), (True, None)):
            with self.subTest(failure=failure):
                app.detected_hands = (hand_at(),)
                app.active_hand_indices = (0,)
                app.input_state = (True, 1., 2., 500., True, 3., 4.)
                app.hud_tex.data[:] = 200
                self.cap.read.return_value = failure
                self.canvas.request_draw.reset_mock()
                self.ns["notify_first_frame"].reset_mock()
                app.animate()
                self.assertFalse(app.detected_hands)
                self.assertFalse(app.active_hand_indices)
                self.assertFalse(app.interacting_earth)
                self.assertFalse(app.interacting_galaxy)
                np.testing.assert_array_equal(app.hud_tex.data[:, :, :3], 0)
                self.detector.detect_for_video.assert_not_called()
                self.canvas.request_draw.assert_called_once_with()
                self.ns["notify_first_frame"].assert_called_once_with(self.cap, frame_processed=False)
        self.cap.read.return_value = (True, self.frame)
        self.assertTrue(app.update_camera(10.1))
        self.assertIsNone(app.camera_failure_since)
        self.detector.detect_for_video.assert_called_once()

    def test_frozen_shared_frame_expires_and_fresh_frame_recovers(self):
        app = self.new_app()
        self.detector.detect_for_video.return_value = detection([hand_at()], ["Right"])
        self.assertTrue(app.update_camera(10.))
        self.assertTrue(app.detected_hands)
        self.assertFalse(app.update_camera(10.25))
        self.assertFalse(app.detected_hands)
        self.assertFalse(app.active_hand_indices)
        np.testing.assert_array_equal(app.hud_tex.data[:, :, :3], 0)
        self.detector.detect_for_video.assert_called_once()
        self.cap.last_read_frame_id = 2
        self.assertTrue(app.update_camera(10.3))
        self.assertTrue(app.detected_hands)
        self.assertIsNone(app.camera_failure_since)

    def test_prolonged_camera_loss_notifies_failure_after_one_second(self):
        app = self.new_app()
        self.cap.read.return_value = (False, None)
        self.assertFalse(app.update_camera(10.))
        with self.assertRaisesRegex(RuntimeError, "shared camera unavailable"):
            app.update_camera(11.)
        self.ns["notify_exit_request"].assert_called_once_with("camera_read_failed_timeout")
        self.assertFalse(app.detected_hands)

    def test_first_frame_follows_successful_inference_and_both_render_passes(self):
        app = self.new_app()
        order = mock.Mock()
        order.attach_mock(self.detector.detect_for_video, "infer")
        order.attach_mock(app.renderer.render, "render")
        order.attach_mock(self.ns["notify_first_frame"], "ready")
        app.animate()
        self.assertEqual([call[0] for call in order.mock_calls], ["infer", "render", "render", "ready"])
        app.renderer.render.assert_has_calls([
            mock.call(app.scene, app.camera, flush=False),
            mock.call(app.hud_scene, app.hud_camera, clear=False),
        ])
        self.ns["notify_first_frame"].assert_called_once_with(self.cap, frame_processed=True)
        self.canvas.request_draw.assert_called_once_with()

    def test_inference_failure_clears_feedback_and_cannot_announce_readiness(self):
        app = self.new_app()
        app.detected_hands = (hand_at(),)
        app.hud_tex.data[:] = 200
        self.detector.detect_for_video.side_effect = RuntimeError("injected inference failure")
        with self.assertRaisesRegex(RuntimeError, "injected inference"):
            app.animate()
        self.assertFalse(app.detected_hands)
        np.testing.assert_array_equal(app.hud_tex.data[:, :, :3], 0)
        self.ns["notify_first_frame"].assert_not_called()
        self.ns["loop"].stop.assert_called_once_with()
        self.canvas.request_draw.assert_called_once_with()

    def test_either_render_failure_blocks_first_frame_and_stops_the_loop(self):
        app = self.new_app()
        for failing_pass in (0, 1):
            with self.subTest(failing_pass=failing_pass):
                app.renderer.render.reset_mock()
                app.renderer.render.side_effect = [RuntimeError("injected render failure") if index == failing_pass
                                                   else None for index in range(2)]
                self.ns["loop"].stop.reset_mock()
                self.canvas.request_draw.reset_mock()
                with self.assertRaisesRegex(RuntimeError, "injected render"):
                    app.animate()
                self.ns["notify_first_frame"].assert_not_called()
                self.ns["loop"].stop.assert_called_once_with()
                self.canvas.request_draw.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
