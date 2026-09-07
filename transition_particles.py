"""Cached colored chips and deterministic per-transition release variations."""

from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class _Chip:
    x: float
    y: float
    phase: float
    delay: float
    sprite: int


@dataclass(frozen=True)
class _Fragment:
    area: tuple
    delay: float
    fall: float
    drift: float


class ParticleCurtain:
    """Decorate an opaque curtain; the caller owns coverage, alpha and flip.

    ``rect`` only clips the existing full-screen layout. Geometry and all sprite
    surfaces are created once; every frame only computes positions and blits.
    """

    SEED = 0xC0107
    TRANSPARENT_COLOR = (255, 0, 128)
    PALETTE = ((31, 55, 77), (37, 66, 83), (43, 76, 91),
               (55, 66, 93), (68, 84, 108), (93, 119, 135))
    PALETTES = (
        ("prism", ((30, 113, 134), (125, 42, 117), (165, 93, 43),
                   (53, 138, 106), (91, 64, 156), (157, 58, 85))),
        ("aurora", ((26, 88, 112), (39, 130, 122), (70, 68, 145),
                    (109, 53, 137), (43, 111, 159), (87, 155, 140))),
        ("ember", ((111, 39, 81), (162, 62, 73), (173, 109, 46),
                   (116, 60, 126), (73, 51, 111), (187, 132, 77))),
        ("acid", ((103, 137, 36), (36, 112, 113), (130, 66, 153),
                  (157, 128, 42), (42, 141, 92), (63, 73, 141))),
        ("lagoon", ((26, 76, 116), (35, 116, 146), (58, 149, 143),
                    (53, 83, 146), (94, 67, 140), (99, 159, 170))),
    )
    MOTIONS = ("fall", "rise", "split", "scatter")

    def __init__(self, size):
        self.available = False
        self.warning = None
        try:
            import pygame

            self._pygame = pygame
            self.size = tuple(map(int, size))
            if len(self.size) != 2 or min(self.size) <= 0:
                raise ValueError("Particle output size must be two positive dimensions")
            width, height = self.size
            columns = max(2, min(60, round(math.sqrt(760 * width / height))))
            rows = max(2, min(60, round(760 / columns)))
            self._cell = width / columns, height / rows
            sprite_size = (max(2, math.ceil(self._cell[0] * 1.50)),
                           max(2, math.ceil(self._cell[1] * 1.50)))
            self._sprites = tuple(self._make_sprite(sprite_size, color, shape)
                                  for color in self.PALETTE for shape in range(3))
            self._sprite_banks = tuple(
                tuple(self._make_sprite(sprite_size, color, shape)
                      for color in palette for shape in range(3))
                for _, palette in self.PALETTES)
            self._cycle = None
            self.motion = "fall"
            self._sprite_indices = None
            rng = random.Random(self.SEED)
            column_delays = [rng.uniform(0.0, 0.13) for _ in range(columns + 2)]
            chips = []
            for row in range(-1, rows + 1):
                for column in range(-1, columns + 1):
                    x = (column + 0.5 + rng.uniform(-0.16, 0.16)) * self._cell[0]
                    y = (row + 0.5 + rng.uniform(-0.16, 0.16)) * self._cell[1]
                    # Mid-tones carry the field; only a few chips are luminous.
                    color = rng.choices(range(6), weights=(19, 25, 24, 21, 9, 2))[0]
                    if abs(x / width - 0.5) < 0.20 and abs(y / height - 0.5) < 0.24:
                        color = min(color, 2)
                    chips.append(_Chip(x, y, rng.uniform(0, math.tau),
                                       0.025 + column_delays[column + 1] + rng.uniform(0, 0.085),
                                       color * 3 + rng.randrange(3)))
            self._chips = tuple(chips)
            # Separate, gapless tiles break up the complete live composition,
            # including camera and logo. This avoids moving the chips twice.
            fragment_columns = max(2, min(60, round(math.sqrt(520 * width / height))))
            fragment_rows = max(2, min(60, round(520 / fragment_columns)))
            fragments = []
            fragment_rng = random.Random(self.SEED ^ 0xF011)
            delays = [fragment_rng.uniform(0.0, 0.13) for _ in range(fragment_columns)]
            for row in range(fragment_rows):
                top, bottom = height * row // fragment_rows, height * (row + 1) // fragment_rows
                for column in range(fragment_columns):
                    left, right = width * column // fragment_columns, width * (column + 1) // fragment_columns
                    if right <= left or bottom <= top:
                        continue
                    fragments.append(_Fragment((left, top, right - left, bottom - top),
                                               0.025 + delays[column] + fragment_rng.uniform(0, 0.075),
                                               fragment_rng.uniform(1.9, 2.3),
                                               fragment_rng.uniform(-1.5, 1.5)))
            self._fragments = tuple(fragments)
            self._fragment_layouts = tuple(self._make_block_layout(index)
                                           for index in range(4))
            self._snapshot = pygame.Surface(self.size, depth=32)
            self.available = True
        except Exception as exc:
            self._disable(exc)

    def _make_block_layout(self, variant):
        """Unequal rectangles tile the whole composition, with no initial holes."""
        width, height = self.size
        rng = random.Random(self.SEED ^ (0xB10C + variant))
        rows = min(height, max(2, round(math.sqrt(420 * height / width))))
        weights = [rng.uniform(0.55, 1.65) for _ in range(rows)]
        total = sum(weights)
        top = 0
        accumulated = 0.0
        fragments = []
        for row, weight in enumerate(weights):
            accumulated += weight
            bottom = height if row == rows - 1 else round(height * accumulated / total)
            columns = min(width, max(2, round(420 / rows * rng.uniform(0.65, 1.35))))
            spans = [rng.uniform(0.45, 1.8) for _ in range(columns)]
            span_total = sum(spans)
            left = 0
            x_accumulated = 0.0
            for column, span in enumerate(spans):
                x_accumulated += span
                right = width if column == columns - 1 else round(width * x_accumulated / span_total)
                if right > left and bottom > top:
                    fragments.append(_Fragment(
                        (left, top, right - left, bottom - top), rng.uniform(0.025, 0.23),
                        rng.uniform(1.9, 2.3), rng.uniform(-1.5, 1.5)))
                left = right
            top = bottom
        return tuple(fragments)

    def _make_sprite(self, size, color, shape):
        pygame = self._pygame
        width, height = size
        # Supersampling happens only at construction, including the thin glint.
        sprite = pygame.Surface((width * 2, height * 2), pygame.SRCALPHA)
        outlines = (
            ((0.08, 0.03), (0.87, 0.00), (1.00, 0.22), (0.93, 0.95), (0.06, 1.00), (0.00, 0.19)),
            ((0.02, 0.10), (0.92, 0.02), (1.00, 0.86), (0.84, 1.00), (0.00, 0.91)),
            ((0.12, 0.00), (0.99, 0.07), (0.93, 0.99), (0.04, 0.91), (0.00, 0.16)),
        )
        points = [(round(x * (width * 2 - 1)), round(y * (height * 2 - 1)))
                  for x, y in outlines[shape]]
        pygame.draw.polygon(sprite, (*color, 238), points)
        edge = tuple(min(255, channel + 22) for channel in color)
        pygame.draw.lines(sprite, (*edge, 190), False, points[:3], 2)
        # A small broken glint gives each chip substance without a set motif.
        pygame.draw.line(sprite, (*edge, 115), (round(width * 0.42), round(height * 0.65)),
                         (round(width * 0.78), round(height * 0.59)), 2)
        return pygame.transform.smoothscale(sprite, size)

    def _disable(self, exc):
        self.available = False
        if self.warning is None:
            self.warning = f"Particle curtain disabled: {type(exc).__name__}: {exc}"
            try:
                print(f"[ParticleCurtain] {self.warning}", flush=True)
            except Exception:
                pass

    @classmethod
    def pattern_for_cycle(cls, cycle):
        index = max(0, int(cycle) - 1)
        return (index % len(cls.PALETTES),
                cls.MOTIONS[index % len(cls.MOTIONS)],
                (index // (len(cls.PALETTES) * len(cls.MOTIONS))) % 4 != 3)

    def _select_pattern(self, curtain):
        cycle = getattr(curtain, "cycle", 0)
        if cycle <= 0 or cycle == self._cycle:
            return
        # Freeze colors and motion through covered/reveal, including retries.
        if self._cycle is not None and curtain.state != "covering":
            return
        palette, self.motion, randomized = self.pattern_for_cycle(cycle)
        self._cycle = cycle
        self._sprites = self._sprite_banks[palette]
        self._fragments = self._fragment_layouts[((cycle - 1) // len(self.MOTIONS))
                                                % len(self._fragment_layouts)]
        rng = random.Random(self.SEED ^ (cycle * 0x9E3779B1))
        self._sprite_indices = tuple(
            (rng.randrange(6) if randomized else
             min(5, max(0, int(chip.y / self.size[1] * 6)))) * 3 + chip.sprite % 3
            for chip in self._chips)
        print(f"[ParticleCurtain] cycle={cycle} palette={self.PALETTES[palette][0]} "
              f"motion={self.motion} colors={'random-blocks' if randomized else 'bands'}",
              flush=True)

    @staticmethod
    def _reveal_progress(curtain, now):
        if curtain.state != "revealing":
            return 0.0
        started = getattr(curtain, "_started", None)
        duration = getattr(curtain, "reveal_duration", None)
        if (started is not None and duration is not None and math.isfinite(started)
                and math.isfinite(duration) and duration > 0):
            return min(1.0, max(0.0, (now - started) / duration))
        return min(1.0, max(0.0, 1.0 - float(curtain.level)))

    def _position(self, chip, now, state, level):
        cell_width, cell_height = self._cell
        x = chip.x + math.sin(now * 0.52 + chip.phase) * cell_width * 0.045
        y = chip.y + math.sin(now * 0.63 + chip.phase * 1.3) * cell_height * 0.065
        if state == "covering":
            y -= (1.0 - level) * cell_height * (0.6 + chip.delay * 2)
        return x, y

    def _fragment_position(self, fragment, progress):
        left, top, width, height = fragment.area
        falling = max(0.0, (progress - fragment.delay) / (1.0 - fragment.delay))
        motion = getattr(self, "motion", "fall")
        if motion == "rise":
            return (round(left + fragment.drift * width * falling * falling),
                    round(top - self.size[1] * fragment.fall * falling * falling))
        if motion == "split":
            direction = -1 if left + width / 2 < self.size[0] / 2 else 1
            return (round(left + direction * self.size[0] * fragment.fall * falling * falling), top)
        if motion == "scatter":
            dx = (left + width / 2) / self.size[0] - .5
            dy = (top + height / 2) / self.size[1] - .5
            # Keep central and midline tiles diagonal without dividing by zero.
            dx = math.copysign(max(abs(dx), .075), dx)
            dy = math.copysign(max(abs(dy), .075), dy)
            # The dominant axis travels a full screen multiple, so even central
            # tiles have entirely left the viewport before the reveal completes.
            distance = fragment.fall * falling * falling / max(abs(dx), abs(dy))
            return (round(left + self.size[0] * dx * distance),
                    round(top + self.size[1] * dy * distance))
        return (round(left + fragment.drift * width * falling * falling),
                round(top + self.size[1] * fragment.fall * falling * falling))

    def draw(self, screen, rect, now, curtain):
        if not self.available:
            return False
        try:
            state = curtain.state
            level = float(curtain.level)
            if (state not in ("covering", "covered", "revealing")
                    or not math.isfinite(now) or not math.isfinite(level) or level <= 0):
                return False
            level = min(1.0, level)
            self._select_pattern(curtain)
            previous_clip = screen.get_clip()
            clip = previous_clip.clip(self._pygame.Rect(rect)).clip(screen.get_rect())
            if clip.width <= 0 or clip.height <= 0:
                return False
            screen.set_clip(clip)
            try:
                for index, chip in enumerate(self._chips):
                    sprite = self._sprites[chip.sprite if self._sprite_indices is None
                                           else self._sprite_indices[index]]
                    x, y = self._position(chip, now, state, level)
                    left = round(x - sprite.get_width() / 2)
                    top = round(y - sprite.get_height() / 2)
                    if (left + sprite.get_width() <= clip.left or left >= clip.right
                            or top + sprite.get_height() <= clip.top or top >= clip.bottom):
                        continue
                    screen.blit(sprite, (left, top))
            finally:
                screen.set_clip(previous_clip)
            return True
        except Exception as exc:
            self._disable(exc)
            return False

    def breakup(self, screen, now, curtain):
        """Drop the current composition through color-key gaps on reveal only.

        Call after the whole frame has been composed, with the next scene ready
        underneath and window alpha held at 255. One reusable memory copy keeps
        camera and logo live inside the fragments; nothing is saved to disk.
        """
        if not self.available or curtain.state != "revealing":
            return False
        try:
            if not math.isfinite(now) or not math.isfinite(float(curtain.level)):
                return False
            progress = self._reveal_progress(curtain, now)
            if progress <= 0.0 and curtain.level > 0:
                return True
            previous_clip = screen.get_clip()
            clip = previous_clip.clip(screen.get_rect())
            if clip.width <= 0 or clip.height <= 0:
                return False
            self._snapshot.blit(screen, (0, 0))
            screen.set_clip(clip)
            try:
                screen.fill(self.TRANSPARENT_COLOR)
                if curtain.level <= 0 or progress >= 1.0:
                    return True
                for fragment in self._fragments:
                    left, top = self._fragment_position(fragment, progress)
                    _, _, width, height = fragment.area
                    if (left + width <= clip.left or left >= clip.right
                            or top + height <= clip.top or top >= clip.bottom):
                        continue
                    screen.blit(self._snapshot, (left, top), fragment.area)
            except Exception:
                # Let the caller's fade fallback start from the complete frame
                # if an optional fragment blit fails after opening some gaps.
                try:
                    screen.blit(self._snapshot, (0, 0))
                except Exception:
                    pass
                raise
            finally:
                screen.set_clip(previous_clip)
            return True
        except Exception as exc:
            self._disable(exc)
            return False
