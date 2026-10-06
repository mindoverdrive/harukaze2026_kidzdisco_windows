"""Pixel checks for navigation cues, using only dummy SDL and synthetic points."""
import os
import unittest
from unittest import mock

import transition_overlay as overlay


class NavigationFeedbackRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.enterClassContext(mock.patch.dict(os.environ, {
            "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy",
            "PYGAME_HIDE_SUPPORT_PROMPT": "1",
        }))
        try:
            import pygame
        except ImportError as exc:
            raise unittest.SkipTest("Pygame is required for offscreen rendering") from exc
        cls.pygame = pygame
        pygame.init()
        cls.addClassCleanup(pygame.quit)
        pygame.display.set_mode((1, 1))

    def setUp(self):
        self.regions = overlay.navigation_regions(1280, 720)
        self.hold = overlay.NavigationHold(self.regions)
        self.style = overlay.NavigationStyle(self.pygame, self.regions)
        self.screen = self.pygame.Surface((1280, 720))

    def draw(self):
        self.screen.fill(overlay.TRANSPARENT_COLOR)
        overlay.draw_navigation(self.screen, self.pygame, self.style, self.hold, now=1)

    def point_in(self, action):
        x, y, w, h = self.regions[action]
        return x + w // 2, y + h // 2

    def test_fresh_fingertip_outside_buttons_has_a_hollow_visible_ring(self):
        point = (640, 360)
        self.hold.update([point], 0, 0)
        self.draw()
        self.assertEqual(self.screen.get_at(point)[:3], overlay.TRANSPARENT_COLOR)
        self.assertNotEqual(self.screen.get_at((point[0] + self.style.marker_radius, point[1]))[:3],
                            overlay.TRANSPARENT_COLOR)
        self.assertIsNone(self.hold.point)

    def test_stale_detection_removes_the_marker(self):
        point = (640, 360)
        self.hold.update([point], 0, 0)
        self.hold.update([point], 0, .251)
        self.draw()
        area = self.pygame.Rect(point[0] - 20, point[1] - 20, 40, 40)
        pixels = self.pygame.surfarray.array3d(self.screen.subsurface(area))
        self.assertTrue((pixels == overlay.TRANSPARENT_COLOR).all())

    def test_conflict_keeps_both_rings_but_no_hold_target_or_progress(self):
        points = [self.point_in("back"), self.point_in("next")]
        self.hold.update(points, 0, 0)
        self.draw()
        self.assertEqual(self.hold.feedback, "conflict")
        self.assertIsNone(self.hold.point)
        self.assertEqual(self.hold.progress, 0)
        for x, y in points:
            # Pygame's positive circle edge is inside the radius-sized bounds.
            self.assertEqual(self.screen.get_at((x + self.style.marker_radius - 1, y))[:3], (235, 245, 255))

    def test_operation_states_leave_the_space_between_buttons_clear(self):
        for size in ((1280, 720), (1920, 1080)):
            regions = overlay.navigation_regions(*size)
            style = overlay.NavigationStyle(self.pygame, regions)
            hold = overlay.NavigationHold(regions)
            screen = self.pygame.Surface(size)
            left = regions["back"][0] + regions["back"][2] + 8
            right = regions["next"][0] - 8
            top = regions["back"][1]
            height = regions["back"][3]
            for state in ("ready", "holding", "no_hand", "stale", "conflict", "release"):
                with self.subTest(size=size, state=state):
                    hold.feedback = state
                    screen.fill(overlay.TRANSPARENT_COLOR)
                    overlay.draw_navigation(screen, self.pygame, style, hold, now=1)
                    area = self.pygame.Rect(left, top, right - left, height)
                    pixels = self.pygame.surfarray.array3d(screen.subsurface(area))
                    self.assertTrue((pixels == overlay.TRANSPARENT_COLOR).all())

    def test_ring_drawing_does_not_allocate_surfaces_or_change_input_state(self):
        for feedback, points in (("release", [self.point_in("next")]),
                                 ("conflict", [self.point_in("back"), self.point_in("next")]),
                                 ("no_hand", []), ("stale", [])):
            self.hold.visible_points = tuple(points)
            self.hold.feedback = feedback
            state = dict(vars(self.hold))
            with (mock.patch.object(self.pygame, "Surface", side_effect=AssertionError("frame allocation")),
                  mock.patch.object(self.pygame.font, "Font", side_effect=AssertionError("font allocation")),
                  mock.patch.object(self.pygame.transform, "smoothscale", side_effect=AssertionError("resampling"))):
                self.draw()
            self.assertEqual(vars(self.hold), state)


if __name__ == "__main__":
    unittest.main()
