import unittest
from unittest import mock

from transition_overlay import Curtain, COVER_COLOR, present_frame, OverlayOpacity


class FadeTests(unittest.TestCase):
    def setUp(self):
        self.screen, self.pg, self.opacity = mock.Mock(), mock.Mock(), mock.Mock()
        self.screen.get_size.return_value = (1920, 1080)
        self.curtain = Curtain(cover_duration=1.2, reveal_duration=1.6)

    def frame(self, now):
        return present_frame(self.screen, self.pg, self.curtain, now, opacity=self.opacity)

    def test_full_surface_fades_and_full_opacity_sync_precedes_cover_ack(self):
        self.curtain.command("COVER", 1, 0)
        self.assertIsNone(self.frame(.6))
        self.opacity.assert_called_with(128)
        self.screen.fill.assert_called_with(COVER_COLOR)
        self.opacity.sync.assert_not_called()
        self.opacity.sync.side_effect = RuntimeError("compositor failed")
        with self.assertRaises(RuntimeError):
            self.frame(1.2)
        self.opacity.assert_called_with(255)
        self.assertEqual(self.curtain.state, "covering")
        self.opacity.sync.side_effect = None
        self.assertEqual(self.frame(1.2), "COVERED")
        self.assertIsNone(self.frame(100))
        self.opacity.assert_called_with(255)

    def test_reveal_uses_longer_fade_and_idle_cannot_flash_previous_cover(self):
        self.curtain.command("COVER", 1, 0)
        self.frame(1.2)
        self.curtain.command("REVEAL", 1, 2)
        self.assertIsNone(self.frame(2.8))
        self.opacity.assert_called_with(128)
        self.assertEqual(self.frame(3.6), "REVEALED")
        self.opacity.assert_called_with(0)
        trace = []
        self.pg.display.flip.side_effect = lambda: trace.append("flip")
        self.opacity.side_effect = lambda alpha: trace.append(alpha)
        self.frame(3.7)
        self.assertEqual(trace, ["flip", 255])

    def test_emergency_cover_overrides_partial_alpha(self):
        self.curtain.fail()
        self.frame(0)
        self.opacity.assert_called_with(255)
        self.screen.fill.assert_called_with(COVER_COLOR)

    def test_breakup_only_runs_after_cover_release_and_before_presentation(self):
        breakup = mock.Mock()
        self.curtain.command("COVER", 1, 0)
        present_frame(self.screen, self.pg, self.curtain, 1.2,
                      opacity=self.opacity, draw_breakup=breakup)
        breakup.assert_not_called()
        self.curtain.command("REVEAL", 1, 2)
        trace = []
        breakup.side_effect = lambda: trace.append("breakup")
        self.pg.display.flip.side_effect = lambda: trace.append("flip")
        present_frame(self.screen, self.pg, self.curtain, 2.8,
                      opacity=self.opacity, draw_breakup=breakup)
        self.opacity.assert_called_with(255)
        self.assertEqual(trace, ["breakup", "flip"])
        breakup.side_effect = RuntimeError("breakup failed")
        with self.assertRaises(RuntimeError):
            present_frame(self.screen, self.pg, self.curtain, 3.6,
                          opacity=self.opacity, draw_breakup=breakup)
        self.assertEqual(self.curtain.state, "revealing")

    def test_win32_opacity_uses_alpha_and_colorkey_and_checks_compositor(self):
        import ctypes
        pg, win = mock.Mock(), mock.Mock()
        pg.display.get_wm_info.return_value = {"window": 123}
        win.SetLayeredWindowAttributes.return_value = True
        win.DwmFlush.return_value = 0
        with mock.patch.object(ctypes, "WinDLL", return_value=win, create=True):
            opacity = OverlayOpacity(pg)
            opacity(128)
            self.assertEqual(win.SetLayeredWindowAttributes.call_args.args[-2:], (128, 3))
            opacity(128)
            win.SetLayeredWindowAttributes.assert_called_once()
            opacity.sync()
            win.DwmFlush.return_value = -1
            with self.assertRaises(OSError):
                opacity.sync()

    def test_unavailable_breakup_falls_back_to_fade_after_safe_release(self):
        self.curtain.command("COVER", 1, 0)
        self.frame(1.2)
        self.curtain.command("REVEAL", 1, 2)
        present_frame(self.screen, self.pg, self.curtain, 2.8,
                      opacity=self.opacity, draw_breakup=lambda: False)
        self.opacity.assert_called_with(128)
