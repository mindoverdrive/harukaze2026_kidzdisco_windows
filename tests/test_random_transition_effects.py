"""Random effect selection and all 48 logo/effect compositions, offline only.

Real graphics checks use in-memory CPU surfaces. No display or camera is opened.
Camera ownership and basic preview controls are covered by test_logo_preview.
"""

from collections import Counter
from pathlib import Path
import random
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

from transition_branding import AlternatingCurtainLogo
from transition_particles import ParticleCurtain
from scripts import preview_transition_logos as preview

try:
    import numpy as np
    import pygame
    REAL_GRAPHICS = (
        isinstance(np, ModuleType) and isinstance(pygame, ModuleType)
        and isinstance(getattr(np, "__version__", None), str)
        and isinstance(getattr(pygame, "__file__", None), str)
        and not isinstance(getattr(pygame, "Surface", None), mock.Mock)
    )
except ImportError:
    np = pygame = None
    REAL_GRAPHICS = False


class EffectCatalogTests(unittest.TestCase):
    def test_effect_catalog_contains_each_motion_layout_pair_once(self):
        expected = tuple((motion, layout) for motion in ("fall", "rise", "split", "scatter")
                         for layout in range(4))
        self.assertEqual(ParticleCurtain.EFFECTS, expected)
        self.assertEqual(len(set(ParticleCurtain.EFFECTS)), 16)

    def test_color_schedule_and_brand_weights_are_unchanged(self):
        patterns = [ParticleCurtain.color_pattern_for_cycle(cycle) for cycle in range(1, 81)]
        self.assertEqual(Counter(palette for palette, _randomized in patterns),
                         {palette: 16 for palette in range(5)})
        self.assertEqual([randomized for _palette, randomized in patterns],
                         [True] * 60 + [False] * 20)
        self.assertEqual(ParticleCurtain.color_pattern_for_cycle(81), (0, True))
        weights = dict(zip(AlternatingCurtainLogo.BRANDS, AlternatingCurtainLogo.WEIGHTS))
        total = sum(weights.values())
        self.assertEqual({brand: value / total for brand, value in weights.items()},
                         {"asobi_tune": .5, "colony": .25, "tokyo_island": .25})


@unittest.skipUnless(REAL_GRAPHICS, "Real pygame/numpy required for offscreen effects")
class RandomEffectSelectionTests(unittest.TestCase):
    SIZE = (320, 180)

    def make_particles(self, rng=None):
        result = ParticleCurtain(self.SIZE, rng=rng)
        self.assertTrue(result.available, result.warning)
        return result

    @staticmethod
    def state(name="covering", cycle=1, level=1.0):
        return SimpleNamespace(state=name, cycle=cycle, level=level,
                               _started=10.0, reveal_duration=1.6)

    def test_zero_level_selects_once_and_clips_redraws_and_noncover_states_do_not_repick(self):
        rng = mock.Mock(choice=mock.Mock(side_effect=[("scatter", 3), ("rise", 1)]))
        particles = self.make_particles(rng)
        screen = pygame.Surface(self.SIZE)
        left = pygame.Rect(0, 0, 160, 180)
        right = pygame.Rect(160, 0, 160, 180)
        rng.choice.assert_not_called()
        for name in ("idle", "failed", "covered", "revealing"):
            particles.draw(screen, left, 10.0, self.state(name, cycle=1))
        rng.choice.assert_not_called()
        # The first COVER frame may be invisible; it still fixes the effect.
        particles.draw(screen, left, 10.0, self.state(level=0.0))
        rng.choice.assert_called_once_with(ParticleCurtain.EFFECTS)
        self.assertEqual(particles.effect, ("scatter", 3))
        self.assertEqual(particles.motion, "scatter")
        self.assertIs(particles._fragments, particles._fragment_layouts[3])
        for rect in (left, right, screen.get_rect(), left):
            particles.draw(screen, rect, 10.2, self.state(level=.5))
        for name in ("covered", "revealing", "failed", "idle"):
            for cycle in (1, 999):
                particles.draw(screen, screen.get_rect(), 10.5, self.state(name, cycle=cycle))
        particles.breakup(screen, 10.8, self.state("revealing"))
        self.assertEqual(rng.choice.call_count, 1)
        self.assertEqual(particles.effect, ("scatter", 3))
        particles.draw(screen, left, 12.0, self.state(cycle=2, level=0.0))
        self.assertEqual(rng.choice.call_count, 2)
        self.assertEqual(particles.effect, ("rise", 1))
        self.assertIs(particles._fragments, particles._fragment_layouts[1])

    def test_repeated_random_results_are_valid_and_are_not_rerolled(self):
        rng = mock.Mock(choice=mock.Mock(return_value=("split", 2)))
        particles = self.make_particles(rng)
        screen = pygame.Surface(self.SIZE)
        for cycle in range(1, 6):
            particles.draw(screen, screen.get_rect(), 10.0, self.state(cycle=cycle, level=0.0))
            particles.draw(screen, screen.get_rect(), 10.1, self.state(cycle=cycle))
            self.assertEqual(particles.effect, ("split", 2))
            self.assertEqual(rng.choice.call_count, cycle)

    def test_default_effect_rng_does_not_consume_global_brand_random_state(self):
        original = random.getstate()
        try:
            random.seed(31062026)
            before = random.getstate()
            particles = self.make_particles()
            screen = pygame.Surface(self.SIZE)
            for cycle in range(1, 9):
                particles.draw(screen, screen.get_rect(), 10.0, self.state(cycle=cycle))
                particles.draw(screen, screen.get_rect(), 10.2, self.state("covered", cycle=cycle))
            self.assertEqual(random.getstate(), before)
            expected_rng = random.Random()
            expected_rng.setstate(before)
            expected = expected_rng.choices(AlternatingCurtainLogo.BRANDS,
                                            weights=AlternatingCurtainLogo.WEIGHTS, k=20)
            actual = random.choices(AlternatingCurtainLogo.BRANDS,
                                    weights=AlternatingCurtainLogo.WEIGHTS, k=20)
            self.assertEqual(actual, expected)
        finally:
            random.setstate(original)

    def test_injected_seed_reproduces_effect_sequence_and_pixels(self):
        first = self.make_particles(random.Random(77192026))
        second = self.make_particles(random.Random(77192026))
        frames = (pygame.Surface(self.SIZE), pygame.Surface(self.SIZE))
        effects = []
        for cycle in range(1, 25):
            for particles, screen in zip((first, second), frames):
                screen.fill((16, 23, 42))
                particles.draw(screen, screen.get_rect(), 10.0, self.state(cycle=cycle))
                particles.breakup(screen, 10.8, self.state("revealing", cycle=cycle, level=.5))
            self.assertEqual(first.effect, second.effect)
            self.assertEqual(pygame.image.tobytes(frames[0], "RGB"),
                             pygame.image.tobytes(frames[1], "RGB"))
            effects.append(first.effect)
        self.assertGreater(len(set(effects)), 1)

    def test_manual_next_back_and_replay_select_only_on_the_new_cover_draw(self):
        expected = [("fall", 0), ("rise", 1), ("split", 2), ("scatter", 3)]
        rng = mock.Mock(choice=mock.Mock(side_effect=expected))
        controller = preview.PreviewController(now=0.0)
        renderer = preview.Renderer(pygame, self.SIZE, controller, effect_rng=rng)
        background = pygame.Surface(self.SIZE)
        background.fill((11, 43, 71))
        rng.choice.assert_not_called()
        renderer.draw(0.0, background)
        self.assertEqual(rng.choice.call_count, 1)
        self.assertEqual(renderer.particles.effect, expected[0])
        renderer.draw(2.0, background)
        for selection, action, action_time, reveal_time, cover_time in (
            (1, "next", 3.0, 5.0, 7.0),
            (2, "back", 8.0, 10.0, 12.0),
            (3, "replay", 13.0, 15.0, 17.0),
        ):
            with self.subTest(action=action):
                self.assertTrue(controller.action(action, action_time))
                for repeated in ("next", "back", "replay"):
                    self.assertFalse(controller.action(repeated, action_time + .01))
                renderer.draw(action_time + .8, background)
                renderer.draw(reveal_time, background)
                # REVEALED schedules the next cover but has not drawn it yet.
                self.assertEqual(rng.choice.call_count, selection)
                renderer.draw(reveal_time + .01, background)
                self.assertEqual(rng.choice.call_count, selection + 1)
                self.assertEqual(renderer.particles.effect, expected[selection])
                renderer.draw(cover_time, background)
                self.assertEqual(rng.choice.call_count, selection + 1)
        self.assertTrue(controller.action("quit", 18.0))
        self.assertFalse(controller.running)
        self.assertEqual(rng.choice.call_count, 4)

    def test_failed_presentation_retry_keeps_the_already_selected_effect(self):
        rng = mock.Mock(choice=mock.Mock(side_effect=[("scatter", 2), ("fall", 1)]))
        controller = preview.PreviewController(now=0.0)
        renderer = preview.Renderer(pygame, self.SIZE, controller, effect_rng=rng)
        background = pygame.Surface(self.SIZE)
        with self.assertRaisesRegex(RuntimeError, "injected flip"):
            renderer.draw(0.0, background,
                          flip=mock.Mock(side_effect=RuntimeError("injected flip")))
        self.assertEqual(rng.choice.call_count, 1)
        self.assertEqual(renderer.particles.effect, ("scatter", 2))
        self.assertEqual(controller.curtain.state, "covering")
        renderer.draw(.01, background, flip=lambda _frame: None)
        self.assertEqual(rng.choice.call_count, 1)
        self.assertEqual(renderer.particles.effect, ("scatter", 2))


@unittest.skipUnless(REAL_GRAPHICS, "Real pygame/numpy required for all 48 logo/effect compositions")
class AllLogoEffectCompositionsTests(unittest.TestCase):
    SIZE = (640, 360)

    def test_all_three_logos_with_every_motion_layout_preserve_artwork_and_clear(self):
        assets = Path(__file__).resolve().parents[1] / "assets"
        source_paths = {
            "asobi_tune": assets / "asobi_tune_logo.png",
            "tokyo_island": assets / "tokyo_island_2026_logo.webp",
            "colony": assets / "transition_logo.png",
        }
        source_files = {brand: path.read_bytes() for brand, path in source_paths.items()}
        sources = {brand: pygame.image.load(str(path)) for brand, path in source_paths.items()}
        source_pixels = {brand: pygame.image.tobytes(surface, "RGBA") for brand, surface in sources.items()}
        background = preview.checker(pygame, self.SIZE)
        background_bytes = pygame.image.tobytes(background, "RGB")
        combinations = set()

        for index, (brand, _label) in enumerate(preview.ORDER):
            rng = mock.Mock()
            controller = preview.PreviewController(now=0.0)
            controller.index = index
            controller.selector.brand = brand
            renderer = preview.Renderer(pygame, self.SIZE, controller, effect_rng=rng)
            cached_art = {"asobi_tune": renderer.logo.asobi,
                          "tokyo_island": renderer.logo.tokyo,
                          "colony": renderer.logo.colony._logo}
            cache_pixels = {key: pygame.image.tobytes(surface, "RGBA")
                            for key, surface in cached_art.items()}
            # Color artwork retains source RGB/per-pixel alpha after the existing
            # size fit. Colony intentionally uses its existing white silhouette.
            for color_brand in ("asobi_tune", "tokyo_island"):
                expected = pygame.transform.smoothscale(sources[color_brand], cached_art[color_brand].get_size())
                self.assertEqual(cache_pixels[color_brand], pygame.image.tobytes(expected, "RGBA"))
            now = 0.0

            for number, effect in enumerate(ParticleCurtain.EFFECTS, start=1):
                with self.subTest(brand=brand, motion=effect[0], layout=effect[1]):
                    rng.choice.return_value = effect
                    renderer.draw(now, background)
                    self.assertEqual(renderer.particles.effect, effect)
                    self.assertEqual(rng.choice.call_count, number)
                    self.assertIs(renderer.particles._fragments,
                                  renderer.particles._fragment_layouts[effect[1]])
                    held_at = now + 1.3
                    held = renderer.draw(held_at, background).copy()
                    self.assertEqual(controller.curtain.state, "covered")
                    self.assertEqual(renderer.logo.brand, brand)
                    self.assertNotEqual(pygame.image.tobytes(held, "RGB"), background_bytes)
                    self.assertTrue(controller.action("replay", held_at))
                    start = renderer.draw(held_at, background)
                    self.assertEqual(pygame.image.tobytes(start, "RGB"),
                                     pygame.image.tobytes(held, "RGB"))
                    renderer.draw(held_at + .8, background)
                    pixels = pygame.surfarray.array3d(renderer.stage)
                    holes = np.all(pixels == ParticleCurtain.TRANSPARENT_COLOR, axis=2)
                    self.assertTrue(np.any(holes), "mid-reveal must expose some background")
                    self.assertTrue(np.any(~holes), "mid-reveal must retain some moving fragments")
                    self.assertEqual(rng.choice.call_count, number)
                    self.assertEqual(renderer.particles.effect, effect)
                    end = renderer.draw(held_at + 1.7, background)
                    self.assertEqual(pygame.image.tobytes(end, "RGB"), background_bytes)
                    self.assertEqual(controller.curtain.state, "covering")
                    self.assertEqual(rng.choice.call_count, number)
                    for key, surface in cached_art.items():
                        self.assertEqual(pygame.image.tobytes(surface, "RGBA"), cache_pixels[key])
                    combinations.add((brand, *effect))
                    now = held_at + 1.7

        self.assertEqual(len(combinations), 48)
        for brand, source in sources.items():
            self.assertEqual(pygame.image.tobytes(source, "RGBA"), source_pixels[brand])
            self.assertEqual(source_paths[brand].read_bytes(), source_files[brand])


if __name__ == "__main__":
    unittest.main()
