from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

try:
    import numpy as np
    if not isinstance(np, ModuleType):
        raise ImportError("Rendering requires real numpy")
    import pygame
    REAL_GRAPHICS = (isinstance(pygame, ModuleType)
                     and isinstance(getattr(pygame, "__file__", None), str)
                     and isinstance(getattr(np, "__version__", None), str)
                     and not isinstance(getattr(pygame, "Surface", None), mock.Mock))
except ImportError:
    np = pygame = None
    REAL_GRAPHICS = False

from transition_particles import ParticleCurtain


@unittest.skipUnless(REAL_GRAPHICS, "Real numpy and pygame are required for rendering tests")
class ParticleCurtainTests(unittest.TestCase):
    SIZE = (640, 360)
    BASE = (16, 23, 42, 255)

    def setUp(self):
        self.particles = ParticleCurtain(self.SIZE)
        self.assertTrue(self.particles.available, self.particles.warning)

    def screen(self):
        surface = pygame.Surface(self.SIZE, pygame.SRCALPHA)
        surface.fill(self.BASE)
        return surface

    def curtain(self, state="covered", level=1.0, **kwargs):
        return SimpleNamespace(state=state, level=level, **kwargs)

    def render(self, curtain=None, now=7.0, particles=None):
        screen = self.screen()
        (particles or self.particles).draw(screen, screen.get_rect(), now, curtain or self.curtain())
        return pygame.surfarray.array3d(screen)

    def test_dense_fill_reaches_every_edge_and_preserves_opaque_alpha(self):
        screen = self.screen()
        self.particles.draw(screen, screen.get_rect(), 7, self.curtain())
        pixels = pygame.surfarray.array3d(screen)
        changed = np.any(pixels != np.array(self.BASE[:3]), axis=2)
        self.assertGreater(float(changed.mean()), 0.97)
        for edge in (changed[0, :], changed[-1, :], changed[:, 0], changed[:, -1]):
            self.assertGreater(float(edge.mean()), 0.95)
        self.assertTrue(np.all(pygame.surfarray.array_alpha(screen) == 255))
        self.assertFalse(np.any(np.all(pixels == (255, 0, 128), axis=2)))

    def test_particle_and_cache_counts_are_bounded_and_never_rebuilt(self):
        chips = self.particles._chips
        sprites = self.particles._sprites
        snapshot = self.particles._snapshot
        self.assertTrue(500 <= len(chips) <= 1000)
        self.assertEqual(len(sprites), 18)
        self.assertTrue(400 <= len(self.particles._fragments) <= 650)
        screen = self.screen()
        with (mock.patch.object(pygame, "Surface", side_effect=AssertionError("frame allocation")),
              mock.patch.object(pygame.transform, "smoothscale", side_effect=AssertionError("frame scaling"))):
            for cycle in range(1, 101):
                self.assertTrue(self.particles.draw(screen, screen.get_rect(), 7 + cycle * 0.1,
                                                    self.curtain(cycle=cycle)))
                self.assertTrue(self.particles.breakup(screen, 7.7,
                                                      self.curtain("revealing", 0.5, _started=7,
                                                                   reveal_duration=1.6)))
        self.assertIs(self.particles._chips, chips)
        self.assertIs(self.particles._sprites, sprites)
        self.assertIs(self.particles._snapshot, snapshot)

    def test_seed_reproduces_layout_and_release_delays(self):
        other = ParticleCurtain(self.SIZE)
        self.assertEqual(other._chips, self.particles._chips)
        self.assertEqual(other._fragments, self.particles._fragments)
        np.testing.assert_array_equal(self.render(particles=other), self.render())
        delays = [fragment.delay for fragment in self.particles._fragments]
        self.assertGreater(max(delays) - min(delays), 0.1)

    def test_covered_micro_motion_continues_without_rebuilding(self):
        self.assertFalse(np.array_equal(self.render(now=7), self.render(now=8)))

    def test_phase_boundaries_do_not_jump(self):
        covered = self.render()
        np.testing.assert_array_equal(covered, self.render(self.curtain("covering", 1)))
        np.testing.assert_array_equal(covered, self.render(self.curtain("revealing", 1,
                                                                       _started=7, reveal_duration=1.6)))

    def test_reveal_falls_downward_and_all_fragments_exit_before_end(self):
        upper_energy = []
        for fraction in (0, 0.4, 0.7, 0.99):
            curtain = self.curtain("revealing", 1 - fraction, _started=7, reveal_duration=1.6)
            screen = self.screen()
            self.particles.draw(screen, screen.get_rect(), 7 + fraction * 1.6, curtain)
            self.particles.breakup(screen, 7 + fraction * 1.6, curtain)
            pixels = pygame.surfarray.array3d(screen)
            visible = np.any(pixels != np.array(self.particles.TRANSPARENT_COLOR), axis=2)
            upper_energy.append(int(visible[:, :180].sum()))
        self.assertGreater(upper_energy[0], upper_energy[1])
        self.assertGreater(upper_energy[1], upper_energy[2])
        self.assertEqual(upper_energy[-1], 0)
        for fragment in self.particles._fragments:
            _, y = self.particles._fragment_position(fragment, 0.99)
            self.assertGreater(y, self.SIZE[1])

    def test_breakup_start_is_pixel_identical_and_inactive_states_are_untouched(self):
        for state in ("covered", "covering", "idle", "failed", "revealing"):
            screen = self.screen()
            pygame.draw.circle(screen, (230, 150, 210), (320, 180), 90)
            before = pygame.surfarray.array3d(screen)
            self.particles.breakup(screen, 7, self.curtain(state, 1, _started=7, reveal_duration=1.6))
            np.testing.assert_array_equal(pygame.surfarray.array3d(screen), before)

    def test_breakup_moves_current_composition_and_opens_holes(self):
        screen = self.screen()
        pygame.draw.rect(screen, (190, 235, 173), (0, 0, 640, 90))
        self.particles.breakup(screen, 7.8, self.curtain("revealing", 0.5, _started=7, reveal_duration=1.6))
        pixels = pygame.surfarray.array3d(screen)
        holes = np.all(pixels == self.particles.TRANSPARENT_COLOR, axis=2)
        source_pixels = np.all(pixels == (190, 235, 173), axis=2)
        self.assertGreater(int(holes.sum()), 10000)
        self.assertGreater(int(source_pixels[:, 90:].sum()), 1000)
        self.assertTrue(np.all(pygame.surfarray.array_alpha(screen) == 255))

    def test_breakup_end_is_transparent_with_no_residue(self):
        for level, now in ((0, 7), (0, 8.6), (0.1, 9)):
            screen = self.screen()
            self.particles.breakup(screen, now, self.curtain("revealing", level, _started=7, reveal_duration=1.6))
            self.assertTrue(np.all(pygame.surfarray.array3d(screen) == self.particles.TRANSPARENT_COLOR))

    def test_breakup_respects_clip_at_middle_and_end(self):
        for level, now in ((0.5, 7.8), (0, 8.6)):
            screen = self.screen()
            clip = pygame.Rect(90, 50, 400, 240)
            screen.set_clip(clip)
            self.particles.breakup(screen, now, self.curtain("revealing", level, _started=7, reveal_duration=1.6))
            self.assertEqual(screen.get_clip(), clip)
            pixels = pygame.surfarray.array3d(screen)
            changed = np.any(pixels != np.array(self.BASE[:3]), axis=2)
            allowed = np.zeros(self.SIZE, dtype=bool)
            allowed[clip.left:clip.right, clip.top:clip.bottom] = True
            self.assertFalse(np.any(changed & ~allowed))
            self.assertTrue(np.any(changed))

    def test_breakup_blit_failure_restores_composition_for_fade_fallback(self):
        class FailOnceSurface(pygame.Surface):
            failed = False

            def blit(self, *args, **kwargs):
                if not self.failed:
                    self.failed = True
                    raise RuntimeError("fragment blit failed")
                return super().blit(*args, **kwargs)

        screen = FailOnceSurface(self.SIZE, pygame.SRCALPHA)
        screen.fill(self.BASE)
        clip = pygame.Rect(30, 40, 580, 280)
        screen.set_clip(clip)
        before = pygame.surfarray.array3d(screen)
        with mock.patch("builtins.print"):
            self.assertFalse(self.particles.breakup(screen, 7.8,
                                                   self.curtain("revealing", 0.5, _started=7,
                                                                reveal_duration=1.6)))
        self.assertEqual(screen.get_clip(), clip)
        self.assertFalse(self.particles.available)
        np.testing.assert_array_equal(pygame.surfarray.array3d(screen), before)

    def test_timer_drives_reveal_independently_of_smoothed_level(self):
        curtain = self.curtain("revealing", 0.784, _started=10, reveal_duration=1.6)
        self.assertAlmostEqual(self.particles._reveal_progress(curtain, 10.4), 0.25)
        self.assertEqual(self.particles._reveal_progress(curtain, 9), 0)
        self.assertEqual(self.particles._reveal_progress(curtain, 15), 1)

    def test_idle_failed_and_finished_reveal_do_not_paint(self):
        base = pygame.surfarray.array3d(self.screen())
        for state, level in (("idle", 1), ("failed", 1), ("revealing", 0), ("covering", 0)):
            np.testing.assert_array_equal(self.render(self.curtain(state, level)), base)

    def test_panel_and_existing_clip_are_intersected_and_restored(self):
        screen = self.screen()
        original = pygame.Rect(90, 50, 400, 240)
        panel = pygame.Rect(0, 0, 320, 360)
        screen.set_clip(original)
        self.particles.draw(screen, panel, 7, self.curtain())
        self.assertEqual(screen.get_clip(), original)
        pixels = pygame.surfarray.array3d(screen)
        changed = np.any(pixels != np.array(self.BASE[:3]), axis=2)
        expected = np.zeros(self.SIZE, dtype=bool)
        intersection = original.clip(panel)
        expected[intersection.left:intersection.right, intersection.top:intersection.bottom] = True
        self.assertTrue(np.any(changed))
        self.assertFalse(np.any(changed & ~expected))

    def test_split_panels_match_one_full_render(self):
        screen = self.screen()
        self.particles.draw(screen, (0, 0, 320, 360), 7, self.curtain())
        self.particles.draw(screen, (320, 0, 320, 360), 7, self.curtain())
        np.testing.assert_array_equal(pygame.surfarray.array3d(screen), self.render())

    def test_empty_clip_does_not_change_surface_or_existing_clip(self):
        screen = self.screen()
        original = screen.get_clip()
        self.assertFalse(self.particles.draw(screen, (800, 800, 10, 10), 7, self.curtain()))
        self.assertEqual(screen.get_clip(), original)
        np.testing.assert_array_equal(pygame.surfarray.array3d(screen), pygame.surfarray.array3d(self.screen()))

    def test_draw_failure_restores_clip_and_disables_decoration(self):
        actual = self.screen()
        original = actual.get_clip()
        screen = SimpleNamespace(get_clip=actual.get_clip, set_clip=actual.set_clip,
                                 get_rect=actual.get_rect, blit=mock.Mock(side_effect=RuntimeError("failed blit")))
        with mock.patch("builtins.print"):
            self.assertFalse(self.particles.draw(screen, (0, 0, 320, 360), 7, self.curtain()))
        self.assertEqual(actual.get_clip(), original)
        self.assertFalse(self.particles.available)
        self.assertIn("failed blit", self.particles.warning)


if __name__ == "__main__":
    unittest.main()
