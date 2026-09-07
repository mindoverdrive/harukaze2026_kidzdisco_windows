import math
import os
from pathlib import Path
import random
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

from transition_particles import ParticleCurtain, _Fragment


MOTIONS = ("fall", "rise", "split", "scatter")


def varied_fragments(size):
    """Include full-size, central and edge tiles, plus uneven bounded rectangles."""
    width, height = size
    areas = [(0, 0, width, height), (0, 0, 1, 1),
             (width - 1, height - 1, 1, 1),
             (width // 2, 0, width - width // 2, height),
             (0, height // 2, width, height - height // 2)]
    rng = random.Random(9041)
    for _ in range(40):
        left, top = rng.randrange(width), rng.randrange(height)
        areas.append((left, top, rng.randint(1, width - left), rng.randint(1, height - top)))
    for index, area in enumerate(areas):
        # Latest release and smallest travel factor are the hardest exit case.
        yield _Fragment(area, .23, 1.9, (-1.5, 0.0, 1.5)[index % 3])


class FragmentMotionTests(unittest.TestCase):
    SIZES = ((1, 1), (73, 41), (640, 360), (1920, 1080), (1080, 1920))

    def particles(self, size, motion=None):
        # Motion is pure geometry: these tests run even when graphics are stubbed.
        particles = ParticleCurtain.__new__(ParticleCurtain)
        particles.size = size
        if motion is not None:
            particles.motion = motion
        return particles

    def test_start_and_release_boundary_preserve_every_source_position(self):
        for size in self.SIZES:
            for motion in MOTIONS:
                particles = self.particles(size, motion)
                for fragment in varied_fragments(size):
                    for progress in (-.1, 0.0, fragment.delay, fragment.delay + 1e-9):
                        with self.subTest(size=size, motion=motion, area=fragment.area, progress=progress):
                            self.assertEqual(particles._fragment_position(fragment, progress), fragment.area[:2])

    def test_default_explicit_and_unknown_fall_keep_the_original_trajectory(self):
        size = (1920, 1080)
        for motion in (None, "fall", "unknown"):
            particles = self.particles(size, motion)
            for fragment in varied_fragments(size):
                left, top, width, _ = fragment.area
                for progress in (0.0, .3, .55, .9, .99, 1.0):
                    falling = max(0.0, (progress - fragment.delay) / (1.0 - fragment.delay))
                    expected = (round(left + fragment.drift * width * falling * falling),
                                round(top + size[1] * fragment.fall * falling * falling))
                    self.assertEqual(particles._fragment_position(fragment, progress), expected)

    def test_motion_directions_include_all_quadrants_and_the_exact_center(self):
        size = (1000, 600)
        for area in ((50, 40, 30, 20), (900, 40, 30, 20),
                     (50, 530, 30, 20), (900, 530, 30, 20),
                     (485, 290, 30, 20)):
            fragment = _Fragment(area, .1, 2.0, .8)
            left, top, width, height = area
            sx = -1 if left + width / 2 < size[0] / 2 else 1
            sy = -1 if top + height / 2 < size[1] / 2 else 1
            for motion in MOTIONS:
                with self.subTest(area=area, motion=motion):
                    x, y = self.particles(size, motion)._fragment_position(fragment, .65)
                    if motion == "fall":
                        self.assertGreater(y, top)
                    elif motion == "rise":
                        self.assertLess(y, top)
                    elif motion == "split":
                        self.assertGreater((x - left) * sx, 0)
                        self.assertEqual(y, top)
                    else:
                        self.assertGreater((x - left) * sx, 0)
                        self.assertGreater((y - top) * sy, 0)

    def test_entire_uneven_fragments_exit_by_point_99_for_every_motion(self):
        for size in self.SIZES:
            for motion in MOTIONS:
                particles = self.particles(size, motion)
                for fragment in varied_fragments(size):
                    for progress in (.99, 1.0):
                        with self.subTest(size=size, motion=motion, area=fragment.area, progress=progress):
                            x, y = particles._fragment_position(fragment, progress)
                            _, _, width, height = fragment.area
                            self.assertTrue(x + width <= 0 or x >= size[0]
                                            or y + height <= 0 or y >= size[1])

    def test_coordinates_stay_finite_across_release_and_progress_boundaries(self):
        for size in self.SIZES:
            for motion in MOTIONS:
                particles = self.particles(size, motion)
                for fragment in varied_fragments(size):
                    for progress in (-.1, 0.0, fragment.delay - 1e-9, fragment.delay,
                                     fragment.delay + 1e-9, .5, .99, 1.0, 1.25):
                        point = particles._fragment_position(fragment, progress)
                        self.assertTrue(all(isinstance(value, int) and math.isfinite(value) for value in point))


try:
    import numpy as np
    if not isinstance(np, ModuleType):
        raise ImportError("Rendering requires real numpy")
    import pygame
    REAL_GRAPHICS = (isinstance(pygame, ModuleType)
                     and isinstance(getattr(pygame, "__file__", None), str)
                     and not isinstance(getattr(pygame, "Surface", None), mock.Mock))
except ImportError:
    pygame = None
    REAL_GRAPHICS = False


@unittest.skipUnless(REAL_GRAPHICS, "Real pygame is required for offscreen breakup tests")
class FragmentMotionRenderingTests(unittest.TestCase):
    def test_actual_breakup_moves_all_variants_then_clears_without_surface_allocation(self):
        size = (320, 180)
        particles = ParticleCurtain(size)
        self.assertTrue(particles.available, particles.warning)
        screen = pygame.Surface(size)
        screen.fill(particles.TRANSPARENT_COLOR)
        cleared = pygame.image.tobytes(screen, "RGB")
        base = (32, 75, 111)
        screen.fill(base)
        original = pygame.image.tobytes(screen, "RGB")
        snapshot = particles._snapshot
        with (mock.patch.object(pygame, "Surface", side_effect=AssertionError("frame surface allocation")),
              mock.patch.object(pygame.transform, "smoothscale", side_effect=AssertionError("frame resampling"))):
            for layout_index, fragments in enumerate((particles._fragments, *particles._fragment_layouts)):
                particles._fragments = fragments
                for motion in MOTIONS:
                    particles.motion = motion
                    for progress in (0.0, .55, .99):
                        with self.subTest(layout=layout_index, motion=motion, progress=progress):
                            screen.fill(base)
                            curtain = SimpleNamespace(state="revealing", level=1 - progress,
                                                      _started=0.0, reveal_duration=1.0)
                            self.assertTrue(particles.breakup(screen, progress, curtain))
                            pixels = pygame.image.tobytes(screen, "RGB")
                            if progress == 0.0:
                                self.assertEqual(pixels, original)
                            elif progress == .99:
                                self.assertEqual(pixels, cleared)
                            else:
                                self.assertNotEqual(pixels, original)
                                self.assertNotEqual(pixels, cleared)
        self.assertIs(particles._snapshot, snapshot)


def render_contact_sheet(path):
    """Render all production palette/motion pairs using only in-memory surfaces."""
    if not REAL_GRAPHICS:
        raise RuntimeError("Real pygame is required for the preview")
    font_was_initialized = pygame.font.get_init()
    pygame.font.init()
    try:
        size = (320, 180)
        particles = ParticleCurtain(size)
        if not particles.available:
            raise RuntimeError(particles.warning)
        sheet = pygame.Surface((1844, 1000))
        sheet.fill((12, 19, 29))
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/bahnschrift.ttf"
        title_font = pygame.font.Font(str(font_path), 27)
        label_font = pygame.font.Font(str(font_path), 20)
        detail_font = pygame.font.Font(str(font_path), 17)
        sheet.blit(title_font.render("BREAKUP VARIANTS / 4 MOTIONS x 5 PALETTES", True, (230, 238, 245)), (25, 22))
        sheet.blit(detail_font.render("Reveal at 50% | Production rendering | Uneven block layouts | No camera", True,
                                      (151, 174, 193)), (25, 57))
        for column, (palette_name, _) in enumerate(particles.PALETTES):
            x = 148 + column * 336
            sheet.blit(label_font.render(palette_name.upper(), True, (201, 216, 230)), (x, 91))
            for row, motion in enumerate(MOTIONS):
                y = 128 + row * 220
                if column == 0:
                    sheet.blit(label_font.render(motion.upper(), True, (201, 216, 230)), (25, y + 69))
                cycle = next(value for value in range(1, 21)
                             if particles.pattern_for_cycle(value)[:2] == (column, motion))
                source = pygame.Surface(size)
                source.fill((16, 23, 42))
                covered = SimpleNamespace(state="covering", level=1.0, cycle=cycle)
                with mock.patch("builtins.print"):
                    if not particles.draw(source, source.get_rect(), 10.0, covered):
                        raise RuntimeError(particles.warning)
                revealing = SimpleNamespace(state="revealing", level=.5, cycle=cycle,
                                            _started=10.0, reveal_duration=1.0)
                if not particles.breakup(source, 10.5, revealing):
                    raise RuntimeError(particles.warning)
                destination = pygame.Rect(x, y, *size)
                pygame.draw.rect(sheet, (7, 15, 22), destination)
                for grid_x in range(0, size[0], 20):
                    pygame.draw.line(sheet, (23, 39, 49), (x + grid_x, y), (x + grid_x, y + size[1] - 1))
                for grid_y in range(0, size[1], 20):
                    pygame.draw.line(sheet, (23, 39, 49), (x, y + grid_y), (x + size[0] - 1, y + grid_y))
                source.set_colorkey(particles.TRANSPARENT_COLOR)
                sheet.blit(source, destination)
                pygame.draw.rect(sheet, (48, 66, 81), destination, 1)
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(sheet, str(destination))
    finally:
        if not font_was_initialized:
            pygame.font.quit()


if __name__ == "__main__":
    unittest.main()
