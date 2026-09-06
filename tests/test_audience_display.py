"""Audience output must not fall back onto the Acer operator display."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())
import display_utils
import manager
import scene_profile_runner
import stage_display


PRIMARY = r"\\.\DISPLAY1"
AUDIENCE = r"\\.\DISPLAY2"


def monitor(name, x, y, width, height, primary=False):
    return SimpleNamespace(name=name, x=x, y=y, width=width, height=height, is_primary=primary)


def config():
    return {"DISPLAY_TARGET": "audience", "DISPLAY_NAME": AUDIENCE,
            "CONTROL_DISPLAY_NAME": PRIMARY}


class AudienceDisplayTests(unittest.TestCase):
    def test_missing_display2_never_falls_back_to_operator_screen(self):
        screens = [monitor(PRIMARY, 0, 0, 1920, 1080, True)]
        with mock.patch.object(display_utils, "_DISPLAY_CFG", config()), mock.patch.dict(
            sys.modules, {"screeninfo": SimpleNamespace(get_monitors=lambda: screens)}
        ):
            with self.assertRaisesRegex(RuntimeError, "DISPLAY2"):
                display_utils.get_second_monitor()

    def test_display2_is_selected_by_name_and_live_geometry_not_enumeration_order(self):
        screens = [monitor(r"\\.\DISPLAY3", 1920, 0, 1366, 768),
                   monitor(PRIMARY, 0, 0, 1920, 1080, True),
                   monitor(AUDIENCE, -1920, -120, 1920, 1080)]
        stale = dict(config(), DISPLAY_X=1920, DISPLAY_Y=0, DISPLAY_WIDTH=1360, DISPLAY_HEIGHT=800)
        with mock.patch.object(display_utils, "_DISPLAY_CFG", stale), mock.patch.dict(
            sys.modules, {"screeninfo": SimpleNamespace(get_monitors=lambda: screens)}
        ):
            self.assertEqual(display_utils.get_second_monitor(), (-1920, -120, 1920, 1080))

    def test_cloned_or_primary_audience_output_is_rejected(self):
        cases = [
            [monitor(PRIMARY, 0, 0, 1920, 1080, True), monitor(AUDIENCE, 0, 0, 1920, 1080)],
            [monitor(PRIMARY, 1920, 0, 1920, 1080), monitor(AUDIENCE, 0, 0, 1920, 1080, True)],
        ]
        for screens in cases:
            with self.subTest(screens=screens), mock.patch.object(display_utils, "_DISPLAY_CFG", config()), mock.patch.dict(
                sys.modules, {"screeninfo": SimpleNamespace(get_monitors=lambda: screens)}
            ):
                with self.assertRaises(RuntimeError):
                    display_utils.get_second_monitor()

    def test_child_rejects_layout_change_instead_of_disagreeing_with_transition(self):
        screens = [monitor(PRIMARY, 0, 0, 1920, 1080, True), monitor(AUDIENCE, -1920, 0, 1920, 1080)]
        resolved = dict(config(), DISPLAY_RESOLVED=True, DISPLAY_X=1920, DISPLAY_Y=0,
                        DISPLAY_WIDTH=1920, DISPLAY_HEIGHT=1080)
        with mock.patch.object(display_utils, "_DISPLAY_CFG", resolved), mock.patch.dict(
            sys.modules, {"screeninfo": SimpleNamespace(get_monitors=lambda: screens)}
        ):
            with self.assertRaisesRegex(stage_display.DisplayConfigurationError, "layout changed"):
                display_utils.get_second_monitor()

    def test_manager_checks_audience_display_before_allocating_camera(self):
        kids = Path(__file__).resolve().parents[1] / "configs" / "kids_test_acer.json"
        settings = json.loads(kids.read_text(encoding="utf-8"))
        settings.update(config())
        screens = [monitor(PRIMARY, 0, 0, 1920, 1080, True)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audience.json"
            path.write_text(json.dumps(settings), encoding="utf-8")
            with (
                mock.patch.object(sys, "argv", ["manager.py", "--config", str(path)]),
                mock.patch.object(manager, "CONFIG", dict(manager.CONFIG)),
                mock.patch.object(manager, "configure_audience_dpi"),
                mock.patch.dict(sys.modules, {"screeninfo": SimpleNamespace(get_monitors=lambda: screens)}),
                mock.patch.object(manager, "SharedCameraRelay") as relay,
                mock.patch("builtins.print"),
                mock.patch.object(manager.traceback, "print_exc"),
            ):
                relay.return_value.start.side_effect = RuntimeError("unexpected physical camera allocation")
                self.assertEqual(manager.main(), 2)
                relay.assert_not_called()

    def test_scene_and_transition_receive_the_same_resolved_geometry(self):
        screens = [monitor(PRIMARY, 0, 0, 1920, 1080, True),
                   monitor(AUDIENCE, -1920, -120, 1920, 1080)]
        with mock.patch.dict(sys.modules, {"screeninfo": SimpleNamespace(get_monitors=lambda: screens)}):
            resolved = stage_display.apply_audience_displays(dict(manager.DEFAULT_CONFIG, **config()))
        with mock.patch.object(manager, "CONFIG", resolved), mock.patch.dict(
            manager.os.environ, {"KIDZDISCO_DISPLAY_TARGET": "primary", "SDL_WINDOWS_DPI_SCALING": "1"}
        ):
            owner = manager.SceneManager(scenes=["fixture_acer.py"])
            env = owner._scene_env()
            geometry = tuple(int(env[f"KIDZDISCO_DISPLAY_{k}"]) for k in ("X", "Y", "WIDTH", "HEIGHT"))
            self.assertEqual(owner._stage_geometry(), geometry)
            self.assertEqual(geometry, (-1920, -120, 1920, 1080))
            self.assertEqual(env["KIDZDISCO_DISPLAY_TARGET"], "audience")
            self.assertEqual(env["KIDZDISCO_DISPLAY_NAME"], AUDIENCE)
            self.assertEqual(env["SDL_WINDOWS_DPI_SCALING"], "0")

    def test_manager_places_control_on_primary_and_cleans_up_on_quit(self):
        root = Path(__file__).resolve().parents[1]
        settings = json.loads((root / "configs/rebirth_acer_xiaomi.json").read_text(encoding="utf-8"))
        screens = [monitor(settings["CONTROL_DISPLAY_NAME"], 0, 0, 1920, 1080, True),
                   monitor(settings["DISPLAY_NAME"], 1920, 0, 1920, 1080)]
        owner = mock.Mock(fatal_error=None, completed_promotions=1)
        owner.is_scene_running.return_value = True
        relay = mock.Mock(thread=None)
        relay.export_env.return_value = {}
        panel = mock.Mock()
        panel.consume_action.return_value = "quit"
        with (
            mock.patch.object(sys, "argv", ["manager.py", "--config", str(root / "configs/rebirth_acer_xiaomi.json"), "--operator-port", "8766"]),
            mock.patch.object(manager, "CONFIG", dict(manager.CONFIG)),
            mock.patch.object(manager, "configure_audience_dpi"),
            mock.patch.dict(sys.modules, {"screeninfo": SimpleNamespace(get_monitors=lambda: screens)}),
            mock.patch.object(manager, "SharedCameraRelay", return_value=relay),
            mock.patch.object(manager, "SceneManager", return_value=owner),
            mock.patch.object(manager, "OperatorPanel", return_value=panel) as construct_panel,
            mock.patch.object(manager.cv2, "moveWindow") as move_window,
            mock.patch("builtins.print"),
        ):
            self.assertEqual(manager.main(), 0)
        move_window.assert_called_once_with("Manager Control", 20, 40)
        self.assertEqual(construct_panel.call_args.args[2], "127.0.0.1")
        owner.cleanup.assert_called_once_with()
        relay.close.assert_called_once_with()
        panel.close.assert_called_once_with()

    def test_audience_mode_rejects_remote_bind_before_camera_or_server(self):
        root = Path(__file__).resolve().parents[1]
        with (
            mock.patch.object(sys, "argv", ["manager.py", "--config", str(root / "configs/rebirth_acer_xiaomi.json"),
                                           "--operator-host", "192.168.1.2", "--operator-port", "8766"]),
            mock.patch.object(manager, "CONFIG", dict(manager.CONFIG)),
            mock.patch.object(manager, "SharedCameraRelay") as relay,
            mock.patch.object(manager, "OperatorPanel") as panel,
            mock.patch.object(manager, "configure_audience_dpi") as dpi,
            mock.patch("builtins.print"),
        ):
            self.assertEqual(manager.main(), 2)
        relay.assert_not_called()
        panel.assert_not_called()
        dpi.assert_not_called()

    def test_runner_sets_physical_pixel_mode_before_source_and_restores_environment(self):
        prior = {"KIDZDISCO_DISPLAY_TARGET": "audience", "SDL_WINDOWS_DPI_SCALING": "1"}
        events = []

        def source(*_args, **_kwargs):
            events.append("source")
            self.assertEqual(scene_profile_runner.os.environ["SDL_WINDOWS_DPI_SCALING"], "0")
            self.assertEqual(scene_profile_runner.os.environ["SDL_WINDOWS_DPI_AWARENESS"], "permonitorv2")

        with (
            mock.patch.object(scene_profile_runner.os, "environ", dict(prior)),
            mock.patch.object(sys, "argv", ["fixture_acer.py"]),
            mock.patch.object(stage_display, "configure_audience_dpi", side_effect=lambda: events.append("dpi")),
            mock.patch.object(scene_profile_runner.runpy, "run_path", side_effect=source),
            mock.patch.object(scene_profile_runner.signal, "signal"),
            mock.patch("builtins.print"),
        ):
            scene_profile_runner.run_scene("finger_colorfull_dots_2.py", profile="acer")
            self.assertEqual(scene_profile_runner.os.environ, prior)
        self.assertEqual(events, ["dpi", "source"])

    @unittest.skipUnless(sys.platform == "win32", "Windows DPI API")
    def test_dpi_allows_existing_per_monitor_mode_but_rejects_virtualized_pixels(self):
        import ctypes
        for changed, error, awareness, accepted in [(1, 0, 2, True), (0, 5, 2, True),
                                                    (0, 5, 1, False), (0, 87, 2, False), (1, 0, 1, False)]:
            user32 = mock.Mock()
            user32.SetProcessDpiAwarenessContext.return_value = changed
            user32.GetAwarenessFromDpiAwarenessContext.return_value = awareness
            with self.subTest(changed=changed, error=error, awareness=awareness), mock.patch.object(
                ctypes, "WinDLL", return_value=user32
            ), mock.patch.object(ctypes, "get_last_error", return_value=error):
                if accepted:
                    self.assertTrue(stage_display.configure_audience_dpi()["physical_pixels"])
                else:
                    with self.assertRaises(stage_display.DisplayConfigurationError):
                        stage_display.configure_audience_dpi()


if __name__ == "__main__":
    unittest.main()
