import ast
from contextlib import ExitStack
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

from test_tree_scene import SceneHarness as TreeHarness


scene = ModuleType("jacket_scene_test_target")
scene.__dict__.update(ExitStack=ExitStack, sys=sys)
source = ast.parse((Path(__file__).resolve().parents[1] / "sci_fi_jacket.py").read_text(encoding="utf-8"))
exec(compile(ast.Module(body=[node for node in source.body if isinstance(node, (ast.Assign, ast.FunctionDef))],
                        type_ignores=[]), "sci_fi_jacket.py", "exec"), scene.__dict__)


class JacketHarness(TreeHarness):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pygame.display.set_caption = mock.Mock()
        self.mp.solutions.selfie_segmentation = SimpleNamespace(SelfieSegmentation=mock.Mock(return_value=self.hands))
        self.camera_frame = SimpleNamespace(shape=(30, 30, 3))
        self.layout = {"offset_x": 0, "offset_y": 0, "scaled_width": 30, "scaled_height": 30}
        self.display.prepare_camera_frame.return_value = self.camera_frame, self.stage_frame, self.layout
        self.effect = SimpleNamespace(size=(30, 30), clear=mock.Mock(),
                                      render=mock.Mock(return_value=(mock.sentinel.pattern, mock.sentinel.alpha)))
        self.factory = mock.Mock(return_value=self.effect)
        self.blend = mock.Mock(return_value=self.stage_frame)

    def run(self):
        values = {"pygame": self.pygame, "display_utils": self.display, "cv2": self.cv2,
                  "mp": self.mp, "time": self.time, "atexit": self.atexit,
                  "notify_first_frame": self.first, "notify_exit_request": self.reason,
                  "JacketFlow": self.factory, "blend_on_stage": self.blend}
        with mock.patch.dict(scene.__dict__, values):
            scene.main()


class JacketSceneTests(unittest.TestCase):
    def test_real_loop_presents_processed_video_before_first_frame_and_releases(self):
        harness = JacketHarness()
        harness.run()
        self.assertEqual(harness.trace, ["camera", "flip", "first"])
        harness.effect.render.assert_called_once()
        harness.blend.assert_called_once_with(harness.stage_frame, mock.sentinel.pattern, mock.sentinel.alpha,
                                             harness.layout)
        harness.first.assert_called_once_with(harness.cap, frame_processed=True)
        harness.hands.close.assert_called_once()
        harness.cap.release.assert_called_once()
        harness.pygame.quit.assert_called_once()

    def test_quit_and_both_exit_keys_prevent_another_camera_read(self):
        for event, reason in ((SimpleNamespace(type=1), "pygame_quit"),
                              (SimpleNamespace(type=2, key=3), "key_escape"),
                              (SimpleNamespace(type=2, key=4), "key_q")):
            harness = JacketHarness(events=[[event]])
            harness.run()
            harness.cap.read.assert_not_called()
            harness.first.assert_not_called()
            harness.reason.assert_called_once_with(reason)

    def test_failed_camera_attach_closes_pygame_and_does_not_construct_model(self):
        harness = JacketHarness()
        harness.display.open_camera.return_value = None
        with self.assertRaisesRegex(RuntimeError, "shared camera"):
            harness.run()
        harness.pygame.quit.assert_called_once()
        harness.mp.solutions.selfie_segmentation.SelfieSegmentation.assert_not_called()

    def test_camera_failures_allow_one_second_and_recovery_restarts_the_grace(self):
        harness = JacketHarness(reads=[(False, None), (True, object()), (False, None), (False, None), (False, None)],
                                events=[[], [], [], [], []], times=[0, .7, 1.5, 2.1, 2.6])
        harness.run()
        self.assertEqual([call.kwargs["frame_processed"] for call in harness.first.call_args_list],
                         [False, True, False, False])
        harness.reason.assert_called_once_with("camera_read_failed_timeout")
        self.assertEqual(harness.effect.clear.call_count, 3)
        harness.cap.release.assert_called_once()

    def test_processing_and_present_errors_cannot_ack_first_frame_and_still_release(self):
        for failure_at in ("processing", "present"):
            harness = JacketHarness()
            target = harness.hands.process if failure_at == "processing" else harness.pygame.display.flip
            target.side_effect = RuntimeError(failure_at)
            with self.assertRaisesRegex(RuntimeError, failure_at):
                harness.run()
            harness.first.assert_not_called()
            harness.hands.close.assert_called_once()
            harness.cap.release.assert_called_once()
            harness.pygame.quit.assert_called_once()

    def test_model_initialization_and_close_failure_release_other_owned_resources(self):
        for failure_at in ("initialization", "close"):
            harness = JacketHarness()
            target = (harness.mp.solutions.selfie_segmentation.SelfieSegmentation
                      if failure_at == "initialization" else harness.hands.close)
            target.side_effect = RuntimeError(failure_at)
            with self.assertRaisesRegex(RuntimeError, failure_at):
                harness.run()
            harness.cap.release.assert_called_once()
            harness.pygame.quit.assert_called_once()

    def test_processing_resolution_preserves_aspect_ratio_and_bounds(self):
        cv = SimpleNamespace(resize=mock.Mock(), INTER_AREA=3)
        with mock.patch.dict(scene.__dict__, cv2=cv):
            scene.processing_frame(SimpleNamespace(shape=(1080, 1920, 3)))
            self.assertEqual(cv.resize.call_args.args[1], (640, 360))
            scene.processing_frame(SimpleNamespace(shape=(1920, 1080, 3)))
            self.assertEqual(cv.resize.call_args.args[1], (360, 640))


if __name__ == "__main__":
    unittest.main()
