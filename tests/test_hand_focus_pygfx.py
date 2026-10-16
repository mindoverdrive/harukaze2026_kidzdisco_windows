"""Shared hand feedback tests; optional actual GPU screenshots use fake input.

Run this file with --render OUTPUT_DIRECTORY for offscreen render validation.
No test opens a physical camera, starts a MediaPipe model or opens a window.
"""

import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
import pygame
import pygfx as gfx

import display_utils
from hand_focus_overlay import stage_points
from hand_focus_pygfx import PygfxHandOverlay

ROOT = Path(__file__).resolve().parents[1]


def hand_at(x=.36, y=.5):
    # Open hand with a distinct index-tip coordinate, already in mirror space.
    xy = [(0, .20), (-.09, .14), (-.15, .09), (-.19, .04), (-.22, -.02),
          (-.07, .04), (-.08, -.07), (-.08, -.15), (-.08, -.22),
          (0, .02), (0, -.10), (0, -.19), (0, -.26),
          (.07, .04), (.08, -.07), (.09, -.15), (.10, -.21),
          (.13, .08), (.16, 0), (.18, -.07), (.20, -.12)]
    return [SimpleNamespace(x=x + dx, y=y + dy, z=0.) for dx, dy in xy]


def methods(filename, class_name, names, namespace):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=body, type_ignores=[]), filename, "exec"), namespace)
    return namespace


class HandFocusPygfxTests(unittest.TestCase):
    def test_texture_uses_stage_layout_and_multiple_hands_without_second_mirror(self):
        overlay = PygfxHandOverlay(800, 450)
        layout = display_utils.get_uniform_layout(640, 480, 800, 450)
        hands = [hand_at(.32), hand_at(.72)]
        colors = ((255, 0, 68), (0, 255, 255))
        overlay.update(hands, layout=layout, focus=(8,), palm_focus=True, cursor_colors=colors)
        self.assertTrue(overlay.mesh.visible)
        for hand, color in zip(hands, colors):
            x, y = stage_points(hand, overlay.size, layout)[8]
            np.testing.assert_array_equal(overlay.pixels[y, x], (*color, 255))
        self.assertFalse(overlay.pixels[:, :layout['offset_x'], 3].any())
        # Two hands plus skeletons are drawn, but the rest is transparent.
        self.assertGreater(np.count_nonzero(overlay.pixels[:, :, 3]), 100)
        self.assertLess(np.count_nonzero(overlay.pixels[:, :, 3]), 800 * 450 / 5)

    def test_new_result_and_hand_loss_remove_old_pixels(self):
        overlay = PygfxHandOverlay(800, 450)
        old = hand_at(.30)
        overlay.update([old], focus=(8,))
        old_x, old_y = stage_points(old, overlay.size)[8]
        self.assertGreater(overlay.pixels[old_y, old_x, 3], 0)
        overlay.update([hand_at(.76)], focus=(4, 8))
        self.assertEqual(overlay.pixels[old_y, old_x, 3], 0)
        overlay.update([])
        self.assertFalse(overlay.mesh.visible)
        self.assertFalse(overlay.pixels.any())

    def test_transparent_overlay_does_not_write_or_test_particle_depth(self):
        overlay = PygfxHandOverlay(800, 450)
        self.assertFalse(overlay.mesh.material.depth_write)
        self.assertFalse(overlay.mesh.material.depth_test)
        self.assertEqual(overlay.mesh.material.alpha_mode, "blend")
        # Surface writes go straight into the texture's CPU memory.
        overlay.surface.set_at((4, 5), (1, 2, 3, 4))
        np.testing.assert_array_equal(overlay.texture.data[5, 4], (1, 2, 3, 4))

    def test_storm_feedback_tracks_actual_index_and_gesture(self):
        ns = methods("particle_storm_2.py", "ParticleStormApp", ["analyze_hands", "_clear_hands"],
                     dict(math=math, EXPLOSION_THRESHOLD=.22))
        app = SimpleNamespace(hand_overlay=mock.Mock(),
                              _landmark_to_world=lambda lm, _: (np.zeros(3), (12, 34)))
        app._clear_hands = lambda: ns["_clear_hands"](app)
        opened = hand_at()
        closed = [SimpleNamespace(x=.5, y=.5, z=0.) for _ in range(21)]
        result = SimpleNamespace(hand_landmarks=[opened, closed])
        ns["analyze_hands"](app, result, "layout")
        self.assertEqual([hand['gest'] for hand in app.hand_data], [-2., 1.])
        app.hand_overlay.update.assert_called_once_with(
            result.hand_landmarks, layout="layout", focus=(8,), palm_focus=True,
            cursor_colors=[(0, 255, 255), (255, 0, 68)])
        ns["analyze_hands"](app, SimpleNamespace(hand_landmarks=[]), "layout")
        self.assertFalse(app.hand_data)
        app.hand_overlay.clear.assert_called()

    def test_saturn_clears_overlay_on_capture_or_detector_failure(self):
        import cv2
        ns = methods("saturn_particles_2.py", "SaturnParticlesApp", ["detect_hands", "_clear_hands"],
                     dict(cv2=cv2, display_utils=display_utils, WINDOW_WIDTH=320, WINDOW_HEIGHT=180,
                          time=mock.Mock(time=lambda: 123.), mp=mock.Mock()))
        for failure in ("camera", "empty_frame", "missing_detector", "exception", "no_hands"):
            with self.subTest(failure=failure):
                app = SimpleNamespace(cap=mock.Mock(),
                                      hand_overlay=mock.Mock(), hand_data_list=["stale"], last_timestamp=0,
                                      cam_tex=mock.Mock(data=np.zeros((180, 320, 4), dtype=np.uint8)),
                                      detector=mock.Mock())
                app._clear_hands = lambda: ns["_clear_hands"](app)
                app.cap.read.return_value = (
                    failure != "camera", None if failure == "empty_frame"
                    else np.zeros((180, 320, 3), np.uint8))
                if failure == "missing_detector":
                    app.detector = None
                elif failure == "exception":
                    app.detector.detect_for_video.side_effect = RuntimeError("injected")
                else:
                    app.detector.detect_for_video.return_value = SimpleNamespace(hand_landmarks=[])
                ns["detect_hands"](app)
                self.assertFalse(app.hand_data_list)
                app.hand_overlay.clear.assert_called()

    def test_saturn_overlay_is_last_pass_and_failure_blocks_ready_notification(self):
        ns = methods("saturn_particles_2.py", "SaturnParticlesApp", ["animate"],
                     dict(time=mock.Mock(monotonic=lambda: 123.), notify_first_frame=mock.Mock()))
        for failure in (None, 0, 1):
            with self.subTest(failure=failure):
                app = mock.Mock(last_time=122.99)
                app.detect_hands.return_value = True
                app.renderer.render.side_effect = [RuntimeError("injected") if index == failure else None
                                                    for index in range(2)]
                ns["notify_first_frame"].reset_mock()
                ns["animate"](app)
                app.renderer.render.assert_any_call(app.scene, app.camera, flush=False)
                if failure is None:
                    self.assertEqual(app.renderer.render.call_args,
                                     mock.call(app.hand_overlay.scene, app.hand_overlay.camera, clear=False))
                    ns["notify_first_frame"].assert_called_once_with(app.cap, frame_processed=True)
                else:
                    ns["notify_first_frame"].assert_not_called()

    def test_saturn_reuses_tasks_result_and_highlights_the_two_actual_inputs(self):
        import cv2
        ns = methods("saturn_particles_2.py", "SaturnParticlesApp", ["detect_hands", "_clear_hands"],
                     dict(cv2=cv2, display_utils=display_utils, WINDOW_WIDTH=320, WINDOW_HEIGHT=180,
                          time=mock.Mock(time=lambda: 123.), mp=mock.Mock(), math=math, np=np))
        hands = [hand_at(.30), hand_at(.70)]
        hands[1][4] = hands[1][8]  # Pinch on the hand assigned to Saturn's ring.
        detector = mock.Mock()
        detector.detect_for_video.return_value = SimpleNamespace(hand_landmarks=hands)
        cap = mock.Mock()
        cap.read.return_value = (True, np.zeros((240, 320, 3), np.uint8))
        app = SimpleNamespace(cap=cap, hand_overlay=mock.Mock(), last_timestamp=0,
                              cam_tex=mock.Mock(data=np.zeros((180, 320, 4), dtype=np.uint8)),
                              detector=detector,
                              _landmark_to_world=lambda lm, layout: (np.zeros(3),
                                  display_utils.normalized_to_stage(lm.x, lm.y, layout)))
        app._clear_hands = lambda: ns["_clear_hands"](app)
        self.assertTrue(ns["detect_hands"](app))
        detector.detect_for_video.assert_called_once()
        cap.read.assert_called_once()
        self.assertEqual([h['pinch'] for h in app.hand_data_list], [False, True])
        app.hand_overlay.update.assert_called_once_with(hands, layout=app.camera_layout, focus=(4, 8),
                                                      cursor_colors=((255, 204, 0), (0, 204, 255)))

    def test_storm_clears_feedback_on_lost_camera_or_failed_detector(self):
        ns = methods("particle_storm_2.py", "ParticleStormApp", ["animate", "_clear_hands"],
                     dict(cv2=mock.Mock(), display_utils=mock.Mock(), WINDOW_WIDTH=320, WINDOW_HEIGHT=180,
                          time=mock.Mock(monotonic=lambda: 123.), mp=mock.Mock(), notify_first_frame=mock.Mock()))
        ns["display_utils"].prepare_camera_frame.return_value = (object(), object(), object())
        for failure in ("camera", "empty_frame", "missing_detector", "exception"):
            with self.subTest(failure=failure):
                app = mock.Mock(last_time=122.99, last_timestamp=0)
                app._clear_hands = lambda: ns["_clear_hands"](app)
                app.cap.read.return_value = (failure != "camera", None if failure == "empty_frame" else object())
                app.cam_tex = mock.MagicMock()
                app.hand_data = ["stale"]
                if failure == "missing_detector":
                    app.detector = None
                elif failure == "exception":
                    app.detector.detect_for_video.side_effect = RuntimeError("injected")
                ns["notify_first_frame"].reset_mock()
                ns["animate"](app)
                self.assertFalse(app.hand_data)
                app.hand_overlay.clear.assert_called()
                ns["notify_first_frame"].assert_called_once_with(app.cap, frame_processed=False)


def render_examples(output_directory):
    """Render actual scene callbacks on the real GPU, using synthetic landmarks."""
    import importlib
    import cv2
    import time
    from rendercanvas.offscreen import RenderCanvas

    destination = Path(output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    width, height = 960, 540
    # No private imagery: this neutral backdrop stands in for the camera feed.
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = (32, 24, 18)
    frame[:, :100] = (65, 45, 35)
    hands = [hand_at(.32), hand_at(.72)]
    for module_name, class_name in (("particle_storm_2", "ParticleStormApp"),
                                     ("saturn_particles_2", "SaturnParticlesApp")):
        module = importlib.import_module(module_name)
        capture = mock.Mock(isOpened=lambda: True, read=lambda: (True, frame))
        with mock.patch.multiple(module, WINDOW_WIDTH=width, WINDOW_HEIGHT=height, RenderCanvas=RenderCanvas), \
             mock.patch.object(module.display_utils, "setup_rendercanvas_fullscreen"), \
             mock.patch.object(module.display_utils, "is_valid_model_asset", return_value=False), \
             mock.patch.object(module.display_utils, "open_camera", return_value=capture), \
             mock.patch.object(module, "notify_first_frame"):
            np.random.seed(12)
            app = getattr(module, class_name)()
            try:
                app.detector = SimpleNamespace(detect_for_video=lambda *args: SimpleNamespace(hand_landmarks=hands))
                app.last_time = time.monotonic() - .016
                app.canvas.request_draw(app.animate)
                image = np.asarray(app.canvas.draw()).copy()
                cv2.imwrite(str(destination / (module_name + "_hand_focus.png")),
                            cv2.cvtColor(image, cv2.COLOR_RGBA2BGRA))
                # The final pass must keep both index targets visible above
                # the actual 40k/45k particle field, at camera-aligned pixels.
                layout = display_utils.get_uniform_layout(640, 480, width, height)
                for hand in hands:
                    x, y = stage_points(hand, (width, height), layout)[8]
                    roi = image[y - 16:y + 17, x - 16:x + 17, :3]
                    if np.count_nonzero(np.all(roi > 225, axis=2)) < 12:
                        raise AssertionError(f"{module_name}: index ring missing at {(x, y)}")
                app.detector = SimpleNamespace(detect_for_video=lambda *args: SimpleNamespace(hand_landmarks=[]))
                app.canvas.draw()
                if app.hand_overlay.mesh.visible:
                    raise AssertionError(f"{module_name}: stale hand overlay")
                print(f"RENDER PASS {module_name}: 2 index rings, letterbox alignment, and loss clearing")
            finally:
                app.cleanup()


if __name__ == "__main__":
    import sys
    if "--render" in sys.argv:
        render_examples(sys.argv[sys.argv.index("--render") + 1])
    else:
        unittest.main()
