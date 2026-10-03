import hashlib
from pathlib import Path
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
    def make_logo(self):
        with mock.patch("transition_branding.CurtainLogo") as colony:
            result = AlternatingCurtainLogo((640, 360))
        return result

    def test_alternates_whole_composition_and_latches_until_next_cover(self):
        logo = self.make_logo()
        screen = pygame.Surface((640, 360))
        for cycle in range(1, 7):
            curtain = SimpleNamespace(state="covering", level=1, cycle=cycle)
            logo.draw(screen, screen.get_rect(), 0, curtain)
            expected = "colony" if cycle % 2 else "tokyo_island"
            self.assertEqual(logo.brand, expected)
            curtain.state = "revealing"
            curtain.cycle = cycle + 1
            logo.draw(screen, screen.get_rect(), 0, curtain)
            self.assertEqual(logo.brand, expected)
        # Tokyo Island draw does not add Colony text underneath.
        self.assertEqual(logo.colony.draw.call_count, 6)

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

    def test_white_color_transparency_and_fade_survive_on_dark_background(self):
        source = pygame.Surface((4, 4), pygame.SRCALPHA)
        source.fill((255, 255, 255, 0))
        source.set_at((1, 1), (255, 255, 255, 255))  # White year/details.
        source.set_at((2, 1), (250, 80, 30, 255))  # Saturated original color.
        source.set_at((1, 2), (30, 160, 240, 128))  # Antialiased alpha.
        with mock.patch("transition_branding.CurtainLogo"), \
                mock.patch("pygame.image.load", return_value=source):
            logo = AlternatingCurtainLogo((8, 8))
        self.assertEqual(pygame.image.tobytes(logo.tokyo, "RGBA"),
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
                                         on_warning=warnings.append)
        self.assertEqual(len(warnings), 1)
        screen = pygame.Surface((640, 360))
        logo.draw(screen, screen.get_rect(), 0, SimpleNamespace(state="covered", level=1, cycle=2))
        logo.colony.draw.assert_called_once()
