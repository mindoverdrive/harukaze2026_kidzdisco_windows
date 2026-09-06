import os
import sys
import json
import tempfile
import threading
import unittest
from unittest import mock


sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())

import scene_profile_runner
import shared_camera
import manager


class CameraProfileTests(unittest.TestCase):
    def test_exposure_is_explicit_verified_and_preserved_for_reopen(self):
        relay = shared_camera.SharedCameraRelay.__new__(shared_camera.SharedCameraRelay)
        relay.camera_index, relay.width, relay.height, relay.fps = 1, 1280, 720, 30
        relay.fourcc, relay.backend_preference = "MJPG", "dshow"
        relay.fallback_to_default, relay.strict_backend, relay.exposure = False, True, -5
        relay.zoom, relay.controls = None, mock.Mock()
        relay.stop_event = threading.Event()
        with mock.patch.object(shared_camera, "_open_with_backends") as open_capture:
            open_capture.return_value.get.return_value = -1
            relay._create_capture()
            self.assertEqual(open_capture.call_args.kwargs["exposure"], -5)

        for requested, actual, accepted in [(None, -4, True), (-5, -5, True), (-5, -4, True), (-5, -5, False)]:
            with self.subTest(requested=requested, actual=actual, accepted=accepted):
                cap = mock.Mock()
                cap.get.return_value = actual
                cap.set.return_value = accepted
                with (mock.patch.object(shared_camera.cv2, "CAP_PROP_EXPOSURE", 15),
                      mock.patch.object(shared_camera.cv2, "VideoCapture", return_value=cap),
                      mock.patch.object(shared_camera, "_backend_order", return_value=[700])):
                    result = shared_camera._open_with_backends(1, 1280, 720, 30, "MJPG", "dshow", False, True,
                                                              exposure=requested)
                exposure_calls = [call for call in cap.set.call_args_list if call.args[0] == 15]
                if requested is None:
                    self.assertEqual(exposure_calls, [])
                else:
                    self.assertEqual(len(exposure_calls), 1)
                if requested is not None and (actual != requested or not accepted):
                    self.assertIsNone(result)
                    cap.release.assert_called_once()
                else:
                    self.assertIs(result, cap)

    def test_dshow_format_survives_fps_device_reconfiguration(self):
        # Model the OpenCV DShow FPS setter reopening with its default format.
        properties = {3: 640, 4: 480, 5: 15, 6: 844715353}

        def set_property(key, value):
            properties[key] = value
            if key == 5:
                properties[6] = 844715353  # YUY2
            return True

        cap = mock.Mock()
        cap.set.side_effect = set_property
        cap.get.side_effect = lambda key: properties.get(key, 0)
        with (
            mock.patch.multiple(shared_camera.cv2, CAP_PROP_FRAME_WIDTH=3, CAP_PROP_FRAME_HEIGHT=4,
                                CAP_PROP_FPS=5, CAP_PROP_FOURCC=6, CAP_PROP_CONVERT_RGB=16,
                                CAP_PROP_BUFFERSIZE=38, CAP_DSHOW=700),
            mock.patch.object(shared_camera.cv2, "VideoCapture", return_value=cap),
            mock.patch.object(shared_camera.cv2, "VideoWriter_fourcc", return_value=1196444237),
            mock.patch.object(shared_camera, "_backend_order", return_value=[700]),
        ):
            opened = shared_camera._open_with_backends(1, 1280, 720, 30, "MJPG", "dshow", False, True)
        self.assertIs(opened, cap)
        self.assertEqual((properties[3], properties[4], properties[5]), (1280, 720, 30))
        self.assertEqual(shared_camera._decode_fourcc(properties[6]), "MJPG")

    def test_capture_fps_counts_intervals_between_first_and_last_frame(self):
        cap = mock.Mock()
        cap.read.return_value = (True, object())
        with mock.patch.object(shared_camera.time, "perf_counter", side_effect=[0, 0, 0.5, 0.75, 1.0, 2.0]):
            measured_fps, count = shared_camera._measure_capture_fps(cap, 2)
        self.assertEqual(count, 2)
        self.assertEqual(measured_fps, 2.0)

    def test_manager_camera_environment_overrides_json_config(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as config_file:
            json.dump(
                {
                    "CAMERA_FPS": 60,
                    "CAMERA_EXPOSURE": -4,
                    "CAMERA_BACKEND": "msmf",
                    "CAMERA_ALLOW_FALLBACK": True,
                },
                config_file,
            )
            config_path = config_file.name

        try:
            with mock.patch.dict(
                os.environ,
                {
                    "KIDZDISCO_CAMERA_FPS": "30",
                    "KIDZDISCO_CAMERA_EXPOSURE": "-5",
                    "KIDZDISCO_CAMERA_BACKEND": "dshow",
                    "KIDZDISCO_CAMERA_ALLOW_FALLBACK": "false",
                },
                clear=False,
            ):
                config = manager.load_config(config_path)
        finally:
            os.unlink(config_path)

        self.assertEqual(config["CAMERA_FPS"], 30)
        self.assertEqual(config["CAMERA_EXPOSURE"], -5)
        self.assertEqual(config["CAMERA_BACKEND"], "dshow")
        self.assertIs(config["CAMERA_ALLOW_FALLBACK"], False)
        self.assertEqual(config["_CAMERA_CONFIG_SOURCES"]["CAMERA_FPS"], "environment")

    def test_explicit_camera_index_must_match_configured_device_name(self):
        devices = ["Integrated Camera", "Logitech C922 Pro Stream Webcam"]
        with mock.patch.object(shared_camera, "enumerate_camera_devices", return_value=devices):
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                shared_camera.choose_camera_index(
                    camera_index=1,
                    camera_name_hint=["c922"],
                    exclude_name_hints=["virtual"],
                    explicit_index=0,
                )

            selected = shared_camera.choose_camera_index(
                camera_index=0,
                camera_name_hint=["c922"],
                exclude_name_hints=["virtual"],
                explicit_index=1,
            )

        self.assertEqual(selected, 1)

    def test_acer_profile_does_not_overwrite_manager_camera_environment(self):
        inherited = {
            "KIDZDISCO_CAMERA_INDEX": "7",
            "KIDZDISCO_CAMERA_BACKEND": "dshow",
            "KIDZDISCO_CAMERA_STRICT_BACKEND": "true",
            "KIDZDISCO_CAMERA_ALLOW_FALLBACK": "false",
        }
        observed = {}

        def capture_environment(*_args, **_kwargs):
            observed.update(os.environ)

        with (
            mock.patch.dict(os.environ, inherited, clear=True),
            mock.patch.object(scene_profile_runner.runpy, "run_path", side_effect=capture_environment),
        ):
            scene_profile_runner.run_scene("finger_colorfull_dots_2.py", profile="acer")

        for key, value in inherited.items():
            self.assertEqual(observed[key], value)
        self.assertEqual(observed["KIDZDISCO_DISPLAY_TARGET"], "primary")

    def test_standalone_acer_profile_still_supplies_camera_defaults(self):
        observed = {}

        def capture_environment(*_args, **_kwargs):
            observed.update(os.environ)

        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(scene_profile_runner.runpy, "run_path", side_effect=capture_environment),
        ):
            scene_profile_runner.run_scene("finger_colorfull_dots_2.py", profile="acer")

        self.assertEqual(observed["KIDZDISCO_CAMERA_INDEX"], "0")
        self.assertEqual(observed["KIDZDISCO_CAMERA_BACKEND"], "any")
        self.assertEqual(observed["KIDZDISCO_CAMERA_ALLOW_FALLBACK"], "true")

    def test_relay_exports_resolved_camera_profile_to_managed_scene(self):
        relay = shared_camera.SharedCameraRelay.__new__(shared_camera.SharedCameraRelay)
        relay.shm_name = "test_camera"
        relay.width = 640
        relay.height = 360
        relay.channels = 3
        relay.fps = 60.0
        relay.fourcc = "MJPG"
        relay.exposure = -5
        relay.zoom = None
        relay.camera_index = 2
        relay.backend_preference = "dshow"
        relay.strict_backend = True
        relay.fallback_to_default = False

        env = relay.export_env()

        self.assertEqual(env["HARUKAZE_SHARED_CAMERA_REQUIRED"], "1")
        self.assertEqual(env["KIDZDISCO_CAMERA_INDEX"], "2")
        self.assertEqual(env["KIDZDISCO_CAMERA_OPENCV_INDEX"], "2")
        self.assertEqual(env["KIDZDISCO_CAMERA_WIDTH"], "640")
        self.assertEqual(env["KIDZDISCO_CAMERA_HEIGHT"], "360")
        self.assertEqual(env["KIDZDISCO_CAMERA_FPS"], "60")
        self.assertEqual(env["KIDZDISCO_CAMERA_EXPOSURE"], "-5")
        self.assertEqual(env["KIDZDISCO_CAMERA_BACKEND"], "dshow")
        self.assertEqual(env["KIDZDISCO_CAMERA_STRICT_BACKEND"], "true")
        self.assertEqual(env["KIDZDISCO_CAMERA_ALLOW_FALLBACK"], "false")

    def test_managed_scene_never_falls_back_to_physical_camera(self):
        required_env = {
            shared_camera.ENV_ENABLED: "1",
            "HARUKAZE_SHARED_CAMERA_REQUIRED": "1",
        }
        with (
            mock.patch.dict(os.environ, required_env, clear=True),
            mock.patch.object(shared_camera.SharedMemoryCamera, "from_env", return_value=None),
            mock.patch.object(shared_camera.SharedMemoryCamera, "from_session_file") as session_attach,
            mock.patch.object(shared_camera, "_open_with_backends") as physical_open,
        ):
            with self.assertRaisesRegex(RuntimeError, "required"):
                shared_camera.open_camera_source(0, 640, 360, 60)

        session_attach.assert_not_called()
        physical_open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
