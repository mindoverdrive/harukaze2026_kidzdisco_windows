"""Cached, additive curtain branding that cannot remove the opaque cover."""

import math
from pathlib import Path


TITLE = "KidzDisco Colony"


class CurtainLogo:
    """Draw one centered composition through each supplied panel clip.

    Construct after pygame initialization. ``rect`` in ``draw`` is the panel's
    visible area, not a new layout origin. Neither the curtain nor the display is
    presented or cleared here; the caller continues to own both operations.
    """

    FONT_STYLES = (
        ("bahnschrift,segoeui,arial", 0.045),
        ("segoeuisemilight,segoeuilight,segoeui,arial", 0.085),
        ("arial,segoeui", 0.012),
    )
    PALETTES = ((185, 250, 225), (227, 205, 255), (255, 223, 186))

    def __init__(self, size, asset_path=None, on_warning=None):
        self.available = False
        self.warning = None
        self.on_warning = on_warning
        self._pygame = None
        self.pattern = None
        self._cycle = None
        try:
            import pygame
            import numpy as np

            self._pygame = pygame
            self.size = tuple(map(int, size))
            if len(self.size) != 2 or min(self.size) <= 0:
                raise ValueError("Logo output size must be two positive dimensions")
            path = Path(asset_path) if asset_path is not None else Path(__file__).resolve().parent / "assets" / "transition_logo.png"
            source = pygame.image.load(str(path))
            source_width, source_height = source.get_size()
            target_height = max(1, min(320, round(self.size[1] * 0.28)))
            scale = min(target_height / source_height, self.size[0] * 0.62 / source_width)
            image_size = (max(1, round(source_width * scale)), max(1, round(source_height * scale)))
            # Retain the white silhouette and antialiased edges, while removing
            # the source's dark surround before additive compositing. Apply
            # source alpha before resizing so invisible RGB cannot bleed in.
            rgb = pygame.surfarray.array3d(source).astype(np.float32)
            luminance = rgb[:, :, 0] * 0.2126 + rgb[:, :, 1] * 0.7152 + rgb[:, :, 2] * 0.0722
            light = np.clip((luminance - 48.0) * (255.0 / 207.0), 0.0, 255.0)
            light *= pygame.surfarray.array_alpha(source).astype(np.float32) / 255.0
            pixels = np.repeat(light.astype(np.uint8)[:, :, None], 3, axis=2)
            self._logo = pygame.transform.smoothscale(pygame.surfarray.make_surface(pixels), image_size)

            self._padding = max(2, round(image_size[1] * 0.065))
            halo_size = (image_size[0] + self._padding * 2, image_size[1] + self._padding * 2)
            halo = pygame.Surface(halo_size, depth=32)
            halo.fill((0, 0, 0))
            halo.blit(self._logo, (self._padding, self._padding))
            small = pygame.transform.smoothscale(halo, (max(1, halo_size[0] // 14), max(1, halo_size[1] // 14)))
            self._halo = pygame.transform.smoothscale(small, halo_size)

            if not pygame.font.get_init():
                pygame.font.init()
            font_size = max(12, min(48, round(self.size[1] * 0.044)))
            labels = []
            for family, spacing in self.FONT_STYLES:
                font = pygame.font.SysFont(family, font_size)
                tracking = max(0, round(font_size * spacing))
                glyphs = [font.render(character, True, (255, 255, 255)) for character in TITLE]
                text_size = (sum(glyph.get_width() for glyph in glyphs) + tracking * (len(glyphs) - 1),
                             max(glyph.get_height() for glyph in glyphs))
                text = pygame.Surface(text_size, depth=32)
                text.fill((0, 0, 0))
                cursor = 0
                for glyph in glyphs:
                    text.blit(glyph, (cursor, 0))
                    cursor += glyph.get_width() + tracking
                if text.get_width() > self.size[0] * 0.76:
                    factor = self.size[0] * 0.76 / text.get_width()
                    text = pygame.transform.smoothscale(text, (max(1, round(text.get_width() * factor)),
                                                               max(1, round(text.get_height() * factor))))
                labels.append(text)
            common_size = (max(label.get_width() for label in labels), max(label.get_height() for label in labels))
            self._texts = []
            for label in labels:
                cached = pygame.Surface(common_size, depth=32)
                cached.fill((0, 0, 0))
                cached.blit(label, ((common_size[0] - label.get_width()) // 2,
                                    (common_size[1] - label.get_height()) // 2))
                self._texts.append(cached)
            self._work_logo = self._logo.copy()
            self._work_halo = self._halo.copy()
            self._work_text = self._texts[0].copy()
            self._gap = max(5, round(font_size * 0.38))
            self.available = True
        except Exception as exc:
            self._disable(exc)

    def _disable(self, reason):
        self.available = False
        if self.warning is not None:
            return
        self.warning = f"Curtain logo disabled: {type(reason).__name__}: {reason}"
        try:
            if self.on_warning is not None:
                self.on_warning(self.warning)
            else:
                print(f"[CurtainLogo] {self.warning}", flush=True)
        except Exception:
            # Optional diagnostic output cannot become a transition failure.
            pass

    @staticmethod
    def pattern_for_cycle(cycle):
        index = max(0, int(cycle) - 1) % 9
        return index % 3, index // 3

    def _select_pattern(self, curtain):
        cycle = getattr(curtain, "cycle", 1)
        if self.pattern is None or (curtain.state == "covering" and cycle != self._cycle):
            self._cycle = cycle
            self.pattern = self.pattern_for_cycle(cycle)
        return self.pattern

    def _motion(self, now, variant):
        if variant == 1:
            return (math.sin(now * 0.28) * min(4.0, self.size[0] * 0.002),
                    math.sin(now * 0.35) * min(5.0, self.size[1] * 0.004),
                    0.94 + 0.025 * math.sin(now * 0.52),
                    0.94 + 0.02 * math.sin(now * 0.52 + 0.25))
        if variant == 2:
            return (0.0, math.sin(now * 1.05) * min(2.0, self.size[1] * 0.002),
                    0.91 + 0.065 * math.sin(now * 1.25),
                    0.90 + 0.06 * math.sin(now * 1.25 - 0.65))
        return (0.0, math.sin(now * 0.65) * min(2.5, self.size[1] * 0.0025),
                0.92 + 0.055 * math.sin(now * 0.85),
                0.92 + 0.03 * math.sin(now * 0.85 + 0.25))

    @staticmethod
    def _fade(curtain):
        if curtain.state not in ("covering", "covered", "revealing"):
            return 0.0
        level = float(curtain.level)
        if not math.isfinite(level):
            return 0.0
        level = max(0.0, min(1.0, level))
        return level * level * (3.0 - 2.0 * level)

    def _add(self, screen, base, work, position, color, amount):
        pygame = self._pygame
        work.blit(base, (0, 0))
        work.fill(tuple(max(0, min(255, round(channel * amount))) for channel in color),
                  special_flags=pygame.BLEND_RGB_MULT)
        screen.blit(work, position, special_flags=pygame.BLEND_RGB_ADD)

    def draw(self, screen, rect, now, curtain):
        if not self.available:
            return False
        try:
            fade = self._fade(curtain)
            if fade <= 0.0 or not math.isfinite(now):
                return False
            typography, motion = self._select_pattern(curtain)
            text = self._texts[typography]
            previous_clip = screen.get_clip()
            clip = previous_clip.clip(self._pygame.Rect(rect)).clip(screen.get_rect())
            if clip.width <= 0 or clip.height <= 0:
                return False
            screen.set_clip(clip)
            try:
                # Absolute time is intentionally shared by every panel and cycle.
                drift, bob, pulse, text_pulse = self._motion(now, motion)
                color = tuple(channel * (0.97 + 0.03 * math.sin(now * 0.19 + index))
                              for index, channel in enumerate(self.PALETTES[typography]))
                group_height = self._logo.get_height() + self._gap + text.get_height()
                top = (self.size[1] - group_height) / 2
                logo_position = (round((self.size[0] - self._logo.get_width()) / 2 + drift), round(top + bob))
                halo_position = (logo_position[0] - self._padding, logo_position[1] - self._padding)
                self._add(screen, self._halo, self._work_halo, halo_position, color, fade * pulse * 0.22)
                self._add(screen, self._logo, self._work_logo, logo_position, color, fade * pulse * 0.86)
                text_position = (round((self.size[0] - text.get_width()) / 2 + drift),
                                 round(top + self._logo.get_height() + self._gap
                                       + bob * 0.6))
                self._add(screen, text, self._work_text, text_position, color, fade * text_pulse)
            finally:
                screen.set_clip(previous_clip)
            return True
        except Exception as exc:
            self._disable(exc)
            return False
