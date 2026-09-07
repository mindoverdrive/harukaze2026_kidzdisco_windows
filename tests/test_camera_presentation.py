import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from camera_presentation import (
    CameraPresentationControl, CameraPresentationReader, ENV_KEY,
    apply_camera_opacity,
)


class CameraPresentationTests(unittest.TestCase):
    def test_session_update_reaches_separate_reader_and_cleanup(self):
        control = CameraPresentationControl()
        path = control.path
        try:
            with mock.patch.dict(os.environ, control.export_env()):
                reader = CameraPresentationReader.from_env()
            reader.poll_interval = 0
            self.assertEqual(reader.opacity(), 1)
            control.set_opacity(0.25)
            self.assertEqual(reader.opacity(), 0.25)
            self.assertEqual(control.opacity, 0.25)
        finally:
            control.close()
        self.assertFalse(path.exists())
        self.assertEqual(reader.opacity(), 0.25)

    def test_invalid_commands_do_not_change_published_value(self):
        control = CameraPresentationControl()
        try:
            for value in (True, "0.5", None, -0.1, 1.1, float("nan"), float("inf")):
                with self.assertRaises(ValueError):
                    control.set_opacity(value)
            self.assertEqual(CameraPresentationReader(control.path).opacity(), 1)
        finally:
            control.close()

    def test_corrupt_or_missing_control_retains_last_value(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            reader = CameraPresentationReader(path, poll_interval=0)
            self.assertEqual(reader.opacity(), 1)
            path.write_text('{"opacity": 0.4}')
            self.assertEqual(reader.opacity(), 0.4)
            for raw in ('{', '[]', '{"opacity": null}', '{"opacity": true}', 'x' * 1025):
                path.write_text(raw)
                self.assertEqual(reader.opacity(), 0.4)

    def test_polling_is_bounded_and_sessions_are_isolated(self):
        one, two = CameraPresentationControl(), CameraPresentationControl()
        try:
            reader = CameraPresentationReader(one.path)
            with mock.patch("camera_presentation.time.monotonic", return_value=10):
                self.assertEqual(reader.opacity(), 1)
                one.set_opacity(0)
                self.assertEqual(reader.opacity(), 1)
            with mock.patch("camera_presentation.time.monotonic", return_value=10.2):
                self.assertEqual(reader.opacity(), 0)
            self.assertEqual(CameraPresentationReader(two.path).opacity(), 1)
        finally:
            one.close()
            two.close()

    def test_default_is_exact_identity_without_numpy_dependency(self):
        frame = object()
        self.assertIs(apply_camera_opacity(frame, 1), frame)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(CameraPresentationReader.from_env().opacity(), 1)

    def test_display_copy_changes_without_touching_detection_array(self):
        try:
            import numpy as np
            import cv2
            if not isinstance(np.__version__, str) or isinstance(cv2.convertScaleAbs, mock.Mock):
                self.skipTest("Real numpy/OpenCV required")
        except (ImportError, AttributeError):
            self.skipTest("Real numpy required")
        frame = np.array([[[0, 80, 200], [40, 120, 240]]], dtype=np.uint8)
        original = frame.copy()
        dimmed = apply_camera_opacity(frame, 0.5)
        np.testing.assert_array_equal(frame, original)
        np.testing.assert_array_equal(dimmed, [[[0, 40, 100], [20, 60, 120]]])
        self.assertFalse(np.shares_memory(frame, dimmed))
        self.assertFalse(apply_camera_opacity(frame, 0).any())

    def test_prepare_frame_keeps_detection_and_layout_at_zero_opacity(self):
        import numpy as np
        import cv2
        if not isinstance(getattr(np, '__version__', None), str) or isinstance(cv2.flip, mock.Mock):
            self.skipTest('Real numpy/OpenCV required')
        import display_utils
        frame = np.full((4, 8, 3), 120, dtype=np.uint8)
        with mock.patch.object(display_utils._camera_presentation, 'opacity', return_value=1):
            detected, visible, layout = display_utils.prepare_camera_frame(frame, 16, 8)
        with mock.patch.object(display_utils._camera_presentation, 'opacity', return_value=0):
            detected_hidden, hidden, hidden_layout = display_utils.prepare_camera_frame(frame, 16, 8)
        np.testing.assert_array_equal(detected, detected_hidden)
        np.testing.assert_array_equal(frame, np.full((4, 8, 3), 120, dtype=np.uint8))
        self.assertEqual(layout, hidden_layout)
        self.assertTrue(visible.any())
        self.assertFalse(hidden.any())


if __name__ == "__main__":
    unittest.main()
