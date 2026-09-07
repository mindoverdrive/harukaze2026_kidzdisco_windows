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
            expected = "colony" if cycle % 2 else "rebirth"
            self.assertEqual(logo.brand, expected)
            curtain.state = "revealing"
            curtain.cycle = cycle + 1
            logo.draw(screen, screen.get_rect(), 0, curtain)
            self.assertEqual(logo.brand, expected)
        # Rebirth draw does not add Colony text underneath.
        self.assertEqual(logo.colony.draw.call_count, 6)

    def test_rebirth_preserves_source_and_transparently_cuts_white(self):
        logo = self.make_logo()
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
        before = pygame.image.tobytes(logo.rebirth, "RGB")
        screen = pygame.Surface((640, 360), pygame.SRCALPHA)
        screen.fill((20, 30, 40, 255))
        clip = pygame.Rect(10, 10, 600, 320)
        screen.set_clip(clip)
        self.assertTrue(logo.draw(screen, screen.get_rect(), 10,
                        SimpleNamespace(state="covering", level=.6, cycle=2)))
        self.assertEqual(screen.get_clip(), clip)
        self.assertEqual(pygame.image.tobytes(logo.rebirth, "RGB"), before)
        self.assertEqual(screen.get_at((320, 180)).a, 255)

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

    def test_missing_rebirth_falls_back_without_breaking_cover(self):
        with mock.patch("transition_branding.CurtainLogo"):
            warnings = []
            logo = AlternatingCurtainLogo((640, 360), rebirth_path="missing-logo-file.jpg",
                                         on_warning=warnings.append)
        self.assertEqual(len(warnings), 1)
        screen = pygame.Surface((640, 360))
        logo.draw(screen, screen.get_rect(), 0, SimpleNamespace(state="covered", level=1, cycle=2))
        logo.colony.draw.assert_called_once()
