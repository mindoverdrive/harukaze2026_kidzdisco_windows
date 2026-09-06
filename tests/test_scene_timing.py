"""Exercise actual particle callbacks with fake clocks and no native resources."""

import ast
from contextlib import ExitStack
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCENES = (("particle_storm_2.py", "ParticleStormApp"),
          ("saturn_particles_2.py", "SaturnParticlesApp"))


class StrictVideoDetector:
    """Model MediaPipe VIDEO's strict timestamp check at the actual call boundary."""

    def __init__(self):
        self.timestamps = []
        self.close = mock.Mock()

    def detect_for_video(self, image, timestamp_ms):
        if self.timestamps and timestamp_ms <= self.timestamps[-1]:
            raise ValueError("Input timestamps must increase")
        self.timestamps.append(timestamp_ms)
        return SimpleNamespace(hand_landmarks=[])


class SceneTimingTests(unittest.TestCase):
    def build_scene(self, filename, class_name):
        clock = SimpleNamespace(wall=1000.0, steady=30.0)
        detector = StrictVideoDetector()
        display = mock.Mock()
        display.is_valid_model_asset.return_value = True
        display.open_camera.return_value.isOpened.return_value = True
        display.open_camera.return_value.read.return_value = (True, object())
        display.prepare_camera_frame.return_value = (object(), object(), object())
        vision = mock.Mock()
        vision.HandLandmarker.create_from_options.return_value = detector
        ns = dict(time=SimpleNamespace(time=lambda: clock.wall, monotonic=lambda: clock.steady),
                  math=math, ExitStack=ExitStack, atexit=mock.Mock(), cv2=mock.Mock(),
                  mp=mock.Mock(), python=mock.Mock(), vision=vision, np=mock.MagicMock(),
                  gfx=mock.MagicMock(), la=mock.Mock(), display_utils=display,
                  RenderCanvas=mock.Mock(), loop=mock.Mock(), notify_first_frame=mock.Mock(),
                  WINDOW_WIDTH=640, WINDOW_HEIGHT=360)
        tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
        selected = [node for node in tree.body
                    if (isinstance(node, ast.ClassDef) and node.name == class_name)
                    or (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant))]
        exec(compile(ast.Module(body=selected, type_ignores=[]), filename, "exec"), ns)
        cls = ns[class_name]
        # Keep the real constructor's timing fields, but allocate no particles or native resources.
        with mock.patch.object(cls, "init_particles"):
            app = cls()
        self.addCleanup(app.cleanup)
        app.cursors = []
        app.update_physics = mock.Mock()
        return SimpleNamespace(app=app, clock=clock, detector=detector,
                               notify=ns["notify_first_frame"])

    def assert_frame_completed(self, case, count):
        self.assertEqual(case.app.canvas.request_draw.call_count, count)
        self.assertEqual(len(case.detector.timestamps), count)
        case.notify.assert_called_with(case.app.cap, frame_processed=True)

    def test_storm_wall_clock_rollback_keeps_detection_and_next_draw(self):
        case = self.build_scene(*SCENES[0])
        case.app.animate()
        case.clock.wall -= 10.0
        case.clock.steady += 0.04
        case.app.animate()
        self.assert_frame_completed(case, 2)
        self.assertGreater(case.detector.timestamps[1], case.detector.timestamps[0])

    def test_storm_frames_in_the_same_millisecond_get_distinct_timestamps(self):
        case = self.build_scene(*SCENES[0])
        for _ in range(3):
            case.app.animate()
        self.assert_frame_completed(case, 3)
        timestamps = case.detector.timestamps
        self.assertTrue(all(later > earlier for earlier, later in zip(timestamps, timestamps[1:])))

    def test_wall_clock_adjustments_do_not_change_physics_elapsed_time(self):
        for filename, class_name in SCENES:
            for wall_jump in (-10.0, 300.0):
                with self.subTest(scene=filename, wall_jump=wall_jump):
                    case = self.build_scene(filename, class_name)
                    # Isolate the physics input even if the camera has no usable frame yet.
                    case.app.cap.read.return_value = (False, None)
                    case.clock.wall += wall_jump
                    case.clock.steady += 0.04
                    case.app.animate()
                    self.assertEqual(case.app.update_physics.call_count, 1)
                    self.assertAlmostEqual(case.app.update_physics.call_args.args[0], 0.04)
                    case.app.canvas.request_draw.assert_called_once_with()

    def test_elapsed_time_retains_the_existing_lag_cap(self):
        for filename, class_name in SCENES:
            with self.subTest(scene=filename):
                case = self.build_scene(filename, class_name)
                case.clock.wall += 2.0
                case.clock.steady += 2.0
                case.app.animate()
                case.app.update_physics.assert_called_once_with(0.1)
                self.assert_frame_completed(case, 1)

    def test_saturn_existing_timestamp_guard_handles_rollback_and_same_ms(self):
        case = self.build_scene(*SCENES[1])
        case.app.animate()
        case.clock.wall -= 10.0
        case.clock.steady += 0.04
        case.app.animate()
        case.app.animate()
        self.assert_frame_completed(case, 3)

    def test_capture_failure_and_recovery_preserve_draw_scheduling(self):
        for filename, class_name in SCENES:
            with self.subTest(scene=filename):
                case = self.build_scene(filename, class_name)
                case.app.animate()
                case.app.cap.read.return_value = (False, None)
                case.clock.wall += 0.04
                case.clock.steady += 0.04
                case.app.animate()
                case.notify.assert_called_with(case.app.cap, frame_processed=False)
                case.app.cap.read.return_value = (True, object())
                case.clock.wall += 0.04
                case.clock.steady += 0.04
                case.app.animate()
                self.assertEqual(case.app.canvas.request_draw.call_count, 3)
                self.assertEqual(len(case.detector.timestamps), 2)
                case.notify.assert_called_with(case.app.cap, frame_processed=True)


if __name__ == "__main__":
    unittest.main()
