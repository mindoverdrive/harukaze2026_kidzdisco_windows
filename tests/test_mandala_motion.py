import unittest
from types import ModuleType
from unittest import mock

try:
    import numpy as np
    import pygame
    import cv2
    REAL = (all(isinstance(module, ModuleType) for module in (np, pygame, cv2))
            and isinstance(np.__version__, str) and isinstance(pygame.version.ver, str)
            and not isinstance(cv2.warpAffine, mock.Mock))
    if REAL:
        from mandala_motion import ArtworkOutwardDrift
except (ImportError, AttributeError):
    REAL = False


@unittest.skipUnless(REAL, "Real graphics arrays required")
class MandalaMotionTests(unittest.TestCase):
    def test_old_ink_moves_outwards_and_both_color_surfaces_keep_alpha_in_sync(self):
        size = (256, 144)
        original = pygame.Surface(size, pygame.SRCALPHA)
        colored = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.circle(original, (240, 60, 30, 255), (200, 72), 5)
        pygame.draw.circle(colored, (30, 240, 60, 255), (200, 72), 5)
        drift = ArtworkOutwardDrift(size)
        buffer_id = id(drift._target)
        for index in range(81):
            drift.advance(original, colored, index / 8)
        alpha = pygame.surfarray.array_alpha(original)
        x = np.arange(size[0])[:, None]
        centroid = float((alpha * x).sum() / alpha.sum())
        self.assertGreater(centroid, 206)
        self.assertLess(centroid, 214)
        np.testing.assert_array_equal(alpha, pygame.surfarray.array_alpha(colored))
        self.assertLess(int(alpha.max()), 255)
        self.assertEqual(buffer_id, id(drift._target))
        self.assertFalse(original.get_locked())
        self.assertFalse(colored.get_locked())
        # Fresh strokes retain full strength at the actual input location.
        pygame.draw.circle(original, (255, 0, 0, 255), (100, 72), 2)
        self.assertEqual(original.get_at((100, 72)).a, 255)

    def test_old_center_ink_eventually_disappears_without_whole_canvas_reset(self):
        original = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.circle(original, (120, 200, 80, 255), (32, 32), 5)
        colored = original.copy()
        drift = ArtworkOutwardDrift((64, 64))
        for index in range(1041):
            drift.advance(original, colored, index / 8)
        self.assertEqual(int(pygame.surfarray.array_alpha(original).max()), 0)

    def test_short_intervals_and_bad_time_do_not_mutate_or_jump(self):
        original = pygame.Surface((64, 64), pygame.SRCALPHA)
        original.fill((40, 80, 120, 255))
        colored = original.copy()
        drift = ArtworkOutwardDrift((64, 64))
        before = pygame.image.tobytes(original, "RGBA")
        for now in (0, .01, float("nan"), -.1):
            self.assertFalse(drift.advance(original, colored, now))
        self.assertEqual(before, pygame.image.tobytes(original, "RGBA"))
        drift.advance(original, colored, 1000)
        self.assertGreaterEqual(original.get_at((32, 32)).a, 254)

    def test_hue_refresh_does_not_restore_old_geometry_or_alpha(self):
        from mandala_colors import ArtworkHueCycle
        size = (128, 72)
        original = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.circle(original, (220, 70, 40, 255), (100, 36), 4)
        colors = ArtworkHueCycle(size)
        drift = ArtworkOutwardDrift(size)
        for index in range(321):
            now = index / 8
            drift.advance(original, colors.surface, now)
            shown = colors.refresh(original, now)
            np.testing.assert_array_equal(pygame.surfarray.array_alpha(original),
                                          pygame.surfarray.array_alpha(shown))
        self.assertLess(int(pygame.surfarray.array_alpha(shown).max()), 200)
