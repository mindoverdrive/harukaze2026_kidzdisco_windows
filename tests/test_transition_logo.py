import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

try:
    import numpy as np
    if not isinstance(np, ModuleType):
        raise ImportError("Rendering requires real numpy, not a test stub")
    import pygame
    REAL_GRAPHICS = (isinstance(np, ModuleType) and isinstance(pygame, ModuleType)
                     and isinstance(getattr(np, "__version__", None), str)
                     and isinstance(getattr(pygame, "__file__", None), str)
                     and not isinstance(getattr(pygame, "Surface", None), mock.Mock)
                     and not isinstance(getattr(np, "array", None), mock.Mock))
except ImportError:
    np = pygame = None
    REAL_GRAPHICS = False

from transition_logo import CurtainLogo, TITLE


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(REAL_GRAPHICS, "Real numpy and pygame are required for rendering tests")
class CurtainLogoTests(unittest.TestCase):
    def make_logo(self, size=(640, 360), source=None):
        if source is None:
            source = pygame.Surface((80, 40), pygame.SRCALPHA)
            source.fill((25, 25, 25, 255))
            pygame.draw.rect(source, (255, 255, 255, 255), (20, 8, 40, 24))
        warnings = []
        with mock.patch.object(pygame.image, "load", return_value=source):
            logo = CurtainLogo(size, on_warning=warnings.append)
        self.assertTrue(logo.available, warnings)
        return logo

    def screen(self, size=(640, 360)):
        surface = pygame.Surface(size, pygame.SRCALPHA)
        surface.fill((16, 23, 42, 255))
        return surface

    def render(self, logo, *, state="covered", level=1.0, cycle=1, now=7.0):
        screen = self.screen(logo.size)
        logo.draw(screen, screen.get_rect(), now, SimpleNamespace(state=state, level=level, cycle=cycle))
        return pygame.surfarray.array3d(screen)

    def test_single_load_cached_text_and_no_per_frame_scaling_or_font_render(self):
        source = pygame.Surface((80, 40))
        source.fill((255, 255, 255))
        with mock.patch.object(pygame.image, "load", return_value=source) as load:
            logo = CurtainLogo((640, 360))
            self.assertTrue(logo.available)
            with (mock.patch.object(pygame.transform, "smoothscale", side_effect=AssertionError("frame resize")),
                  mock.patch.object(pygame.font, "SysFont", side_effect=AssertionError("frame font"))):
                for cycle in range(1, 10):
                    self.render(logo, state="covering", cycle=cycle)
        load.assert_called_once()
        self.assertEqual(len(logo._texts), 3)
        self.assertEqual(TITLE, "KidzDisco Colony")
        self.assertLessEqual(abs(logo._logo.get_width() / logo._logo.get_height() - 2.0), 0.02)
        self.assertLessEqual(logo._logo.get_height(), 320)

    def test_all_nine_selections_repeat_after_nine_cycles(self):
        patterns = [CurtainLogo.pattern_for_cycle(cycle) for cycle in range(1, 10)]
        self.assertEqual(set(patterns), {(font, motion) for font in range(3) for motion in range(3)})
        self.assertEqual(patterns, [CurtainLogo.pattern_for_cycle(cycle) for cycle in range(10, 19)])

    def test_pattern_remains_fixed_while_covered_or_revealing(self):
        logo = self.make_logo()
        self.render(logo, state="covering", cycle=2)
        chosen = logo.pattern
        for state in ("covered", "revealing"):
            self.render(logo, state=state, cycle=9, now=23)
            self.assertEqual(logo.pattern, chosen)
        self.render(logo, state="covering", cycle=9)
        self.assertEqual(logo.pattern, CurtainLogo.pattern_for_cycle(9))

    def test_idle_failed_and_zero_fade_do_not_touch_the_surface(self):
        logo = self.make_logo()
        expected = pygame.surfarray.array3d(self.screen())
        for state, level in (("idle", 0), ("idle", 1), ("failed", 1), ("revealing", 0)):
            np.testing.assert_array_equal(self.render(logo, state=state, level=level), expected)

    def test_phase_boundaries_have_identical_pixels_at_same_time_and_level(self):
        logo = self.make_logo()
        covering = self.render(logo, state="covering")
        np.testing.assert_array_equal(covering, self.render(logo, state="covered"))
        np.testing.assert_array_equal(covering, self.render(logo, state="revealing"))
        empty = self.render(logo, state="revealing", level=0)
        almost_empty = self.render(logo, state="revealing", level=0.00001)
        np.testing.assert_array_equal(empty, almost_empty)

    def test_fade_brightness_increases_monotonically_without_alpha_changes(self):
        logo = self.make_logo()
        energies = [int(self.render(logo, state="covering", level=value).sum()) for value in (0, 0.25, 0.5, 0.75, 1)]
        self.assertEqual(energies, sorted(energies))
        self.assertEqual(len(set(energies)), 5)
        screen = self.screen()
        logo.draw(screen, screen.get_rect(), 7, SimpleNamespace(state="covered", level=1, cycle=1))
        self.assertTrue(np.all(pygame.surfarray.array_alpha(screen) == 255))

    def test_existing_clip_and_panel_intersection_are_preserved(self):
        logo = self.make_logo()
        screen = self.screen()
        before = pygame.surfarray.array3d(screen)
        old_clip = pygame.Rect(280, 90, 100, 180)
        panel = pygame.Rect(0, 0, 320, 360)
        screen.set_clip(old_clip)
        logo.draw(screen, panel, 7, SimpleNamespace(state="covered", level=1, cycle=1))
        self.assertEqual(screen.get_clip(), old_clip)
        changed = np.any(pygame.surfarray.array3d(screen) != before, axis=2)
        allowed = np.zeros(changed.shape, dtype=bool)
        intersection = old_clip.clip(panel)
        allowed[intersection.left:intersection.right, intersection.top:intersection.bottom] = True
        self.assertTrue(np.any(changed))
        self.assertFalse(np.any(changed & ~allowed))

    def test_two_nonoverlapping_panels_equal_one_full_draw(self):
        logo = self.make_logo()
        screen = self.screen()
        curtain = SimpleNamespace(state="covering", level=0.9, cycle=1)
        logo.draw(screen, (0, 0, 320, 360), 7, curtain)
        logo.draw(screen, (320, 0, 320, 360), 7, curtain)
        np.testing.assert_array_equal(pygame.surfarray.array3d(screen), self.render(logo, state="covering", level=0.9))

    def test_read_failure_warns_once_and_does_not_affect_cover(self):
        warnings = []
        with mock.patch.object(pygame.image, "load", side_effect=OSError("missing logo")):
            logo = CurtainLogo((640, 360), on_warning=warnings.append)
        screen = self.screen()
        before = pygame.surfarray.array3d(screen)
        for _ in range(3):
            self.assertFalse(logo.draw(screen, screen.get_rect(), 7, SimpleNamespace(state="covered", level=1)))
        self.assertEqual(len(warnings), 1)
        np.testing.assert_array_equal(pygame.surfarray.array3d(screen), before)

    def test_draw_failure_restores_clip_and_disables_only_logo(self):
        logo = self.make_logo()
        warnings = []
        logo.on_warning = warnings.append
        actual = self.screen()
        actual.set_clip((5, 6, 600, 320))
        previous = actual.get_clip()
        screen = SimpleNamespace(get_clip=actual.get_clip, set_clip=actual.set_clip,
                                 get_rect=actual.get_rect, blit=mock.Mock(side_effect=RuntimeError("blit failed")))
        self.assertFalse(logo.draw(screen, (0, 0, 320, 360), 7, SimpleNamespace(state="covered", level=1)))
        self.assertEqual(actual.get_clip(), previous)
        self.assertFalse(logo.available)
        self.assertEqual(len(warnings), 1)

    def test_dark_source_surround_and_transparent_pixels_produce_no_light(self):
        source = pygame.Surface((40, 40), pygame.SRCALPHA)
        source.fill((30, 30, 30, 255))
        source.set_at((20, 20), (255, 255, 255, 0))
        logo = self.make_logo(source=source)
        self.assertEqual(int(pygame.surfarray.array3d(logo._logo).sum()), 0)

    @unittest.skipUnless((ROOT / "assets" / "transition_logo.png").is_file(), "Logo asset is not installed")
    def test_real_asset_all_patterns_over_bright_camera_like_background_have_no_colorkey_holes(self):
        logo = CurtainLogo((960, 540))
        self.assertTrue(logo.available, logo.warning)
        color_key = np.array((255, 0, 128), dtype=np.uint8)
        signatures = set()
        for cycle in range(1, 10):
            screen = self.screen((960, 540))
            # This is the brightest possible camera at alpha 96 over COVER_COLOR.
            screen.fill((106, 110, 122, 255))
            before = pygame.surfarray.array3d(screen)
            logo.draw(screen, screen.get_rect(), 7, SimpleNamespace(state="covering", level=1, cycle=cycle))
            after = pygame.surfarray.array3d(screen)
            self.assertFalse(np.any(np.all(after == color_key, axis=2)))
            self.assertTrue(np.all(after >= before))
            self.assertGreater(int((after.astype(np.int16) - before).max()), 90)
            self.assertTrue(np.all(pygame.surfarray.array_alpha(screen) == 255))
            signatures.add(after.tobytes())
        self.assertEqual(len(signatures), 9)


if __name__ == "__main__":
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    unittest.main()
