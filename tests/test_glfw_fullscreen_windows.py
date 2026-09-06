"""Opt-in real GLFW regression; windows stay hidden and no camera/GPU is opened."""
import os
from pathlib import Path
import json
from types import SimpleNamespace
import unittest
from unittest import mock


@unittest.skipUnless(os.name == "nt" and os.environ.get("KIDZDISCO_TEST_GLFW") == "1",
                     "Set KIDZDISCO_TEST_GLFW=1 in the Acer graphics runtime")
class GlfwFullscreenWindowsTests(unittest.TestCase):
    def test_hidden_resizable_window_covers_audience_after_decoration_change(self):
        import glfw
        import display_utils
        from stage_display import configure_audience_dpi, resolve_audience_displays

        configure_audience_dpi()
        settings = json.loads((Path(__file__).resolve().parents[1] /
                              "configs/rebirth_acer_xiaomi.json").read_text(encoding="utf-8"))
        stage = resolve_audience_displays(settings)["audience"]
        expected = tuple(stage[key] for key in ("x", "y", "width", "height"))
        self.assertTrue(glfw.init())
        try:
            for initial_size in ((640, 480), expected[2:]):
                with self.subTest(initial_size=initial_size):
                    glfw.window_hint(glfw.CLIENT_API, glfw.NO_API)
                    glfw.window_hint(glfw.RESIZABLE, True)
                    glfw.window_hint(glfw.VISIBLE, False)
                    window = glfw.create_window(*initial_size, "Hidden fullscreen regression", None, None)
                    self.assertTrue(window)
                    try:
                        with mock.patch.object(display_utils, "get_second_monitor", return_value=expected):
                            display_utils.setup_rendercanvas_fullscreen(SimpleNamespace(_window=window))
                        glfw.poll_events()
                        self.assertFalse(glfw.get_window_attrib(window, glfw.VISIBLE))
                        actual = (*glfw.get_window_pos(window), *glfw.get_window_size(window))
                        self.assertEqual(actual, expected,
                            "Audience client bounds must still cover the screen after removing decorations")
                    finally:
                        glfw.destroy_window(window)
        finally:
            glfw.terminate()


if __name__ == "__main__":
    unittest.main()
