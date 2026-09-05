import sys
import unittest
from unittest import mock

sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())
import display_utils


class CameraCoordinateTests(unittest.TestCase):
    def test_all_landmark_corners_stay_inside_the_displayed_camera_rectangle(self):
        for source, stage in [((1280, 720), (1920, 1080)), ((640, 480), (1920, 1080)),
                              ((1280, 720), (1360, 800)), ((1280, 720), (721, 1281))]:
            with self.subTest(source=source, stage=stage):
                layout = display_utils.get_uniform_layout(*source, *stage)
                left, top = layout["offset_x"], layout["offset_y"]
                right = left + layout["scaled_width"] - 1
                bottom = top + layout["scaled_height"] - 1
                self.assertEqual(display_utils.normalized_to_stage(0, 0, layout), (left, top))
                self.assertEqual(display_utils.normalized_to_stage(1, 1, layout), (right, bottom))
                self.assertEqual(display_utils.normalized_to_stage(-1, 2, layout), (left, bottom))
                x, y = display_utils.normalized_to_stage(0.5, 0.5, layout)
                self.assertLessEqual(abs(x - (left + right) / 2), 0.5)
                self.assertLessEqual(abs(y - (top + bottom) / 2), 0.5)

    def test_mediapipe_input_and_display_share_one_mirror_and_one_layout(self):
        raw_frame = mock.Mock(shape=(720, 1280, 3))
        mirrored_frame = mock.Mock(shape=(720, 1280, 3))
        stage_frame = object()
        with (
            mock.patch.object(display_utils.cv2, "flip", return_value=mirrored_frame) as flip,
            mock.patch.object(display_utils, "fit_frame_to_size", return_value=stage_frame) as fit,
        ):
            camera_input, shown_frame, layout = display_utils.prepare_camera_frame(raw_frame, 1360, 800)
        self.assertIs(camera_input, mirrored_frame)
        self.assertIs(shown_frame, stage_frame)
        flip.assert_called_once_with(raw_frame, 1)
        self.assertIs(fit.call_args.args[0], camera_input)
        self.assertIs(fit.call_args.kwargs["layout"], layout)


if __name__ == "__main__":
    unittest.main()
