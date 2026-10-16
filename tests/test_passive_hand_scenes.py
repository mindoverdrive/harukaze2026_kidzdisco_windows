"""Run camera-effect loops on synthetic frames without cameras or display windows."""
import ast
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import cv2
import numpy as np
import pygame
import display_utils


ROOT = Path(__file__).resolve().parents[1]
SCENES = ("kaleidoscope_camera.py", "living_mosaic.py", "polygon_face_stage.py")


class Harness:
    def __init__(self, filename, reads=None):
        self.filename = filename
        self.frame = np.zeros((480, 640, 3), np.uint8)
        self.frame[:, :180, 0] = 120
        self.reads = reads if reads is not None else [(True, self.frame)]
        self.cap = mock.Mock()
        self.cap.isOpened.return_value = True
        self.cap.read.side_effect = self.reads
        self.screen = pygame.Surface((640, 360))
        self.snapshots = []
        self.hand = mock.sentinel.hand
        self.hand_detector = mock.Mock()
        self.hand_detector.detect.side_effect = lambda frame: () if frame is None else (self.hand,)
        self.hand_factory = mock.Mock(return_value=self.hand_detector)
        self.draw_cv2 = mock.Mock(side_effect=self.mark_stage)
        self.draw_pygame = mock.Mock()
        self.focus = mock.Mock()
        self.first = mock.Mock()
        self.mosaic = mock.Mock()
        self.mosaic.render.side_effect = lambda source, *_: np.zeros_like(source)
        self.face = mock.MagicMock()
        self.face.__enter__.return_value = self.face
        self.face.process.return_value = SimpleNamespace(multi_face_landmarks=[])
        self.field = mock.Mock(opening=1.)
        self.field.step.return_value = (np.empty((0, 3, 2)), np.empty((0, 3)))
        self.display = SimpleNamespace(
            setup_pygame_fullscreen=mock.Mock(return_value=(self.screen, self.screen.get_size())),
            open_camera=mock.Mock(return_value=self.cap),
            prepare_camera_frame=display_utils.prepare_camera_frame,
            normalized_to_stage=display_utils.normalized_to_stage,
            fit_frame_to_size=display_utils.fit_frame_to_size,
            apply_camera_opacity=display_utils.apply_camera_opacity,
            _camera_presentation=SimpleNamespace(opacity=lambda: 1.))
        self.pg = SimpleNamespace(
            init=mock.Mock(), quit=mock.Mock(), QUIT=1, KEYDOWN=2, K_ESCAPE=3,
            Surface=pygame.Surface, draw=pygame.draw, image=pygame.image, transform=pygame.transform,
            event=SimpleNamespace(get=mock.Mock(side_effect=[[] for _ in self.reads] +
                                              [[SimpleNamespace(type=1)]])),
            display=SimpleNamespace(flip=lambda: self.snapshots.append(pygame.surfarray.array3d(self.screen))),
            time=SimpleNamespace(Clock=mock.Mock(return_value=mock.Mock())))
        self.ns = dict(ExitStack=ExitStack, time=SimpleNamespace(monotonic=lambda: 0.),
                       cv2=cv2, np=np, pygame=self.pg, display_utils=self.display,
                       PassiveHandDetector=self.hand_factory, draw_cv2=self.draw_cv2,
                       draw_pygame=self.draw_pygame, draw_focus_points=self.focus,
                       notify_first_frame=self.first, LivingMosaic=mock.Mock(return_value=self.mosaic),
                       FaceField=mock.Mock(return_value=self.field), mouth_openness=lambda _: .8,
                       mp=SimpleNamespace(solutions=SimpleNamespace(face_mesh=SimpleNamespace(
                           FaceMesh=mock.Mock(return_value=self.face)))))
        tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
        nodes = [node for node in tree.body if isinstance(node, (ast.Assign, ast.FunctionDef))]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), self.ns)

    @staticmethod
    def mark_stage(stage, hands, *, layout, focus):
        if hands:
            point = display_utils.normalized_to_stage(.7, .55, layout)
            cv2.circle(stage, point, 7, (40, 230, 250), -1)

    def run(self):
        with mock.patch.object(display_utils._camera_presentation, "opacity", return_value=1.):
            self.ns["main"]()


class PassiveSceneTests(unittest.TestCase):
    def test_each_scene_reuses_mirrored_frame_and_closes_one_hand_detector(self):
        for filename in SCENES:
            with self.subTest(filename=filename):
                h = Harness(filename)
                h.run()
                h.display.open_camera.assert_called_once_with()
                h.cap.read.assert_called_once()
                h.hand_factory.assert_called_once_with()
                np.testing.assert_array_equal(h.hand_detector.detect.call_args.args[0], cv2.flip(h.frame, 1))
                h.hand_detector.close.assert_called_once()
                h.cap.release.assert_called_once()
                h.pg.quit.assert_called_once()
                h.first.assert_called_once_with(h.cap, frame_processed=True)
                draw = h.draw_pygame if filename == "polygon_face_stage.py" else h.draw_cv2
                self.assertEqual(draw.call_args.kwargs["focus"], ())

    def test_camera_failure_clears_hands_and_stale_image(self):
        for filename in SCENES:
            with self.subTest(filename=filename):
                h = Harness(filename)
                h.reads.append((False, None))
                h.cap.read.side_effect = h.reads
                h.pg.event.get.side_effect = [[], [], [SimpleNamespace(type=1)]]
                h.run()
                h.hand_detector.detect.assert_called_with(None)
                self.assertEqual(h.first.call_args.kwargs["frame_processed"], False)
                if filename == "polygon_face_stage.py":
                    self.assertEqual(h.draw_pygame.call_args.args[1], ())
                else:
                    self.assertFalse(np.any(h.snapshots[-1]))

    def test_detector_initialization_failure_releases_camera_and_window(self):
        for filename in SCENES:
            with self.subTest(filename=filename):
                h = Harness(filename)
                h.hand_factory.side_effect = RuntimeError("hand initialization")
                with self.assertRaisesRegex(RuntimeError, "hand initialization"):
                    h.run()
                h.cap.release.assert_called_once()
                h.pg.quit.assert_called_once()
                h.cap.read.assert_not_called()

    def test_detector_processing_failure_releases_detector_camera_and_window(self):
        for filename in SCENES:
            with self.subTest(filename=filename):
                h = Harness(filename)
                h.hand_detector.detect.side_effect = RuntimeError("hand inference")
                with self.assertRaisesRegex(RuntimeError, "hand inference"):
                    h.run()
                h.hand_detector.close.assert_called_once()
                h.cap.release.assert_called_once()
                h.pg.quit.assert_called_once()
                h.first.assert_not_called()

    def test_kaleidoscope_hand_frame_uses_exact_same_polar_remap_as_video(self):
        h = Harness("kaleidoscope_camera.py")
        h.run()
        _, stage, layout = display_utils.prepare_camera_frame(h.frame, 640, 360)
        Harness.mark_stage(stage, (h.hand,), layout=layout, focus=())
        mx, my = h.ns["kaleidoscope_maps"](640, 360, 0.)
        expected = cv2.remap(stage, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
        np.testing.assert_array_equal(h.snapshots[0], cv2.cvtColor(expected, cv2.COLOR_BGR2RGB).transpose(1, 0, 2))

    def test_mosaic_uses_letterbox_for_both_input_and_post_effect_overlay(self):
        h = Harness("living_mosaic.py")
        h.run()
        camera, source, layout = display_utils.prepare_camera_frame(h.frame, 640, 360)
        np.testing.assert_array_equal(h.mosaic.render.call_args.args[0], source)
        self.assertEqual(layout["offset_x"], 80)
        self.assertEqual(h.draw_cv2.call_args.kwargs["layout"], layout)
        point = display_utils.normalized_to_stage(.7, .55, layout)
        self.assertEqual(tuple(h.snapshots[0][point]), (250, 230, 40))
        # The mark must not be applied before motion/inversion, or stretched to
        # the full stage instead of the camera's centered 4:3 region.
        self.assertEqual(tuple(h.snapshots[0][round(.7 * 639), round(.55 * 359)]), (0, 0, 0))
        np.testing.assert_array_equal(camera, cv2.flip(h.frame, 1))

    def test_face_marks_actual_mouth_control_and_clears_marker_when_face_lost(self):
        h = Harness("polygon_face_stage.py")
        landmarks = [SimpleNamespace(x=.5, y=.5) for _ in range(468)]
        landmarks[13] = SimpleNamespace(x=.7, y=.3)
        landmarks[14] = SimpleNamespace(x=.7, y=.5)
        h.face.process.side_effect = [SimpleNamespace(multi_face_landmarks=[SimpleNamespace(landmark=landmarks)]),
                                      SimpleNamespace(multi_face_landmarks=[])]
        h.cap.read.side_effect = [(True, h.frame), (True, h.frame)]
        h.pg.event.get.side_effect = [[], [], [SimpleNamespace(type=1)]]
        h.run()
        _, _, layout = display_utils.prepare_camera_frame(h.frame, 640, 360)
        mouth = display_utils.normalized_to_stage(.7, .4, layout)
        h.focus.assert_called_once_with(h.screen, (mouth,))
        self.assertEqual(h.field.step.call_args_list[0].args[:2], (mouth, .8))
        self.assertEqual(h.field.step.call_args_list[1].args[:2], (None, 0.))


if __name__ == "__main__":
    unittest.main()
