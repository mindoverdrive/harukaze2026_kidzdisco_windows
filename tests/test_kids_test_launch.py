import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())
import manager
import shared_camera


class KidsTestLaunchTests(unittest.TestCase):
    def test_explicit_kids_config_reaches_manager_camera_and_single_scene(self):
        config_path = Path(__file__).resolve().parents[1] / "configs" / "kids_test_acer.json"
        relay = mock.Mock()
        relay.start.side_effect = RuntimeError("stop before opening hardware")
        with (
            mock.patch.object(sys, "argv", ["manager.py", "--config", str(config_path)]),
            mock.patch.object(manager, "CONFIG", dict(manager.CONFIG)),
            mock.patch.object(manager, "SharedCameraRelay", return_value=relay) as relay_constructor,
            mock.patch("builtins.print"),
            mock.patch.object(manager.traceback, "print_exc"),
        ):
            self.assertEqual(manager.main(), 1)
            self.assertEqual(manager.CONFIG["PRODUCTION_SCENES"], ["finger_colorfull_dots_acer.py"])
            self.assertFalse(manager.CONFIG["CLAP_MONITOR_ENABLED"])
            self.assertEqual(manager.CONFIG["PRELOAD_COUNT"], 0)
        self.assertEqual(relay_constructor.call_args.kwargs["fps"], 30)
        self.assertEqual(relay_constructor.call_args.kwargs["exposure"], -5)
        self.assertIsNone(relay_constructor.call_args.kwargs["explicit_index"])
        self.assertTrue(relay_constructor.call_args.kwargs["require_name_match"])

    def test_required_c922_name_never_falls_back_to_builtin_camera(self):
        with mock.patch.object(shared_camera, "enumerate_camera_devices", return_value=["ACER HD User Facing"]):
            with self.assertRaisesRegex(RuntimeError, "No camera matches"):
                shared_camera.choose_camera_index(0, ["c922"], require_name_match=True)

    def test_bad_explicit_config_does_not_start_default_playlist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text("{bad json", encoding="utf-8")
            with (
                mock.patch.object(sys, "argv", ["manager.py", "--config", str(path)]),
                mock.patch.object(manager, "CONFIG", dict(manager.CONFIG)),
                mock.patch.object(manager, "SharedCameraRelay") as relay,
                mock.patch("builtins.print"),
                mock.patch.object(manager.traceback, "print_exc"),
            ):
                relay.return_value.start.side_effect = RuntimeError("unexpected camera startup")
                self.assertEqual(manager.main(), 2)
                relay.assert_not_called()


if __name__ == "__main__":
    unittest.main()
