"""Verify only artwork colors change, with immutable source pixels and alpha."""
from types import ModuleType
import unittest
from unittest import mock

try:
    import numpy as np
    import pygame
    import cv2
    REAL = all(isinstance(module, ModuleType) for module in (np, pygame, cv2)) and isinstance(np.__version__, str)
    if REAL:
        from mandala_colors import ArtworkHueCycle
except (ImportError, AttributeError):
    REAL = False


@unittest.skipUnless(REAL, "Real graphics dependencies required")
class MandalaColorTests(unittest.TestCase):
    def setUp(self):
        self.art = pygame.Surface((80, 50), pygame.SRCALPHA, 32)
        self.art.fill((0, 0, 0, 0))
        for index, color in enumerate(((255, 0, 0), (0, 255, 0), (0, 0, 255))):
            pygame.draw.line(self.art, color, (8 + index * 25, 4), (8 + index * 25, 45), 2)
        self.cycle = ArtworkHueCycle(self.art.get_size())

    def test_old_strokes_change_color_without_changing_source_or_alpha(self):
        original = pygame.surfarray.array3d(self.art)
        alpha = pygame.surfarray.array_alpha(self.art)
        self.cycle.refresh(self.art, 0)
        shown = self.cycle.refresh(self.art, 25)
        self.assertFalse(np.array_equal(original, pygame.surfarray.array3d(shown)))
        np.testing.assert_array_equal(pygame.surfarray.array3d(self.art), original)
        np.testing.assert_array_equal(pygame.surfarray.array_alpha(shown), alpha)
        colors = [tuple(shown.get_at((8 + index * 25, 20))) for index in range(3)]
        self.assertEqual(len(set(colors)), 3)

    def test_full_cycles_restore_exact_original_without_accumulated_damage(self):
        original = pygame.surfarray.array3d(self.art)
        self.cycle.refresh(self.art, 0)
        for seconds in range(1, 361):
            shown = self.cycle.refresh(self.art, seconds)
        np.testing.assert_array_equal(pygame.surfarray.array3d(shown), original)

    def test_cached_interval_keeps_immediately_added_ink(self):
        shown = self.cycle.refresh(self.art, 0)
        color = pygame.Color(255, 100, 0)
        pygame.draw.circle(self.art, color, (40, 25), 3)
        pygame.draw.circle(shown, self.cycle.display_color(color), (40, 25), 3)
        with mock.patch.object(cv2, "cvtColor", side_effect=AssertionError("unneeded refresh")):
            self.assertIs(self.cycle.refresh(self.art, .1), shown)
        self.assertEqual(shown.get_at((40, 25)), color)
        self.cycle.refresh(self.art, 20)
        self.assertEqual(shown.get_at((40, 25)), self.cycle.display_color(color))

    def test_refresh_reuses_surfaces_and_full_frame_buffers(self):
        self.cycle.refresh(self.art, 0)
        buffers = tuple(id(value) for value in (self.cycle._rgb, self.cycle._hsv, self.cycle._output))
        with mock.patch.object(pygame, "Surface", side_effect=AssertionError("allocation")):
            self.cycle.refresh(self.art, 30)
        self.assertEqual(buffers, tuple(id(value) for value in (self.cycle._rgb, self.cycle._hsv, self.cycle._output)))
        self.assertFalse(self.art.get_locked())
        self.assertFalse(self.cycle.surface.get_locked())

    def test_invalid_time_leaves_display_unchanged(self):
        shown = self.cycle.refresh(self.art, 0)
        before = pygame.surfarray.array3d(shown)
        for now in (float("nan"), float("inf")):
            self.cycle.refresh(self.art, now)
        np.testing.assert_array_equal(pygame.surfarray.array3d(shown), before)


if __name__ == "__main__":
    unittest.main()
