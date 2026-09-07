"""A cached field of abstract chips that breaks apart and falls on reveal."""

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
            self._snapshot = pygame.Surface(self.size, depth=32)
            self.available = True
        except Exception as exc:
            self._disable(exc)

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
        left, top, width, _ = fragment.area
        falling = max(0.0, (progress - fragment.delay) / (1.0 - fragment.delay))
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
            previous_clip = screen.get_clip()
            clip = previous_clip.clip(self._pygame.Rect(rect)).clip(screen.get_rect())
            if clip.width <= 0 or clip.height <= 0:
                return False
            screen.set_clip(clip)
            try:
                for chip in self._chips:
                    sprite = self._sprites[chip.sprite]
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
