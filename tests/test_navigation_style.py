import math
import os
import sys
from types import ModuleType
from pathlib import Path
import unittest
from unittest import mock

import transition_overlay as overlay


class NavigationStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.enterClassContext(mock.patch.dict(os.environ, {
            "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy",
            "PYGAME_HIDE_SUPPORT_PROMPT": "1",
        }))
        try:
            numpy_module = sys.modules.get("numpy")
            if numpy_module is not None and not isinstance(numpy_module, ModuleType):
                raise ImportError("Rendering requires real numpy, not a test stub")
            import pygame
        except ImportError as exc:
            raise unittest.SkipTest("Pygame is required for offscreen rendering") from exc
        cls.pygame = pygame
        pygame.init()
        cls.addClassCleanup(pygame.quit)
        pygame.display.set_mode((1, 1))

    def setUp(self):
        self.regions = overlay.navigation_regions(1920, 1080)
        self.hold = overlay.NavigationHold(self.regions)
        self.style = overlay.NavigationStyle(self.pygame, self.regions)
        self.screen = self.pygame.Surface((1920, 1080))

    def test_front_and_rear_planes_keep_their_centers_and_most_pixels_clear(self):
        for action, (_, _, width, height) in self.regions.items():
            with self.subTest(action=action):
                for surface in (self.style.cards[action], self.style.depth_layers[action]):
                    painted = self.pygame.mask.from_surface(surface, 0).count()
                    area = surface.get_width() * surface.get_height()
                    self.assertLess(painted, area * .25)
                    self.assertEqual(painted, self.pygame.mask.from_surface(surface, 254).count(),
                                     "Partial alpha would introduce a magenta fringe in the colorkey window")
                self.assertEqual(self.style.cards[action].get_at((width // 2, height - 24)).a, 0)
        self.screen.fill(overlay.TRANSPARENT_COLOR)
        overlay.draw_navigation(self.screen, self.pygame, self.style, self.hold, now=0)
        for x, y, width, height in self.regions.values():
            self.assertEqual(self.screen.get_at((x + width // 2, y + height - 24))[:3],
                             overlay.TRANSPARENT_COLOR)

    def test_no_rear_edge_while_navigation_regions_stay_fixed(self):
        original = dict(self.hold.regions)
        self.screen.fill(overlay.TRANSPARENT_COLOR)
        overlay.draw_navigation(self.screen, self.pygame, self.style, self.hold, now=1)
        for x, y, width, height in self.regions.values():
            self.assertFalse(any(
                self.screen.get_at((x + width + offset, y + height // 2))[:3] != overlay.TRANSPARENT_COLOR
                for offset in range(1, 18)
            ))
        self.assertEqual(self.hold.regions, original)
        for layer in self.style.depth_layers.values():
            self.assertEqual(self.pygame.mask.from_surface(layer, 0).count(), 0)

    def test_foreground_fits_a_centered_capsule_at_both_output_sizes(self):
        for output_size in ((1280, 720), (1920, 1080)):
            regions = overlay.navigation_regions(*output_size)
            style = overlay.NavigationStyle(self.pygame, regions)
            for action, (_, _, width, height) in regions.items():
                with self.subTest(output_size=output_size, action=action):
                    card = style.cards[action]
                    bounds = card.get_bounding_rect()
                    self.assertEqual(bounds.width, width)
                    self.assertTrue(.80 <= bounds.height / height <= .84)
                    self.assertLessEqual(abs(bounds.centery - height // 2), 1)
                    radius = bounds.height // 2
                    # A small corner radius would paint this point; a semicircular
                    # cap must leave it clear and reach the full width at mid-height.
                    self.assertEqual(card.get_at((radius // 2, bounds.top + 1)).a, 0)
                    self.assertEqual(card.get_at((0, bounds.centery)).a, 255)
                    allowed = self.pygame.Surface(card.get_size(), self.pygame.SRCALPHA)
                    self.pygame.draw.rect(allowed, (255, 255, 255), bounds, border_radius=radius)
                    ink = self.pygame.mask.from_surface(card, 0)
                    self.assertEqual(ink.overlap_area(self.pygame.mask.from_surface(allowed), (0, 0)),
                                     ink.count(), "Typography and arrow must stay inside the capsule")

    def test_active_outline_and_progress_follow_the_slim_capsule(self):
        self.hold.active, self.hold.progress = "next", .65
        self.screen.fill(overlay.TRANSPARENT_COLOR)
        overlay.draw_navigation(self.screen, self.pygame, self.style, self.hold, now=1)
        x, y, width, _ = self.regions["next"]
        bounds = self.style.cards["next"].get_bounding_rect()
        self.assertEqual(self.screen.get_at((x + width // 2, y))[:3], overlay.TRANSPARENT_COLOR)
        self.assertNotEqual(self.screen.get_at((x + width // 2, y + bounds.top))[:3],
                            overlay.TRANSPARENT_COLOR)
        track = self.style.progress_tracks["next"]
        self.assertGreaterEqual(track.left, bounds.height // 2)
        self.assertLessEqual(track.right, width - bounds.height // 2)
        self.assertTrue(bounds.contains(track))
        fill = round(track.width * self.hold.progress)
        self.assertEqual(self.screen.get_at((x + track.left + fill - 2, y + track.centery))[:3],
                         overlay.TRANSPARENT_COLOR)
        self.assertEqual(self.screen.get_at((x + track.right - 2, y + track.centery))[:3],
                         overlay.TRANSPARENT_COLOR)

    def test_hold_still_fires_in_the_original_region_above_the_visual_capsule(self):
        for action, (x, y, width, _) in self.regions.items():
            with self.subTest(action=action):
                hold = overlay.NavigationHold(self.regions)
                point = (x + width // 2, y + 1)
                self.assertLess(point[1] - y, self.style.cards[action].get_bounding_rect().top)
                result = None
                for step in range(6):
                    observed_at = step * .2
                    result = hold.update([point], observed_at, observed_at)
                self.assertEqual(result, action)

    def test_each_frame_reuses_surfaces_and_fonts_and_preserves_hold_feedback(self):
        self.hold.active = "next"
        x, y, width, height = self.regions["next"]
        self.hold.point = (x + width // 2, y + height // 2)
        self.hold.progress = .65
        state = dict(vars(self.hold))
        with (
            mock.patch.object(self.pygame, "Surface", side_effect=AssertionError("frame surface allocation")),
            mock.patch.object(self.pygame.font, "Font", side_effect=AssertionError("frame font allocation")),
            mock.patch.object(self.pygame.transform, "smoothscale", side_effect=AssertionError("frame resampling")),
        ):
            for now in (0.0, 1.0, 2.0):
                self.screen.fill(overlay.TRANSPARENT_COLOR)
                overlay.draw_navigation(self.screen, self.pygame, self.style, self.hold, now=now)
        self.assertEqual(vars(self.hold), state)
        self.assertEqual(self.screen.get_at(self.hold.point)[:3], (245, 250, 255))

    def test_breathing_changes_edge_light_without_changing_open_interior(self):
        images = []
        for now in (0.0, 5.5):
            self.screen.fill(overlay.TRANSPARENT_COLOR)
            overlay.draw_navigation(self.screen, self.pygame, self.style, self.hold, now=now)
            images.append(self.pygame.image.tobytes(self.screen, "RGB"))
            for x, y, width, height in self.regions.values():
                self.assertEqual(self.screen.get_at((x + width // 2, y + height - 24))[:3],
                                 overlay.TRANSPARENT_COLOR)
        self.assertNotEqual(images[0], images[1])


def render_preview(path):
    """Render the real cached artwork over a synthetic scene, using dummy SDL."""
    with mock.patch.dict(os.environ, {
        "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy",
        "PYGAME_HIDE_SUPPORT_PROMPT": "1",
    }):
        import pygame
        pygame.init()
        try:
            pygame.display.set_mode((1, 1))
            screen = pygame.Surface((1280, 720))
            for y in range(720):
                shade = y / 719
                pygame.draw.line(screen, (round(20 + 10 * shade), round(37 + 17 * shade),
                                          round(53 + 23 * shade)), (0, y), (1279, y))
            for column in range(-5, 20):
                pygame.draw.line(screen, (43, 70, 91), (column * 90, 0), (column * 90 - 180, 720), 1)
            for y in range(30, 720, 50):
                pygame.draw.line(screen, (43, 70, 91), (0, y), (1280, y), 1)
            for row in range(3):
                points = [(x, round(210 + row * 115 + math.sin(x / 150 + row) * 58))
                          for x in range(0, 1280, 5)]
                pygame.draw.lines(screen, ((62, 133, 153), (91, 104, 161), (58, 124, 115))[row],
                                  False, points, 3)
            font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/bahnschrift.ttf"
            font = pygame.font.Font(str(font_path), 19)
            screen.blit(font.render("FLOATING CAPSULE / TRANSPARENT NAVIGATION", True, (218, 229, 237)), (100, 37))
            for y, label, active in ((135, "IDLE", None), (440, "HOLD FEEDBACK", "next")):
                screen.blit(font.render(label, True, (155, 184, 202)), (100, y - 38))
                regions = {"back": (100, y, 384, 162), "next": (790, y, 384, 162)}
                hold = overlay.NavigationHold(regions)
                if active:
                    hold.active, hold.progress, hold.point = active, .68, (1010, y + 72)
                style = overlay.NavigationStyle(pygame, regions)
                window = pygame.Surface(screen.get_size())
                window.fill(overlay.TRANSPARENT_COLOR)
                overlay.draw_navigation(window, pygame, style, hold, now=2.0)
                window.set_colorkey(overlay.TRANSPARENT_COLOR)
                screen.blit(window, (0, 0))
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(screen, str(destination))
        finally:
            pygame.quit()


if __name__ == "__main__":
    unittest.main()
