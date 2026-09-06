"""Execute the actual GPU draw callbacks without requiring a GPU or camera."""
import ast
from pathlib import Path
import unittest
from unittest import mock


def load_callback(filename, class_name, method_name, namespace):
    path = Path(__file__).resolve().parents[1] / filename
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    module = ast.Module(body=[method], type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[method_name]


class FirstFrameRenderTests(unittest.TestCase):
    def test_particle_render_failure_is_not_reported_as_first_frame(self):
        for failed_pass in (0, 1, 2, None):
            with self.subTest(failed_pass=failed_pass):
                notify = mock.Mock()
                display = mock.Mock()
                display.prepare_camera_frame.return_value = (object(), object(), object())
                ns = dict(time=mock.Mock(), cv2=mock.Mock(), mp=mock.Mock(),
                          display_utils=display, WINDOW_WIDTH=640, WINDOW_HEIGHT=360,
                          notify_first_frame=notify)
                ns["time"].time.return_value = 100.1
                ns["time"].monotonic.return_value = 100.1
                callback = load_callback("particle_storm_2.py", "ParticleStormApp", "animate", ns)
                app = mock.Mock(last_time=100.0, last_timestamp=0)
                app.cap.read.return_value = (True, object())
                app.cam_tex = mock.MagicMock()
                app.renderer.render.side_effect = [RuntimeError("injected GPU failure") if i == failed_pass else None for i in range(3)]
                callback(app)
                notify.assert_called_once_with(app.cap, frame_processed=failed_pass is None)

    def test_saturn_render_failure_does_not_send_first_frame(self):
        notify = mock.Mock()
        ns = dict(time=mock.Mock(), notify_first_frame=notify)
        ns["time"].time.return_value = 100.1
        ns["time"].monotonic.return_value = 100.1
        callback = load_callback("saturn_particles_2.py", "SaturnParticlesApp", "animate", ns)
        app = mock.Mock(last_time=100.0)
        app.detect_hands.return_value = True
        app.renderer.render.side_effect = RuntimeError("injected GPU failure")
        callback(app)
        notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
