import hashlib
from collections import Counter
from pathlib import Path
import random
from types import SimpleNamespace
import unittest
from unittest import mock

try:
    import pygame
    REAL = isinstance(pygame.version.ver, str)
except ImportError:
    REAL = False

from transition_branding import AlternatingCurtainLogo, white_paper_to_alpha


@unittest.skipUnless(REAL, "Real pygame required")
class TransitionBrandingTests(unittest.TestCase):
    def make_logo(self, rng=None):
        with mock.patch("transition_branding.CurtainLogo") as colony:
            result = AlternatingCurtainLogo((640, 360),
                                           rng=rng if rng is not None else mock.Mock(
                                               choices=mock.Mock(return_value=["tokyo_island"])))
        return result

    def test_weighted_choice_is_once_per_cover_and_latches_all_three_logos(self):
        brands = ["asobi_tune", "asobi_tune", "colony", "tokyo_island", "colony", "asobi_tune"]
        rng = mock.Mock(choices=mock.Mock(side_effect=[[brand] for brand in brands]))
        logo = self.make_logo(rng)
        screen = pygame.Surface((640, 360))
        for cycle, expected in enumerate(brands, 1):
            curtain = SimpleNamespace(state="covering", level=1, cycle=cycle)
            logo.draw(screen, screen.get_rect(), 0, curtain)
            self.assertEqual(logo.brand, expected)
            # The second panel clip must use the same choice, including repeats.
            logo.draw(screen, screen.get_rect(), 0, curtain)
            curtain.state = "covered"
            logo.draw(screen, screen.get_rect(), 0, curtain)
            curtain.state = "revealing"
            curtain.cycle = cycle + 1
            logo.draw(screen, screen.get_rect(), 0, curtain)
            self.assertEqual(logo.brand, expected)
        self.assertEqual(rng.choices.call_count, len(brands))
        rng.choices.assert_called_with(("colony", "tokyo_island", "asobi_tune"),
                                       weights=(1, 1, 2), k=1)
        # Neither color logo adds Colony text; Colony appearances advance variants.
        self.assertEqual(logo.colony.draw.call_count, 8)
        self.assertEqual(logo._colony_cycle, 2)

    def test_seeded_repeated_covers_follow_two_to_one_to_one_probabilities(self):
        logo = self.make_logo(random.Random(20261003))
        screen = pygame.Surface((1, 1))
        empty = pygame.Rect(0, 0, 0, 0)
        counts = Counter()
        for cycle in range(1, 2001):
            logo.draw(screen, empty, 0, SimpleNamespace(state="covering", level=1, cycle=cycle))
            counts[logo.brand] += 1
        for brand, probability in (("asobi_tune", .5), ("colony", .25), ("tokyo_island", .25)):
            self.assertAlmostEqual(counts[brand] / 2000, probability, delta=.04)

    def test_original_rebirth_is_preserved_for_rollback(self):
        path = Path(__file__).resolve().parents[1] / "assets" / "rebirth_logo_source.jpg"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "3ab9a7e05f1c3a845a8131a6eb635d909304d138b25d4e351fbba5187543d6fc")
        original = pygame.image.load(str(path))
        source_bytes = pygame.image.tobytes(original, "RGB")
        cutout = white_paper_to_alpha(original)
        self.assertEqual(pygame.image.tobytes(original, "RGB"), source_bytes)
        self.assertEqual(cutout.get_at((0, 0)).a, 0)
        self.assertEqual(cutout.get_at((400, 315)).a, 0)  # Interior white hole.
        self.assertGreater(cutout.get_at((600, 200)).a, 240)  # Dark outer arc.

    def test_tokyo_official_asset_and_render_preserve_rgb_alpha(self):
        logo = self.make_logo()
        path = Path(__file__).resolve().parents[1] / "assets" / "tokyo_island_2026_logo.webp"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "2aa13aec05387fa2b3280846da722f4201c87a996b26af1ea98e120492839068")
        original = pygame.image.load(str(path))
        self.assertEqual(original.get_size(), (1560, 1147))
        self.assertEqual(original.get_at((0, 0)).a, 0)
        expected = pygame.transform.smoothscale(original, logo.tokyo.get_size())
        self.assertEqual(pygame.image.tobytes(logo.tokyo, "RGBA"),
                         pygame.image.tobytes(expected, "RGBA"))
        before = pygame.image.tobytes(logo.tokyo, "RGBA")
        screen = pygame.Surface((640, 360), pygame.SRCALPHA)
        screen.fill((20, 30, 40, 255))
        clip = pygame.Rect(10, 10, 600, 320)
        screen.set_clip(clip)
        self.assertTrue(logo.draw(screen, screen.get_rect(), 10,
                        SimpleNamespace(state="covering", level=.6, cycle=2)))
        self.assertEqual(screen.get_clip(), clip)
        self.assertEqual(pygame.image.tobytes(logo.tokyo, "RGBA"), before)
        self.assertEqual(screen.get_at((320, 180)).a, 255)

    def test_asobi_two_line_source_and_render_preserve_rgb_alpha(self):
        logo = self.make_logo(mock.Mock(choices=mock.Mock(return_value=["asobi_tune"])))
        path = Path(__file__).resolve().parents[1] / "assets" / "asobi_tune_logo.png"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "86101a2b219fd10b9ba5aae64375d6a519ec589ca13dfb28644c13bf9869956e")
        source = pygame.image.load(str(path))
        self.assertEqual(source.get_size(), (1448, 1086))
        self.assertEqual(source.get_at((0, 0)).a, 0)
        expected = pygame.transform.smoothscale(source, logo.asobi.get_size())
        self.assertEqual(pygame.image.tobytes(logo.asobi, "RGBA"),
                         pygame.image.tobytes(expected, "RGBA"))
        screen = pygame.Surface((640, 360))
        screen.fill((0, 0, 0))
        logo.draw(screen, screen.get_rect(), 0, SimpleNamespace(state="covered", level=1, cycle=1))
        reference = pygame.Surface(screen.get_size())
        reference.fill((0, 0, 0))
        reference.blit(expected, (round((640 - expected.get_width()) / 2),
                                  round((360 - expected.get_height()) / 2)))
        self.assertEqual(pygame.image.tobytes(screen, "RGB"), pygame.image.tobytes(reference, "RGB"))
        logo.colony.draw.assert_not_called()

    def test_white_color_transparency_and_fade_survive_on_dark_background(self):
        source = pygame.Surface((4, 4), pygame.SRCALPHA)
        source.fill((255, 255, 255, 0))
        source.set_at((1, 1), (255, 255, 255, 255))  # White year/details.
        source.set_at((2, 1), (250, 80, 30, 255))  # Saturated original color.
        source.set_at((1, 2), (30, 160, 240, 128))  # Antialiased alpha.
        for brand in ("tokyo_island", "asobi_tune"):
            with self.subTest(brand=brand):
                with mock.patch("transition_branding.CurtainLogo"), \
                        mock.patch("pygame.image.load", return_value=source):
                    logo = AlternatingCurtainLogo((8, 8), rng=mock.Mock(
                        choices=mock.Mock(return_value=[brand])))
                artwork = logo.tokyo if brand == "tokyo_island" else logo.asobi
                self.assertEqual(pygame.image.tobytes(artwork, "RGBA"),
                                 pygame.image.tobytes(source, "RGBA"))
                screen = pygame.Surface((8, 8))
                for level in (1.0, .5, 0.0):
                    screen.fill((0, 0, 0))
                    logo.draw(screen, screen.get_rect(), 0,
                              SimpleNamespace(state="covered", level=level, cycle=2))
                    if level == 1.0:
                        self.assertEqual(tuple(screen.get_at((3, 3)))[:3], (255, 255, 255))
                        self.assertEqual(tuple(screen.get_at((4, 3)))[:3], (250, 80, 30))
                        self.assertEqual(tuple(screen.get_at((2, 2)))[:3], (0, 0, 0))
                    elif level == .5:
                        self.assertTrue(126 <= screen.get_at((3, 3)).r <= 129)
                    else:
                        self.assertEqual(tuple(screen.get_at((3, 3)))[:3], (0, 0, 0))

    def test_colony_source_is_unchanged(self):
        path = Path(__file__).resolve().parents[1] / "assets" / "transition_logo.png"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "d0e7ec4901e4a65ec834af232bcd9233f4792f4053d26c1b5026faaacb1192a6")

    def test_paper_and_holes_reveal_background_but_dark_ink_remains(self):
        source = pygame.Surface((40, 40))
        source.fill((255, 255, 255))
        pygame.draw.circle(source, (30, 24, 22), (20, 20), 15)
        pygame.draw.circle(source, (255, 255, 255), (20, 20), 6)
        cutout = white_paper_to_alpha(source)
        background = pygame.Surface((40, 40))
        background.fill((70, 130, 180))
        background.blit(cutout, (0, 0))
        self.assertEqual(tuple(background.get_at((0, 0)))[:3], (70, 130, 180))
        self.assertEqual(tuple(background.get_at((20, 20)))[:3], (70, 130, 180))
        self.assertEqual(tuple(background.get_at((20, 10)))[:3], (30, 24, 22))

    def test_missing_tokyo_falls_back_without_breaking_cover(self):
        with mock.patch("transition_branding.CurtainLogo"):
            warnings = []
            logo = AlternatingCurtainLogo((640, 360), tokyo_path="missing-logo-file.webp",
                                         on_warning=warnings.append, rng=mock.Mock(
                                             choices=mock.Mock(return_value=["tokyo_island"])))
        self.assertEqual(len(warnings), 1)
        screen = pygame.Surface((640, 360))
        logo.draw(screen, screen.get_rect(), 0, SimpleNamespace(state="covered", level=1, cycle=2))
        logo.colony.draw.assert_called_once()

    def test_missing_asobi_falls_back_without_redrawing_or_rechoosing(self):
        rng = mock.Mock(choices=mock.Mock(return_value=["asobi_tune"]))
        with mock.patch("transition_branding.CurtainLogo"):
            warnings = []
            logo = AlternatingCurtainLogo((640, 360), asobi_path="missing-asobi.png",
                                         on_warning=warnings.append, rng=rng)
        self.assertEqual(len(warnings), 1)
        screen = pygame.Surface((640, 360))
        for state in ("covering", "covered", "revealing"):
            logo.draw(screen, screen.get_rect(), 0, SimpleNamespace(state=state, level=1, cycle=1))
        self.assertEqual(rng.choices.call_count, 1)
        self.assertEqual(logo.colony.draw.call_count, 3)
