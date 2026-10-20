"""Execute real Minecraft lifecycle methods with mocked native resources."""
import ast
from contextlib import ExitStack
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock
from shared_camera import ENV_REQUIRED
from minecraft_reset import TwoHandReset, reset_sample, MAX_PARTICLES, RESET_SECONDS

ROOT = Path(os.environ.get('MINECRAFT_TEST_ROOT', Path(__file__).resolve().parents[1]))


def load_classes():
    path = Path(os.environ.get('MINECRAFT_TEST_SOURCE', ROOT / 'minecraft.py'))
    tree = ast.parse(path.read_text(encoding='utf-8'))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in {'MinecraftApp', 'GestureManager'}]
    ns = dict(ExitStack=ExitStack, scene_control=mock.Mock(_child_control=object()),
              time=mock.Mock(), cv2=mock.MagicMock(), gfx=mock.MagicMock(),
              RenderCanvas=mock.Mock(), display_utils=mock.Mock(), loop=mock.Mock(),
              WINDOW_WIDTH=1280, WINDOW_HEIGHT=720, np=mock.MagicMock(),
              mp=mock.MagicMock(), TwoHandReset=TwoHandReset, reset_sample=reset_sample,
              MAX_PARTICLES=MAX_PARTICLES, RESET_SECONDS=RESET_SECONDS)
    ns['time'].time.return_value = 1.0
    ns['time'].monotonic.return_value = 1.0
    exec(compile(ast.Module(body=classes, type_ignores=[]), str(path), 'exec'), ns)
    return ns


class MinecraftLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_classes()
        self.cls = self.ns['MinecraftApp']

    def frame_app(self):
        app = self.cls.__new__(self.cls)
        app.last_time = 0
        app._reset_remaining = 0.0
        app._reset_finished_this_frame = False
        app.cursor = mock.Mock()
        app._camera_failure_since = None
        app._last_frame_id = None
        app._last_fresh_at = 1
        app._frame_error = None
        app.update_particles = mock.Mock()
        app.cap = mock.Mock(last_read_frame_id=1)
        app.cap.read.return_value = (True, object())
        app.canvas = mock.Mock()
        app.renderer = mock.Mock()
        app.hand_overlay = mock.Mock()
        app.scene, app.camera = object(), object()
        app.bg_tex = mock.MagicMock()
        app.gesture_manager = mock.Mock(reset_trigger=False, color_cycle_trigger=False)
        app.gesture_manager.reset_gesture = TwoHandReset()
        app.gesture_manager.process.return_value = {'left_hand': None, 'right_hand': None}
        app.update_camera = mock.Mock()
        return app

    def test_first_frame_sent_only_after_successful_render(self):
        app = self.frame_app()
        order = []
        app.renderer.render.side_effect = lambda *a, **kw: order.append('render')
        self.ns['scene_control'].notify_first_frame.side_effect = lambda *a: order.append('frame')
        app._animate_frame()
        self.assertEqual(order, ['render', 'render', 'frame'])

    def test_overlay_render_failure_also_blocks_first_frame(self):
        app = self.frame_app()
        app.renderer.render.side_effect = [None, RuntimeError('overlay failed')]
        app.animate()
        self.ns['scene_control'].notify_first_frame.assert_not_called()
        self.assertIsInstance(app._frame_error, RuntimeError)

    def test_missing_or_frozen_input_clears_feedback_without_rearming_or_first_frame(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                app = self.frame_app()
                app._last_frame_id = 1
                self.ns['time'].monotonic.return_value = 1.3
                if missing:
                    app.cap.read.return_value = (False, None)
                app._animate_frame()
                app.hand_overlay.clear.assert_called_once()
                app.gesture_manager.process.assert_not_called()
                self.ns['scene_control'].notify_first_frame.assert_not_called()
                self.assertEqual(app.renderer.render.call_count, 2)

    def test_render_exception_stops_loop_and_is_not_announced_as_first_frame(self):
        app = self.frame_app()
        app.renderer.render.side_effect = RuntimeError('GPU surface lost')
        app.animate()
        self.ns['loop'].stop.assert_called_once()
        self.ns['scene_control'].notify_first_frame.assert_not_called()
        self.assertIsInstance(app._frame_error, RuntimeError)

    def test_draw_callback_exception_becomes_observable_process_error(self):
        app = self.frame_app()
        app._frame_error = RuntimeError('callback failed')
        app.cleanup = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, 'callback failed'):
            app.run()
        app.cleanup.assert_called_once()

    def test_camera_miss_schedules_retry_then_expires(self):
        app = self.frame_app()
        app.cap.read.return_value = (False, None)
        app._animate_frame()
        app.canvas.request_draw.assert_called_once()
        self.ns['time'].monotonic.return_value = 5
        with self.assertRaisesRegex(RuntimeError, 'input stopped'):
            app._animate_frame()
        self.ns['scene_control'].notify_first_frame.assert_not_called()

    def test_frozen_shared_frame_is_detected_without_false_first_frame(self):
        app = self.frame_app()
        app._last_frame_id = 1
        self.ns['time'].monotonic.return_value = 5
        with self.assertRaisesRegex(RuntimeError, 'stopped advancing'):
            app._animate_frame()
        self.ns['scene_control'].notify_first_frame.assert_not_called()

    def test_managed_start_without_shared_metadata_allocates_nothing(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'physical fallback'):
                self.cls()
        self.ns['RenderCanvas'].assert_not_called()
        self.ns['display_utils'].open_camera.assert_not_called()

    def test_attach_failure_closes_created_canvas(self):
        canvas = mock.Mock()
        self.ns['RenderCanvas'].return_value = canvas
        self.ns['display_utils'].open_camera.return_value = None
        with mock.patch.dict(os.environ, {'HARUKAZE_CAMERA_SHM': 'test', ENV_REQUIRED: '1'}):
            with mock.patch.object(self.cls, 'verify_managed_display'), self.assertRaisesRegex(RuntimeError, 'attach failed'):
                self.cls()
        canvas.close.assert_called_once()

    def test_partial_model_initialization_closes_first_model(self):
        hands = self.ns['mp'].solutions.hands.Hands.return_value
        self.ns['mp'].solutions.face_mesh.FaceMesh.side_effect = RuntimeError('model failed')
        with self.assertRaisesRegex(RuntimeError, 'model failed'):
            self.ns['GestureManager']()
        hands.close.assert_called_once()

    def test_cleanup_is_idempotent_and_attempts_all_resources_on_error(self):
        app = self.cls.__new__(self.cls)
        app._resources = ExitStack()
        cap, canvas, detector = mock.Mock(), mock.Mock(), mock.Mock()
        app._resources.callback(canvas.close)
        app._resources.callback(cap.release)
        app._resources.callback(detector.close)
        detector.close.side_effect = RuntimeError('close error')
        app.renderer = object()
        with self.assertRaises(RuntimeError):
            app.cleanup()
        app.cleanup()
        cap.release.assert_called_once()
        canvas.close.assert_called_once()
        self.assertIsNone(app.renderer)

    def test_window_close_stops_loop(self):
        app = self.cls.__new__(self.cls)
        app.on_event({'event_type': 'close'})
        self.ns['loop'].stop.assert_called_once()

    def test_wrong_display_position_rejects_startup(self):
        app = self.cls.__new__(self.cls)
        app.canvas = mock.Mock()
        self.ns['display_utils'].get_second_monitor_size.return_value = (1920, 1080, 1920, 0)
        glfw = mock.Mock()
        glfw.get_window_pos.return_value = (0, 0)
        glfw.get_window_size.return_value = (1920, 1080)
        with mock.patch.dict('sys.modules', {'glfw': glfw}), self.assertRaisesRegex(RuntimeError, 'geometry mismatch'):
            app.verify_managed_display()

    def test_correct_audience_geometry_is_accepted(self):
        app = self.cls.__new__(self.cls)
        app.canvas = mock.Mock()
        self.ns['display_utils'].get_second_monitor_size.return_value = (1920, 1080, 1920, 0)
        glfw = mock.Mock()
        glfw.get_window_pos.return_value = (1920, 0)
        glfw.get_window_size.return_value = (1920, 1080)
        with mock.patch.dict('sys.modules', {'glfw': glfw}):
            app.verify_managed_display()

    def test_scheduling_error_also_releases_resources(self):
        app = self.frame_app()
        app.canvas.request_draw.side_effect = RuntimeError('draw schedule failed')
        app.cleanup = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, 'schedule failed'):
            app.run()
        app.cleanup.assert_called_once()

    def test_render_design_and_gesture_methods_match_committed_baseline(self):
        before = ast.parse(subprocess.check_output(['git', 'show', '3f98cb0ad6f400d6264b07fa512c133be2f0ed33:minecraft.py'], cwd=ROOT).decode('utf-8'))
        after = ast.parse(Path(os.environ.get('MINECRAFT_TEST_SOURCE', ROOT/'minecraft.py')).read_text(encoding='utf-8'))
        def definitions(tree):
            return {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        old, new = definitions(before), definitions(after)
        # Reset/effect and corrected projection have dedicated behavioral regression tests.
        for name in ('is_pointing', 'is_palm_open', 'is_fist',
                     'grid_coords', 'create_block',
                     'update_camera', 'update_hud_color'):
            with self.subTest(method=name):
                self.assertEqual(ast.dump(old[name]), ast.dump(new[name]))


if __name__ == '__main__':
    unittest.main()
